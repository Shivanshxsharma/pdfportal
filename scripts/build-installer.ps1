<#
  build-installer.ps1 — builds PDFportal's Windows installer.

    npm run installer
    (or: powershell -ExecutionPolicy Bypass -File scripts\build-installer.ps1 [-SkipTests])

  1. Freezes the Python PDF engine into engine\dist\pdfportal-engine\
     (PyInstaller, "folder" mode: a single-file exe would unpack itself to a
     temporary folder on every job and start a second or two slower).
  2. Runs the engine's whole test suite against that frozen copy, with no
     Python on the PATH, as on a computer that never had Python.
  3. Builds the app and the installer (tauri build). tauri.conf.json bundles
     the frozen engine next to pdfportal.exe, where the app looks first.
  4. Copies the installer to a stable name, PDFportal-Setup.exe (the README's
     download link points at that name in the latest GitHub release), and
     prints its SHA-256 for the release notes.

  Needs: Rust, Node.js, and the engine's .venv (see the README).
#>
param([switch] $SkipTests)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$engine = Join-Path $root 'engine'
$python = Join-Path $engine '.venv\Scripts\python.exe'
$frozen = Join-Path $engine 'dist\pdfportal-engine\pdfportal-engine.exe'
$version = (Get-Content (Join-Path $root 'src-tauri\tauri.conf.json') -Raw | ConvertFrom-Json).version

function Step($text) { Write-Host "`n== $text" -ForegroundColor Magenta }

# A running copy built here locks its own .exe and the build would fail.
$running = Get-Process pdfportal -ErrorAction SilentlyContinue | Where-Object { $_.Path -like (Join-Path $root 'src-tauri\target\*') }
if ($running) {
  Step 'Closing the PDFportal built here (it locks the files the build replaces)'
  $running | Stop-Process -Confirm:$false
  Start-Sleep -Milliseconds 800
}

Step "Freezing the PDF engine (PyInstaller)"
& $python -m pip install --quiet 'pyinstaller>=6.16'
Push-Location $engine
try {
  Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
  & $python -m PyInstaller --noconfirm --clean --log-level WARN --name pdfportal-engine --console `
    --paths . --distpath dist --workpath build --specpath build `
    --exclude-module tkinter --exclude-module pytest --exclude-module _pytest `
    --exclude-module pip --exclude-module setuptools pdfportal_engine.py
  if ($LASTEXITCODE) { throw 'PyInstaller failed.' }
  & $frozen --version
  if ($LASTEXITCODE) { throw 'The frozen engine does not start.' }

  if (-not $SkipTests) {
    Step 'Testing the frozen engine (all tools, no Python on PATH)'
    $env:PORTAL_ENGINE_EXE = $frozen
    try { & $python -m pytest -q } finally { Remove-Item Env:\PORTAL_ENGINE_EXE }
    if ($LASTEXITCODE) { throw 'The frozen engine failed its tests.' }
  }
} finally {
  Pop-Location
}

Step "Building PDFportal $version and its installer (tauri build)"
Push-Location $root
try {
  npx tauri build
  if ($LASTEXITCODE) { throw 'tauri build failed.' }
} finally {
  Pop-Location
}

$nsis = Join-Path $root 'src-tauri\target\release\bundle\nsis'
$setup = Get-ChildItem $nsis -Filter "PDFportal_$($version)_x64-setup.exe" | Select-Object -First 1
if (-not $setup) { throw "No installer found in $nsis" }
$stable = Join-Path $nsis 'PDFportal-Setup.exe'
Copy-Item $setup.FullName $stable -Force

Step 'Done'
$hash = (Get-FileHash $stable -Algorithm SHA256).Hash.ToLower()
Write-Host "Installer: $stable"
Write-Host ("Size:      {0:N1} MB" -f ((Get-Item $stable).Length / 1MB))
Write-Host "SHA-256:   $hash"
