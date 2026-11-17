# Transit Code i/c optical review — 16 November 2026

Recommendation: revise i; retain c. The proposed i has a flat upper flag, with
its shaft and diamond 24 units right of their current positions. Its centered
base, existing stroke thickness, height and 600-unit advance remain intact.
This counters the original curved top's diagonal movement and left-heavy color.
The c appears balanced in words and at text sizes beside the reference fonts.
Its asymmetry belongs to the open bowl; no c change is proposed.

Comparison.png/pdf/svg: current Code Book350 / proposed i / JetBrains Mono400 /
Source Code Pro400 / Menlo Regular, at equal character-cell sizes. References
have different stroke weights; these are not identical optical-weight matches.
Weights.png/pdf/svg: current/proposed across Light300, Book350, Regular400 in
both polarities. Browser.png uses actual loaded webfont text at13,14,16px in
Chrome157, device scale2; all5 font-face load checks passed. The outlined proof
and browser text were opened and visually reviewed. Terminal rendering was not
re-tested. The browser source stays private because it embeds reference fonts.

The reference binaries are recorded by version and SHA256 in report.json:
JetBrains Mono2.305, locally installed Source Code Pro1.018 and Menlo22.0d2e1.
Sources: https://github.com/JetBrains/JetBrainsMono and
https://github.com/adobe-fonts/source-code-pro; Menlo is the macOS system font.
Reference fonts are not bundled. metrics.csv records ink bounds, sidebearings
and area centroids; an area centroid is a diagnostic, not an optical-centering
rule. Current i ink center46.82% of cell; proposed48.90%. Reference c area centers
range44.96–46.41%; Transit c46.98%, with comparable open-bowl asymmetry.

The separate trial family is Daikonic Transit Code Balance Study. It includes
a VF300–400/defaultBook350 and three named static snapshots. All4 files pass
OpenType Sanitizer; i's topology and600-unit advance were checked at11 weights.
All other outline/variation functions, layout and metrics match production.
Only plain i is revised. Dotless/accented i forms still use their current
outlines; align them as part of adoption if this design is selected.
Released/installed Code1.017, Sans0.109 and System0.117 are unchanged.

Editable construction and reproducible comparison: tools/code_balance_study.py.
Run from the repository root; optional --jetbrains, --source-code and --menlo
arguments specify reference font files. It writes .build/code-balance.

```sh
.venv/bin/python tools/code_balance_study.py
.venv/bin/python tools/render_svg.py --scale 2 .build/code-balance/Comparison.svg .build/code-balance/Weights.svg
```

The study VF keeps all production tables except i's outline/variation data and
trial names. Prior artifacts remain intact. OFL.txt and NOTICE.txt apply to the
Transit font derivation; the references serve only as comparison artwork.
