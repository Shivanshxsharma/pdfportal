"""Draws PDFportal's app icon: the portal itself, in miniature.

Same geometry as the ring in the app (src/js/ring.js), scaled up: eight
chunky rounded slots with even gaps, the top-right one lit in cream and
pushed outward, the cream "dial notch" above it on a ring of mauve dots,
and the centre disk with a cream rim holding a document glyph, on a night
purple tile.

    engine\\.venv\\Scripts\\python scripts\\make_icon.py
    npx tauri icon src-tauri\\icons\\icon-source.png -o src-tauri\\icons

The first command writes the 1024 px source; the second makes every size
Windows needs (icon.ico, 32x32.png, …) from it.
"""

import math
from pathlib import Path

import pymupdf


def hex_rgb(value):
    """"#854f6c" -> (0.52, 0.31, 0.42), the 0-1 colours PyMuPDF wants."""
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


# The palette (portal.css).
NIGHT = hex_rgb("#190019")
VIOLET = hex_rgb("#2b124c")
PLUM = hex_rgb("#522b5b")
MAUVE = hex_rgb("#854f6c")
CREAM = hex_rgb("#fbe4d8")

SIZE = 1024
C = SIZE / 2
# ring.js numbers (R_IN 104, R_OUT 204, rim 217, disk 92, gap 6, corner 8,
# push 8), times SCALE.
SCALE = 2.0
R_IN, R_OUT, R_RIM, R_DISK = 104 * SCALE, 204 * SCALE, 217 * SCALE, 92 * SCALE
GAP, CORNER, PUSH = 7 * SCALE, 9 * SCALE, 10 * SCALE
LIT = 1  # which slot is lit: 1 = top right, like the portal mid-hover

OUT = Path(__file__).resolve().parents[1] / "src-tauri" / "icons" / "icon-source.png"


def polar(r, a, dx=0.0, dy=0.0):
    return pymupdf.Point(C + dx + r * math.cos(a), C + dy + r * math.sin(a))


def arc(r, a0, a1, steps=48, dx=0.0, dy=0.0):
    return [polar(r, a0 + (a1 - a0) * i / steps, dx, dy) for i in range(steps + 1)]


def slot_outline(a0, a1, dx=0.0, dy=0.0):
    """One slot, shrunk by CORNER on every side; a 2 × CORNER stroke with
    round joins grows it back with rounded corners (as in portal.css)."""
    outer, inner = R_OUT - CORNER, R_IN + CORNER
    half = GAP / 2 + CORNER
    go, gi = half / outer, half / inner  # constant-width gaps
    points = arc(outer, a0 + go, a1 - go, dx=dx, dy=dy) + arc(inner, a1 - gi, a0 + gi, dx=dx, dy=dy)
    return points + [points[0]]


def rounded_rect(x0, y0, x1, y1, r, steps=10):
    """A rounded rectangle as a closed polyline (for the document glyph)."""
    corners = [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]
    points = []
    for cx, cy, start in corners:
        for i in range(steps + 1):
            a = math.radians(start + 90 * i / steps)
            points.append(pymupdf.Point(cx + r * math.cos(a), cy + r * math.sin(a)))
    return points + [points[0]]


def main():
    doc = pymupdf.open()
    page = doc.new_page(width=SIZE, height=SIZE)
    shape = page.new_shape()

    # The tile: Windows shows icons on any background, so it carries its own.
    shape.draw_rect(pymupdf.Rect(28, 28, SIZE - 28, SIZE - 28), radius=0.23)
    shape.finish(fill=NIGHT, color=None)

    # The ring of dots.
    dots = 72
    for k in range(dots):
        shape.draw_circle(polar(R_RIM, 2 * math.pi * k / dots), 4.2)
    shape.finish(fill=MAUVE, color=None)

    # Eight slots, slot 0 at 12 o'clock, clockwise.
    step = 2 * math.pi / 8
    for k in range(8):
        mid = -math.pi / 2 + k * step
        lit = k == LIT
        dx, dy = (PUSH * math.cos(mid), PUSH * math.sin(mid)) if lit else (0.0, 0.0)
        shape.draw_polyline(slot_outline(mid - step / 2, mid + step / 2, dx, dy))
        colour = CREAM if lit else VIOLET
        shape.finish(fill=colour, color=colour, width=2 * CORNER, lineJoin=1, closePath=True)

    # The dial notch: a cream arc on the rim, over the lit slot.
    lit_mid = -math.pi / 2 + LIT * step
    spread = math.radians(13)
    shape.draw_polyline(arc(R_RIM, lit_mid - spread, lit_mid + spread))
    shape.finish(color=CREAM, width=4 * SCALE, lineCap=1, closePath=False)

    # The thin line around the disk, then the disk with its cream rim.
    shape.draw_circle(pymupdf.Point(C, C), R_IN - 6 * SCALE)
    shape.finish(color=PLUM, width=2.5)
    shape.draw_circle(pymupdf.Point(C, C), R_DISK)
    shape.finish(fill=NIGHT, color=CREAM, width=2.5 * SCALE)

    # The document glyph: the app's "pdf" icon (index.html, 24-unit grid),
    # centred in the disk. y grows downward, so angle 90° points down.
    g = 9.0                      # px per grid unit
    ox, oy = C - 12 * g, C - 12 * g
    P = lambda x, y: pymupdf.Point(ox + x * g, oy + y * g)  # noqa: E731

    def corner(cx, cy, a0, a1, r=2.0, steps=10):
        return [P(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
                  cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / steps))) for i in range(steps + 1)]

    body = (
        [P(14, 3.5), P(18.5, 8)]               # the folded corner's diagonal
        + corner(16.5, 18.5, 0, 90)            # bottom right
        + corner(7.5, 18.5, 90, 180)           # bottom left
        + corner(7.5, 5.5, 180, 270)           # top left
        + [P(14, 3.5)]
    )
    shape.draw_polyline(body)
    shape.draw_polyline([P(14, 3.5), P(14, 8), P(18.5, 8)])
    shape.draw_line(P(9, 13), P(15, 13))
    shape.draw_line(P(9, 16.5), P(13, 16.5))
    shape.finish(color=CREAM, width=1.9 * g, lineCap=1, lineJoin=1, closePath=False)
    shape.commit()

    pixmap = page.get_pixmap(clip=page.rect, alpha=True, dpi=72)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(OUT)
    print(f"wrote {OUT} ({pixmap.width}x{pixmap.height})")


if __name__ == "__main__":
    main()
