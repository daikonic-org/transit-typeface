# Code: heavier underscore

A review trial built on the selected delimiter/GPOS placement candidate. Only
underscore thickness changes: multiply its vertical coordinates and variation
deltas by 1.20, rounded to the nearest font unit. Its bottom remains y=0 and
its full-cell width remains x=0..600. Light/Book/Regular thicknesses change
66/80/92 to 79/96/110 units. Delimiters, selected i and optical pair positioning
are retained exactly. The prior trial remains available separately.

Includes VF 300–400/default Book 350 and Light/Book/Regular snapshots under the
family Daikonic Transit Code Underscore Study. All four binaries pass OTS.
Checks at 11 weights confirm height within one unit of the intended factor,
baseline and full width, plus exact retention of all unrelated outlines,
variation data, layout and metrics. See validation.json.

Comparison.png/pdf/svg covers named weights in both polarities. Browser.png
shows Book at 13/14/16px using actual loaded fonts in Chrome 157, device scale 2.
Both font-load checks passed; images were opened and visually reviewed. Editor
and terminal use has not been tested. No production install or release occurred.

Editable recipe: tools/code_underscore_weight_study.py in the repository;
recipe.py is its archived copy and uses shared tools/ helpers. Run from repo
root with .venv/bin/python tools/code_underscore_weight_study.py. The preceding
trials/2026-11-16-code-delimiters position-study VF is required. Matched PNG/PDF
exports use tools/render_svg.py. Existing OFL.txt and NOTICE.txt apply.
