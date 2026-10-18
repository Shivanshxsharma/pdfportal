//! Receiving the dragged files: the "drop surface".
//!
//! When you let go of a dragged file, Windows asks the window under the
//! cursor (or its nearest parent that registered one) for a drop target
//! (an IDropTarget, set up with RegisterDragDrop). A WebView2 window is a
//! stack of windows, partly owned by Edge's own processes, and WebView2
//! registers and re-registers drop targets in that stack on its own
//! schedule. In testing, drops onto it never reached us reliably.
//!
//! So while the portal is open we put a plain native window of our own
//! exactly on top of it: the drop surface. It's 1/255 opaque (invisible,
//! but Windows still sends it the mouse; fully transparent windows are
//! skipped), it never takes focus, and WE register its drop target. It
//! reads the file paths (CF_HDROP), follows the cursor, and sends the page
//! "drag" events: enter (with paths), over, leave, drop (with paths).
//! Positions are relative to the portal window, in physical pixels;
//! api.js converts them to CSS pixels. The ring underneath does the drawing.
//!
//! Everything here runs on the main thread: Windows requires drop targets
//! to live on a thread with a message loop that initialised OLE, and Tauri's
//! main thread is that thread.

use std::cell::RefCell;
use std::collections::HashMap;
use std::sync::Mutex;

use serde_json::json;
use tauri::{AppHandle, Emitter, EventTarget};
use windows::core::{implement, w};
use windows::Win32::Foundation::{COLORREF, HINSTANCE, HWND, LPARAM, LRESULT, POINT, POINTL, WPARAM};
use windows::Win32::Graphics::Gdi::ScreenToClient;
use windows::Win32::System::Com::{IDataObject, DVASPECT_CONTENT, FORMATETC, TYMED_HGLOBAL};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::Ole::{
    IDropTarget, IDropTarget_Impl, RegisterDragDrop, ReleaseStgMedium, RevokeDragDrop, CF_HDROP, DROPEFFECT,
    DROPEFFECT_COPY, DROPEFFECT_NONE,
};
use windows::Win32::System::SystemServices::MODIFIERKEYS_FLAGS;
use windows::Win32::UI::Shell::{DragQueryFileW, HDROP};
use windows::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, DefWindowProcW, DestroyWindow, GetWindowRect, LoadCursorW, RegisterClassExW,
    SetLayeredWindowAttributes, SetWindowPos, ShowWindow, HWND_TOPMOST, IDC_ARROW, LWA_ALPHA, MA_NOACTIVATE,
    SWP_NOACTIVATE, SW_HIDE, SW_SHOWNOACTIVATE, WM_MOUSEACTIVATE, WNDCLASSEXW, WS_EX_LAYERED, WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_POPUP,
};

// ── The drop target ──────────────────────────────────────────────────────────

#[implement(IDropTarget)]
struct DropTarget {
    app: AppHandle,
    label: String,  // the portal window this surface belongs to
    portal: isize,  // its HWND: positions are reported relative to it
    surface: isize, // our own window, hidden right after a drop
    // The paths of the drag in progress (None: not files, so we refuse it).
    // Windows calls a drop target on one thread only, so RefCell is enough.
    files: RefCell<Option<Vec<String>>>,
}

impl DropTarget {
    fn send(&self, kind: &str, paths: &[String], screen: Option<&POINTL>) {
        let position = screen.map(|pt| {
            let mut p = POINT { x: pt.x, y: pt.y };
            unsafe {
                let _ = ScreenToClient(HWND(self.portal as *mut _), &mut p);
            }
            json!({ "x": p.x, "y": p.y })
        });
        let payload = json!({ "type": kind, "paths": paths, "position": position });
        let _ = self.app.emit_to(EventTarget::webview_window(&self.label), "drag", payload);
    }
}

/// The dragged files' full paths, if the drag carries files at all (text or
/// a link from a browser doesn't).
fn file_paths(data: &IDataObject) -> Option<Vec<String>> {
    let format = FORMATETC {
        cfFormat: CF_HDROP.0,
        ptd: std::ptr::null_mut(),
        dwAspect: DVASPECT_CONTENT.0,
        lindex: -1,
        tymed: TYMED_HGLOBAL.0 as u32,
    };
    unsafe {
        let mut medium = data.GetData(&format).ok()?;
        let drop = HDROP(medium.u.hGlobal.0);
        let count = DragQueryFileW(drop, u32::MAX, None); // u32::MAX = "how many files?"
        let mut paths = Vec::with_capacity(count as usize);
        for i in 0..count {
            let len = DragQueryFileW(drop, i, None) as usize;
            let mut buffer = vec![0u16; len + 1];
            DragQueryFileW(drop, i, Some(&mut buffer));
            paths.push(String::from_utf16_lossy(&buffer[..len]));
        }
        ReleaseStgMedium(&mut medium);
        (!paths.is_empty()).then_some(paths)
    }
}

fn set_effect(effect: *mut DROPEFFECT, accept: bool) {
    if !effect.is_null() {
        unsafe { *effect = if accept { DROPEFFECT_COPY } else { DROPEFFECT_NONE } };
    }
}

