//! The portal windows.
//!
//! Each window shows one web page (../src/index.html) that can be in one of
//! two shapes: the round PORTAL (a ring of tools you drop a file on) or the
//! small CARD (what a job is doing, then its result). The window that
//! receives your drop simply turns into that job's card, so nothing has to
//! be handed over between windows and nothing flickers.
//!
//! Creating a WebView takes a moment (~0.2 s), far too slow to start when
//! you shake. So we keep one hidden, fully loaded window ready ("idle"),
//! and make a new spare as soon as it's used.
//!
//! Window placement uses Win32 directly (SetWindowPos): it moves AND resizes
//! in one step, which keeps the card perfectly still while it changes size.

use std::mem::size_of;
use std::thread;

use tauri::{AppHandle, Emitter, EventTarget, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use windows::Win32::Foundation::{HWND, POINT, RECT};
use windows::Win32::Graphics::Gdi::{GetMonitorInfoW, MonitorFromPoint, MONITORINFO, MONITOR_DEFAULTTONEAREST};
use windows::Win32::UI::HiDpi::{GetDpiForMonitor, MDT_EFFECTIVE_DPI};
use windows::Win32::UI::WindowsAndMessaging::{
    GetWindowLongPtrW, GetWindowRect, SetWindowLongPtrW, SetWindowPos, ShowWindow, GWL_EXSTYLE, HWND_TOPMOST,
    SWP_FRAMECHANGED, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SW_HIDE, SW_SHOWNOACTIVATE,
    WS_EX_APPWINDOW, WS_EX_TOOLWINDOW,
};

use crate::config::{APP_NAME, MAX_WINDOWS, PORTAL_SIZE};
use crate::AppState;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Mode {
    /// Hidden, loaded, ready to be summoned.
    Idle,
    /// Showing the ring under the cursor, waiting for a drop.
    Portal,
    /// Showing a job (or the "how to use" hint).
    Card,
}

#[derive(Default)]
pub struct Pool {
    windows: Vec<(String, Mode)>,
    next_id: u32,
    /// True while a spare window is being created, so two shakes in a row
    /// don't create two.
    warming: bool,
}

impl Pool {
    fn find(&self, mode: Mode) -> Option<String> {
        self.windows.iter().find(|(_, m)| *m == mode).map(|(label, _)| label.clone())
    }

    fn set(&mut self, label: &str, mode: Mode) {
        if let Some(entry) = self.windows.iter_mut().find(|(l, _)| l == label) {
            entry.1 = mode;
        }
    }

    pub fn mode_of(&self, label: &str) -> Option<Mode> {
        self.windows.iter().find(|(l, _)| l == label).map(|(_, m)| *m)
    }
}

// ── Win32 helpers ───────────────────────────────────────────────────────────

/// The native window handle, as an integer (raw pointers can't cross threads).
fn raw_hwnd(window: &WebviewWindow) -> isize {
    window.hwnd().map(|h| h.0 as isize).unwrap_or(0)
}

fn hwnd(raw: isize) -> HWND {
    HWND(raw as *mut _)
}

/// The usable part of the monitor under a point (the screen minus the
/// taskbar), and that monitor's scale (1.0 = 100%, 1.5 = 150%…).
fn monitor_at(x: i32, y: i32) -> (RECT, f64) {
    unsafe {
        let monitor = MonitorFromPoint(POINT { x, y }, MONITOR_DEFAULTTONEAREST);
        let mut info = MONITORINFO { cbSize: size_of::<MONITORINFO>() as u32, ..Default::default() };
        let _ = GetMonitorInfoW(monitor, &mut info);
        let (mut dpi_x, mut dpi_y) = (96u32, 96u32);
        let _ = GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, &mut dpi_x, &mut dpi_y);
        (info.rcWork, dpi_x as f64 / 96.0)
    }
}

