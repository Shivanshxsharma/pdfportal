"""End-to-end tests for every tool.

Each test runs the real engine the way the app does (a new process, the job
as JSON on stdin, events read back from stdout), on PDFs and images made on
the fly in a temporary folder. Run with:

    .venv\\Scripts\\python -m pytest -q

To test the frozen engine that ships in the installer instead, point
PORTAL_ENGINE_EXE at it. It then runs with a bare environment (no Python on
PATH, no PYTHON* variables), the way it would on a computer without Python:

    set PORTAL_ENGINE_EXE=dist\\pdfportal-engine\\pdfportal-engine.exe
    .venv\\Scripts\\python -m pytest -q
"""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1]
FROZEN = os.environ.get("PORTAL_ENGINE_EXE")


def engine_command():
    """How to start the engine: the frozen exe (with a bare environment),
    or this Python running the package."""
    if FROZEN:
        windows = os.environ.get("SystemRoot", r"C:\Windows")
        bare = {
            "SystemRoot": windows,
            "PATH": os.path.join(windows, "System32"),
            "TEMP": os.environ.get("TEMP", ""),
            "TMP": os.environ.get("TMP", ""),
        }
        return [str(Path(FROZEN).resolve())], bare
    return [sys.executable, "-m", "portal_engine"], None


# ── Helpers ──────────────────────────────────────────────────────────────────

def run_engine(tool, inputs, options=None, fallback_dir=""):
    request = {"tool": tool, "inputs": [str(p) for p in inputs], "options": options or {}, "fallback_dir": str(fallback_dir)}
    command, env = engine_command()
    proc = subprocess.run(
        command,
        input=json.dumps(request).encode("utf-8"),
        capture_output=True,
        cwd=ENGINE_DIR,
        env=env,
        timeout=120,
    )
    events = [json.loads(line) for line in proc.stdout.decode("ascii").splitlines() if line.strip()]
    assert events, f"no events; stderr:\n{proc.stderr.decode(errors='replace')}"
    final = events[-1]
    assert final["event"] in ("done", "error"), events
    return final, events


def done(tool, inputs, options=None):
    final, events = run_engine(tool, inputs, options)
    assert final["event"] == "done", final
    assert all(0 <= e["fraction"] <= 1 for e in events if e["event"] == "progress")
    return final


def text_pdf(path: Path, pages=3, rotation=0, size=(595, 842)) -> Path:
    doc = pymupdf.open()
    for n in range(pages):
        page = doc.new_page(width=size[0], height=size[1])
        page.insert_text((72, 100), f"Hello from page {n + 1}", fontsize=24)
        if rotation:
            page.set_rotation(rotation)
    doc.save(path)
    doc.close()
    return path


def blank_pdf(path: Path, rotations) -> Path:
    doc = pymupdf.open()
    for rotation in rotations:
        page = doc.new_page(width=595, height=842)
        page.set_rotation(rotation)
    doc.save(path)
    doc.close()
    return path


