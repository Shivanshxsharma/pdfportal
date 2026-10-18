# PDFportal

**Drag. Shake. Drop.** Free PDF tools that open right under your cursor.

<p align="center">
  <img src="docs/screenshots/ring.png" width="420" alt="The PDFportal ring: eight tools around a disk, Compress lit">
</p>

PDFportal is a small Windows app that puts PDF tools one gesture away. Drag any
PDF or image, give it a quick shake, and a ring of tools opens under your
cursor. Drop the file on a tool: the ring turns into a small card that shows
the progress, then hands you the result.

- **Completely offline.** Your files never leave your computer. No uploads, no accounts.
- **Free and open source** (AGPL-3.0). No ads, no limits, no watermarks on your results.
- **Nothing is ever overwritten.** Results land next to the original:
  `report.pdf` → `report (compressed).pdf`.

<p align="center">
  <img src="docs/screenshots/done.png" width="270" alt="A finished Compress card: 74% smaller">
  <img src="docs/screenshots/form.png" width="270" alt="The Protect card asking for a password">
  <img src="docs/screenshots/hint.png" width="270" alt="The welcome card: Drag. Shake. Drop.">
</p>

## Tools

| Tool | What it does |
|---|---|
| **Compress** | Makes a PDF smaller to email or upload (shrinks oversized images, tidies the file) |
| **Merge** | Joins PDFs, and images, into one PDF, in the order you dragged them |
| **Split** | One PDF per page, or your own ranges like `1-3, 5, 8-` |
| **Rotate** | Turns every page 90° clockwise |
| **To JPG** | Saves every page as a picture |
| **Numbers** | Numbers every page |
| **Watermark** | Stamps faint diagonal text across every page |
| **Protect** | Locks a PDF with a password (AES-256) |
| **Unlock** | Removes a PDF's password or its restrictions |
| **To PDF** | Puts images into one PDF |

The ring shows the tools that fit what you're dragging: one PDF, several
PDFs (Merge), images (To PDF), or a mix (Merge).

## Using it

1. Start PDFportal. It lives in the tray, next to the clock; there is no main window.
2. Drag a file, and while still holding the mouse button, **shake it** quickly left and right.
3. The ring opens under your cursor. Move onto a tool; the middle tells you what it does.
4. Let go on the tool. Let go in the middle, or anywhere else, to cancel.

The tray icon has *How to use PDFportal*, *Pause the shake gesture*, *Start
with Windows* and *Quit*.

## Status

Version 0.1: the ten tools above. There's no installer yet, so build it from
source (below). The app isn't code-signed, so Windows may warn you the first
time you run it.

## Build from source

You need Windows 10 or 11, [Rust](https://rustup.rs), [Node.js](https://nodejs.org) 18+
and [Python](https://www.python.org) 3.11+.

```powershell
git clone https://github.com/Shivanshxsharma/pdfportal.git
cd pdfportal
npm install
npm run fonts

cd engine
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd ..

npx tauri dev
```

## How it works

```
 drag + shake ──▶ mouse hook (shake.rs) ──▶ portal window under the cursor (portal.rs)
                                             + an invisible "drop surface" on top (droptarget.rs)
 drop on a tool ─▶ the page asks Rust to run the job (commands.rs, engine.rs)
                  ──▶ PDF engine process (engine/, Python + PyMuPDF)
                  ──▶ progress events ──▶ the card (src/js/card.js)
```

- **`src-tauri/`**, the Rust app (Tauri 2). Windows doesn't tell apps when a
  drag starts, so a low-level mouse hook watches for the shake. The portal
  windows are kept in a small pool so the ring opens instantly. Files are
  received by a plain native window laid over the ring, not by the WebView
  (the comments in `droptarget.rs` explain why).
- **`src/`**, the interface: plain HTML, CSS and JavaScript, no framework.
  `ring.js` draws the ring, `card.js` the cards, `app.js` ties them together.
  `mock.js` stands in for Rust when you open the page in a normal browser.
- **`engine/`**, the PDF engine (Python, [PyMuPDF](https://pymupdf.readthedocs.io)).
  The app starts it once per job, sends the job as JSON on stdin, and reads
  one JSON event per line back (`engine/portal_engine/protocol.py`). A
  damaged PDF can only fail its own job, never the app.

## Tests

```powershell
npm test                               # the PDF engine, 27 tests
cd src-tauri; cargo test --lib         # the shake detector
```

`scripts/e2e-drag.ps1` tests the whole thing with a real Windows drag (it
moves your mouse for a few seconds). `scripts/screenshots.ps1` re-renders the
pictures in this README.

## Roadmap

- **Next tools:** OCR for scanned PDFs, sign, add text and images, redact,
  crop, PDF/A, repair, compare.
- **Office files:** Word, Excel and PowerPoint to PDF and back (LibreOffice).
- **An installer** with the engine bundled, and releases on GitHub.

## License

PDFportal is free software under the **GNU Affero General Public License v3.0
or later**. See [LICENSE](LICENSE).

It's built on [Tauri](https://tauri.app) (MIT/Apache-2.0) and
[PyMuPDF](https://github.com/pymupdf/PyMuPDF) (AGPL-3.0). The fonts are
[Oswald](https://github.com/googlefonts/OswaldFont) and
[DM Mono](https://github.com/googlefonts/dm-mono), both under the SIL Open
Font License (`src/fonts`).

© 2026 Shivansh Sharma
