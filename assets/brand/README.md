# ThreadLeaf icon exports

A simple folded document and sage leaf, with lavender accents matching the app.
The mark stays readable at small sizes; the banner pairs it with the name and slogan.

| File | Use |
| --- | --- |
| `threadleaf-banner.svg` | Horizontal banner for a repository, website or presentation |
| `threadleaf-icon.svg` | Transparent vector mark for websites, slides and documents |
| `threadleaf-app-icon.svg` | Vector mark on the current rounded lavender tile |
| `threadleaf-icon-SIZE.png` | Transparent raster mark, ready to use without SVG support |
| `threadleaf-app-icon-SIZE.png` | Rounded tile for app icons, profiles and shortcuts |
| `threadleaf.ico` | Windows shortcuts or browser favicons; includes 16, 32, 48, 64, 128 and 256 px frames |

PNG sizes: **16, 32, 48, 64, 128, 256, 512 and 1024 px**, square and RGBA.
Use SVG when possible; it scales without becoming blurry. Use 512 or 1024 px PNG
for general sharing and smaller PNG sizes for interface controls. Backgrounds
outside the mark or rounded tile are transparent.

Colors match the current interface:

- Document outline: `#77618a`
- Leaf: `#71876c`
- Paper: `#fffefa`
- App tile: `#eee6f4`
- Leaf vein: `#fffefa`

The icon vectors use no fonts, external images or icon libraries.
The banner uses the system sans-serif font.
They are also the source for the PNG and ICO exports. `export-icons.ps1` rebuilds
the raster files on Windows using built-in .NET drawing, without downloads:

```powershell
& ./assets/brand/export-icons.ps1
```

The exporter supports the SVG paths and transforms used by these icons. More
complex SVG edits may need a general-purpose SVG renderer.

An archive containing these files is available at `assets/threadleaf-icons.zip`.

Copyright © 2026 Pasquale Esposito. These original ThreadLeaf assets are licensed
under GNU GPL version 3 or later (`GPL-3.0-or-later`). The full text is included as
`LICENSE` in this folder and in the archive, with the project's `COPYRIGHT` notice.
Commercial use is permitted subject to GPLv3. Preserve the notices and provide
the corresponding editable sources when required by the license. The SVGs are
the editable sources for the raster icons; the exporter is included in the bundle.
