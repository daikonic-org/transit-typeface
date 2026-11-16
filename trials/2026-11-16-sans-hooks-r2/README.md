# Sans hook interaction study R2

Refines the approved `ai` idea: removes the old a foot below the new hook,
using a curved join from the bowl into the hook. The original ai spacing,
upper i shaft, diamond, bowl and top profile are retained.

For `li`, the i moves 135 units left at each named weight. Its horizontal
stem gap now matches ai: 101 units (Book rounds to 101.5 versus ai 101).
The pair advance shortens by the same amount; outer kerning is retained.
Standalone l and i are unchanged.

Five static installable weights: 300, 350, 400, 500, 600. Family name:
Daikonic Transit Sans Hook Study R2. This trial does not replace installed
fonts or the released Sans VF. Variable compatibility remains untested.

Comparison: previous hook study / ordinary letters / revised hooks.
PNG, vector PDF and editable outlined SVG show Book through Semibold.
All five fonts pass OpenType Sanitizer. Thirty word-spacing checks verify
unchanged ai advances and the intended 135-unit reduction per li occurrence,
including retained surrounding kerning. See report.json for measurements.

Reproduce from the repository root:

```sh
.venv/bin/python tools/hook_ligature_study.py
.venv/bin/python tools/render_svg.py --scale 2 .build/hook-ligatures-r2/Comparison.svg
```

The editable construction is tools/hook_ligature_study.py; it derives from
the production Sans VF and its l hook. Previous study artifacts are retained
in trials/2026-11-16-sans-hooks. OFL.txt and NOTICE.txt apply.
