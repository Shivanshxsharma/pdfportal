/**
 * app.js — how a drag becomes a job (loaded last)
 * ============================================================================
 *
 *   idle ──summon──▶ portal ──drop on a tool──▶ card ──close──▶ idle
 *                      │
 *                      └─ drop elsewhere / let go / Esc ──▶ idle
 *
 * 1. You drag a file and shake it. Rust shows this window under the cursor
 *    and sends "summon".
 * 2. Windows drags the file INTO the window: Tauri reports "enter" with the
 *    file paths, then "over" as you move. We pick tools for the files and
 *    light up the slot under the cursor.
 * 3. You let go over a slot ("drop"): the disk grows into a card and the
 *    job starts (after one quick question, for a few tools).
 *    Let go anywhere else and the portal closes ("release" arrives from
 *    the mouse hook even when the drop happens outside this window).
 */

'use strict';

const state = {
  mode: 'idle',     // idle | portal | card
  paths: [],        // the files being dragged
  files: [],        // [{ path, name, size }] once Rust has looked them up
  tools: [],
  problem: '',      // why none of the tools fit, if so
  hot: null,        // slot index, 'center' or null
  dropped: false,
  job: null,        // { tool, files, options } of this card
};

const portalEl = $('portal');
const disk = $('disk');

// ── The disk in the middle ───────────────────────────────────────────────────

// What the disk should show now: a key that names the state (so we know
// when it really changed) and the content.
function diskFace() {
  const tool = typeof state.hot === 'number' ? TOOLS[Ring.toolAt(state.hot)] : null;
  if (tool) {
    return {
      key: `tool:${tool.title}`,
      parts: [h('strong', { class: 'disk-title caps' }, tool.title), h('span', { class: 'disk-text' }, tool.desc)],
    };
  }
  if (state.problem) {
    return {
      key: 'problem',
      parts: [h('span', { class: 'icon-badge coral' }, icon('alert')), h('span', { class: 'disk-text' }, state.problem)],
    };
  }
  if (state.paths.length) {
    const many = state.paths.length > 1;
    const total = state.files.reduce((sum, f) => sum + f.size, 0);
    const kind = kindOf(state.paths[0]) === 'image' ? 'image' : 'pdf';
    const label = many ? plural(state.paths.length, 'file') : kind.toUpperCase();
    const center = state.hot === 'center';
    return {
      key: center ? 'center' : 'files',
      parts: [
        h('span', { class: 'chip' }, icon(kind), h('span', {}, total ? `${label} · ${formatBytes(total)}` : label)),
        h('span', { class: 'disk-name' }, many ? `${baseName(state.paths[0])} +${state.paths.length - 1}` : baseName(state.paths[0])),
        h('strong', { class: 'disk-title small caps' }, center ? 'Let go to cancel' : 'Drop on a tool'),
      ],
    };
  }
  return {
    key: 'waiting',
    parts: [h('span', { class: 'disk-pulse' }), h('strong', { class: 'disk-title small caps' }, 'Bring it in')],
  };
}

let shownFace = { key: '', node: null };

// Shows the disk's new state. A real change (another tool, files arrived)
// slides the old face up and out and the new one up and in; the same state
// with new details (the file size arriving) just updates in place.
function renderDisk() {
  const { key, parts } = diskFace();
  const tool = key.startsWith('tool:');
  disk.classList.toggle('lit', tool);
  const node = h('div', { class: 'disk-face' }, ...parts);
  const old = shownFace.node;
  const changed = key !== shownFace.key;
  shownFace = { key, node };
  if (!old || !changed || calmMotion()) {
    if (old) old.remove();
    disk.append(node);
    return;
  }
  old.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(-10px)' }], {
    duration: 140, easing: 'cubic-bezier(0.5, 0, 0.75, 0)', fill: 'forwards',
  }).finished.then(() => old.remove(), () => old.remove());
  disk.append(node);
  node.animate([{ opacity: 0, transform: 'translateY(12px)' }, { opacity: 1, transform: 'none' }], {
    duration: 320, delay: 60, easing: 'cubic-bezier(0.16, 1, 0.3, 1)', fill: 'backwards',
  });
}

function setHot(hot) {
  if (hot === state.hot) return;
  state.hot = hot;
  Ring.setHot(typeof hot === 'number' ? hot : null);
  renderDisk();
}

// ── Portal ──────────────────────────────────────────────────────────────────

async function openPortal() {
  Card.hide();
  Object.assign(state, { mode: 'portal', paths: [], files: [], tools: [], problem: '', hot: null, dropped: false, job: null });
  Ring.reset();
  Ring.setTools([]);
  disk.replaceChildren();
  shownFace = { key: '', node: null };
  renderDisk();
  portalEl.hidden = false;
  portalEl.classList.remove('opening', 'closing', 'chosen');
  await nextFrame();
  portalEl.classList.add('opening');
}

