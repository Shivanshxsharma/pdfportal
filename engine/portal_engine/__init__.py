"""PDFportal's PDF engine.

The desktop app (Rust, ../src-tauri) starts this engine once per job:

    python -m portal_engine            (in development)
    pdfportal-engine.exe                  (in the installed app, built by PyInstaller)

It reads ONE job request as JSON from stdin, does the work, and writes one
JSON event per line to stdout (progress, then done or error). See
protocol.py for the exact format.

Why a separate process instead of doing PDF work in Rust: Python has the best
free PDF libraries (PyMuPDF today; OCRmyPDF, pdf2docx and others later), and
a crash in a broken PDF can only take down this job, never the app.
"""

__version__ = "0.1.0"
