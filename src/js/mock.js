/**
 * mock.js — a pretend backend, for working on the UI in a normal browser
 * ============================================================================
 * Open src/index.html directly in a browser (no Tauri): this file stands in
 * for Rust so you can see and click through the portal and the cards.
 * Inside the real app window.__TAURI__ exists and this file does nothing.
 *
 *   index.html?files=report.pdf          the files you "drag"
 *   move the mouse = drag over the ring, click = drop, S = open the portal
 *
 * The dashed outline is the window's edge, so you can see Rust's resizing.
 * From DevTools: mock.summon(), mock.drag(x, y), mock.drop(x, y), mock.hint()
 */

'use strict';

(() => {
  if (window.__TAURI__) return;

  const params = new URLSearchParams(location.search);
  const files = (params.get('files') || 'Quarterly report.pdf').split(',');
  const listeners = {};
  let entered = false;
  let open = false;
  const frame = { w: 520, h: 520 };

  const emit = (event, payload) => (listeners[event] || []).forEach((cb) => cb({ payload }));

  function applyFrame() {
    // A transform on <body> makes position:fixed children use the body as
    // their viewport, so the page behaves as if the window were this size.
    Object.assign(document.body.style, {
      position: 'absolute',
      left: '50%',
      top: '50%',
      width: `${frame.w}px`,
      height: `${frame.h}px`,
      transform: 'translate(-50%, -50%)',
      outline: params.get('demo') ? 'none' : '1px dashed rgba(0, 0, 0, 0.25)',
    });
    // innerWidth/innerHeight are what app.js uses to find the ring's centre.
    Object.defineProperty(window, 'innerWidth', { configurable: true, get: () => frame.w });
    Object.defineProperty(window, 'innerHeight', { configurable: true, get: () => frame.h });
  }

  function point(event) {
    const box = document.body.getBoundingClientRect();
    return { x: (event.clientX - box.left) * devicePixelRatio, y: (event.clientY - box.top) * devicePixelRatio };
  }

  const paths = files.map((name) => `C:\\Users\\you\\Documents\\${name}`);

  function drag(type, position) {
    emit('drag', { type, paths: type === 'enter' || type === 'drop' ? paths : [], position });
  }

  function summon() {
    frame.w = frame.h = 520;
    applyFrame();
    entered = false;
    open = true;
    emit('summon', {});
  }

  // Fake jobs: a few progress steps, then a plausible result.
  function fakeJob({ tool, inputs, options }) {
    const first = inputs[0].replace(/\.[^.\\]+$/, '');
    if (tool === 'unlock' && !options.input_password) {
      setTimeout(() => emit('job', { event: 'error', code: 'needs_password', message: 'It is locked.' }), 400);
      return;
    }
    if (options.input_password === 'wrong') {
      setTimeout(() => emit('job', { event: 'error', code: 'wrong_password', message: "That password didn't work. Try again." }), 400);
      return;
    }
    const results = {
      compress: { outputs: [`${first} (compressed).pdf`], summary: '4.2 MB → 1.1 MB · 74% smaller', details: { before: 4_404_019, after: 1_148_211 } },
      split: { outputs: [`${first} (split)`], folder: `${first} (split)`, summary: '12 PDFs in “Quarterly report (split)”' },
      rotate: { outputs: [`${first} (rotated).pdf`], summary: '12 pages turned 90° clockwise' },
      pdf_to_images: { outputs: [`${first} (images)`], folder: `${first} (images)`, summary: '12 JPG images at 150 dpi' },
    };
    const result = results[tool] || { outputs: [`${first} (${tool}).pdf`], summary: 'Done.' };
    const steps = ['Reading', 'Shrinking images', 'Shrinking images', 'Saving', 'Saving'];
    steps.forEach((message, i) =>
      setTimeout(() => emit('job', { event: 'progress', fraction: (i + 1) / (steps.length + 1), message }), 300 + i * 350));
    setTimeout(() => emit('job', { event: 'done', ...result }), 300 + steps.length * 350 + 200);
  }

  const commands = {
    file_info: ({ paths }) => paths.map((path, i) => ({ path, name: path.split('\\').pop(), size: 4_404_019 + i * 1_200_000, exists: true })),
    start_job: (args) => fakeJob(args),
    cancel_job: () => setTimeout(() => emit('job', { event: 'cancelled' }), 50),
    resize_card: ({ width, height }) => {
      frame.w = Math.round(width);
      frame.h = Math.round(height);
      applyFrame();
    },
    dismiss: () => {
      open = false;
      document.body.style.outline = 'none';
    },
    focus_card: () => {},
    open_result: ({ path }) => console.log('[mock] open', path),
    reveal_result: ({ path }) => console.log('[mock] reveal', path),
  };

  window.__TAURI__ = {
    core: { invoke: async (cmd, args) => commands[cmd](args || {}) },
    webviewWindow: {
      getCurrentWebviewWindow: () => ({
        listen: async (event, cb) => {
          (listeners[event] = listeners[event] || []).push(cb);
          return () => {};
        },
      }),
    },
  };

  window.mock = {
    summon,
    hint: () => {
      frame.w = frame.h = 520;
      applyFrame();
      emit('hint', {});
    },
    drag: (x, y) => {
      if (!entered) {
        entered = true;
        drag('enter', { x, y });
      }
      drag('over', { x, y });
    },
    drop: (x, y) => {
      drag('drop', { x, y });
      setTimeout(() => emit('release', {}), 30);
    },
  };

  document.addEventListener('DOMContentLoaded', () => {
    document.documentElement.style.background = params.get('bg') || '#dcdbe3';
    applyFrame();
    document.addEventListener('mousemove', (event) => open && !document.getElementById('portal').hidden && window.mock.drag(point(event).x, point(event).y));
    document.addEventListener('click', (event) => {
      if (open && !document.getElementById('portal').hidden) window.mock.drop(point(event).x, point(event).y);
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 's' && !open) summon();
    });
    const demo = params.get('demo');
    if (demo) runDemo(demo);
    else if (params.get('start') !== 'none') setTimeout(params.get('start') === 'hint' ? window.mock.hint : summon, 200);
  });

  // ?demo=ring|done|form|hint plays one state by itself, for the README's
  // screenshots (scripts/screenshots.ps1 opens these in headless Edge).
  async function runDemo(demo) {
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const d = devicePixelRatio;
    const slot = (index, count = 8) => {
      const a = -Math.PI / 2 + (index * 2 * Math.PI) / count;
      return [(260 + 154 * Math.cos(a)) * d, (260 + 154 * Math.sin(a)) * d];
    };
    document.body.style.outline = 'none';
    if (demo === 'hint') return window.mock.hint();
    summon();
    await sleep(300);
    window.mock.drag(260 * d, 260 * d);
    await sleep(300);
    const [x, y] = slot(demo === 'form' ? 6 : 1); // Protect, or Compress
    window.mock.drag(x, y);
    if (demo === 'ring') return;
    await sleep(400);
    window.mock.drop(x, y);
    if (demo === 'form') {
      await sleep(1500);
      const inputs = document.querySelectorAll('#card input.text');
      inputs.forEach((input) => (input.value = 'correct horse'));
    }
  }
})();
