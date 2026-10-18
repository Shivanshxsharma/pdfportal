"""Every tool the engine can run, by id.

The ids must match the ones in the app's tool list (src/js/tools.js), which
also holds what the UI needs: names, icons, which files each tool accepts.
"""

from . import compress, images, pages, security, stamp

REGISTRY = {
    "compress": compress.run,
    "merge": pages.merge,
    "split": pages.split,
    "rotate": pages.rotate,
    "page_numbers": stamp.page_numbers,
    "watermark": stamp.watermark,
    "protect": security.protect,
    "unlock": security.unlock,
    "pdf_to_images": images.pdf_to_images,
    "images_to_pdf": images.images_to_pdf,
}
