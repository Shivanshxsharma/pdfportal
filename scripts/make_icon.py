"""Draws PDFportal's app icon: a ring of eight tool slots around a disk, one
slot lit, on a dark rounded tile. Same shapes as the portal itself.

    engine\\.venv\\Scripts\\python scripts\\make_icon.py
    npx tauri icon src-tauri\\icons\\icon-source.png

The first command writes the 1024 px source; the second makes every size
Windows needs (icon.ico, 32x32.png, …) from it.
"""

import math
from pathlib import Path

import pymupdf

def hex_rgb(value):
    """"#4299cb" -> (0.26, 0.6, 0.8), the 0-1 colours PyMuPDF wants."""
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


SIZE = 1024
# The ocean palette (portal.css).
TILE = hex_rgb("#001a2a")    # abyss
SLOT = hex_rgb("#013c73")    # deep
ACCENT = hex_rgb("#d2ecff")  # foam: the lit slot
RIM = hex_rgb("#4299cb")     # sea
DISK = hex_rgb("#001a2a")
OUT = Path(__file__).resolve().parents[1] / "src-tauri" / "icons" / "icon-source.png"


def ring_slot(shape, cx, cy, r_in, r_out, start_deg, end_deg, steps=40):
    points = []
    for i in range(steps + 1):
        a = math.radians(start_deg + (end_deg - start_deg) * i / steps)
        points.append(pymupdf.Point(cx + r_out * math.cos(a), cy + r_out * math.sin(a)))
    for i in range(steps, -1, -1):
        a = math.radians(start_deg + (end_deg - start_deg) * i / steps)
        points.append(pymupdf.Point(cx + r_in * math.cos(a), cy + r_in * math.sin(a)))
    shape.draw_polyline(points + [points[0]])


def main():
    doc = pymupdf.open()
    page = doc.new_page(width=SIZE, height=SIZE)
    shape = page.new_shape()

    # The tile: Windows shows icons on any background, so it carries its own.
    shape.draw_rect(pymupdf.Rect(40, 40, SIZE - 40, SIZE - 40), radius=0.22)
    shape.finish(fill=TILE, color=None)

    cx = cy = SIZE / 2
    slots, gap = 8, 7  # degrees between slots
    for k in range(slots):
        start = -90 - 180 / slots + k * 360 / slots + gap / 2
        ring_slot(shape, cx, cy, 250, 400, start, start + 360 / slots - gap)
        # The slot at the top right is "the one you're hovering".
        shape.finish(fill=ACCENT if k == 1 else SLOT, color=None, closePath=True)

    shape.draw_circle(pymupdf.Point(cx, cy), 205)
    shape.finish(fill=DISK, color=RIM, width=12)
    shape.draw_circle(pymupdf.Point(cx, cy), 64)
    shape.finish(fill=ACCENT, color=None)
    shape.commit()

    pixmap = page.get_pixmap(clip=page.rect, alpha=True, dpi=72)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(OUT)
    print(f"wrote {OUT} ({pixmap.width}×{pixmap.height})")


if __name__ == "__main__":
    main()