impl IDropTarget_Impl for DropTarget_Impl {
    fn DragEnter(
        &self,
        data: Option<&IDataObject>,
        _keys: MODIFIERKEYS_FLAGS,
        pt: &POINTL,
        effect: *mut DROPEFFECT,
    ) -> windows::core::Result<()> {
        let files = data.and_then(file_paths);
        set_effect(effect, files.is_some());
        #[cfg(debug_assertions)]
        eprintln!("[drop] enter {}: {:?}", self.label, files);
        if let Some(paths) = &files {
            self.send("enter", paths, Some(pt));
        }
        *self.files.borrow_mut() = files;
        Ok(())
    }

    fn DragOver(&self, _keys: MODIFIERKEYS_FLAGS, pt: &POINTL, effect: *mut DROPEFFECT) -> windows::core::Result<()> {
        let accepting = self.files.borrow().is_some();
        set_effect(effect, accepting);
        if accepting {
            self.send("over", &[], Some(pt));
        }
        Ok(())
    }

    fn DragLeave(&self) -> windows::core::Result<()> {
        if self.files.borrow_mut().take().is_some() {
            self.send("leave", &[], None);
        }
        Ok(())
    }

    fn Drop(
        &self,
        data: Option<&IDataObject>,
        _keys: MODIFIERKEYS_FLAGS,
        pt: &POINTL,
        effect: *mut DROPEFFECT,
    ) -> windows::core::Result<()> {
        let files = self.files.borrow_mut().take().or_else(|| data.and_then(file_paths));
        set_effect(effect, files.is_some());
        // The drag is over: get out of the way of the card.
        unsafe {
            let _ = ShowWindow(HWND(self.surface as *mut _), SW_HIDE);
        }
        if let Some(paths) = files {
            self.send("drop", &paths, Some(pt));
        }
        Ok(())
    }
}

// ── The surface window ───────────────────────────────────────────────────────

/// One surface per portal window, by window label: (surface HWND).
static SURFACES: Mutex<Option<HashMap<String, isize>>> = Mutex::new(None);

unsafe extern "system" fn surface_proc(hwnd: HWND, message: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if message == WM_MOUSEACTIVATE {
        // Never take focus from the app you're dragging from.
        return LRESULT(MA_NOACTIVATE as isize);
    }
    DefWindowProcW(hwnd, message, wparam, lparam)
}

fn create_surface(app: &AppHandle, label: &str, portal: isize) -> windows::core::Result<isize> {
    unsafe {
        let instance = HINSTANCE(GetModuleHandleW(None)?.0);
        let class = WNDCLASSEXW {
            cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
            lpfnWndProc: Some(surface_proc),
            hInstance: instance,
            hCursor: LoadCursorW(None, IDC_ARROW)?,
            lpszClassName: w!("PortalDropSurface"),
            ..Default::default()
        };
        RegisterClassExW(&class); // 0 the second time ("already registered"): fine
        let hwnd = CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE,
            w!("PortalDropSurface"),
            w!("PDFportal drop surface"),
            WS_POPUP,
            0,
            0,
            1,
            1,
            None,
            None,
            instance,
            None,
        )?;
        // 1 of 255: invisible to you, but not "fully transparent", which
        // Windows would skip when it looks for the window under the cursor.
        SetLayeredWindowAttributes(hwnd, COLORREF(0), 1, LWA_ALPHA)?;
        let target: IDropTarget = DropTarget {
            app: app.clone(),
            label: label.to_string(),
            portal,
            surface: hwnd.0 as isize,
            files: RefCell::new(None),
        }
        .into();
        RegisterDragDrop(hwnd, &target)?;
        Ok(hwnd.0 as isize)
    }
}

/// Puts the drop surface exactly over the portal window (creating it the
/// first time), on top of everything. Main thread only.
pub fn show_over(app: &AppHandle, label: &str, portal: isize) {
    let mut surfaces = SURFACES.lock().unwrap();
    let map = surfaces.get_or_insert_with(HashMap::new);
    let surface = match map.get(label) {
        Some(&hwnd) => hwnd,
        None => match create_surface(app, label, portal) {
            Ok(hwnd) => {
                map.insert(label.to_string(), hwnd);
                hwnd
            }
            Err(err) => {
                eprintln!("[drop] could not create the drop surface: {err}");
                return;
            }
        },
    };
    unsafe {
        let mut rect = Default::default();
        let _ = GetWindowRect(HWND(portal as *mut _), &mut rect);
        let hwnd = HWND(surface as *mut _);
        let (w, h) = (rect.right - rect.left, rect.bottom - rect.top);
        let _ = SetWindowPos(hwnd, HWND_TOPMOST, rect.left, rect.top, w, h, SWP_NOACTIVATE);
        let _ = ShowWindow(hwnd, SW_SHOWNOACTIVATE);
    }
}

/// Hides the surface (the portal closed or became a card). Main thread only.
pub fn hide(label: &str) {
    if let Some(&hwnd) = SURFACES.lock().unwrap().as_ref().and_then(|m| m.get(label)) {
        unsafe {
            let _ = ShowWindow(HWND(hwnd as *mut _), SW_HIDE);
        }
    }
}

/// The portal window is going away: so does its surface. Main thread only.
pub fn destroy(label: &str) {
    if let Some(hwnd) = SURFACES.lock().unwrap().as_mut().and_then(|m| m.remove(label)) {
        unsafe {
            let hwnd = HWND(hwnd as *mut _);
            let _ = RevokeDragDrop(hwnd);
            let _ = DestroyWindow(hwnd);
        }
    }
}
