//! Everything the page may ask Rust to do (`invoke` in src/js/api.js).
//!
//! Tauri runs non-async commands on the main thread, which is right for
//! window placement but means they must stay quick.

use std::path::PathBuf;

use serde::Serialize;
use serde_json::Value;
use tauri::{AppHandle, Manager, WebviewWindow};
use tauri_plugin_opener::OpenerExt;

use crate::{engine, portal, AppState};

#[derive(Serialize)]
pub struct FileInfo {
    path: String,
    name: String,
    size: u64,
    exists: bool,
}

/// Names and sizes of the dropped files, for the card.
#[tauri::command]
pub fn file_info(paths: Vec<String>) -> Vec<FileInfo> {
    paths
        .into_iter()
        .map(|path| {
            let p = PathBuf::from(&path);
            let meta = std::fs::metadata(&p).ok();
            FileInfo {
                name: p.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| path.clone()),
                size: meta.as_ref().map(|m| m.len()).unwrap_or(0),
                exists: meta.map(|m| m.is_file()).unwrap_or(false),
                path,
            }
        })
        .collect()
}

#[tauri::command]
pub fn start_job(app: AppHandle, window: WebviewWindow, tool: String, inputs: Vec<String>, options: Value) -> Result<(), String> {
    engine::start(&app, window.label(), &tool, inputs, options)
}

#[tauri::command]
pub fn cancel_job(app: AppHandle, window: WebviewWindow) {
    engine::cancel(&app, window.label());
}

/// The page became a card of this size (logical pixels, shadow included).
#[tauri::command]
pub fn resize_card(app: AppHandle, window: WebviewWindow, width: f64, height: f64) {
    let width = width.clamp(120.0, 900.0);
    let height = height.clamp(80.0, 900.0);
    portal::resize_card(&app, &window, width, height);
}

/// Close this portal or card (stops its job if one is running).
#[tauri::command]
pub fn dismiss(app: AppHandle, window: WebviewWindow) {
    engine::cancel(&app, window.label());
    portal::dismiss(&app, &window);
}

#[tauri::command]
pub fn focus_card(window: WebviewWindow) {
    portal::focus(&window);
}

fn checked_result(app: &AppHandle, path: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(path);
    if !app.state::<AppState>().jobs.is_result(&path) {
        return Err("Only files PDFportal made can be opened from here.".into());
    }
    if !path.exists() {
        return Err("That file isn't there any more. Was it moved or deleted?".into());
    }
    Ok(path)
}

/// Opens a result in its usual app (a PDF reader, Photos, File Explorer).
#[tauri::command]
pub fn open_result(app: AppHandle, path: String) -> Result<(), String> {
    let path = checked_result(&app, &path)?;
    app.opener().open_path(path.to_string_lossy(), None::<&str>).map_err(|err| err.to_string())
}

/// Opens File Explorer with the result selected.
#[tauri::command]
pub fn reveal_result(app: AppHandle, path: String) -> Result<(), String> {
    let path = checked_result(&app, &path)?;
    app.opener().reveal_item_in_dir(path).map_err(|err| err.to_string())
}
