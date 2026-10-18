//! Noticing "drag a file, then shake it".
//!
//! Windows doesn't tell other apps when you start dragging a file, so we
//! watch the mouse itself with a low-level mouse hook (WH_MOUSE_LL): Windows
//! calls `on_mouse` for every mouse event on the whole desktop. While the
//! left button is held, a `ShakeDetector` looks for a quick zig-zag. When it
//! sees one, we show the portal under the cursor.
//!
//! We can't tell from the mouse alone whether you're dragging a FILE or,
//! say, a window. That's fine: the portal only lights up when Windows
//! actually drags files into it (portal.js); otherwise it closes again when
//! you let go of the button.
//!
//! The hook runs on its own thread with a message loop (Windows delivers
//! hook calls as messages). `on_mouse` must return fast, or Windows drops
//! the hook, so it only does a little arithmetic and sends a message on a
//! channel; the app reacts on another thread.

use std::cell::RefCell;
use std::sync::mpsc::Sender;
use std::sync::OnceLock;
use std::thread;

use windows::Win32::Foundation::{HWND, LPARAM, LRESULT, WPARAM};
use windows::Win32::UI::WindowsAndMessaging::{
    CallNextHookEx, GetMessageW, SetWindowsHookExW, HHOOK, MSG, MSLLHOOKSTRUCT, WH_MOUSE_LL, WM_LBUTTONDOWN,
    WM_LBUTTONUP, WM_MOUSEMOVE,
};

use crate::config::{SHAKE_HYSTERESIS, SHAKE_MIN_SWING, SHAKE_REVERSALS, SHAKE_WINDOW_MS};

/// What the hook tells the app.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Gesture {
    /// The mouse was shaken with the left button held, at this screen point
    /// (physical pixels).
    Shake { x: i32, y: i32 },
    /// The left button was released after a shake.
    Release { x: i32, y: i32 },
}

// ── The detector (plain logic, no Windows calls, unit-tested below) ─────────

/// Watches ONE axis for swings: a run in one direction, then a turn back.
#[derive(Default)]
struct Axis {
    direction: i32, // +1, -1, or 0 before the first swing
    anchor: i32,    // where the current swing started
    extreme: i32,   // the furthest point reached in the current direction
}

impl Axis {
    fn start(&mut self, at: i32) {
        *self = Axis { direction: 0, anchor: at, extreme: at };
    }

    /// Feeds one position. Returns true when a long-enough swing just ended
    /// with a turn.
    fn feed(&mut self, at: i32) -> bool {
        if self.direction == 0 {
            if (at - self.anchor).abs() > SHAKE_HYSTERESIS {
                self.direction = (at - self.anchor).signum();
                self.extreme = at;
            }
            return false;
        }
        let further = (at - self.extreme) * self.direction > 0;
        if further {
            self.extreme = at;
            return false;
        }
        let came_back = (self.extreme - at) * self.direction > SHAKE_HYSTERESIS;
        if !came_back {
            return false;
        }
        // A turn. It counts if the swing that just ended was long enough.
        let swing = (self.extreme - self.anchor).abs();
        self.anchor = self.extreme;
        self.direction = -self.direction;
        self.extreme = at;
        swing >= SHAKE_MIN_SWING
    }
}

#[derive(Default)]
pub struct ShakeDetector {
    down: bool,
    fired: bool,
    x: Axis,
    y: Axis,
    turns_x: Vec<u32>, // times (ms) of recent turns on each axis
    turns_y: Vec<u32>,
}

impl ShakeDetector {
    pub fn button_down(&mut self, x: i32, y: i32) {
        self.down = true;
        self.fired = false;
        self.x.start(x);
        self.y.start(y);
        self.turns_x.clear();
        self.turns_y.clear();
    }

    /// Returns true if the button was held and a shake had fired, i.e. the
    /// app should hear about the release.
    pub fn button_up(&mut self) -> bool {
        let fired = self.down && self.fired;
        self.down = false;
        self.fired = false;
        fired
    }

    /// Returns true exactly once per drag: when the shake is complete.
    pub fn moved(&mut self, x: i32, y: i32, time_ms: u32) -> bool {
        if !self.down || self.fired {
            return false;
        }
        let horizontal = self.x.feed(x);
        let vertical = self.y.feed(y);
        for (turned, turns) in [(horizontal, &mut self.turns_x), (vertical, &mut self.turns_y)] {
            if turned {
                turns.push(time_ms);
            }
            // Forget turns that are too old. wrapping_sub copes with the
            // millisecond clock wrapping around every ~49 days.
            turns.retain(|&t| time_ms.wrapping_sub(t) <= SHAKE_WINDOW_MS);
        }
        if self.turns_x.len() >= SHAKE_REVERSALS || self.turns_y.len() >= SHAKE_REVERSALS {
            self.fired = true;
            return true;
        }
        false
    }
}

// ── The Windows hook ────────────────────────────────────────────────────────

static SENDER: OnceLock<Sender<Gesture>> = OnceLock::new();

