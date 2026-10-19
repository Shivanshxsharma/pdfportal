"""What PyInstaller freezes into pdfportal-engine.exe (scripts/build-installer.ps1).

The engine itself is the portal_engine package; this file only starts it,
because PyInstaller needs a script to begin from rather than `python -m`.
"""

import sys

from portal_engine.__main__ import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
