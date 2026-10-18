<#
  screenshots.ps1 — renders the README's pictures of PDFportal.

  Serves src/ locally, opens each demo state of the UI (src/js/mock.js,
  ?demo=ring|done|form|hint) in headless Microsoft Edge, and saves 2x PNGs
  to docs/screenshots. Uses the pretend backend only: no real files, nothing
  from your screen. Edge runs with a throwaway profile, not yours.

    powershell -File scripts\screenshots.ps1
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$out = Join-Path $root 'docs\screenshots'
New-Item -ItemType Directory -Force $out | Out-Null

$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") |
  Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { throw 'Microsoft Edge not found.' }
$python = Join-Path $root 'engine\.venv\Scripts\python.exe'
$port = 5191
$profileDir = Join-Path $env:TEMP 'pdfportal-screenshots-edge'

$server = Start-Process -FilePath $python -ArgumentList '-m', 'http.server', $port, '--bind', '127.0.0.1', '--directory', (Join-Path $root 'src') -PassThru -WindowStyle Hidden
try {
  Start-Sleep -Seconds 1
  # Edge reports "N bytes written" on stderr; that's news, not an error.
  $ErrorActionPreference = 'Continue'
  foreach ($demo in 'ring', 'done', 'form', 'hint') {
    $file = Join-Path $out "$demo.png"
    $url = "http://127.0.0.1:$port/index.html?demo=$demo&files=Quarterly%20report.pdf&bg=%23dfe9f1"
    # --virtual-time-budget lets the pretend job run before the shot; reduced
    # motion makes every animation land on its final frame (headless Edge
    # doesn't paint the frames in between).
    & $edge --headless=new --disable-gpu --hide-scrollbars --no-first-run "--user-data-dir=$profileDir" `
      --force-prefers-reduced-motion --force-device-scale-factor=2 --window-size=520,520 `
      --virtual-time-budget=7000 "--screenshot=$file" $url 2>$null | Out-Null
    Write-Host "docs/screenshots/$demo.png"
  }
} finally {
  Stop-Process -Id $server.Id -Confirm:$false -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $profileDir -Recurse -Force -ErrorAction SilentlyContinue -Confirm:$false
}
