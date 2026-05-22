$ErrorActionPreference = "Stop"

$assetDir = Join-Path $PSScriptRoot "..\src\md_reader\assets"
New-Item -ItemType Directory -Path $assetDir -Force | Out-Null

$iconPath = Join-Path $assetDir "mdreader.ico"

Add-Type -AssemblyName System.Drawing

$size = 256
$bitmap = New-Object System.Drawing.Bitmap $size, $size
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

$background = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(33, 37, 41))
$foreground = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
$graphics.FillRectangle($background, 0, 0, $size, $size)

$fontFamily = New-Object System.Drawing.FontFamily "Segoe UI"
$font = New-Object System.Drawing.Font $fontFamily, 88, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
$format = New-Object System.Drawing.StringFormat
$format.Alignment = [System.Drawing.StringAlignment]::Center
$format.LineAlignment = [System.Drawing.StringAlignment]::Center

$rect = New-Object System.Drawing.RectangleF 0, -4, $size, $size
$graphics.DrawString("MD", $font, $foreground, $rect, $format)

$handle = $bitmap.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($handle)
$stream = [System.IO.File]::Create($iconPath)
$icon.Save($stream)
$stream.Close()

$icon.Dispose()
$font.Dispose()
$fontFamily.Dispose()
$foreground.Dispose()
$background.Dispose()
$graphics.Dispose()
$bitmap.Dispose()

Write-Host "Wrote $iconPath"
