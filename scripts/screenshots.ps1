<#
  screenshots.ps1 — renders every picture in the README.

  Serves the repository locally and opens each picture in headless
  Microsoft Edge, saving 2x PNGs:

    docs/screenshots/ring|done|form|hint.png   the app's states (src/js/mock.js
                                                ?demo=…), on a transparent
                                                background so they float on
                                                GitHub's page, light or dark
    docs/brand/banner.png                       the README's hero
    docs/brand/social-preview.png               for GitHub → Settings → Social preview
    docs/brand/steps.png                        Drag. Shake. Drop.
    docs/brand/tools.png                        the ten tools
    docs/brand/flow.png                         how a drop becomes a file
    src-tauri/icons/installer-sidebar.bmp       the installer's welcome/finish picture
    src-tauri/icons/installer-header.bmp        the installer's page header
                                                (rendered 1:1, then made BMP by png_to_bmp.py)

  Uses the pretend backend only: no real files, nothing from your screen.
  Edge runs with a throwaway profile, not yours.

    powershell -File scripts\screenshots.ps1
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
New-Item -ItemType Directory -Force (Join-Path $root 'docs\screenshots'), (Join-Path $root 'docs\brand') | Out-Null

$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") |
  Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { throw 'Microsoft Edge not found.' }
$python = Join-Path $root 'engine\.venv\Scripts\python.exe'
$port = 5191
$profileDir = Join-Path $env:TEMP 'pdfportal-screenshots-edge'

# What to render: output file, page, window size (CSS pixels), and the scale
# (2 = crisp on high-DPI screens; 1 = exact pixels, for the installer).
$shots = @(
  @('docs\screenshots\ring.png', 'src/index.html?demo=ring', '520,520'),
  @('docs\screenshots\done.png', 'src/index.html?demo=done', '520,520'),
  @('docs\screenshots\form.png', 'src/index.html?demo=form', '520,520'),
  @('docs\screenshots\hint.png', 'src/index.html?demo=hint', '520,520'),
  @('docs\brand\banner.png', 'docs/brand/brand.html?view=banner', '1200,480'),
  @('docs\brand\social-preview.png', 'docs/brand/brand.html?view=social', '1280,640'),
  @('docs\brand\steps.png', 'docs/brand/brand.html?view=steps', '1200,360'),
  @('docs\brand\tools.png', 'docs/brand/brand.html?view=tools', '1200,400'),
  @('docs\brand\flow.png', 'docs/brand/brand.html?view=flow', '1200,176'),
  @('src-tauri\icons\installer-sidebar.png', 'docs/brand/brand.html?view=sidebar', '164,314', 1),
  @('src-tauri\icons\installer-header.png', 'docs/brand/brand.html?view=header', '150,57', 1)
)

$server = Start-Process -FilePath $python -ArgumentList '-m', 'http.server', $port, '--bind', '127.0.0.1', '--directory', $root -PassThru -WindowStyle Hidden
try {
  Start-Sleep -Seconds 1
  # Edge reports "N bytes written" on stderr; that's news, not an error.
  $ErrorActionPreference = 'Continue'
  foreach ($shot in $shots) {
    $file = Join-Path $root $shot[0]
    $url = "http://127.0.0.1:$port/$($shot[1])&files=Quarterly%20report.pdf&bg=transparent"
    # --virtual-time-budget lets the pretend job run before the shot; reduced
    # motion makes every animation land on its final frame (headless Edge
    # doesn't paint the frames in between); the background colour 00000000
    # keeps everything outside the cards transparent.
    $scale = if ($shot.Count -gt 3) { $shot[3] } else { 2 }
    & $edge --headless=new --disable-gpu --hide-scrollbars --no-first-run "--user-data-dir=$profileDir" `
      --force-prefers-reduced-motion "--force-device-scale-factor=$scale" "--window-size=$($shot[2])" `
      --default-background-color=00000000 --virtual-time-budget=7000 "--screenshot=$file" $url 2>$null | Out-Null
    Write-Host ($shot[0] -replace '\\', '/')
  }
  # The app's states are drawn in a big transparent square; crop it to the card.
  & $python (Join-Path $PSScriptRoot 'trim_png.py') @($shots[0..3] | ForEach-Object { Join-Path $root $_[0] })
  # The installer reads only BMP: convert, then drop the PNGs.
  $icons = Join-Path $root 'src-tauri\icons'
  & $python (Join-Path $PSScriptRoot 'png_to_bmp.py') `
    (Join-Path $icons 'installer-sidebar.png') (Join-Path $icons 'installer-sidebar.bmp') `
    (Join-Path $icons 'installer-header.png') (Join-Path $icons 'installer-header.bmp')
  Remove-Item (Join-Path $icons 'installer-sidebar.png'), (Join-Path $icons 'installer-header.png') -Confirm:$false
} finally {
  Stop-Process -Id $server.Id -Confirm:$false -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $profileDir -Recurse -Force -ErrorAction SilentlyContinue -Confirm:$false
}
