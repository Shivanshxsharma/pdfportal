"""Converts PNGs to the 24-bit BMPs the installer (NSIS) needs.

    engine\\.venv\\Scripts\\python scripts\\png_to_bmp.py in.png out.bmp [in2.png out2.bmp ...]

NSIS only reads BMP, without transparency, so any transparent pixel is laid
over the night colour first.
"""

import struct
import sys

import pymupdf

NIGHT = (0x19, 0x00, 0x19)


def to_bmp(src, dst):
    pix = pymupdf.Pixmap(src)
    if pix.n not in (3, 4):  # e.g. a grey PNG: make it RGB first
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    w, h, n, s = pix.width, pix.height, pix.n, pix.samples
    row_size = (w * 3 + 3) & ~3  # BMP rows are padded to 4 bytes
    rows = []
    for y in range(h - 1, -1, -1):  # BMP stores the bottom row first
        row = bytearray()
        for x in range(w):
            i = (y * w + x) * n
            r, g, b = s[i], s[i + 1], s[i + 2]
            if n == 4:  # blend over night by the pixel's alpha
                a = s[i + 3] / 255
                r, g, b = (round(c * a + bg * (1 - a)) for c, bg in zip((r, g, b), NIGHT))
            row += bytes((b, g, r))  # BMP is BGR
        row += b"\0" * (row_size - len(row))
        rows.append(bytes(row))
    pixels = b"".join(rows)
    header = struct.pack("<2sIHHI", b"BM", 54 + len(pixels), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
    with open(dst, "wb") as f:
        f.write(header + info + pixels)
    print(f"{dst}: {w}x{h}, 24-bit")


if __name__ == "__main__":
    args = sys.argv[1:]
    for src, dst in zip(args[::2], args[1::2]):
        to_bmp(src, dst)