def noisy_png(path: Path, w=1600, h=1200) -> Path:
    """A photo-like image: smooth gradients plus noise, so JPEG re-encoding
    at a lower resolution really does save space (as with real scans)."""
    rng = random.Random(7)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h), False)
    data = bytearray(w * h * 3)
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 3
            n = rng.randrange(24)
            data[i] = (x * 255 // w + n) % 256
            data[i + 1] = (y * 255 // h + n) % 256
            data[i + 2] = ((x + y) * 128 // (w + h) + n) % 256
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, bytes(data), False)
    pix.save(path)
    return path


def photo_pdf(path: Path, image: Path) -> Path:
    """A one-page PDF with a big image squeezed onto it (~400 dpi), like a
    phone scan."""
    doc = pymupdf.open()
    page = doc.new_page(width=288, height=216)  # 4 × 3 inches
    page.insert_image(page.rect, filename=image)
    doc.save(path)
    doc.close()
    return path


def ink(page, threshold):
    """Coordinates of every pixel darker than `threshold` (0-255) on the
    page as rendered, i.e. as a person sees it, rotation included."""
    pix = page.get_pixmap(dpi=36, colorspace=pymupdf.csGRAY)
    s, w = pix.samples, pix.width
    points = [(i % w, i // w) for i, v in enumerate(s) if v < threshold]
    return points, pix.width, pix.height


@pytest.fixture
def work(tmp_path):
    yield tmp_path
    leftovers = list(tmp_path.rglob(".portal-*"))
    assert not leftovers, f"temporary files left behind: {leftovers}"


# ── Compress ─────────────────────────────────────────────────────────────────

def test_compress_shrinks_an_image_heavy_pdf(work):
    src = photo_pdf(work / "scan.pdf", noisy_png(work / "photo.png"))
    final = done("compress", [src])
    out = Path(final["outputs"][0])
    assert out.name == "scan (compressed).pdf"
    assert out.stat().st_size < src.stat().st_size * 0.6
    assert pymupdf.open(out).page_count == 1
    assert "smaller" in final["summary"]


def test_compress_leaves_an_already_small_pdf_alone(work):
    plain = text_pdf(work / "plain.pdf", pages=1)
    src = work / "notes.pdf"
    with pymupdf.open(plain) as doc:  # save it already fully optimised
        doc.save(src, garbage=4, deflate=True, use_objstms=1)
    final = done("compress", [src], {"level": "less"})
    assert final["outputs"] == []
    assert "already" in final["summary"]


def test_compress_keeps_a_locked_pdf_locked(work):
    src = photo_pdf(work / "scan.pdf", noisy_png(work / "photo.png"))
    locked = Path(done("protect", [src], {"new_password": "s3cret"})["outputs"][0])
    final, _ = run_engine("compress", [locked])
    assert final["code"] == "needs_password"
    out = Path(done("compress", [locked], {"input_password": "s3cret"})["outputs"][0])
    doc = pymupdf.open(out)
    assert doc.needs_pass and doc.authenticate("s3cret")


# ── Merge / split / rotate ───────────────────────────────────────────────────

def test_merge_joins_pdfs_and_images_in_order(work):
    a = text_pdf(work / "a.pdf", pages=2)
    b = text_pdf(work / "b.pdf", pages=3)
    img = noisy_png(work / "c.png", 200, 100)
    out = Path(done("merge", [a, img, b])["outputs"][0])
    assert out.name == "a (merged).pdf"
    doc = pymupdf.open(out)
    assert doc.page_count == 6
    assert "page 2" in doc[1].get_text() and doc[2].get_text().strip() == ""  # the image page
    assert "page 1" in doc[3].get_text()


def test_merge_needs_two_files(work):
    final, _ = run_engine("merge", [text_pdf(work / "a.pdf")])
    assert final["code"] == "bad_input"


def test_split_every_page(work):
    src = text_pdf(work / "report.pdf", pages=12)
    final = done("split", [src])
    folder = Path(final["folder"])
    assert folder.name == "report (split)"
    names = sorted(p.name for p in folder.iterdir())
    assert len(names) == 12 and names[0] == "report - page 01.pdf" and names[-1] == "report - page 12.pdf"


def test_split_ranges(work):
    src = text_pdf(work / "report.pdf", pages=5)
    folder = Path(done("split", [src], {"mode": "ranges", "ranges": "1-2, 4-"})["folder"])
    files = sorted(folder.iterdir())
    assert [p.name for p in files] == ["report - pages 1-2.pdf", "report - pages 4-5.pdf"]
    assert pymupdf.open(files[1]).page_count == 2


@pytest.mark.parametrize("ranges", ["0-2", "3-9", "abc", "5-2", ""])
def test_split_rejects_bad_ranges(work, ranges):
    final, _ = run_engine("split", [text_pdf(work / "r.pdf", pages=4)], {"mode": "ranges", "ranges": ranges})
    assert final["code"] == "bad_input"


def test_split_one_page_has_nothing_to_do(work):
    final, _ = run_engine("split", [text_pdf(work / "one.pdf", pages=1)])
    assert final["code"] == "nothing_to_do"


def test_rotate_and_unique_names(work):
    src = text_pdf(work / "doc.pdf", pages=2)
    first = Path(done("rotate", [src])["outputs"][0])
    second = Path(done("rotate", [src], {"angle": 270})["outputs"][0])
    assert first.name == "doc (rotated).pdf" and second.name == "doc (rotated) 2.pdf"
    assert [p.rotation for p in pymupdf.open(first)] == [90, 90]
    assert [p.rotation for p in pymupdf.open(second)] == [270, 270]


# ── Stamps (rotated pages are the hard case) ─────────────────────────────────

ROTATIONS = [0, 90, 180, 270]


def ink_bitmap(page, threshold=160):
    """The inked area of a page, cropped tight, as rows of 0/1."""
    pix = page.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)
    s, w = pix.samples, pix.width
    points = [(i % w, i // w) for i, v in enumerate(s) if v < threshold]
    x0, x1 = min(p[0] for p in points), max(p[0] for p in points)
    y0, y1 = min(p[1] for p in points), max(p[1] for p in points)
    return [[1 if s[y * w + x] < threshold else 0 for x in range(x0, x1 + 1)] for y in range(y0, y1 + 1)]


def test_page_numbers_sit_bottom_center_and_upright_on_every_rotation(work):
    src = blank_pdf(work / "blank.pdf", ROTATIONS)
    out = Path(done("page_numbers", [src], {"style": "page-n-of-total"})["outputs"][0])
    for number, page in enumerate(pymupdf.open(out), start=1):
        points, w, h = ink(page, 160)
        assert points, f"no number on a page rotated {page.rotation}"
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        assert min(ys) > h * 0.85, f"rotation {page.rotation}: number not at the bottom"
        assert abs((min(xs) + max(xs)) / 2 - w / 2) < w * 0.05, f"rotation {page.rotation}: not centred"
        # Upright, not sideways or upside down: the label must look exactly
        # like the same label stamped on an unrotated page of the same shape.
        ref_path = work / f"ref{number}.pdf"
        with pymupdf.open() as ref_doc:
            ref_doc.new_page(width=page.rect.width, height=page.rect.height)
            ref_doc.save(ref_path)
        ref_out = Path(done("page_numbers", [ref_path], {"style": "page-n-of-total", "start": number})["outputs"][0])
        with pymupdf.open(ref_out) as ref:
            want = ink_bitmap(ref[0])
        got = ink_bitmap(page)
        # The reference says "Page n of n" (1 page); compare only the
        # "Page n" part on the left, which is identical in both.
        width = min(len(want[0]), len(got[0])) // 2
        assert len(got) == len(want), f"rotation {page.rotation}: number has the wrong height (sideways?)"
        mismatch = sum(a != b for rw, rg in zip(want, got) for a, b in zip(rw[:width], rg[:width]))
        assert mismatch / (len(want) * width) < 0.05, f"rotation {page.rotation}: number isn't upright"


def test_watermark_is_centred_and_diagonal_on_every_rotation(work):
    src = blank_pdf(work / "blank.pdf", ROTATIONS)
    out = Path(done("watermark", [src], {"text": "CONFIDENTIAL"})["outputs"][0])
    for page in pymupdf.open(out):
        points, w, h = ink(page, 250)
        assert len(points) > 50, f"no watermark on a page rotated {page.rotation}"
        mx = sum(p[0] for p in points) / len(points)
        my = sum(p[1] for p in points) / len(points)
        assert abs(mx - w / 2) < w * 0.08 and abs(my - h / 2) < h * 0.08
        # Screen y grows downward, so bottom-left → top-right means x and y
        # move in opposite directions: negative covariance.
        cov = sum((x - mx) * (y - my) for x, y in points) / len(points)
        assert cov < 0, f"rotation {page.rotation}: watermark runs the wrong way"


def test_watermark_needs_text(work):
    final, _ = run_engine("watermark", [text_pdf(work / "a.pdf")], {"text": "  "})
    assert final["code"] == "needs_input"


# ── Protect / unlock ─────────────────────────────────────────────────────────

def test_protect_then_unlock(work):
    src = text_pdf(work / "secret.pdf")
    locked = Path(done("protect", [src], {"new_password": "pässwörd"})["outputs"][0])
    doc = pymupdf.open(locked)
    assert doc.needs_pass and not doc.authenticate("nope") and doc.authenticate("pässwörd")
    doc.close()

    assert run_engine("unlock", [locked])[0]["code"] == "needs_password"
    assert run_engine("unlock", [locked], {"input_password": "nope"})[0]["code"] == "wrong_password"
    out = Path(done("unlock", [locked], {"input_password": "pässwörd"})["outputs"][0])
    opened = pymupdf.open(out)
    assert not opened.needs_pass and not opened.metadata.get("encryption")
    assert "page 1" in opened[0].get_text()


def test_unlock_removes_owner_only_restrictions_without_a_password(work):
    src = work / "restricted.pdf"
    doc = pymupdf.open(text_pdf(work / "plain.pdf"))
    doc.save(src, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="", permissions=0)
    doc.close()
    out = Path(done("unlock", [src])["outputs"][0])
    assert not pymupdf.open(out).metadata.get("encryption")


def test_unlock_an_unlocked_pdf(work):
    final, _ = run_engine("unlock", [text_pdf(work / "open.pdf")])
    assert final["code"] == "nothing_to_do"


def test_protect_needs_a_password(work):
    final, _ = run_engine("protect", [text_pdf(work / "a.pdf")])
    assert final["code"] == "needs_input"


# ── Images ───────────────────────────────────────────────────────────────────

def test_pdf_to_images(work):
    one = Path(done("pdf_to_images", [text_pdf(work / "one.pdf", pages=1)])["outputs"][0])
    assert one.name == "one.jpg" and one.read_bytes()[:3] == b"\xff\xd8\xff"
    final = done("pdf_to_images", [text_pdf(work / "three.pdf", pages=3)], {"format": "png"})
    folder = Path(final["folder"])
    assert sorted(p.name for p in folder.iterdir()) == [f"three - page {n}.png" for n in (1, 2, 3)]


def test_images_to_pdf(work):
    png = noisy_png(work / "first.png", 300, 200)
    jpg = work / "second.jpg"
    pymupdf.Pixmap(png).save(jpg)
    out = Path(done("images_to_pdf", [png, jpg])["outputs"][0])
    assert out.name == "first.pdf" and pymupdf.open(out).page_count == 2


# ── Paths and errors ─────────────────────────────────────────────────────────

def test_non_english_paths(work):
    folder = work / "हिन्दी दस्तावेज़ 文件"
    folder.mkdir()
    src = text_pdf(folder / "रिपोर्ट.pdf", pages=2)
    out = Path(done("rotate", [src])["outputs"][0])
    assert out == folder / "रिपोर्ट (rotated).pdf" and out.exists()


def test_missing_file(work):
    final, _ = run_engine("compress", [work / "gone.pdf"])
    assert final["code"] == "bad_input" and "gone.pdf" in final["message"]


def test_unknown_tool(work):
    assert run_engine("teleport", [])[0]["code"] == "bad_input"


def test_a_damaged_pdf_is_reported_not_crashed(work):
    broken = work / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7\nthis is not really a pdf")
    final, _ = run_engine("rotate", [broken])
    assert final["event"] == "error"
