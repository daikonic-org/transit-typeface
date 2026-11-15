# Release layout

Following [Adobe Source Sans releases](https://github.com/adobe-fonts/source-sans/releases), downloads are separated by format. We include formats actually built, rather than listing unsupported OTF or legacy WOFF files.

| Release | Tag |
| --- | --- |
| Fonts version 0.108 — Daikonic Transit Sans (TTF, VF, WOFF2) | `Sans-0.108R` |
| Fonts version 0.117 — Daikonic Transit System (TTF, VF, WOFF2) | `System-0.117R` |
| Fonts version 1.017 — Daikonic Transit Code (TTF, VF, WOFF2) | `Code-1.017R` |

Example assets for Code:

```text
TTF-daikonic-transit-code-1.017R.zip
VF-daikonic-transit-code-1.017R.zip
WOFF2-daikonic-transit-code-1.017R.zip
SOURCE-daikonic-transit-code-1.017R.zip
SPECIMEN-daikonic-transit-code-1.017R.zip
SHA256SUMS-daikonic-transit-code-1.017R.txt
```

Static TTFs are named-weight snapshots of the corresponding VF. System static files cover Caption10, Text14 and Display36 at five weights. Each archive includes license/notice records and a short description; WOFF2 includes an `@font-face` stylesheet. SOURCE includes compatible binary masters, metadata and editor sources. SPECIMEN includes PNG/PDF/outlined SVG.

`tools/release.py` writes these assets and ready-to-publish Markdown notes to `.dist/<family>/<version>/`. Tags for the first three family releases point to the same reviewed initial repository snapshot. This repository's first commit packages the current accepted fonts; it does not pretend the older local studies were public releases.