async function closePortal() {
  if (state.mode !== 'portal') return;
  state.mode = 'idle';
  portalEl.classList.add('closing');
  await wait(180);
  portalEl.hidden = true;
  portalEl.classList.remove('opening', 'closing');
  await portal.dismiss();
}

function filesEntered(paths) {
  state.paths = paths;
  const { tools, problem = '' } = toolsFor(paths);
  state.tools = tools;
  state.problem = problem;
  Ring.setTools(tools, { muted: Boolean(problem) });
  renderDisk();
  portal.fileInfo(paths).then((files) => {
    if (state.paths !== paths) return; // a newer drag replaced these
    state.files = files;
    renderDisk();
  });
}

// Window coordinates → ring coordinates. The ring is centred in the window
// (portal.css); computed from the layout, not getBoundingClientRect(), which
// would be off while the opening animation scales the ring.
function ringPoint(point) {
  if (!point) return null;
  return { x: point.x - (window.innerWidth - Ring.size) / 2, y: point.y - (window.innerHeight - Ring.size) / 2 };
}

portal.onDragDrop(({ type, paths, point: windowPoint }) => {
  if (state.mode !== 'portal') return;
  const point = ringPoint(windowPoint);
  if (type === 'enter') {
    filesEntered(paths);
    setHot(Ring.hitTest(point));
  } else if (type === 'over') {
    setHot(Ring.hitTest(point));
  } else if (type === 'leave') {
    setHot(null);
  } else if (type === 'drop') {
    state.dropped = true;
    const tool = state.problem ? null : Ring.toolAt(Ring.hitTest(point));
    if (tool) startTool(tool, paths.length ? paths : state.paths);
    else closePortal();
  }
});

// The mouse button went up. If that was a drop on a tool, "drop" arrives
// around the same moment; give it a beat before deciding it wasn't.
portal.on('release', async () => {
  await wait(350);
  if (state.mode === 'portal' && !state.dropped) closePortal();
});

portal.on('summon', openPortal);

// ── Card ────────────────────────────────────────────────────────────────────

async function startTool(tool, paths) {
  state.mode = 'card';
  portalEl.classList.add('chosen');
  const files = state.files.length === paths.length
    ? state.files
    : paths.map((path) => ({ path, name: baseName(path), size: 0 }));
  state.job = { tool, paths, files, options: {} };

  const job = {
    tool,
    files,
    get options() { return state.job.options; },
    onRun: (options) => run(options),
    onCancel: () => portal.cancelJob(),
    onClose: () => closeCard(),
  };
  const form = TOOLS[tool].form;
  const growing = Card.begin(job, form ? { kind: 'question', form } : { kind: 'run' });
  // Tools without a question start right away, while the card is still
  // opening: the progress view already exists, so early progress lands in it.
  if (!form) run({}, { alreadyShowing: true });
  await wait(440); // the ring's melt-away (.portal.chosen in portal.css)
  portalEl.hidden = true;
  portalEl.classList.remove('opening', 'chosen');
  await growing;
}

async function run(options, { alreadyShowing = false } = {}) {
  // Remember answers (a password typed for "needs_password" is added to
  // the options the tool's own question gave).
  state.job.options = { ...state.job.options, ...options };
  if (!alreadyShowing) await Card.running();
  try {
    await portal.startJob(state.job.tool, state.job.paths, state.job.options);
  } catch (err) {
    Card.failed({ message: String(err) });
  }
}

portal.on('job', (event) => {
  if (state.mode !== 'card' || !state.job) return;
  switch (event.event) {
    case 'progress':
      Card.progress(event.fraction, event.message);
      break;
    case 'done':
      Card.done(event);
      break;
    case 'error':
      if (event.code === 'needs_password' || event.code === 'wrong_password') {
        Card.ask('password', { error: event.code === 'wrong_password' ? event.message : '' });
      } else if (event.code === 'needs_input' && TOOLS[state.job.tool].form) {
        Card.ask(TOOLS[state.job.tool].form, { error: event.message });
      } else {
        Card.failed(event);
      }
      break;
    case 'cancelled':
      closeCard();
      break;
  }
});

async function closeCard() {
  if (state.mode === 'idle') return;
  state.mode = 'idle';
  state.job = null;
  $('card').classList.add('leaving');
  await wait(180);
  $('card').classList.remove('leaving');
  Card.hide();
  await portal.dismiss();  // also stops a running job
}

// ── Hint ("How to use PDFportal" in the tray, and the first start) ─────────

portal.on('hint', () => {
  portalEl.hidden = true;
  state.mode = 'card';
  state.job = null;
  Card.hint(closeCard);
});

// Files arrive through Rust's drop target, never the page. If WebView2's own
// handling ever got a drop anyway, it would open the PDF IN this window;
// refusing the browser's default here makes sure it never navigates away.
for (const type of ['dragover', 'drop']) document.addEventListener(type, (event) => event.preventDefault());

// ── Keyboard ────────────────────────────────────────────────────────────────

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape') return;
  if (state.mode === 'portal') closePortal();
  else if (state.mode === 'card') closeCard();
});

Ring.mount($('ring'));
