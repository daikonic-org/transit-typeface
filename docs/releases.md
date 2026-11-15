# Release layout

Following [Adobe Source Sans releases](https://github.com/adobe-fonts/source-sans/releases), downloads are separated by format. We include formats actually built, rather than listing unsupported OTF or legacy WOFF files.

| Release | Tag |
| --- | --- |
| Fonts version 0.106 — Transit Sans (TTF, VF, WOFF2) | `Sans-0.106R` |
| Fonts version 0.115 — Transit System (TTF, VF, WOFF2) | `System-0.115R` |
| Fonts version 1.015 — Transit Code (TTF, VF, WOFF2) | `Code-1.015R` |

Example assets for Code:

```text
TTF-transit-code-1.015R.zip
VF-transit-code-1.015R.zip
WOFF2-transit-code-1.015R.zip
SOURCE-transit-code-1.015R.zip
SPECIMEN-transit-code-1.015R.zip
SHA256SUMS-transit-code-1.015R.txt
```

Static TTFs are named-weight snapshots of the corresponding VF. System static files cover Caption10, Text14 and Display36 at five weights. Each archive includes license/notice records and a short description; WOFF2 includes an `@font-face` stylesheet. SOURCE includes compatible binary masters, metadata and editor sources. SPECIMEN includes PNG/PDF/outlined SVG.

`tools/release.py` writes these assets and ready-to-publish Markdown notes to `.dist/<family>/`. Tags for the first three family releases point to the same reviewed initial repository snapshot. This repository's first commit packages the current accepted fonts; it does not pretend the older local studies were public releases.
