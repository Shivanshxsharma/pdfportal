/**
 * card.js — the small window a drop turns into
 * ============================================================================
 * One card per job:  [question] → progress → result (or an error).
 *
 * Look (portal.css): a big condensed title, the file as a pill chip, one
 * colour block per state (a sea-blue panel with a big number when done,
 * coral for a problem), pill buttons. Content arrives in a short cascade:
 * each block rises into place a beat after the one above (--n below).
 *
 * Size: the card is always centred in its window (portal.css), and Rust
 * resizes the window around its centre (resize_card). So when the card
 * changes height we either grow the window first and then the card, or
 * shrink the card first and then the window. Either way the card itself
 * never jumps, and the window never cuts it off.
 */

'use strict';

const Card = (() => {
  const WIDTH = 360;        // the card, CSS px (portal.css .card)
  const MARGIN = 26;        // room around it for the shadow
  const RESIZE_MS = 380;    // the card's height transition (portal.css)
  const card = $('card');
  let height = 0;           // the card's current height
  let job = null;           // { tool, files, options, onRun, onCancel, onClose }
  let bar = null;           // progress nodes, updated in place
  let note = null;
  let percent = null;
  let shownPct = 0;         // the percentage on screen (it counts towards the real one)
  let stopCount = () => {};

  // ── Size ──────────────────────────────────────────────────────────────────

  // Lays `body` out at the card's width off-screen and returns its height.
  function measure(body) {
    const probe = h('div', { class: 'card measure' }, body);
    document.body.append(probe);
    const result = Math.ceil(probe.getBoundingClientRect().height);
    probe.remove();
    return result;
  }

  const fitWindow = (cardHeight) => portal.resizeCard(WIDTH + 2 * MARGIN, cardHeight + 2 * MARGIN);

  async function resizeTo(next) {
    if (next > height) {
      await fitWindow(next);
      card.style.height = `${next}px`;
    } else if (next < height) {
      card.style.height = `${next}px`;
      await wait(RESIZE_MS);
      await fitWindow(next);
    }
    height = next;
  }

  // Content that changes height by itself (an error line appearing under a
  // form, "Custom ranges" enabling its field) resizes the card to match.
  // Paused while we're swapping or morphing, which size things themselves.
  let settling = false;
  const watcher = new ResizeObserver((entries) => {
    if (settling || card.hidden) return;
    const next = Math.ceil(entries[0].contentRect.height);
    if (next && next !== height) resizeTo(next);
  });
  function watch(view) {
    watcher.disconnect();
    watcher.observe(view);
  }

  // Numbers the blocks of a view top to bottom, for the rising cascade.
  function stagger(view) {
    let n = 0;
    for (const block of view.children) {
      if (block.classList.contains('card-body')) {
        for (const inner of block.children) inner.style.setProperty('--n', n++);
      } else {
        block.style.setProperty('--n', n++);
      }
    }
    return view;
  }

  // Swaps the card's content for `body`, resizing around it.
  async function show(body) {
    settling = true;
    stagger(body);
    const next = measure(body.cloneNode(true));
    card.classList.add('swapping');
    await wait(120);
    card.replaceChildren(body);
    card.classList.remove('swapping');
    await resizeTo(next);
    watch(body);
    settling = false;
  }

  /**
   * The drop moment: the disk in the middle of the portal grows into the
   * card. It starts as a circle exactly where the disk was; the content
   * rises in once the card has mostly opened.
   */
  async function morphIn(body) {
    settling = true;
    stagger(body);
    const next = measure(body.cloneNode(true));
    const d = 2 * Ring.diskRadius;
    card.replaceChildren(body);
    card.hidden = false;
    card.classList.add('morphing');
    Object.assign(card.style, { width: `${d}px`, height: `${d}px`, borderRadius: `${d / 2}px` });
    await nextFrame();
    Object.assign(card.style, { width: `${WIDTH}px`, height: `${next}px`, borderRadius: '' });
    await wait(520);
    card.classList.remove('morphing');
    height = next;
    await fitWindow(next);
    watch(body);
    settling = false;
  }

  /** Shows the card at full size, popping in (the hint). */
  async function appear(body) {
    settling = true;
    stagger(body);
    const next = measure(body.cloneNode(true));
    card.replaceChildren(body);
    Object.assign(card.style, { width: `${WIDTH}px`, height: `${next}px`, borderRadius: '' });
    height = next;
    await fitWindow(next);
    card.hidden = false;
    card.classList.add('appearing');
    await wait(460);
    card.classList.remove('appearing');
    watch(body);
    settling = false;
  }

  // ── Pieces ────────────────────────────────────────────────────────────────

  function filesLine() {
    const files = job.files;
    const total = files.reduce((sum, f) => sum + (f.size || 0), 0);
    const first = files[0] ? files[0].name : '';
    const size = total ? ` · ${formatBytes(total)}` : '';
    return files.length === 1 ? `${first}${size}` : `${plural(files.length, 'file')}${size}`;
  }

  // The title and the file chip; drag it to move the card around.
  function header() {
    const tool = TOOLS[job.tool];
    const kind = job.files.length && kindOf(job.files[0].name) === 'image' ? 'image' : 'pdf';
    return h('header', { class: 'card-head', 'data-tauri-drag-region': true },
      h('div', { class: 'card-titles', 'data-tauri-drag-region': true },
        h('strong', { class: 'card-title caps', 'data-tauri-drag-region': true }, tool.title),
        h('span', { class: 'chip', title: job.files.map((f) => f.name).join('\n'), 'data-tauri-drag-region': true },
          icon(kind), h('span', {}, filesLine())),
      ),
      h('button', { class: 'round-btn', type: 'button', 'aria-label': 'Close', title: 'Close (Esc)', onclick: () => job.onClose() }, icon('close')),
    );
  }

  const button = (label, onclick, kind = 'secondary', iconName = null) =>
    h('button', { class: `btn ${kind}`, type: kind === 'primary' && !onclick ? 'submit' : 'button', onclick }, iconName && icon(iconName), label);

  function field(label, input, hint) {
    return h('label', { class: 'field' }, h('span', { class: 'field-label' }, label), input, hint && h('span', { class: 'field-hint' }, hint));
  }

  // The colour block: a big headline or number, and a line under it.
  function panel(tone, big, noteText, { check = false } = {}) {
    return h('div', { class: `panel ${tone}` },
      check ? h('span', { class: 'check' }, icon('check')) : null,
      big,
      noteText ? h('span', { class: 'panel-note' }, noteText) : null,
    );
  }

  // ── States ────────────────────────────────────────────────────────────────

  /** A question before the job runs. `kind`: split | watermark | protect | password. */
  function question(kind, { error = '' } = {}) {
    const inputs = {};
    let body;
    const errorLine = h('p', { class: 'form-error', role: 'alert' }, error);
    const submit = (event) => {
      event.preventDefault();
      const options = readForm(kind, inputs, errorLine);
      if (options) job.onRun(options);
    };

    if (kind === 'split') {
      const pages = h('input', { type: 'radio', name: 'mode', value: 'pages', checked: true });
      const ranges = h('input', { type: 'radio', name: 'mode', value: 'ranges' });
      inputs.ranges = h('input', { type: 'text', class: 'text', placeholder: 'e.g. 1-3, 5, 8-', spellcheck: false, disabled: true });
      inputs.mode = () => (ranges.checked ? 'ranges' : 'pages');
      const sync = () => {
        inputs.ranges.disabled = !ranges.checked;
        if (ranges.checked) inputs.ranges.focus();
      };
      pages.addEventListener('change', sync);
      ranges.addEventListener('change', sync);
      body = [
        h('div', { class: 'segmented', role: 'radiogroup' },
          h('label', {}, pages, h('span', {}, 'Every page')),
          h('label', {}, ranges, h('span', {}, 'Custom ranges')),
        ),
        field('Pages', inputs.ranges, 'Each range becomes one PDF.'),
      ];
    } else if (kind === 'watermark') {
      inputs.text = h('input', { type: 'text', class: 'text', value: 'CONFIDENTIAL', maxLength: 80, spellcheck: false });
      body = [field('Watermark text', inputs.text)];
    } else if (kind === 'protect') {
      inputs.password = h('input', { type: 'password', class: 'text', autocomplete: 'new-password' });
      inputs.confirm = h('input', { type: 'password', class: 'text', autocomplete: 'new-password' });
      body = [
        field('Password', h('div', { class: 'with-eye' }, inputs.password, eyeToggle([inputs.password, inputs.confirm]))),
        field('Type it again', inputs.confirm, 'There is no way to recover a forgotten PDF password.'),
      ];
    } else {
      inputs.password = h('input', { type: 'password', class: 'text', autocomplete: 'current-password' });
      body = [
        panel('deep', h('strong', { class: 'panel-head caps' }, 'It’s locked'),
          `${job.files.length === 1 ? job.files[0].name : 'One of these files'} needs its password first.`),
        field('Password', h('div', { class: 'with-eye' }, inputs.password, eyeToggle([inputs.password]))),
      ];
    }

    const primaryLabel = { split: 'Split PDF', watermark: 'Add watermark', protect: 'Protect PDF', password: 'Unlock and continue' }[kind];
    const form = h('form', { class: 'card-body', onsubmit: submit },
      ...body,
      errorLine,
      h('div', { class: 'actions' }, button(primaryLabel, null, 'primary')),
    );
    const view = h('div', { class: 'card-view' }, header(), form);
    const focusFirst = () => {
      const first = form.querySelector('input.text:not([disabled])') || form.querySelector('button');
      portal.focusCard().finally(() => {
        first.focus();
        if (first.select && kind === 'watermark') first.select();
      });
    };
    return { view, focusFirst };
  }

  function eyeToggle(fields) {
    return h('button', {
      type: 'button',
      class: 'eye',
      'aria-label': 'Show password',
      title: 'Show password',
      onclick: (event) => {
        const showing = fields[0].type === 'text';
        fields.forEach((f) => (f.type = showing ? 'password' : 'text'));
        event.currentTarget.classList.toggle('on', !showing);
      },
    }, icon('eye'));
  }

  // Turns a form into job options, or shows what's wrong and returns null.
  function readForm(kind, inputs, errorLine) {
    const fail = (text, input) => {
      errorLine.textContent = text;
      if (input) input.focus();
      return null;
    };
    errorLine.textContent = '';
    if (kind === 'split') {
      const mode = inputs.mode();
      const ranges = inputs.ranges.value.trim();
      if (mode === 'ranges' && !ranges) return fail('Type the pages to keep together, like 1-3, 5.', inputs.ranges);
      return { mode, ranges };
    }
    if (kind === 'watermark') {
      const text = inputs.text.value.trim();
      return text ? { text } : fail('Type the watermark text.', inputs.text);
    }
    if (kind === 'protect') {
      const pw = inputs.password.value;
      if (!pw) return fail('Choose a password.', inputs.password);
      if (pw !== inputs.confirm.value) return fail("The two passwords don't match.", inputs.confirm);
      return { new_password: pw };
    }
    const pw = inputs.password.value;
    return pw ? { input_password: pw } : fail('Enter the password.', inputs.password);
  }

  function running() {
    stopCount();
    shownPct = 0;
    bar = h('div', { class: 'bar-fill' });
    note = h('span', { class: 'progress-note' }, 'Starting…');
    percent = h('strong', { class: 'progress-pct caps' }, '0%');
    return h('div', { class: 'card-view' },
      header(),
      h('div', { class: 'card-body' },
        h('div', { class: 'progress-top' }, percent, note),
        h('div', { class: 'bar waiting', role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': 100 }, bar),
        h('div', { class: 'actions' }, button('Cancel', () => job.onCancel())),
      ),
    );
  }

  function progress(fraction, message) {
    if (!bar) return;
    const track = bar.parentElement;
    const pct = Math.round(fraction * 100);
    track.classList.toggle('waiting', pct <= 0);
    track.setAttribute('aria-valuenow', pct);
    bar.style.width = `${Math.max(pct, 3)}%`;
    if (message) note.textContent = message;
    // The number counts towards the new value instead of jumping to it.
    stopCount();
    const from = shownPct;
    stopCount = tween(from, pct, 500, (v) => {
      shownPct = v;
      percent.textContent = `${Math.round(v)}%`;
    });
  }

  function finished(event) {
    const outputs = event.outputs || [];
    const folder = event.folder;
    const target = folder || outputs[0];
    const isFolder = Boolean(folder);
    const details = event.details || {};

    // The colour block: how much smaller (compress), or a plain "Done".
    let block;
    const saved = details.before && details.after < details.before ? Math.round((1 - details.after / details.before) * 100) : null;
    if (!target) {
      block = panel('deep', h('strong', { class: 'panel-head caps' }, 'Nothing to change'), event.summary);
    } else if (saved !== null) {
      const big = h('strong', { class: 'panel-big caps' }, '−0%');
      setTimeout(() => tween(0, saved, 900, (v) => (big.textContent = `−${Math.round(v)}%`)), 300);
      block = panel('', big, `${formatBytes(details.before)} → ${formatBytes(details.after)}`, { check: true });
    } else {
      block = panel('', h('strong', { class: 'panel-head caps' }, 'Done'), event.summary, { check: true });
    }

    const actions = [];
    let chip = null;
    if (target) {
      chip = h('button', { class: 'result', type: 'button', title: `Open ${baseName(target)}`, onclick: () => portal.openResult(target) },
        icon(isFolder ? 'folder' : kindOf(target) === 'image' ? 'image' : 'pdf'),
        h('span', { class: 'result-name' }, baseName(target)),
        outputs.length > 1 && !isFolder ? h('span', { class: 'result-more' }, `+${outputs.length - 1}`) : null,
        h('span', { class: 'round-btn foam', 'aria-hidden': 'true' }, icon('open')),
      );
      if (isFolder) {
        actions.push(button('Open folder', () => portal.openResult(target), 'primary', 'folder'));
      } else {
        actions.push(button('Open', () => portal.openResult(target), 'primary', 'open'));
        actions.push(button('Show in folder', () => portal.revealResult(target), 'secondary', 'folder'));
      }
    } else {
      actions.push(button('Close', () => job.onClose(), 'secondary'));
    }
    bar = null;
    return h('div', { class: 'card-view' },
      header(),
      h('div', { class: 'card-body' }, block, chip, h('div', { class: 'actions' }, ...actions)),
    );
  }

  function failed(event) {
    bar = null;
    return h('div', { class: 'card-view' },
      header(),
      h('div', { class: 'card-body' },
        panel('coral', h('strong', { class: 'panel-head caps' }, 'Couldn’t finish'), event.message || 'Something went wrong.'),
        h('div', { class: 'actions' },
          button('Try again', () => job.onRun(job.options), 'secondary'),
          button('Close', () => job.onClose(), 'secondary'),
        ),
      ),
    );
  }

  function hintView(onClose) {
    return h('div', { class: 'card-view hint' },
      h('div', { class: 'hint-art', 'aria-hidden': 'true' },
        h('span', { class: 'hint-ring' }),
        h('span', { class: 'hint-file' }, icon('pdf')),
      ),
      h('div', { class: 'card-body' },
        h('span', { class: 'chip' }, h('span', {}, 'PDFportal · works offline')),
        h('h1', { class: 'caps' }, 'Drag. Shake. Drop.'),
        h('p', {}, 'Drag any PDF or image, give it a quick shake, and a ring of tools opens under your cursor. Drop the file on the tool you want.'),
        h('p', { class: 'fine' }, 'Everything happens on this computer. Nothing is uploaded.'),
        h('div', { class: 'actions' }, button('Got it', onClose, 'primary')),
      ),
    );
  }

  // ── One change at a time ──────────────────────────────────────────────────
  // A quick job can finish while the card is still growing out of the disk.
  // Changes therefore wait their turn: each runs after the previous one has
  // finished sizing the card. hide() starts a new "generation", so changes
  // still queued for a card you closed are dropped.

  let queue = Promise.resolve();
  let generation = 0;

  function next(change) {
    const mine = generation;
    const run = () => (mine === generation ? change() : undefined);
    queue = queue.then(run, run);
    return queue;
  }

  // ── Public ────────────────────────────────────────────────────────────────

  return {
    WIDTH,
    MARGIN,
    get height() { return height; },

    /** Starts a card for a job, growing it out of the portal's disk. */
    begin(newJob, first) {
      job = newJob;
      const view = first.kind === 'question' ? question(first.form) : { view: running() };
      return next(async () => {
        await morphIn(view.view);
        if (view.focusFirst) view.focusFirst();
      });
    },

    ask(form, options) {
      return next(async () => {
        const view = question(form, options);
        await show(view.view);
        view.focusFirst();
      });
    },

    running() {
      return next(() => show(running()));
    },

    progress,

    done(event) {
      return next(() => {
        stopCount();
        return show(finished(event));
      });
    },

    failed(event) {
      return next(() => {
        stopCount();
        return show(failed(event));
      });
    },

    hint(onClose) {
      job = null;
      return next(async () => {
        await appear(hintView(onClose));
        const button = card.querySelector('.btn.primary');
        portal.focusCard().finally(() => button && button.focus());
      });
    },

    hide() {
      generation += 1;
      watcher.disconnect();
      stopCount();
      card.hidden = true;
      card.replaceChildren();
      card.removeAttribute('style');
      height = 0;
      job = null;
      bar = null;
    },
  };
})();
