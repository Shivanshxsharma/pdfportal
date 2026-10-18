/**
 * dom.js — small helpers every other script uses (loaded first)
 */

'use strict';

const SVG_NS = 'http://www.w3.org/2000/svg';

const $ = (id) => document.getElementById(id);

// Why: builds DOM with createElement + text nodes, so file names are always
// shown as TEXT. Building HTML strings from them (innerHTML) would let a
// file called "<img onerror=…>.pdf" run code.
//   h('button', { class: 'btn', onclick: fn }, 'Open')
function h(tag, props, ...children) {
  const node = document.createElement(tag);
  setProps(node, props);
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : String(child)); // strings become text, never HTML
  }
  return node;
}

function setProps(node, props) {
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.setAttribute('class', value);
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
    else if (key in node && !(node instanceof SVGElement)) node[key] = value;
    else node.setAttribute(key, value === true ? '' : String(value));
  }
}

// Same as h(), for SVG elements (they need their own namespace).
function s(tag, props, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  setProps(node, props);
  for (const child of children.flat()) {
    if (child) node.append(child);
  }
  return node;
}

// An icon from the sprite in index.html: <svg class="icon"><use href="#i-NAME"/></svg>
function icon(name, extraClass = '') {
  return s('svg', { class: `icon ${extraClass}`.trim(), 'aria-hidden': 'true' }, s('use', { href: `#i-${name}` }));
}

// 1536 -> "1.5 KB". Same rules as the engine's human_size, so the card and
// the engine's summary agree.
function formatBytes(n) {
  let size = Number(n) || 0;
  for (const unit of ['B', 'KB', 'MB', 'GB']) {
    if (size < 1024 || unit === 'GB') return unit === 'B' ? `${Math.round(size)} B` : `${size.toFixed(1)} ${unit}`;
    size /= 1024;
  }
  return `${n} B`;
}

function plural(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

// The last part of a Windows or POSIX path.
function baseName(path) {
  return String(path).split(/[\\/]/).pop();
}

// Resolves after the next paint, so a style change has been drawn before
// the next one (needed to start a CSS transition from a fresh state).
// A window that isn't painting (hidden, minimised) gets no frames at all,
// so a short timer resolves it anyway: nothing may ever wait forever on it.
function nextFrame() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
    setTimeout(resolve, 80);
  });
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// True if the person asked Windows for less motion (Settings → Accessibility
// → Visual effects → Animation effects off).
const calmMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Counts a number smoothly from `from` to `to` (a percentage creeping up,
// "−74%" counting in), calling onFrame(value) on every screen refresh.
// Eases out: fast at first, settling gently. Returns a stop() function.
function tween(from, to, ms, onFrame) {
  if (calmMotion() || ms <= 0) {
    onFrame(to);
    return () => {};
  }
  const start = performance.now();
  let frame = 0;
  const step = (now) => {
    // A frame's timestamp is when the frame began, which can be a hair
    // BEFORE `start`; clamp, or the first frame would count backwards.
    const t = Math.max(0, Math.min(1, (now - start) / ms));
    const eased = 1 - Math.pow(1 - t, 4);
    onFrame(from + (to - from) * eased);
    if (t < 1) frame = requestAnimationFrame(step);
  };
  frame = requestAnimationFrame(step);
  // Without frames (a window that isn't painting) still end on the right number.
  const fallback = setTimeout(() => onFrame(to), ms + 100);
  return () => {
    cancelAnimationFrame(frame);
    clearTimeout(fallback);
  };
}
