# Code: larger @ with matching inner and outer strokes

Review candidate only; installed Code remains local preview1.020.

The fresh spiral centerline enlarges1.06 equally on both axes. Stroke width is
held fixed, so Book's final silhouette grows from590x597 to620x628 units (about5%
larger ink dimensions). Book bounds are x-10..610,y-49..579, centered against o.
Both the a and loop use80% of o's corresponding directional stroke widths:
Book76vertical/71.2horizontal. The previous45% a and weight taper are removed.
This is a uniform stroke rule; ordinary overlapping joins can read darker.

The normal drawing overhangs its600-unit advance slightly. At adjacent @ symbols,
calt selects at.compact, an equally weighted590x597 form, so @@/@@@ stay separate.
The compact form uses the same proportions and stroke rule; every advance stays
600. The adjacency scan over ASCII at300/350/400 found only @ requiring this
fitting. CompactContext.fea contains the added rules. With calt disabled the wide
forms can touch in repeated @; actual editor shaping remains to be checked.

Daikonic Transit Code Uniform At Study contains VF300–400/defaultBook350 and
Light/Book/Regular snapshots. Four files pass OTS. Eleven interpolation positions
check topology, bounds, advance, construction fidelity, repeated-symbol alternate
selection and retained operator/letter shaping. Existing GSUB lookups are retained;
compact context lookups are appended to calt. Other drawings/variation functions,
GPOS and metrics are unchanged except at's bearing and the appended alternate.

Book.png/pdf/svg compares before/after. Comparison.png/pdf/svg covers all named
weights in both polarities. Browser.png shows actual loaded fonts at13/14/16px
in Chrome157, device scale2; both faces loaded and images were visually reviewed.
This has a larger presence and matching interior/exterior stroke treatment.
It is a review drawing, not an installed or released update.

Recipe: tools/code_at_uniform_study.py, with shared code_at_redraw.py and
code_at_study.py. Archived copies are included. Run from repository root with
.venv/bin/python tools/code_at_uniform_study.py; existing tools/ helpers and
preceding trial binaries are prerequisites. Editable SVG specimens and TTF
snapshots are included. Previous cuts remain preserved. OFL.txt/NOTICE.txt apply.

NamedWeights.png/pdf/svg shows Light300, Book350 and Regular400 side by side,
using the same VF at matching positions with enlarged samples and real-size
email/decorator/repeated-at examples in both polarities. The image was opened
and reviewed. Rebuild with tools/code_at_weight_proof.py.
