# Code: raised @ with lighter interior a

The @ translates upward24 units: bounds y=-12..494 become12..518, aligning with
flat lowercase x-height. Overall height and width remain unchanged. Round n/o
retain their existing10-unit top overshoot. The600-unit cell is unchanged.

Only the interior a is lightened: its counter expands12 units per side, and the
inside of its top arch eases upward by up to10 units with a tapered correction.
At Book the counter expands72x48 to96x72. The outer loop is translated exactly,
retaining its stroke weight. Compatible original point structure is retained;
new at-only variation tuples are derived from300/350/400 masters. No general
stroke expansion/thinning or glyph scaling is used. Existing i, delimiters,
underscore, hyphen, k/K positioning and arrow ligatures are unchanged.

Daikonic Transit Code At Study includes VF300–400/defaultBook350 and Light,
Book and Regular snapshots. Four binaries pass OpenType Sanitizer. Checks at11
weights verify alignment, counter growth, topology,600-unit advance, exact outer
translation and exact unrelated glyph/variation/layout/metric table retention.

Comparison.png/pdf/svg compares original, raised-only and raised/lighter versions
at all named weights in both polarities. Browser.png uses actual loaded Book text
at13/14/16px in Chrome157, device scale2; all3font loads passed. Images were opened
and visually reviewed. The lighter counter reads more clearly in the Book proof;
actual editor/terminal rendering remains unverified.

Recipe: tools/code_at_study.py, archived here as recipe.py. Run from repo root
with .venv/bin/python tools/code_at_study.py; shared tools/ helpers and the previous
hyphen-k trial are prerequisites. SVG renders use tools/render_svg.py. Prior
iterations remain preserved. OFL.txt and NOTICE.txt apply.

Installed as canonical Daikonic Transit Code, version1.020 local preview; existing
Book350 editor settings retained. Prior1.019 preview backed up. CoreText font
registration refreshed and resolves1.020. Installation paths/hash recorded in
a local installation log excluded from Git. No repository commit or published release occurred.
