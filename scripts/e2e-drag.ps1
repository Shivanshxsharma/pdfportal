<#
  e2e-drag.ps1 — tests PDFportal the way a person uses it.

  Starts a real Windows file drag (an OLE drag, like File Explorer's),
  carries it to the middle of the screen, shakes it, waits for the portal,
  moves onto a tool slot and lets go. Then waits for the result file.

  It moves YOUR mouse for about four seconds, so don't touch it meanwhile.
  A plain dark backdrop covers the screen while it runs: the drag starts on
  it, any stray click lands on it, and screenshots only ever show PDFportal on
  that backdrop, never your own windows.

  PDFportal must already be running (src-tauri\target\debug\portal.exe).
  Run this from a normal PowerShell, not a sandbox: Windows blocks drag and
  drop between processes that are boxed differently.

    powershell -STA -File scripts\e2e-drag.ps1 -File "C:\path\some.pdf" -Slot 2 -Expect "some (rotated).pdf"

  -Slot is the ring position, clockwise from the top (for one PDF:
  0 Split, 1 Compress, 2 Rotate, 3 To JPG, 4 Numbers, 5 Watermark,
  6 Protect, 7 Unlock). -Shots <folder> saves 1-portal.png (just before
  letting go) and 2-card.png (2.5 s after).

  Why not drag out of a real Explorer window? Explorer doesn't start a drag
  from simulated mouse input, so that test would prove nothing.
#>
param(
  [Parameter(Mandatory)] [string] $File,
  [int] $Slot = 2,
  [int] $Slots = 8,
  [string] $Expect = "",
  [string] $Shots = "",
  [int] $AfterMs = 2500
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms, System.Drawing

Add-Type -ReferencedAssemblies System.Windows.Forms, System.Drawing -TypeDefinition @'
using System;
using System.Collections.Specialized;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

public static class PortalE2E {
    [DllImport("user32.dll")] static extern uint SendInput(uint count, INPUT[] inputs, int size);
    [DllImport("user32.dll")] static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")] static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll")] static extern IntPtr MonitorFromPoint(POINT pt, uint flags);
    [DllImport("shcore.dll")] static extern int GetDpiForMonitor(IntPtr monitor, int type, out uint x, out uint y);
    [DllImport("user32.dll")] static extern bool GetCursorPos(out POINT pt);
    [DllImport("user32.dll")] static extern IntPtr WindowFromPoint(POINT pt);

    [StructLayout(LayoutKind.Sequential)] struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT { public int dx, dy; public uint mouseData, dwFlags, time; public IntPtr extra; }
    [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public MOUSEINPUT mi; }

    const uint MOVE = 0x1, LEFTDOWN = 0x2, LEFTUP = 0x4, VIRTUALDESK = 0x4000, ABSOLUTE = 0x8000;

    static int x, y; // where the pointer is now (physical pixels)

    // Physical pixels everywhere, like PDFportal itself. Per THREAD: without
    // this, Windows silently rescales every coordinate on a 125% screen.
    static void PhysicalPixels() { SetThreadDpiAwarenessContext((IntPtr)(-4)); }

    static void Send(uint flags, int tx, int ty) {
        int vx = GetSystemMetrics(76), vy = GetSystemMetrics(77), vw = GetSystemMetrics(78), vh = GetSystemMetrics(79);
        var input = new INPUT { type = 0, mi = new MOUSEINPUT {
            dx = (int)Math.Round((tx - vx) * 65535.0 / (vw - 1)),
            dy = (int)Math.Round((ty - vy) * 65535.0 / (vh - 1)),
            dwFlags = flags | ABSOLUTE | VIRTUALDESK } };
        SendInput(1, new[] { input }, Marshal.SizeOf(typeof(INPUT)));
        x = tx; y = ty;
    }

    // Moves in small steps, like a hand: Windows' drag loop and PDFportal's
    // shake detector both need to see the movement, not a jump.
    static void Glide(int tx, int ty, int steps, int stepMs) {
        int sx = x, sy = y;
        for (int k = 1; k <= steps; k++) {
            Send(MOVE, sx + (tx - sx) * k / steps, sy + (ty - sy) * k / steps);
            Thread.Sleep(stepMs);
        }
    }

    static void Shot(string path, int cx, int cy, int size) {
        if (string.IsNullOrEmpty(path)) return;
        using (var bmp = new Bitmap(size, size))
        using (var g = Graphics.FromImage(bmp)) {
            g.CopyFromScreen(cx - size / 2, cy - size / 2, 0, 0, bmp.Size);
            bmp.Save(path, ImageFormat.Png);
        }
    }

    public static string Run(string file, int slot, int slots, string shots, int afterMs) {
        PhysicalPixels();
        var screen = Screen.PrimaryScreen.WorkingArea;
        int cx = screen.Left + screen.Width / 2, cy = screen.Top + screen.Height / 2;
        uint dpiX, dpiY;
        GetDpiForMonitor(MonitorFromPoint(new POINT { X = cx, Y = cy }, 2), 0, out dpiX, out dpiY);
        double scale = dpiX / 96.0;

        // The backdrop: covers the work area, and is where the drag starts.
        var form = new Form {
            FormBorderStyle = FormBorderStyle.None, TopMost = true, ShowInTaskbar = false,
            StartPosition = FormStartPosition.Manual, BackColor = Color.FromArgb(30, 30, 36),
            Location = screen.Location, Size = screen.Size,
        };
        int startX = cx - (int)(260 * scale), startY = cy;
        string result = "drop effect: never started";

        form.MouseDown += (s, e) => {
            var data = new DataObject();
            var list = new StringCollection();
            list.Add(file);
            data.SetFileDropList(list);
            // Blocks in Windows' drag loop until the button goes up.
            result = "drop effect: " + form.DoDragDrop(data, DragDropEffects.Copy);
        };

        form.Shown += (s, e) => {
            IntPtr backdrop = form.Handle;
            new Thread(() => {
                PhysicalPixels();
                Thread.Sleep(300);
                Send(MOVE, startX, startY);
                Thread.Sleep(150);
                // Only press the button if the pointer really is on the backdrop.
                POINT at;
                GetCursorPos(out at);
                if (WindowFromPoint(at) != backdrop) {
                    result = "ABORTED: the pointer isn't on the backdrop";
                    form.BeginInvoke(new Action(form.Close));
                    return;
                }
                Send(LEFTDOWN, startX, startY);
                Thread.Sleep(250);
                Glide(cx, cy, 14, 15);                   // carry it to the middle
                int swing = (int)(70 * scale);
                for (int i = 0; i < 3; i++) {            // the shake
                    Glide(cx + swing, cy, 4, 14);
                    Glide(cx - swing, cy, 6, 14);
                }
                Glide(cx, cy, 4, 14);
                Thread.Sleep(700);                       // the portal opens under the pointer
                Glide(cx + 3, cy + 2, 2, 30);            // a nudge, so Windows reports the drag over it
                double angle = (-90.0 + slot * 360.0 / slots) * Math.PI / 180.0;
                int tx = cx + (int)Math.Round(Math.Cos(angle) * 154 * scale);
                int ty = cy + (int)Math.Round(Math.Sin(angle) * 154 * scale);
                Glide(tx, ty, 12, 20);                   // onto the tool
                Thread.Sleep(400);
                Shot(shots == "" ? "" : shots + "\\1-portal.png", cx, cy, (int)(560 * scale));
                Send(LEFTUP, tx, ty);                    // drop
                Thread.Sleep(afterMs);
                Shot(shots == "" ? "" : shots + "\\2-card.png", cx, cy, (int)(440 * scale));
                form.BeginInvoke(new Action(form.Close));
            }) { IsBackground = true }.Start();
        };

        Application.Run(form);
        return "scale " + scale + "; " + result;
    }
}
'@

$file = (Resolve-Path -LiteralPath $File).Path
Write-Host ([PortalE2E]::Run($file, $Slot, $Slots, $Shots, $AfterMs))

if ($Expect) {
  $target = Join-Path (Split-Path $file) $Expect
  for ($i = 0; $i -lt 40 -and -not (Test-Path -LiteralPath $target); $i++) { Start-Sleep -Milliseconds 250 }
  if (Test-Path -LiteralPath $target) { Write-Host "PASS: $target" } else { Write-Host "FAIL: $target never appeared"; exit 1 }
}
