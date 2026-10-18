//! Running jobs in the PDF engine (../engine, Python).
//!
//! One job = one engine process: we write the job as JSON to its stdin and
//! read one JSON event per line from its stdout, forwarding each to the card
//! that owns the job (the "job" event in card.js). A separate process means
//! a PDF that crashes the engine can only fail that one job, and Cancel can
//! stop it instantly by ending the process.

use std::collections::{HashMap, HashSet};
use std::io::{BufRead, BufReader, Read, Write};
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter, EventTarget, Manager};

use crate::AppState;

/// Don't flash a console window when starting the engine.
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// How to start the engine.
#[derive(Clone, Debug)]
pub struct EngineCommand {
    program: PathBuf,
    args: Vec<String>,
    dir: Option<PathBuf>,
}

impl EngineCommand {
    /// Finds the engine, in this order:
    ///   1. PORTAL_ENGINE=<path to pdfportal-engine.exe> (testing a build)
    ///   2. the engine bundled with the installed app
    ///   3. the development copy: ../engine with its .venv
    pub fn locate(app: &AppHandle) -> Option<Self> {
        if let Some(exe) = std::env::var_os("PORTAL_ENGINE").map(PathBuf::from) {
            return Some(Self { program: exe, args: vec![], dir: None });
        }
        if let Ok(resources) = app.path().resource_dir() {
            let exe = resources.join("engine").join("pdfportal-engine.exe");
            if exe.is_file() {
                return Some(Self { program: exe, args: vec![], dir: None });
            }
        }
        let dev = Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("engine");
        let python = dev.join(".venv").join("Scripts").join("python.exe");
        if python.is_file() {
            return Some(Self { program: python, args: vec!["-m".into(), "portal_engine".into()], dir: Some(dev) });
        }
        None
    }
}

struct Running {
    child: Arc<Mutex<Child>>,
    cancelled: Arc<AtomicBool>,
}

#[derive(Default)]
pub struct Jobs {
    running: Mutex<HashMap<String, Running>>, // by window label: one job per card
    /// Files and folders the engine created. Only these may be opened or
    /// shown from a card, so a page can't ask us to open anything else.
    results: Mutex<HashSet<PathBuf>>,
}

impl Jobs {
    pub fn is_result(&self, path: &Path) -> bool {
        self.results.lock().unwrap().contains(path)
    }
}

fn send(app: &AppHandle, label: &str, payload: Value) {
    let _ = app.emit_to(EventTarget::webview_window(label), "job", payload);
}

/// The engine announces each temporary file before writing it. We delete
/// them if the job is cancelled, but only if they really look like the
/// engine's temporary files: a bug can never make us delete your files.
fn remove_temp(path: &Path) {
    let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
    if !(name.starts_with(".portal-") && name.ends_with(".part")) {
        return;
    }
    if path.is_dir() {
        let _ = std::fs::remove_dir_all(path);
    } else {
        let _ = std::fs::remove_file(path);
    }
}

pub fn start(app: &AppHandle, label: &str, tool: &str, inputs: Vec<String>, options: Value) -> Result<(), String> {
    let state = app.state::<AppState>();
    let engine = state.engine.clone().ok_or("PDFportal's PDF engine is missing. Reinstall PDFportal to fix this.")?;
    if state.jobs.running.lock().unwrap().contains_key(label) {
        return Err("This card is already running a job.".into());
    }
    let fallback = app.path().download_dir().map(|d| d.to_string_lossy().into_owned()).unwrap_or_default();
    let request = json!({ "tool": tool, "inputs": inputs, "options": options, "fallback_dir": fallback });

    let mut command = Command::new(&engine.program);
    command
        .args(&engine.args)
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .creation_flags(CREATE_NO_WINDOW);
    if let Some(dir) = &engine.dir {
        command.current_dir(dir);
    }
    let mut child = command.spawn().map_err(|err| format!("Couldn't start the PDF engine: {err}"))?;

    let mut stdin = child.stdin.take().ok_or("no stdin")?;
    let stdout = child.stdout.take().ok_or("no stdout")?;
    let mut stderr = child.stderr.take().ok_or("no stderr")?;
    // Closing stdin (end of the `let`) tells the engine the request is complete.
    stdin.write_all(request.to_string().as_bytes()).map_err(|err| format!("Couldn't send the job: {err}"))?;
    drop(stdin);

    let child = Arc::new(Mutex::new(child));
    let cancelled = Arc::new(AtomicBool::new(false));
    state
        .jobs
        .running
        .lock()
        .unwrap()
        .insert(label.to_string(), Running { child: child.clone(), cancelled: cancelled.clone() });

    // Collect stderr on its own thread: if nobody reads it and the engine
    // writes a lot (a long traceback), the pipe fills up and the engine stalls.
    let errors = thread::spawn(move || {
        let mut text = String::new();
        let _ = stderr.read_to_string(&mut text);
        text
    });

    let app = app.clone();
    let label = label.to_string();
    thread::spawn(move || {
        let mut temps: Vec<PathBuf> = Vec::new();
        let mut finished = false;
        for line in BufReader::new(stdout).lines() {
            let Ok(line) = line else { break };
            let Ok(event) = serde_json::from_str::<Value>(&line) else { continue };
            match event["event"].as_str() {
                Some("temp") => {
                    if let Some(path) = event["path"].as_str() {
                        temps.push(PathBuf::from(path));
                    }
                }
                Some("done") => {
                    finished = true;
                    let state = app.state::<AppState>();
                    let mut results = state.jobs.results.lock().unwrap();
                    for path in event["outputs"].as_array().into_iter().flatten().filter_map(Value::as_str) {
                        results.insert(PathBuf::from(path));
                    }
                    if let Some(folder) = event["folder"].as_str() {
                        results.insert(PathBuf::from(folder));
                    }
                    drop(results);
                    send(&app, &label, event);
                }
                Some("error") => {
                    finished = true;
                    send(&app, &label, event);
                }
                _ => send(&app, &label, event),
            }
        }
        let _ = child.lock().unwrap().wait();
        let stderr_text = errors.join().unwrap_or_default();
        app.state::<AppState>().jobs.running.lock().unwrap().remove(&label);

        if cancelled.load(Ordering::SeqCst) {
            temps.iter().for_each(|p| remove_temp(p));
            send(&app, &label, json!({ "event": "cancelled" }));
        } else if !finished {
            // The engine died without a word (a crash deep inside MuPDF).
            temps.iter().for_each(|p| remove_temp(p));
            eprintln!("[engine] stopped unexpectedly:\n{stderr_text}");
            send(&app, &label, json!({
                "event": "error",
                "code": "internal",
                "message": "The PDF engine stopped unexpectedly. The file may be damaged."
            }));
        }
    });
    Ok(())
}

pub fn cancel(app: &AppHandle, label: &str) {
    let state = app.state::<AppState>();
    let running = state.jobs.running.lock().unwrap();
    if let Some(job) = running.get(label) {
        job.cancelled.store(true, Ordering::SeqCst);
        let _ = job.child.lock().unwrap().kill();
    }
}
