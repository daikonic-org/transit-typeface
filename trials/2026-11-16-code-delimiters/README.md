# Code delimiter, underscore and positioning trials

Review candidates only. Released/installed Code remains 1.017; Sans 0.109 and System 0.117 are unchanged.

## Delimiter candidate

Daikonic Transit Code Delimiter Study: variable weight 300–400, default Book 350,
plus Light, Book and Regular snapshots. Builds on the selected i trial (right base
+40 units; shaft/top/dot +24 right). Plain i only; accented/dotless alignment
remains a production adoption task.

Parentheses, square brackets and braces grow by 12/14/16 units at Light/Book/Regular,
using the adopted 72% horizontal-bar weighting ratio. Opening marks move +14 and
closing marks -14 toward enclosed text. Bracket arms extend 28 units. The pipe
adds 8/10/12 units. All heights remain unchanged.

The brace keeps its existing curves and gains a horizontal nose extending 72
units beyond the weighted original pinch. Nose thickness is 72% of the weighted
quarter-height stem. There is no extra middle-weight treatment. This supersedes
the uniform centerline-stroke experiment; its editable recipe is retained in
recipes/previous-uniform-brace-study.py. JetBrains Mono 2.305 is a visual reference,
not a traced source.

The underscore spans x=0..600, with its bottom at baseline y=0. At Book its
thickness remains 80 units, and it moves +87 vertically. Repeated underscores
meet exactly at cell boundaries. PNG/PDF/SVG compare original, raised original
width, and raised full width; Light/Regular thicknesses remain 66/92 units.

## Separate positioning candidate

Daikonic Transit Code Position Study-VF contains the same drawing plus experimental
GPOS pair positioning under calt. For v/y/slash next to i/l, and the reverse,
letters move 18 units each toward the pair. Every character retains its 600-unit
advance. No joining ligatures or altered outlines are involved. Positioning.fea
is the editable rule source; turn off calt to compare, though this also turns off
existing Code contextual substitutions. Longer mixed strings are in the proofs.

GPOS positioning may behave differently across terminals/editors or syntax runs;
these applications have not yet been checked with this candidate. The modest
adjustment helps some gaps but is not a general kerning pass or a production
recommendation across all lowercase letters.

## Family audit

Sans already has GPOS kern/mark/mkmk and 16 lookups, including its latest hooked
ligature spacing. System has kern/mark/mkmk and 15 lookups. Released Code has
neither GPOS nor legacy kern; its operator substitutions are in GSUB. See
family-positioning-audit.json for exact source hashes and lookup inventory.
Presence of GPOS alone does not establish optical spacing quality.

## Review and validation

Comparison and BeforeAfter show delimiter shapes; Weights covers all three
named weights in both polarities. Underscore compares placement and width.
Positioning compares fixed-cell and adjusted samples. Each has matched PNG,
outlined vector PDF and editable SVG. Browser screenshots use actual loaded
fonts at 13/14/16px in Chrome 157 at device scale 2; all load statuses passed.
Images were opened and visually reviewed. Browser proofs are not terminal tests.

All five candidate binaries passed OpenType Sanitizer. Delimiter validation checks
11 interpolation positions, topology, outline fidelity, unchanged heights, fixed
600-unit advances, empty-pair gaps, and exact retention of unrelated drawings,
variation functions and layout. Positioning validation checks 11 weights and
14 strings with calt on/off: unchanged glyph identities and 600-unit advances.
Its glyf/gvar/hmtx/GSUB/GDEF/HVAR tables match the delimiter candidate exactly.

## Editable construction and packaging

recipes/ holds the current Python recipes and the superseded uniform-brace recipe.
masters/ contains three editable TTF outline masters and their relative-path
designspace. The scripts use shared helpers from this repository's tools/;
run `.venv/bin/python tools/code_delimiter_study.py` from the repository root.
The selected-i trial is a prerequisite. Reference fonts are local prerequisites
for reference proofs and are not bundled. Run tools/render_svg.py on the generated
SVG files for matched PNG/PDF exports. The ZIP contains these fonts, proofs,
recipes, masters, validation records, notes and licenses. No install or release
has been performed. Sources and earlier trials remain preserved.
