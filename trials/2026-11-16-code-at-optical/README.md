# Code: larger @, o-weight outer loop and thinner inner a

Review candidate only; installed local preview remains1.020.

The original @ silhouette scales uniformly1.09 on both axes, centered against o.
At Book the final bounds are x11..589,y-11..541. The o is y2..528: @ extends13
units above and below, about5% greater total height. This is isotropic enlargement,
not vertical stretching. Width remains inside the600-unit cell at every weight.

The inner edge of the outer loop moves inward to match the corresponding o
vertical/horizontal strokes. Book o measures95.00 vertically and89 horizontally;
@ measures95.00/94.87 on left/right and89.00 at bottom/top. The source outer curve
retains its uniformly enlarged silhouette. Corrections ease into the tail/inner-a
junction, where the design transitions to its thinner interior stroke.

The inner a counter and arch are corrected separately, targeting55% of o's
corresponding stem/bar weight at each master. This is a local optical correction,
not whole-symbol thinning. Source curves, point correspondence and600-unit advance
are preserved. Lowercase/uppercase, selected delimiters, hyphen, underscore,
k/K placement, arrows and other glyphs remain unchanged.

Daikonic Transit Code Optical At Study includes VF300–400/defaultBook350 plus
Light/Book/Regular snapshots. Four binaries pass OTS. Eleven interpolation checks
verify contour topology, isotropic silhouette proportions, above/below-o extent,
centering, cell advance, main outer strokes within3units of corresponding o strokes,
and exact unrelated drawings/variations/layout/metrics except at's new sidebearing.
validation.json contains the measured values. Curve joins and the tail are optical
transitions; cardinal measurements do not claim every oblique section is identical.

Book.png/pdf/svg shows before/after with o guides; Comparison.png/pdf/svg covers
all3named weights and both polarities. Browser.png shows real loaded fonts at
13/14/16px in Chrome157, device scale2 (both loads passed). Images were opened
and visually reviewed. Terminal/editor rendering has not been checked.

Editable source: tools/code_at_optical_study.py. The shared font builder now lives
in tools/code_at_study.py; archived copies are included here. The shared builder
was checked to reproduce the prior1.020 trial glyf/gvar/hmtx/GSUB/GPOS/GDEF/HVAR
exactly. Run from repository root with .venv/bin/python tools/code_at_optical_study.py;
existing shared tools/ helpers and prior trial fonts are required. Render editable
SVG proofs with tools/render_svg.py. Previous trials remain preserved. No install,
commit or public release occurred for this candidate. OFL.txt/NOTICE.txt apply.
