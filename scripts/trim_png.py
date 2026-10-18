"""Crops the empty, transparent border off PNGs (keeping a little room for
the shadow), so a card fills its picture in the README.

    engine\\.venv\\Scripts\\python scripts\\trim_png.py docs\\screenshots\\done.png [...]
"""

import sys

import pymupdf

PAD = 18        # px kept around the visible part (the shadow's soft edge)
THRESHOLD = 10  # alpha below this counts as empty (the shadow's faintest tail)


def visible_box(pix):
    """The smallest rectangle holding every pixel at least THRESHOLD opaque."""
    stride, alpha_at = pix.stride, pix.n - 1
    samples = pix.samples
    top = bottom = None
    left, right = pix.width, -1
    cut = bytes(range(THRESHOLD))  # the alpha values that count as empty
    for y in range(pix.height):
        row = samples[y * stride + alpha_at:(y + 1) * stride:pix.n]
        first = len(row) - len(row.lstrip(cut))
        if first == len(row):
            continue
        last = len(row.rstrip(cut)) - 1
        top = y if top is None else top
        bottom = y
        left, right = min(left, first), max(right, last)
    if top is None:
        return None
    return pymupdf.IRect(
        max(0, left - PAD), max(0, top - PAD), min(pix.width, right + 1 + PAD), min(pix.height, bottom + 1 + PAD)
    )


def trim(path):
    pix = pymupdf.Pixmap(path)
    if not pix.alpha:
        print(f"{path}: no transparency, left as is")
        return
    box = visible_box(pix)
    if box is None or box == pix.irect:
        print(f"{path}: nothing to trim")
        return
    out = pymupdf.Pixmap(pix.colorspace, box, True)
    out.copy(pix, box)
    out.set_origin(0, 0)
    out.save(path)
    print(f"{path}: {pix.width}x{pix.height} -> {out.width}x{out.height}")


if __name__ == "__main__":
    for name in sys.argv[1:]:
        trim(name)
