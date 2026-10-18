"""Page tools: merge, split, rotate."""

import re

import pymupdf

from ..files import Staged, check_inputs, kind_of, open_pdf, output_folder, plural, unique_path
from ..protocol import JobError

# Results that are copies of whole documents get this clean-up when saved.
SAVE = {"garbage": 3, "deflate": True}


def add_image_page(out: pymupdf.Document, path) -> None:
    """Appends an image as a page the size of the image (a multi-frame GIF
    or TIFF becomes several pages)."""
    try:
        with pymupdf.open(path) as image:
            pdf_bytes = image.convert_to_pdf()
    except Exception as err:
        raise JobError("bad_input", f"“{path.name}” couldn't be read as an image ({err}).") from err
    with pymupdf.open("pdf", pdf_bytes) as page_doc:
        out.insert_pdf(page_doc)


# ── Merge ────────────────────────────────────────────────────────────────────

def merge(job):
    """Joins files into one PDF, in the order they were dropped. Images are
    welcome too: each becomes a page."""
    files = check_inputs(job.inputs, allowed=("pdf", "image"), at_least=2)
    r = job.reporter
    out = pymupdf.open()
    try:
        for i, path in enumerate(files):
            r.step(i / len(files) * 0.85, f"Adding {path.name}")
            if kind_of(path) == "pdf":
                src = open_pdf(path, job.input_password)
                try:
                    out.insert_pdf(src)
                finally:
                    src.close()
            else:
                add_image_page(out, path)
        r.step(0.9, "Saving", force=True)
        folder = output_folder(files[0], job.fallback_dir)
        with Staged(unique_path(folder, f"{files[0].stem} (merged).pdf"), r) as staged:
            out.save(staged.temp, **SAVE)
            result = staged.commit()
        pages = out.page_count
    finally:
        out.close()
    r.done([result], f"{plural(len(files), 'file')} → 1 PDF · {plural(pages, 'page')}")


# ── Split ────────────────────────────────────────────────────────────────────

def parse_ranges(text: str, page_count: int) -> list:
    """"1-3, 5, 8-" → [(1, 3), (5, 5), (8, page_count)]. Page numbers are
    1-based like everywhere a person sees them. "-4" means 1-4."""
    groups = []
    for part in re.split(r"[,;\s]+", text.strip()):
        if not part:
            continue
        match = re.fullmatch(r"(\d*)\s*-\s*(\d*)|(\d+)", part)
        if not match:
            raise JobError("bad_input", f"“{part}” isn't a page range. Use something like 1-3, 5, 8-.")
        if match.group(3):
            first = last = int(match.group(3))
        else:
            first = int(match.group(1) or 1)
            last = int(match.group(2) or page_count)
        if first < 1 or last > page_count or first > last:
            raise JobError("bad_input", f"“{part}” is outside this PDF's {plural(page_count, 'page')}.")
        groups.append((first, last))
    if not groups:
        raise JobError("bad_input", "Type the pages to keep together, like 1-3, 5, 8-.")
    return groups


def split(job):
    """Every page as its own PDF (default), or custom ranges like "1-3, 4-".
    The parts go into a new folder next to the original."""
    files = check_inputs(job.inputs)
    mode = job.option("mode", "pages")
    r = job.reporter
    folders, total_parts = [], 0
    for i, path in enumerate(files):
        doc = open_pdf(path, job.input_password)
        try:
            n = doc.page_count
            if mode == "ranges":
                groups = parse_ranges(str(job.option("ranges", "")), n)
            else:
                if n < 2:
                    raise JobError("nothing_to_do", f"“{path.name}” has only one page, so there's nothing to split.")
                groups = [(p, p) for p in range(1, n + 1)]
            digits = len(str(n))  # "page 07" sorts correctly next to "page 12"
            target = output_folder(path, job.fallback_dir)
            with Staged(unique_path(target, f"{path.stem} (split)"), r, is_dir=True) as staged:
                for k, (first, last) in enumerate(groups):
                    r.step((i + k / len(groups)) / len(files), f"Part {k + 1} of {len(groups)}")
                    if first == last:
                        name = f"{path.stem} - page {first:0{digits}d}.pdf"
                    else:
                        name = f"{path.stem} - pages {first:0{digits}d}-{last:0{digits}d}.pdf"
                    with pymupdf.open() as part:
                        part.insert_pdf(doc, from_page=first - 1, to_page=last - 1)
                        part.save(staged.temp / name, **SAVE)
                folders.append(staged.commit())
            total_parts += len(groups)
        finally:
            doc.close()
    r.step(1, "Done", force=True)
    where = f"in “{folders[0].name}”" if len(folders) == 1 else f"in {len(folders)} folders"
    r.done(folders, f"{plural(total_parts, 'PDF')} {where}", folder=folders[0])


# ── Rotate ───────────────────────────────────────────────────────────────────

def rotate(job):
    """Turns every page clockwise by `angle` (90, 180 or 270)."""
    files = check_inputs(job.inputs)
    try:
        angle = int(job.option("angle", 90))
    except (TypeError, ValueError):
        angle = -1
    if angle not in (90, 180, 270):
        raise JobError("bad_input", "Pages can be turned by 90, 180 or 270 degrees.")
    r = job.reporter
    outputs, pages = [], 0
    for i, path in enumerate(files):
        doc = open_pdf(path, job.input_password)
        try:
            for k, page in enumerate(doc):
                r.step((i + k / doc.page_count * 0.8) / len(files), f"Page {k + 1} of {doc.page_count}")
                page.set_rotation((page.rotation + angle) % 360)
            pages += doc.page_count
            target = output_folder(path, job.fallback_dir)
            with Staged(unique_path(target, f"{path.stem} (rotated).pdf"), r) as staged:
                doc.save(staged.temp, garbage=1, deflate=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
                outputs.append(staged.commit())
        finally:
            doc.close()
    r.step(1, "Done", force=True)
    r.done(outputs, f"{plural(pages, 'page')} turned {angle}° clockwise")
