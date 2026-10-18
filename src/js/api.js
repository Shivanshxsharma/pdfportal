/**
 * api.js — the bridge to the Rust backend
 * ============================================================================
 * Tauri gives the page `invoke` (call a #[tauri::command] in
 * src-tauri/src/commands.rs) and events. This file wraps them in one object,
 * `window.portal`, so the rest of the UI never talks to Tauri directly.
 *
 * Events this window can receive:
 *   summon   Rust showed this window under the cursor: become the portal
 *   release  the mouse button went up (the drag ended)
 *   hint     show the "how to use" card
 *   job      an event from this window's running job (see engine/protocol.py)
 *   drag     files being dragged over the window: enter / over / leave /
 *            drop (from our own drop target, src-tauri/src/droptarget.rs)
 */

'use strict';

(() => {
  const tauri = window.__TAURI__;
  const { invoke } = tauri.core;
  // Listen on THIS window only: Rust sends each event to one window
  // (emit_to), and a card must never react to another card's job.
  const me = tauri.webviewWindow.getCurrentWebviewWindow();

  window.portal = {
    fileInfo: (paths) => invoke('file_info', { paths }),
    startJob: (tool, inputs, options) => invoke('start_job', { tool, inputs, options: options || {} }),
    cancelJob: () => invoke('cancel_job'),
    resizeCard: (width, height) => invoke('resize_card', { width, height }),
    dismiss: () => invoke('dismiss'),
    focusCard: () => invoke('focus_card'),
    openResult: (path) => invoke('open_result', { path }),
    revealResult: (path) => invoke('reveal_result', { path }),

    on: (event, callback) => me.listen(event, (e) => callback(e.payload)),

    // Files dragged over the window. `position` comes in physical pixels;
    // we convert to CSS pixels, which is what the ring is drawn in.
    onDragDrop: (callback) =>
      me.listen('drag', (e) => {
        const { type, paths, position } = e.payload;
        const point = position
          ? { x: position.x / window.devicePixelRatio, y: position.y / window.devicePixelRatio }
          : null;
        callback({ type, paths: paths || [], point });
      }),
  };
})();
