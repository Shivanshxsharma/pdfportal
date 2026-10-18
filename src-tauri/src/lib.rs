//! PDFportal — the Rust backend (Tauri 2)
//!
//! PDFportal has no main window. It sits in the tray, watches for a file
//! being dragged and shaken, and opens a ring of tools under the cursor.
//!
//!   shake.rs       the mouse hook that notices "drag + shake"
//!   portal.rs      the portal/card windows: a small pool, placement on screen
//!   droptarget.rs  the invisible "drop surface" that receives the files
//!   engine.rs      runs jobs in the Python PDF engine, streams progress
//!   commands.rs    everything the page (../src) may call
//!   config.rs      numbers worth tuning
//!
//! The page itself (index.html + js/) draws the ring and the cards; see
//! src/js/app.js for how a drop becomes a job.

mod commands;
mod config;
mod droptarget;
mod engine;
mod portal;
mod shake;

use std::fs;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Mutex};
use std::thread;

use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

use config::APP_NAME;
use engine::{EngineCommand, Jobs};
use portal::Pool;
use shake::Gesture;

/// Everything shared between commands and background threads.
pub struct AppState {
    pub pool: Mutex<Pool>,
    pub jobs: Jobs,
    pub engine: Option<EngineCommand>,
    /// "Pause the shake gesture" in the tray menu.
    pub paused: AtomicBool,
}

/// Reacts to gestures from the mouse hook, on a thread of its own (the
/// hook must never wait for us).
fn spawn_gesture_loop(app: AppHandle) {
    let (sender, receiver) = mpsc::channel::<Gesture>();
    shake::spawn(sender);
    thread::spawn(move || {
        for gesture in receiver {
            if app.state::<AppState>().paused.load(Ordering::Relaxed) {
                continue;
            }
            match gesture {
                Gesture::Shake { x, y } => portal::summon(&app, x, y),
                Gesture::Release { .. } => portal::release(&app),
            }
        }
    });
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let autostart_on = app.autolaunch().is_enabled().unwrap_or(false);
    let how = MenuItem::with_id(app, "how", "How to use PDFportal", true, None::<&str>)?;
    let pause = CheckMenuItem::with_id(app, "pause", "Pause the shake gesture", true, false, None::<&str>)?;
    let autostart = CheckMenuItem::with_id(app, "autostart", "Start with Windows", true, autostart_on, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit PDFportal", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[&how, &PredefinedMenuItem::separator(app)?, &pause, &autostart, &PredefinedMenuItem::separator(app)?, &quit],
    )?;

    let mut tray = TrayIconBuilder::with_id("portal")
        .tooltip("PDFportal: drag a file and shake it")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event| match event.id().as_ref() {
            "how" => portal::hint(app),
            "pause" => {
                let paused = pause.is_checked().unwrap_or(false);
                app.state::<AppState>().paused.store(paused, Ordering::Relaxed);
            }
            "autostart" => {
                let launcher = app.autolaunch();
                let result = if autostart.is_checked().unwrap_or(false) { launcher.enable() } else { launcher.disable() };
                if let Err(err) = result {
                    eprintln!("[tray] start with Windows: {err}");
                }
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                portal::hint(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;
    Ok(())
}

/// The first time PDFportal starts, show how it works (once).
fn first_run(app: &AppHandle) -> bool {
    let Ok(dir) = app.path().app_data_dir() else { return false };
    let marker = dir.join("welcomed");
    if marker.exists() {
        return false;
    }
    let _ = fs::create_dir_all(&dir).and_then(|_| fs::write(&marker, b""));
    true
}

fn setup(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let handle = app.handle().clone();
    let engine = EngineCommand::locate(&handle);
    if engine.is_none() {
        eprintln!("[{APP_NAME}] the PDF engine wasn't found; jobs will fail");
    }
    app.manage(AppState { pool: Mutex::new(Pool::default()), jobs: Jobs::default(), engine, paused: AtomicBool::new(false) });

    build_tray(&handle)?;
    portal::warm_up(&handle);
    spawn_gesture_loop(handle.clone());

    if first_run(&handle) || std::env::var_os("PORTAL_SHOW_HINT").is_some() {
        // Give the first window a moment to load before showing the hint.
        thread::spawn(move || {
            thread::sleep(std::time::Duration::from_millis(1200));
            portal::hint(&handle);
        });
    }
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        // Must be first: a second launch just shows the hint in the first.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| portal::hint(app)))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))
        .setup(setup)
        .invoke_handler(tauri::generate_handler![
            commands::file_info,
            commands::start_job,
            commands::cancel_job,
            commands::resize_card,
            commands::dismiss,
            commands::focus_card,
            commands::open_result,
            commands::reveal_result,
        ])
        // No windows is normal for PDFportal (it lives in the tray): don't quit
        // when the last card closes.
        .build(tauri::generate_context!())
        .map(|app| {
            app.run(|_app, event| {
                if let tauri::RunEvent::ExitRequested { api, code: None, .. } = event {
                    api.prevent_exit();
                }
            })
        })
        .unwrap_or_else(|err| eprintln!("{APP_NAME} stopped: {err}"));
}
