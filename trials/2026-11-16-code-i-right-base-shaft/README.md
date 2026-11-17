# Code i: right base +40 / shaft +24

Separate review trial based on released Code1.017. The base extends40 units
right. The upper assembly (shaft, curved top and diamond) moves24 units right
as a rigid translation. Its shape, stroke thickness and height remain intact.
The base's outside corners stay fixed apart from the right extension; straight
edge controls are reparameterized to connect the moved shaft. The600-unit
advance, c, all other glyphs, spacing and operator ligatures are unchanged.

At Book350: original shaft center300.5; revised324.5; JetBrains325.
The trial base is94–546, centered320; JetBrains85–555, centered320.
JetBrains' left/right overhangs around its shaft are195/185: the reference base
is almost symmetric around the shaft, but shifted right within the cell.
This distinction matters when interpreting its apparent longer right side.
JetBrains reference2.305 and its file hash are recorded in report.json.

Comparison PNG/PDF/SVG includes preceding construction(s) and JetBrains.
Weights PNG/PDF/SVG compares all3weights in both polarities. Browser.png shows
actual loaded font text at13/14/16px in Chrome157, device scale2. All4font-face
load checks passed. These images were opened and visually reviewed; terminal
rendering was not re-tested.

The family is Daikonic Transit Code Right Base Shaft Study.
It includes VF300–400/defaultBook350 plus Light, Book and Regular snapshots.
All4font files passOTS. At11interpolation positions every modified point matches
its specified translation exactly, i retains2contours and600-unit advance.
All original variation functions and all unrelated outlines/layout/metrics are
retained exactly. Plain i alone is revised. Align dotless/accented i forms as
part of production adoption if selected. Released/installed fonts are unchanged.

Editable recipe: tools/code_balance_study.py. From the repository root:

```sh
.venv/bin/python tools/code_balance_study.py --construction right-base --shaft-shift 24
.venv/bin/python tools/render_svg.py --scale 2 .build/code-right-base-shaft/Comparison.svg .build/code-right-base-shaft/Weights.svg
```

Prior flat-top and base-only studies are retained separately. Reference font
binaries are not bundled. OFL.txt and NOTICE.txt apply to Transit derivations.