thread_local! {
    // The hook is only ever called on the thread that installed it, so the
    // detector can live there without a lock.
    static DETECTOR: RefCell<ShakeDetector> = RefCell::new(ShakeDetector::default());
}

unsafe extern "system" fn on_mouse(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if code >= 0 {
        let info = &*(lparam.0 as *const MSLLHOOKSTRUCT);
        let (x, y) = (info.pt.x, info.pt.y);
        let gesture = DETECTOR.with(|cell| {
            let mut detector = cell.borrow_mut();
            match wparam.0 as u32 {
                WM_LBUTTONDOWN => {
                    detector.button_down(x, y);
                    None
                }
                WM_LBUTTONUP => detector.button_up().then_some(Gesture::Release { x, y }),
                WM_MOUSEMOVE => detector.moved(x, y, info.time).then_some(Gesture::Shake { x, y }),
                _ => None,
            }
        });
        if let (Some(gesture), Some(sender)) = (gesture, SENDER.get()) {
            let _ = sender.send(gesture);
        }
    }
    // Always pass the event on: we only watch, never block, the mouse.
    CallNextHookEx(HHOOK::default(), code, wparam, lparam)
}

/// Installs the hook on a new thread. Gestures arrive on `sender`.
pub fn spawn(sender: Sender<Gesture>) {
    if SENDER.set(sender).is_err() {
        return; // already running
    }
    thread::spawn(|| unsafe {
        match SetWindowsHookExW(WH_MOUSE_LL, Some(on_mouse), None, 0) {
            Ok(_hook) => {
                let mut message = MSG::default();
                while GetMessageW(&mut message, HWND::default(), 0, 0).as_bool() {}
            }
            Err(err) => eprintln!("[shake] could not install the mouse hook: {err}"),
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Drags from (500, 500), then follows `xs` (one point every 16 ms, like
    /// a 60 Hz mouse). Returns the time a shake fired, if it did.
    fn drag(xs: &[i32]) -> Option<u32> {
        let mut d = ShakeDetector::default();
        d.button_down(500, 500);
        for (i, &x) in xs.iter().enumerate() {
            let t = 10_000 + i as u32 * 16;
            if d.moved(x, 500, t) {
                return Some(t);
            }
        }
        None
    }

    /// A path through `points`, interpolated in `step`-pixel moves.
    fn path(points: &[i32], step: i32) -> Vec<i32> {
        let mut out = Vec::new();
        for pair in points.windows(2) {
            let (a, b) = (pair[0], pair[1]);
            let dir = (b - a).signum();
            let mut x = a;
            while x != b {
                x += dir * step.min((b - x).abs());
                out.push(x);
            }
        }
        out
    }

    #[test]
    fn a_quick_shake_fires() {
        assert!(drag(&path(&[500, 580, 500, 580, 500], 20)).is_some());
    }

    #[test]
    fn a_straight_drag_does_not_fire() {
        assert!(drag(&path(&[500, 1400], 15)).is_none());
    }

    #[test]
    fn hand_tremor_does_not_fire() {
        // A slow drag with a few pixels of jitter on every step.
        let xs: Vec<i32> = (0..200).map(|i| 500 + i * 4 + if i % 2 == 0 { 3 } else { -3 }).collect();
        assert!(drag(&xs).is_none());
    }

    #[test]
    fn small_wiggles_do_not_fire() {
        // Turns, but each swing shorter than SHAKE_MIN_SWING.
        assert!(drag(&path(&[500, 525, 500, 525, 500, 525, 500], 5)).is_none());
    }

    #[test]
    fn a_slow_back_and_forth_does_not_fire() {
        // Same swings as a shake, but spread over several seconds.
        assert!(drag(&path(&[500, 700, 500, 700, 500], 2)).is_none());
    }

    #[test]
    fn fires_only_once_per_drag_and_reports_the_release() {
        let mut d = ShakeDetector::default();
        d.button_down(500, 500);
        let mut fired = 0;
        for (i, x) in path(&[500, 580, 500, 580, 500, 580, 500, 580, 500], 20).into_iter().enumerate() {
            fired += d.moved(x, 500, i as u32 * 16) as u32;
        }
        assert_eq!(fired, 1);
        assert!(d.button_up());
        assert!(!d.button_up(), "a second release is not news");
    }

    #[test]
    fn no_shake_without_the_button() {
        let mut d = ShakeDetector::default();
        for (i, x) in path(&[500, 580, 500, 580, 500], 20).into_iter().enumerate() {
            assert!(!d.moved(x, 500, i as u32 * 16));
        }
        assert!(!d.button_up());
    }

    #[test]
    fn vertical_shakes_count_too() {
        let mut d = ShakeDetector::default();
        d.button_down(500, 500);
        let fired = path(&[500, 580, 500, 580, 500], 20)
            .into_iter()
            .enumerate()
            .any(|(i, y)| d.moved(500, y, i as u32 * 16));
        assert!(fired);
    }
}
