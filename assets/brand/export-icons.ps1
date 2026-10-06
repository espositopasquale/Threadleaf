# Rebuild the raster exports from the SVG files on Windows. No downloads required.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.Text.RegularExpressions;

public static class ThreadLeafSvgPath {
    public static GraphicsPath Parse(string data) {
        var matches = Regex.Matches(data, @"[MmLlHhVvCcAaZz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?");
        int i = 0;
        float x = 0, y = 0, sx = 0, sy = 0;
        char command = ' ';
        var path = new GraphicsPath();
        Func<float> number = () => float.Parse(matches[i++].Value, CultureInfo.InvariantCulture);
        while (i < matches.Count) {
            if (Regex.IsMatch(matches[i].Value, @"^[A-Za-z]$")) command = matches[i++].Value[0];
            bool relative = char.IsLower(command);
            float nx, ny;
            switch (char.ToUpperInvariant(command)) {
                case 'M':
                    nx = number(); ny = number();
                    if (relative) { nx += x; ny += y; }
                    path.StartFigure(); x = sx = nx; y = sy = ny;
                    command = relative ? 'l' : 'L'; break;
                case 'L':
                    nx = number(); ny = number();
                    if (relative) { nx += x; ny += y; }
                    path.AddLine(x, y, nx, ny); x = nx; y = ny; break;
                case 'H':
                    nx = number() + (relative ? x : 0);
                    path.AddLine(x, y, nx, y); x = nx; break;
                case 'V':
                    ny = number() + (relative ? y : 0);
                    path.AddLine(x, y, x, ny); y = ny; break;
                case 'C':
                    float ax = number(), ay = number(), bx = number(), by = number();
                    nx = number(); ny = number();
                    if (relative) { ax += x; ay += y; bx += x; by += y; nx += x; ny += y; }
                    path.AddBezier(x, y, ax, ay, bx, by, nx, ny); x = nx; y = ny; break;
                case 'A':
                    float rx = number(), ry = number(), rotation = number();
                    bool large = number() != 0, sweep = number() != 0;
                    nx = number(); ny = number();
                    if (relative) { nx += x; ny += y; }
                    if (rx != ry || rotation != 0) throw new NotSupportedException("This logo exporter supports circular, unrotated SVG arcs.");
                    double dx = (x - nx) / 2.0, dy = (y - ny) / 2.0;
                    double distance = dx * dx + dy * dy;
                    if (distance == 0) break;
                    double radius = Math.Max(rx, Math.Sqrt(distance));
                    double factor = Math.Sqrt(Math.Max(0, (radius * radius - distance) / distance)) * (large == sweep ? -1 : 1);
                    double cx = (x + nx) / 2.0 + factor * dy, cy = (y + ny) / 2.0 - factor * dx;
                    double start = Math.Atan2(y - cy, x - cx) * 180 / Math.PI;
                    double delta = Math.Atan2(ny - cy, nx - cx) * 180 / Math.PI - start;
                    if (sweep && delta < 0) delta += 360;
                    if (!sweep && delta > 0) delta -= 360;
                    path.AddArc((float)(cx - radius), (float)(cy - radius), (float)(radius * 2), (float)(radius * 2), (float)start, (float)delta);
                    x = nx; y = ny; break;
                case 'Z': path.CloseFigure(); x = sx; y = sy; command = ' '; break;
                default: throw new NotSupportedException("Unsupported SVG path command: " + command);
            }
        }
        return path;
    }
}
'@

