//! Numbers worth tuning, in one place.

pub const APP_NAME: &str = "PDFportal";

/// The portal window is a square this many logical pixels wide: the 460 px
/// ring (portal.css) plus room for its shadow.
pub const PORTAL_SIZE: f64 = 520.0;

/// At most this many portal/card windows at once (each running job keeps
/// its card on screen).
pub const MAX_WINDOWS: usize = 6;

// ── Shake detection (physical pixels and milliseconds) ──────────────────────
// A "shake" is the mouse changing direction SHAKE_REVERSALS times within
// SHAKE_WINDOW_MS while the left button is held, each swing at least
// SHAKE_MIN_SWING long. Normal drags almost never zig-zag like that.

/// Shortest swing that counts.
pub const SHAKE_MIN_SWING: i32 = 40;
/// How far the mouse must come back before we call it a turn. Stops hand
/// tremor (a pixel or two back and forth) from counting.
pub const SHAKE_HYSTERESIS: i32 = 10;
/// Turns needed: right-left-right-left is 3 turns.
pub const SHAKE_REVERSALS: usize = 3;
/// All turns must happen within this time.
pub const SHAKE_WINDOW_MS: u32 = 1000;
