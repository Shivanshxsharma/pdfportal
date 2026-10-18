"""Image tools: PDF → JPG and images → PDF."""

import pymupdf

from ..files import Staged, check_inputs, open_pdf, output_folder, plural, unique_path
from .pages import add_image_page

FORMATS = {"jpg": "jpg", "png": "png"}


def pdf_to_images(job):
    """Every page as a picture. A one-page PDF becomes one image next to
    it; longer ones get a folder."""
    files = check_inputs(job.inputs)
    fmt = FORMATS.get(str(job.option("format", "jpg")).lower(), "jpg")
    try:
        dpi = max(72, min(600, int(job.option("dpi", 150))))
    except (TypeError, ValueError):
        dpi = 150
    r = job.reporter
    outputs, images = [], 0
    for i, path in enumerate(files):
        doc = open_pdf(path, job.input_password)
        try:
            total = doc.page_count
            target = output_folder(path, job.fallback_dir)

            def render(page, destination):
                pixmap = page.get_pixmap(dpi=dpi, alpha=False)
                pixmap.save(destination, output=fmt, jpg_quality=88)

            if total == 1:
                r.step(i / len(files), "Rendering the page", force=True)
                with Staged(unique_path(target, f"{path.stem}.{fmt}"), r) as staged:
                    render(doc[0], staged.temp)
                    outputs.append(staged.commit())
            else:
                digits = len(str(total))
                with Staged(unique_path(target, f"{path.stem} (images)"), r, is_dir=True) as staged:
                    for k, page in enumerate(doc):
                        r.step((i + k / total) / len(files), f"Page {k + 1} of {total}")
                        render(page, staged.temp / f"{path.stem} - page {k + 1:0{digits}d}.{fmt}")
                    outputs.append(staged.commit())
            images += total
        finally:
            doc.close()
    r.step(1, "Done", force=True)
    folder = outputs[0] if outputs and outputs[0].is_dir() else None
    r.done(outputs, f"{plural(images, fmt.upper() + ' image')} at {dpi} dpi", folder=folder)


def images_to_pdf(job):
    """All dropped images, in order, as the pages of one PDF."""
    files = check_inputs(job.inputs, allowed=("image",))
    r = job.reporter
    out = pymupdf.open()
    try:
        for i, path in enumerate(files):
            r.step(i / len(files) * 0.9, f"Adding {path.name}")
            add_image_page(out, path)
        r.step(0.92, "Saving", force=True)
        target = output_folder(files[0], job.fallback_dir)
        with Staged(unique_path(target, f"{files[0].stem}.pdf"), r) as staged:
            out.save(staged.temp, garbage=3, deflate=True)
            result = staged.commit()
        pages = out.page_count
    finally:
        out.close()
    r.done([result], f"{plural(len(files), 'image')} → 1 PDF · {plural(pages, 'page')}")