function Draw-SvgNode($Node, $Graphics, $Color) {
    $saved = $Graphics.Save()
    try {
        if ($Node.HasAttribute('color')) { $Color = $Node.GetAttribute('color') }
        if ($Node.HasAttribute('transform')) {
            if ($Node.GetAttribute('transform') -notmatch '^translate\(([\d.]+)\s+([\d.]+)\)$') { throw 'Unsupported SVG transform' }
            $Graphics.TranslateTransform([float]::Parse($Matches[1], [Globalization.CultureInfo]::InvariantCulture), [float]::Parse($Matches[2], [Globalization.CultureInfo]::InvariantCulture))
        }
        $path = $null
        if ($Node.LocalName -eq 'path') { $path = [ThreadLeafSvgPath]::Parse($Node.GetAttribute('d')) }
        if ($Node.LocalName -eq 'rect') {
            $width = [float]$Node.GetAttribute('width'); $height = [float]$Node.GetAttribute('height'); $radius = [float]$Node.GetAttribute('rx')
            $diameter = $radius * 2
            $path = New-Object System.Drawing.Drawing2D.GraphicsPath
            $path.AddArc(0, 0, $diameter, $diameter, 180, 90)
            $path.AddArc($width - $diameter, 0, $diameter, $diameter, 270, 90)
            $path.AddArc($width - $diameter, $height - $diameter, $diameter, $diameter, 0, 90)
            $path.AddArc(0, $height - $diameter, $diameter, $diameter, 90, 90)
            $path.CloseFigure()
        }
        if ($null -ne $path) {
            try {
                $opacity = if ($Node.HasAttribute('opacity')) { [double]::Parse($Node.GetAttribute('opacity'), [Globalization.CultureInfo]::InvariantCulture) } else { 1.0 }
                foreach ($kind in @('fill', 'stroke')) {
                    $paint = $Node.GetAttribute($kind)
                    if (!$paint -or $paint -eq 'none') { continue }
                    if ($paint -eq 'currentColor') { $paint = $Color }
                    $base = [Drawing.ColorTranslator]::FromHtml($paint)
                    $rgba = [Drawing.Color]::FromArgb([int](255 * $opacity), $base.R, $base.G, $base.B)
                    if ($kind -eq 'fill') {
                        $brush = New-Object Drawing.SolidBrush $rgba
                        try { $Graphics.FillPath($brush, $path) } finally { $brush.Dispose() }
                    } else {
                        $lineWidth = [float]::Parse($Node.GetAttribute('stroke-width'), [Globalization.CultureInfo]::InvariantCulture)
                        $pen = New-Object Drawing.Pen $rgba, $lineWidth
                        $pen.LineJoin = [Drawing.Drawing2D.LineJoin]::Round
                        if ($Node.GetAttribute('stroke-linecap') -eq 'round') { $pen.StartCap = $pen.EndCap = [Drawing.Drawing2D.LineCap]::Round }
                        try { $Graphics.DrawPath($pen, $path) } finally { $pen.Dispose() }
                    }
                }
            } finally { $path.Dispose() }
        }
        foreach ($child in $Node.ChildNodes) {
            if ($child -is [Xml.XmlElement]) { Draw-SvgNode $child $Graphics $Color }
        }
    } finally { $Graphics.Restore($saved) }
}

$sizes = @(16, 32, 48, 64, 128, 256, 512, 1024)
foreach ($name in @('threadleaf-icon', 'threadleaf-app-icon')) {
    [xml]$svg = Get-Content -LiteralPath (Join-Path $PSScriptRoot "$name.svg") -Raw
    $viewBox = $svg.DocumentElement.GetAttribute('viewBox').Split(' ')
    foreach ($size in $sizes) {
        # Supersampling gives small icons cleaner edges while keeping transparency.
        $renderSize = [Math]::Max(1024, $size)
        $large = New-Object Drawing.Bitmap $renderSize, $renderSize
        $drawing = [Drawing.Graphics]::FromImage($large)
        try {
            $drawing.Clear([Drawing.Color]::Transparent)
            $drawing.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
            $drawing.ScaleTransform($renderSize / [float]$viewBox[2], $renderSize / [float]$viewBox[3])
            Draw-SvgNode $svg.DocumentElement $drawing '#77618a'
            $bitmap = New-Object Drawing.Bitmap $size, $size
            $resizer = [Drawing.Graphics]::FromImage($bitmap)
            try {
                $resizer.CompositingMode = [Drawing.Drawing2D.CompositingMode]::SourceCopy
                $resizer.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                $resizer.DrawImage($large, 0, 0, $size, $size)
                $bitmap.Save((Join-Path $PSScriptRoot "$name-$size.png"), [Drawing.Imaging.ImageFormat]::Png)
            } finally { $resizer.Dispose(); $bitmap.Dispose() }
        } finally { $drawing.Dispose(); $large.Dispose() }
    }
}

# Modern ICO containers can store PNG frames, retaining their alpha channels.
$icoSizes = @(16, 32, 48, 64, 128, 256)
$frames = @($icoSizes | ForEach-Object { ,([IO.File]::ReadAllBytes((Join-Path $PSScriptRoot "threadleaf-app-icon-$_.png"))) })
$stream = [IO.File]::Create((Join-Path $PSScriptRoot 'threadleaf.ico'))
$writer = New-Object IO.BinaryWriter $stream
try {
    $writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]$icoSizes.Count)
    $offset = 6 + 16 * $icoSizes.Count
    for ($i = 0; $i -lt $icoSizes.Count; $i++) {
        $dimension = if ($icoSizes[$i] -eq 256) { 0 } else { $icoSizes[$i] }
        $writer.Write([byte]$dimension); $writer.Write([byte]$dimension)
        $writer.Write([byte]0); $writer.Write([byte]0); $writer.Write([uint16]1); $writer.Write([uint16]32)
        $writer.Write([uint32]$frames[$i].Length); $writer.Write([uint32]$offset)
        $offset += $frames[$i].Length
    }
    foreach ($frame in $frames) { $writer.Write([byte[]]$frame) }
} finally { $writer.Dispose(); $stream.Dispose() }
Write-Output 'Exported 2 SVG variants to 16 transparent PNGs and a multi-resolution ICO.'
