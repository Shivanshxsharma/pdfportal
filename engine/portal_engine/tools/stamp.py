"""Stamps: page numbers and watermarks.

The tricky part is rotated pages. A PDF page can say "show me turned 90°"
(/Rotate), but drawing commands still use the page's UNturned coordinates.
So we work out where the text should appear on the page as you SEE it,
convert that point with `page.derotation_matrix`, and turn the text back by
the page's rotation, so it always comes out upright (or at the angle we
want) on screen.
"""

import pymupdf

from ..files import Staged, check_inputs, open_pdf, output_folder, plural, unique_path
from ..protocol import JobError

FONT = pymupdf.Font("helv")  # built into every PDF reader, nothing to embed
GRAY = (0.25, 0.25, 0.25)


def draw_text(page, center, text, fontsize, angle=0.0, color=GRAY, opacity=1.0):
    """Draws `text` centred on `center` (a point on the page as you see it),
    turned `angle` degrees (positive = clockwise on screen).

    `morph` turns the text counter-clockwise by its matrix's angle, while
    the page's /Rotate turns everything clockwise by page.rotation. So the
    text ends up at (page.rotation - matrix angle) clockwise; solving for the
    angle we want gives Matrix(page.rotation - angle). The engine tests check
    this on pages turned 0, 90, 180 and 270 degrees.
    """
    pivot = pymupdf.Point(center) * page.derotation_matrix
    width = FONT.text_length(text, fontsize)
    # insert_text wants the start of the baseline; 0.35 × size below the
    # middle puts capital letters roughly centred on the pivot.
    start = pymupdf.Point(pivot.x - width / 2, pivot.y + fontsize * 0.35)
    page.insert_text(
        start,
        text,
        fontsize=fontsize,
        fontname="helv",
        color=color,
        fill_opacity=opacity,
        morph=(pivot, pymupdf.Matrix(page.rotation - angle)),
    )


def _stamp_each_page(job, suffix: str, stamp, summary):
    """Shared loop: open each PDF, call stamp(page, number, total) on every
    page, save as "<name> (<suffix>).pdf"."""
    files = check_inputs(job.inputs)
    r = job.reporter
    outputs, pages = [], 0
    for i, path in enumerate(files):
        doc = open_pdf(path, job.input_password)
        try:
            total = doc.page_count
            for k, page in enumerate(doc):
                r.step((i + k / total * 0.85) / len(files), f"Page {k + 1} of {total}")
                stamp(page, k + 1, total)
            pages += total
            target = output_folder(path, job.fallback_dir)
            with Staged(unique_path(target, f"{path.stem} ({suffix}).pdf"), r) as staged:
                doc.save(staged.temp, garbage=1, deflate=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
                outputs.append(staged.commit())
        finally:
            doc.close()
    r.step(1, "Done", force=True)
    r.done(outputs, summary(pages))


# ── Page numbers ─────────────────────────────────────────────────────────────

POSITIONS = {
    "bottom-center", "bottom-left", "bottom-right",
    "top-center", "top-left", "top-right",
}
STYLES = {
    "n": "{n}",
    "page-n": "Page {n}",
    "n-of-total": "{n} / {total}",
    "page-n-of-total": "Page {n} of {total}",
}


def page_numbers(job):
    position = job.option("position", "bottom-center")
    style = job.option("style", "n")
    if position not in POSITIONS:
        raise JobError("bad_input", f"Unknown position “{position}”.")
    if style not in STYLES:
        raise JobError("bad_input", f"Unknown number style “{style}”.")
    try:
        first = int(job.option("start", 1))
    except (TypeError, ValueError):
        raise JobError("bad_input", "The first page number must be a whole number.")
    template = STYLES[style]
    vertical, horizontal = position.split("-")

    def stamp(page, number, total):
        box = page.rect  # the page as you see it
        short = min(box.width, box.height)
        size = max(8.0, min(12.0, short * 0.018))
        margin = max(18.0, short * 0.045)
        label = template.format(n=number + first - 1, total=total + first - 1)
        width = FONT.text_length(label, size)
        x = {
            "left": margin + width / 2,
            "center": box.width / 2,
            "right": box.width - margin - width / 2,
        }[horizontal]
        y = margin if vertical == "top" else box.height - margin
        draw_text(page, (box.x0 + x, box.y0 + y), label, size)

    _stamp_each_page(job, "numbered", stamp, lambda n: f"Numbered {plural(n, 'page')}")


# ── Watermark ────────────────────────────────────────────────────────────────

def watermark(job):
    """Big, faint, diagonal text across the middle of every page."""
    text = str(job.option("text", "")).strip()
    if not text:
        raise JobError("needs_input", "Type the watermark text.")
    if len(text) > 80:
        raise JobError("bad_input", "Keep the watermark under 80 characters.")
    try:
        opacity = float(job.option("opacity", 0.18))
    except (TypeError, ValueError):
        opacity = 0.18
    opacity = max(0.05, min(1.0, opacity))
    unit_width = FONT.text_length(text, 1)

    def stamp(page, _number, _total):
        box = page.rect
        diagonal = (box.width ** 2 + box.height ** 2) ** 0.5
        # Fill ~70% of the diagonal, but don't let a short word like "DRAFT"
        # become taller than a fifth of the page.
        size = min(diagonal * 0.7 / unit_width, min(box.width, box.height) * 0.2)
        # Along the bottom-left → top-right diagonal, like a rubber stamp.
        draw_text(page, (box.x0 + box.width / 2, box.y0 + box.height / 2), text, size,
                  angle=-45.0, color=(0.55, 0.55, 0.6), opacity=opacity)

    _stamp_each_page(job, "watermarked", stamp, lambda n: f"Watermarked {plural(n, 'page')}")
