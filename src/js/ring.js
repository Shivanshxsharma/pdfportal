/**
 * ring.js — draws the portal: a ring of tool slots around a disk
 * ============================================================================
 * Everything is drawn in a 460 × 460 SVG whose centre is the window's
 * centre, i.e. right under your cursor when the portal opens.
 *
 *   slot k is centred at angle  -90° + k × 360°/n   (slot 0 at the top,
 *   then clockwise, the way you'd read a clock)
 *
 * Gaps between slots are a constant width (not a constant angle), so the
 * edges of neighbouring slots are parallel at every radius. Round corners
 * come from drawing each slot CORNER px smaller all round and outlining it
 * with a 2 × CORNER stroke of its own colour with round joins (portal.css).
 */

'use strict';

const Ring = (() => {
  const C = 230;            // centre
  const R_IN = 104;         // inner edge of the slots (the disk sits inside)
  const R_OUT = 204;        // outer edge
  const R_MID = (R_IN + R_OUT) / 2;
  const R_RIM = R_OUT + 13; // the ring of dots, and the pointer
  const GAP = 6;            // px between slots, as you see them
  const CORNER = 8;         // corner radius, px (portal.css: stroke-width = 2 × CORNER)
  const PUSH = 8;           // how far a hovered slot moves outward, px
  const HIT_SLACK = 24;     // you may overshoot the outer edge a little

  let svg = null;
  let slots = [];           // [{ id, node, angle }]
  let count = 0;
  let pointer = null;
  let pointerAngle = null;  // degrees; kept continuous so it never spins the long way

  const at = (r, a) => `${(C + r * Math.cos(a)).toFixed(2)} ${(C + r * Math.sin(a)).toFixed(2)}`;

  // One slot: the ring between a0 and a1 (radians), shrunk by CORNER on
  // every side (the stroke grows it back, rounding the corners).
  function slotPath(a0, a1) {
    const outer = R_OUT - CORNER;
    const inner = R_IN + CORNER;
    const half = GAP / 2 + CORNER;
    const go = half / outer; // the gap angle differs per radius to keep it even
    const gi = half / inner;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    return [
      `M ${at(outer, a0 + go)}`,
      `A ${outer} ${outer} 0 ${large} 1 ${at(outer, a1 - go)}`,
      `L ${at(inner, a1 - gi)}`,
      `A ${inner} ${inner} 0 ${large} 0 ${at(inner, a0 + gi)}`,
      'Z',
    ].join(' ');
  }

  // A single tool fills the whole ring (two circles, the inner one cut out).
  function fullRingPath() {
    const circle = (r) => `M ${C - r} ${C} a ${r} ${r} 0 1 0 ${2 * r} 0 a ${r} ${r} 0 1 0 ${-2 * r} 0`;
    return `${circle(R_OUT - CORNER)} ${circle(R_IN + CORNER)}`;
  }

  // The pointer's arc, drawn at the top (12 o'clock); CSS rotates it.
  function pointerPath() {
    const spread = (13 * Math.PI) / 180;
    const top = -Math.PI / 2;
    return `M ${at(R_RIM, top - spread)} A ${R_RIM} ${R_RIM} 0 0 1 ${at(R_RIM, top + spread)}`;
  }

  function mount(svgNode) {
    svg = svgNode;
    pointer = s('g', { class: 'pointer' }, s('path', { d: pointerPath() }));
    svg.replaceChildren(
      s('g', { class: 'rim' }, s('circle', { cx: C, cy: C, r: R_RIM })),
      s('circle', { class: 'inner-rim', cx: C, cy: C, r: R_IN - 6 }),
      s('g', { class: 'slots' }),
      pointer,
    );
    setTools([]);
  }

  /**
   * Shows these tools (ids from TOOLS). An empty list draws eight empty
   * "ghost" slots: the portal is open but doesn't know your files yet.
   */
  function setTools(ids, { muted = false } = {}) {
    const group = svg.querySelector('.slots');
    const ghost = ids.length === 0;
    const list = ghost ? Array(8).fill(null) : ids;
    count = ghost ? 0 : list.length;
    const step = (2 * Math.PI) / list.length;

    slots = list.map((id, k) => {
      const mid = -Math.PI / 2 + k * step;
      const tool = id && TOOLS[id];
      const d = list.length === 1 ? fullRingPath() : slotPath(mid - step / 2, mid + step / 2);
      const node = s('g', {
        class: `slot${ghost ? ' ghost' : ''}${muted ? ' muted' : ''}`,
        style: `--i:${k}; --dx:${(Math.cos(mid) * PUSH).toFixed(2)}px; --dy:${(Math.sin(mid) * PUSH).toFixed(2)}px`,
      },
        s('path', { class: 'slot-bg', d, 'fill-rule': 'evenodd' }),
      );
      if (tool) {
        const x = C + R_MID * Math.cos(mid);
        const y = C + R_MID * Math.sin(mid);
        const label = s('text', { class: 'slot-label', x, y: y + 21, 'text-anchor': 'middle' });
        label.textContent = tool.label;
        node.append(
          s('use', { class: 'slot-icon', href: `#i-${tool.icon}`, x: x - 12, y: y - 22, width: 24, height: 24 }),
          label,
        );
      }
      return { id, node, angle: (mid * 180) / Math.PI + 90 };
    });
    group.replaceChildren(...slots.map((slot) => slot.node));
    setHot(null);
  }

  /** Highlights slot `index` (or nothing, for null) and glides the pointer to it. */
  function setHot(index) {
    slots.forEach((slot, k) => slot.node.classList.toggle('hot', k === index));
    const slot = typeof index === 'number' ? slots[index] : null;
    pointer.classList.toggle('on', Boolean(slot) && count > 1);
    if (!slot) return;
    if (pointerAngle === null) {
      pointerAngle = slot.angle;
    } else {
      // Go the short way round: from 350° to 10° is +20°, not −340°.
      const delta = ((((slot.angle - pointerAngle) % 360) + 540) % 360) - 180;
      pointerAngle += delta;
    }
    pointer.style.setProperty('--angle', `${pointerAngle}deg`);
  }

  /**
   * What's under a point (CSS pixels in ring coordinates):
   *   a slot index, 'center' (the disk: cancel), or null (outside).
   */
  function hitTest(point) {
    if (!point) return null;
    const dx = point.x - C;
    const dy = point.y - C;
    const r = Math.hypot(dx, dy);
    if (r < R_IN - 6) return 'center';
    if (r > R_OUT + HIT_SLACK || count === 0) return null;
    const step = (2 * Math.PI) / count;
    // atan2 is 0 at 3 o'clock and grows clockwise (screen y points down);
    // shift by 90° so 0 is 12 o'clock, like slot 0.
    const angle = Math.atan2(dy, dx) + Math.PI / 2;
    return ((Math.round(angle / step) % count) + count) % count;
  }

  /** The tool id of slot `index`. */
  const toolAt = (index) => (typeof index === 'number' && slots[index] ? slots[index].id : null);

  /** Forgets the pointer's position, so a new portal starts fresh. */
  function reset() {
    pointerAngle = null;
    pointer.style.transition = 'none';
    requestAnimationFrame(() => (pointer.style.transition = ''));
  }

  return { mount, setTools, setHot, hitTest, toolAt, reset, size: 2 * C, diskRadius: R_IN - 12 };
})();
