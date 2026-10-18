"""Protect (add a password) and Unlock (remove it).

PDF passwords come in two kinds:
  • a user (open) password: you can't even see the pages without it;
  • an owner password: the pages open, but printing/copying is "restricted".
Protect sets both to the password you choose, with AES-256 (the strongest
PDF encryption). Unlock removes both; an owner-only lock needs no password.
"""

import pymupdf

from ..files import Staged, check_inputs, open_pdf, output_folder, unique_path
from ..protocol import JobError


def protect(job):
    password = str(job.options.get("new_password") or "")
    if not password:
        raise JobError("needs_input", "Choose a password.")
    files = check_inputs(job.inputs)
    r = job.reporter
    outputs = []
    for i, path in enumerate(files):
        r.step(i / len(files), f"Locking {path.name}", force=True)
        doc = open_pdf(path, job.input_password)
        try:
            target = output_folder(path, job.fallback_dir)
            with Staged(unique_path(target, f"{path.stem} (protected).pdf"), r) as staged:
                doc.save(
                    staged.temp,
                    garbage=1,
                    deflate=True,
                    encryption=pymupdf.PDF_ENCRYPT_AES_256,
                    user_pw=password,
                    owner_pw=password,
                    permissions=-1,  # once opened with the password, everything is allowed
                )
                outputs.append(staged.commit())
        finally:
            doc.close()
    r.step(1, "Done", force=True)
    r.done(outputs, "Locked with AES-256. It now asks for the password when it opens.")


def unlock(job):
    files = check_inputs(job.inputs)
    r = job.reporter
    outputs = []
    for i, path in enumerate(files):
        r.step(i / len(files), f"Unlocking {path.name}", force=True)
        doc = open_pdf(path, job.input_password)
        try:
            # metadata["encryption"] describes the lock, e.g. "Standard V5 R6
            # 256-bit AES"; None means there's no lock of any kind.
            if not (doc.metadata or {}).get("encryption"):
                raise JobError("nothing_to_do", f"“{path.name}” isn't locked, so there's nothing to remove.")
            target = output_folder(path, job.fallback_dir)
            with Staged(unique_path(target, f"{path.stem} (unlocked).pdf"), r) as staged:
                doc.save(staged.temp, garbage=1, deflate=True, encryption=pymupdf.PDF_ENCRYPT_NONE)
                outputs.append(staged.commit())
        finally:
            doc.close()
    r.step(1, "Done", force=True)
    r.done(outputs, "Password and restrictions removed.")