/// Moves and sizes the window so it's `width` × `height` logical pixels,
/// centred on (cx, cy), but kept fully on screen.
fn place(raw: isize, cx: i32, cy: i32, width: f64, height: f64) {
    let (work, scale) = monitor_at(cx, cy);
    let w = (width * scale).round() as i32;
    let h = (height * scale).round() as i32;
    let left = (cx - w / 2).min(work.right - w).max(work.left);
    let top = (cy - h / 2).min(work.bottom - h).max(work.top);
    unsafe {
        // Twice on purpose: moving onto a monitor with a different scale
        // makes Windows resize the window for the new scale (WM_DPICHANGED)
        // part-way through the first call. The second call puts it exactly
        // where we want it.
        for _ in 0..2 {
            let _ = SetWindowPos(hwnd(raw), HWND_TOPMOST, left, top, w, h, SWP_NOACTIVATE);
        }
    }
}

fn center_of(raw: isize) -> (i32, i32) {
    let mut rect = RECT::default();
    unsafe {
        let _ = GetWindowRect(hwnd(raw), &mut rect);
    }
    ((rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2)
}

fn show_without_focus(raw: isize) {
    unsafe {
        let _ = ShowWindow(hwnd(raw), SW_SHOWNOACTIVATE);
        let _ = SetWindowPos(hwnd(raw), HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
    }
}

fn hide(raw: isize) {
    unsafe {
        let _ = ShowWindow(hwnd(raw), SW_HIDE);
    }
}

/// A "tool window" doesn't appear in Alt+Tab or the taskbar: the portal is
/// a gesture, not an app you switch to.
fn make_tool_window(raw: isize) {
    unsafe {
        let style = GetWindowLongPtrW(hwnd(raw), GWL_EXSTYLE);
        let wanted = (style | WS_EX_TOOLWINDOW.0 as isize) & !(WS_EX_APPWINDOW.0 as isize);
        if wanted != style {
            SetWindowLongPtrW(hwnd(raw), GWL_EXSTYLE, wanted);
            let flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED;
            let _ = SetWindowPos(hwnd(raw), None, 0, 0, 0, 0, flags);
        }
    }
}

// ── The pool ────────────────────────────────────────────────────────────────

/// Creates a hidden window and adds it to the pool as Idle.
///
/// Never call this from a synchronous command or the hook thread: building
/// a WebView waits for the main thread, which would freeze (Tauri runs sync
/// commands on the main thread). Use `warm_up` instead.
fn create_window(app: &AppHandle) -> tauri::Result<String> {
    let label = {
        let state = app.state::<AppState>();
        let mut pool = state.pool.lock().unwrap();
        pool.next_id += 1;
        format!("portal-{}", pool.next_id)
    };
    let window = WebviewWindowBuilder::new(app, &label, WebviewUrl::App("index.html".into()))
        .title(APP_NAME)
        .inner_size(PORTAL_SIZE, PORTAL_SIZE)
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(false)
        .maximizable(false)
        .minimizable(false)
        .visible(false)
        .focused(false)
        .build()?;
    make_tool_window(raw_hwnd(&window));
    let state = app.state::<AppState>();
    state.pool.lock().unwrap().windows.push((label.clone(), Mode::Idle));
    Ok(label)
}

/// Makes sure one idle window is ready, on a background thread.
pub fn warm_up(app: &AppHandle) {
    {
        let state = app.state::<AppState>();
        let mut pool = state.pool.lock().unwrap();
        if pool.warming || pool.find(Mode::Idle).is_some() || pool.windows.len() >= MAX_WINDOWS {
            return;
        }
        pool.warming = true;
    }
    let app = app.clone();
    thread::spawn(move || {
        if let Err(err) = create_window(&app) {
            eprintln!("[portal] could not create a window: {err}");
        }
        app.state::<AppState>().pool.lock().unwrap().warming = false;
    });
}

fn emit_to(app: &AppHandle, label: &str, event: &str, payload: serde_json::Value) {
    let _ = app.emit_to(EventTarget::webview_window(label), event, payload);
}

/// Takes the open portal (to move it) or an idle window, and marks it.
fn claim(app: &AppHandle, mode: Mode) -> Option<WebviewWindow> {
    let state = app.state::<AppState>();
    let mut pool = state.pool.lock().unwrap();
    // A portal that's already open is reused: a second shake just moves it.
    let label = (mode == Mode::Portal).then(|| pool.find(Mode::Portal)).flatten().or_else(|| pool.find(Mode::Idle))?;
    pool.set(&label, mode);
    drop(pool);
    app.get_webview_window(&label)
}

/// Shows the portal centred on the cursor (physical screen pixels).
pub fn summon(app: &AppHandle, x: i32, y: i32) {
    let Some(window) = claim(app, Mode::Portal) else {
        // No idle window yet (the very first shake right after start, or
        // every window is busy with a job). Get one ready for next time.
        warm_up(app);
        return;
    };
    let raw = raw_hwnd(&window);
    place(raw, x, y, PORTAL_SIZE, PORTAL_SIZE);
    show_without_focus(raw);
    emit_to(app, window.label(), "summon", serde_json::json!({}));
    // The invisible window that actually receives the file goes on top
    // (droptarget.rs explains why). Main thread: it owns our windows.
    let (handle, label) = (app.clone(), window.label().to_string());
    let _ = app.run_on_main_thread(move || crate::droptarget::show_over(&handle, &label, raw));
    warm_up(app);
}

/// The mouse button went up after a shake. The page decides what that
/// means: if no file was dropped on a tool, it closes the portal.
pub fn release(app: &AppHandle) {
    let state = app.state::<AppState>();
    let label = state.pool.lock().unwrap().find(Mode::Portal);
    if let Some(label) = label {
        emit_to(app, &label, "release", serde_json::json!({}));
    }
}

/// Shows the "how to use" card in the middle of the screen the cursor is on.
pub fn hint(app: &AppHandle) {
    let Some(window) = claim(app, Mode::Card) else {
        warm_up(app);
        return;
    };
    let raw = raw_hwnd(&window);
    let mut cursor = POINT::default();
    unsafe {
        let _ = windows::Win32::UI::WindowsAndMessaging::GetCursorPos(&mut cursor);
    }
    let (work, _) = monitor_at(cursor.x, cursor.y);
    place(raw, (work.left + work.right) / 2, (work.top + work.bottom) / 2, PORTAL_SIZE, PORTAL_SIZE);
    show_without_focus(raw);
    emit_to(app, window.label(), "hint", serde_json::json!({}));
    warm_up(app);
}

/// The page became a card of this size (logical pixels). The window shrinks
/// or grows around its centre, so the card itself doesn't move.
pub fn resize_card(app: &AppHandle, window: &WebviewWindow, width: f64, height: f64) {
    let state = app.state::<AppState>();
    state.pool.lock().unwrap().set(window.label(), Mode::Card);
    crate::droptarget::hide(window.label()); // (sync commands run on the main thread)
    let raw = raw_hwnd(window);
    let (cx, cy) = center_of(raw);
    place(raw, cx, cy, width, height);
    warm_up(app);
}

/// Hides the window and puts it back in the pool, portal-sized again.
pub fn dismiss(app: &AppHandle, window: &WebviewWindow) {
    let raw = raw_hwnd(window);
    crate::droptarget::hide(window.label());
    hide(raw);
    let (cx, cy) = center_of(raw);
    place(raw, cx, cy, PORTAL_SIZE, PORTAL_SIZE);
    hide(raw); // place() can't show it, but stay explicit
    let state = app.state::<AppState>();
    let mut pool = state.pool.lock().unwrap();
    // Keep at most one spare: close extra idle windows (e.g. after three
    // jobs ran side by side) so they don't hold memory.
    let spare = pool.find(Mode::Idle);
    if spare.is_some() && spare.as_deref() != Some(window.label()) {
        pool.windows.retain(|(l, _)| l != window.label());
        drop(pool);
        crate::droptarget::destroy(window.label());
        let _ = window.destroy();
    } else {
        pool.set(window.label(), Mode::Idle);
    }
}

/// Lets you type (a password, a page range) into the card.
pub fn focus(window: &WebviewWindow) {
    let _ = window.set_focus();
}
