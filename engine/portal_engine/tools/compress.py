"""Compress: make a PDF smaller.

Most of a PDF's weight is photos and scans, so that's where the savings are:
images printed at more than `dpi_threshold` are scaled down to `dpi_target`
and re-saved as JPEG at `quality`. Then the file itself is tidied up: unused
objects dropped, streams compressed, small objects packed together.

A PDF that's mostly text barely shrinks; that's expected, not a bug. If the
result isn't really smaller, we don't write it at all.
"""

import pymupdf

from ..files import Staged, check_inputs, human_size, open_pdf, output_folder, plural, unique_path
from ..protocol import JobError

LEVELS = {
    # No image changes: only the lossless clean-up.
    "less": None,
    # Matches what most people expect from "compress": screen-sharp, ~print-OK.
    "recommended": {"dpi_threshold": 200, "dpi_target": 150, "quality": 70},
    # Smallest file; images get visibly softer.
    "extreme": {"dpi_threshold": 110, "dpi_target": 96, "quality": 45},
}

# Below this, the "smaller" file isn't worth a second copy on your disk.
MIN_SAVING = 0.02


def run(job):
    files = check_inputs(job.inputs)
    level = job.option("level", "recommended")
    if level not in LEVELS:
        raise JobError("bad_input", f"Unknown compression level “{level}”.")
    settings = LEVELS[level]
    r = job.reporter

    outputs, before_total, after_total, unchanged = [], 0, 0, 0
    share = 1 / len(files)
    for i, path in enumerate(files):
        base = i * share
        prefix = f"{path.name}: " if len(files) > 1 else ""
        r.step(base, f"{prefix}Reading", force=True)
        doc = open_pdf(path, job.input_password)
        try:
            before = path.stat().st_size
            if settings:
                r.step(base + share * 0.1, f"{prefix}Shrinking images", force=True)
                doc.rewrite_images(**settings)
            r.step(base + share * 0.75, f"{prefix}Saving", force=True)
            folder = output_folder(path, job.fallback_dir)
            with Staged(unique_path(folder, f"{path.stem} (compressed).pdf"), r) as staged:
                doc.save(
                    staged.temp,
                    garbage=4,          # drop unused and duplicate objects
                    deflate=True,       # compress every stream that isn't yet
                    deflate_images=True,
                    deflate_fonts=True,
                    use_objstms=1,      # pack small objects into compressed streams
                    encryption=pymupdf.PDF_ENCRYPT_KEEP,  # a locked PDF stays locked
                )
                after = staged.temp.stat().st_size
                if after > before * (1 - MIN_SAVING):
                    staged.discard()
                    unchanged += 1
                    before_total += before
                    after_total += before
                    continue
                outputs.append(staged.commit())
            before_total += before
            after_total += after
        finally:
            doc.close()

    r.step(1, "Done", force=True)
    if not outputs:
        what = "This PDF is" if len(files) == 1 else "These PDFs are"
        r.done([], f"{what} already as small as it gets. Nothing was changed.", before=before_total, after=before_total)
        return

    saved = 1 - after_total / before_total if before_total else 0
    summary = f"{human_size(before_total)} → {human_size(after_total)} · {saved:.0%} smaller"
    if unchanged:
        summary += f" · {plural(unchanged, 'file')} already optimized"
    r.done(outputs, summary, before=before_total, after=after_total)
