"""Where results go and what they're called.

Rule: a result lands next to the file you dropped, named after it
("report.pdf" -> "report (compressed).pdf"), so you find it without looking.
If that folder is read-only (a zip opened in Explorer, a protected folder),
it goes to the fallback folder the app passes in (Downloads).

Results are written to a temporary name first and renamed at the end. A job
that crashes or is cancelled halfway never leaves a broken file that looks
like a finished one.
"""

import os
import shutil
import uuid
from pathlib import Path

import pymupdf

from .protocol import JobError

PDF_SUFFIXES = {".pdf"}
# Images MuPDF can open and turn into PDF pages.
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp", ".jxr", ".jpx", ".pnm", ".psd"}


def kind_of(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        return "pdf"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    return "other"


def check_inputs(paths, allowed=("pdf",), at_least=1) -> list:
    """Turns the request's strings into Paths and refuses anything the tool
    can't read, with a message that names the file."""
    files = [Path(p) for p in paths]
    if len(files) < at_least:
        raise JobError("bad_input", f"This tool needs at least {at_least} files.")
    for f in files:
        if not f.is_file():
            raise JobError("bad_input", f"Can't find “{f.name}”. Was it moved or deleted?")
        if kind_of(f) not in allowed:
            raise JobError("bad_input", f"“{f.name}” isn't a file this tool can use.")
    return files


def _writable(folder: Path) -> bool:
    probe = folder / f".portal-write-test-{uuid.uuid4().hex}"
    try:
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def output_folder(first_input: Path, fallback_dir) -> Path:
    folder = first_input.parent
    if _writable(folder):
        return folder
    fallback = Path(fallback_dir) if fallback_dir else Path.home() / "Downloads"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def unique_path(folder: Path, name: str) -> Path:
    """"report (compressed).pdf", or "report (compressed) 2.pdf" if that's
    taken. Never overwrites anything."""
    candidate = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 2
    while candidate.exists():
        candidate = folder / f"{stem} {n}{suffix}"
        n += 1
    return candidate


class Staged:
    """A result written under a hidden temporary name, published with
    `commit()`. Works for a single file or a whole folder (split, images).

    Use it with `with`: if the tool fails before commit(), the temporary
    file is deleted. (If the app cancels the job it kills this process, so
    the temporary name is also announced to the app, which deletes it.)
    """

    def __init__(self, final: Path, reporter, is_dir: bool = False):
        self.final = final
        self.is_dir = is_dir
        self.temp = final.parent / f".portal-{uuid.uuid4().hex[:10]}.part"
        self._finished = False
        reporter.temp(self.temp)
        if is_dir:
            self.temp.mkdir()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        if not self._finished:
            self.discard()
        return False  # never swallow the error

    def commit(self) -> Path:
        # The final name was free when we started; if something took it in
        # the meantime, pick the next free one rather than overwrite it.
        if self.final.exists():
            self.final = unique_path(self.final.parent, self.final.name)
        os.replace(self.temp, self.final)
        self._finished = True
        return self.final

    def discard(self) -> None:
        self._finished = True
        if self.is_dir:
            shutil.rmtree(self.temp, ignore_errors=True)
        else:
            try:
                self.temp.unlink()
            except FileNotFoundError:
                pass


def open_pdf(path: Path, password: str = "") -> pymupdf.Document:
    """Opens a PDF, unlocking it with `password` if it needs one.

    "needs_password" makes the app ask for the password and run the job
    again with options.password set.
    """
    try:
        doc = pymupdf.open(path)
    except Exception as err:  # MuPDF raises its own error types
        raise JobError("bad_input", f"“{path.name}” looks damaged and couldn't be opened ({err}).") from err
    if not doc.is_pdf:
        doc.close()
        raise JobError("bad_input", f"“{path.name}” isn't a PDF.")
    if doc.needs_pass:
        if not password:
            doc.close()
            raise JobError("needs_password", f"“{path.name}” is locked. Enter its password to continue.")
        if not doc.authenticate(password):
            doc.close()
            raise JobError("wrong_password", "That password didn't work. Try again.")
    return doc


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"
