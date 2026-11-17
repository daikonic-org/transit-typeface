# Code: single-storey a inside @

Review candidate only; installed preview remains1.020.

Changes only the construction inside @: a single rounded bowl and upright stem
replace the double-storey bowl/arch. A cubic ellipse (radii89/110 in the original
centerline coordinates) forms the counter, with the upright terminal aligned to
its top. The normal lowercase a is unchanged. Outer spiral, overall size,
centering, matched inner/outer stroke treatment and600-unit advances are retained.

The primary silhouette remains about620x628units at Book. Both inner and outer
use80% of o's corresponding stroke weights. Repeated@@/@@@ retain the contextual
compact fitting, now with the same single-storey interior. The large form has
slight ink overhang; repeat fitting requires calt. Old double-storey trial remains
preserved. No font installation, commit or public release occurred.

Daikonic Transit Code Single Storey At Study includes VF300–400/defaultBook350
and Light/Book/Regular snapshots. All4fonts pass OTS. Checks at11weights verify
outline/counter topology, dimensions, fixed advances, direct construction fidelity,
repeat alternates and retained operator/letter shaping. The shared builder keeps
unrelated drawings/variation functions/layout/metrics except at's new bearing and
its compact alternate/context rules.

Book.png/pdf/svg compares double/single-storey at Book. Comparison.png/pdf/svg
covers all named weights in both polarities. NamedWeights.png/pdf/svg shows the
single-storey form alone across300/350/400. Browser.png uses actual loaded fonts
at13/14/16px in Chrome157, device scale2; both fonts loaded. Images were opened
and visually reviewed. The single-storey counter stays more open at Regular,
with a less crowded interior. Actual terminal/editor behavior remains unverified.

Editable recipe: tools/code_at_single_storey_study.py. It uses shared drawing,
font building, validation and proof helpers; archived copies are included here.
Run from repository root using .venv/bin/python tools/code_at_single_storey_study.py.
The repo's other tools/ helpers and prior trial binaries are prerequisites.
NamedWeights proof uses code_at_weight_proof.main(out=OUT,
stem='DaikonicTransitCodeSingleStoreyAtStudy'). SVGs and TTF snapshots are editable.
OFL.txt and NOTICE.txt apply.
