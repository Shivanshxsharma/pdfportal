"""Entry point: `python -m portal_engine` (or pdfportal-engine.exe).

    pdfportal-engine            read one job from stdin, run it (what the app does)
    pdfportal-engine --tools    print the tool ids, one per line
    pdfportal-engine --version
"""

import json
import sys
import traceback

import pymupdf

from . import __version__
from .job import Job
from .protocol import JobError, Reporter, use_stdout
from .tools import REGISTRY


def main(argv) -> int:
    if "--version" in argv:
        print(f"pdfportal-engine {__version__} (PyMuPDF {pymupdf.VersionBind})")
        return 0
    if "--tools" in argv:
        print("\n".join(REGISTRY))
        return 0

    # stdout belongs to the protocol. Anything a library prints by accident
    # goes to stderr instead, where it can't be mistaken for an event.
    use_stdout(sys.stdout)
    sys.stdout = sys.stderr
    pymupdf.TOOLS.mupdf_display_errors(False)

    reporter = Reporter()
    try:
        # Read raw bytes and decode as UTF-8 ourselves: Windows would
        # otherwise guess the console code page and garble non-English paths.
        request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        tool = REGISTRY.get(request.get("tool"))
        if tool is None:
            raise JobError("bad_input", f"Unknown tool “{request.get('tool')}”.")
        job = Job(
            inputs=list(request.get("inputs") or []),
            options=dict(request.get("options") or {}),
            fallback_dir=str(request.get("fallback_dir") or ""),
            reporter=reporter,
        )
        tool(job)
        return 0
    except JobError as err:
        reporter.error(err.code, err.message)
        return 1
    except Exception as err:  # a bug or a truly broken file: report, don't hang
        traceback.print_exc()
        reporter.error("internal", f"Something went wrong: {err}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
