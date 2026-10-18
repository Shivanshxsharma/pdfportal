"""How the engine talks to the app.

Request (stdin, one JSON object):

    {
      "tool": "compress",                 # an id from tools.REGISTRY
      "inputs": ["C:\\docs\\report.pdf"],  # absolute paths, in drop order
      "options": {"level": "recommended"}, # tool-specific, all optional
      "fallback_dir": "C:\\Users\\me\\Downloads"
    }

Events (stdout, one JSON object per line, flushed immediately so the app's
progress bar moves in real time):

    {"event": "progress", "fraction": 0.4, "message": "Page 4 of 10"}
    {"event": "temp", "path": "..."}      # delete this if the job is cancelled
    {"event": "done", "outputs": [...], "folder": "...", "summary": "..."}
    {"event": "error", "code": "needs_password", "message": "..."}

JSON is written with ensure_ascii=True, so file names in any language arrive
intact no matter what code page the Windows console uses.
"""

import json
import sys
import time


class JobError(Exception):
    """A problem the user can understand and maybe fix (wrong password, a
    damaged file, nothing to do). `code` lets the app react, e.g. by showing
    a password field for "needs_password"."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_out = sys.stdout


def use_stdout(stream) -> None:
    """Keeps a private handle to the real stdout. __main__ then points
    sys.stdout at stderr, so a stray print() in a library can never be
    mistaken for an event."""
    global _out
    _out = stream


def _emit(payload: dict) -> None:
    _out.write(json.dumps(payload, ensure_ascii=True) + "\n")
    _out.flush()


class Reporter:
    """Progress for one job. Tools call `step()` as often as they like; it
    only writes when the bar would visibly move, so a 2,000-page PDF doesn't
    flood the app with 2,000 messages."""

    MIN_INTERVAL = 0.08  # seconds between progress events

    def __init__(self):
        self._last_time = 0.0
        self._last_fraction = -1.0

    def step(self, fraction: float, message: str = "", force: bool = False) -> None:
        fraction = max(0.0, min(1.0, fraction))
        now = time.monotonic()
        if not force and now - self._last_time < self.MIN_INTERVAL and fraction - self._last_fraction < 0.05:
            return
        self._last_time = now
        self._last_fraction = fraction
        _emit({"event": "progress", "fraction": round(fraction, 4), "message": message})

    def temp(self, path) -> None:
        _emit({"event": "temp", "path": str(path)})

    def done(self, outputs, summary: str, folder=None, **details) -> None:
        payload = {"event": "done", "outputs": [str(p) for p in outputs], "summary": summary}
        if folder is not None:
            payload["folder"] = str(folder)
        if details:
            payload["details"] = details
        _emit(payload)

    def error(self, code: str, message: str) -> None:
        _emit({"event": "error", "code": code, "message": message})
