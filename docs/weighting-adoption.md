# Accepted 72% weighting

The reviewed weighting trial is adopted in **Sans 0.107, System 0.116 and Code
1.016**. This is the same corrected PathOps approach tested in
[the all-weight trial](weighting-trial.md), at horizontal expansion ratio 0.72.
Regular is the source anchor; all other weights derive directly from it with
declared target stems. System retains its enlarged lowercase and optical-size
design, applying the accepted weighting at opsz10,14,36.

## Sources and reproducibility

`sources/weighting-baseline/` freezes the prior reviewed VFs and their hashes.
The generation recipe reads these inputs, not the already reweighted output.
This prevents cumulative offsets on subsequent runs. The accepted trial remains
recorded in `docs/weight-study-approved-regular-ratio-0.72.json`.

Compatible masters were constructed with the existing contour/corner matching
algorithm, shared in `tools/compatibility.py`. Each named weight is now a source
location: five Sans masters, fifteen System weight/optical masters, three Code
masters. Compatibility conversion is checked against every reweighted glyph at
every source location using raster coverage; the permitted difference is 2.5%,
with actual per-glyph results in `qa/*/weighting-fidelity.json`.

Selected glyphs retain the **original glyf and gvar data**, so their interpolation
is preserved throughout the axes rather than merely matching at named weights.
This includes the declared numeral, i/j/l/y and arrow/ligature overrides. The
previously tuned Unicode punctuation and symbol drawings are also retained at
each weight. A final standalone/ligature comparison caught a mismatch between
the generic filter's `=` and the preserved `==`; single horizontal symbols can
also lose intended weight changes when their height is refitted to Regular.
Keeping the tuned symbol repertoire avoids both problems and preserves the
diamond punctuation. The 72% letterforms remain the approved trial drawings.
Code's interpolation regression compares `=`, `==` and `===` bar thicknesses.
The
original GSUB/GPOS/GDEF and metric variation functions are retained, preserving
spacing even where adding rounded intermediate masters would introduce a
one-unit advance difference. `tools/weighting_support.py` applies this shared
postprocessing to both production and repository rebuilds.

`python tools/pipeline.py approved` rebuilds the adopted VFs from compatible
TTF masters, preserved layout/metric inputs and metadata. Static releases are
actual snapshots of the resulting VFs. `python tools/pipeline.py study` uses
the accepted 0.72 default and the frozen Regular baselines; explicit `--ratio-y`
can still generate alternatives. `adopt_weighting.py` records the construction
of this adoption; it stages outputs separately before `promote_weighting.py`.

Editable UFO/designspaces and Glyphs sources accompany the masters. System's
complete Glyphs file exceeds GitHub's individual file limit, so it is stored as
`DaikonicTransitSystem.glyphs.zip`; extract that archive before opening it.
The uncompressed UFO/designspace sources remain directly editable.

## Checks

- OTS on every variable/static TTF and variable WOFF2.
- Exact production static/VF snapshot and repository rebuild parity.
- Nine weight locations in Sans, seven in Code, and nine weights by five optical
  sizes in System: **61 interpolation locations** total.
- Original advances and layout preserved at every sampled location; control
  counter topology and all twelve arrow forms checked between masters.
- Selected glyphs exactly match the original drawings at all 23 named profiles;
  the original selected-glyph variation functions are copied in full.
- The ongoing interpolation check compares complete selected-glyph `glyf/gvar`
  functions and retained layout/metric tables directly, then evaluates actual
  variable glyph sets and HarfBuzz shaping at all 61 locations. Full named static
  instances are checked separately. This avoids repeatedly instancing unused
  glyphs while preserving the coverage of the interpolation checks.
- Every Code operator ligature retains exact cell totals and caret metadata;
  System retains its selected tabular `1` substitution.
- Independent fontmake builds of the editable UFO/designspaces cover every
  named weight/optical profile. Control outlines must remain within 2.5% raster
  coverage difference. Independent compiler rounding can change a System
  advance by **one font unit**; production TTF rebuilds retain exact advances.

The comparison corpus includes H/n/o/a/e/s/f/t, accented forms, selected glyphs,
words, figures and punctuation, in both polarities at 14–43px, plus intermediate
weight/optical-size samples. Proofs use actual VF outlines and HarfBuzz shaping.
Observed letterforms retain the approved 72% trial appearance at named locations;
intermediate controls are reviewed for smooth visual changes. This is a bounded
local visual review, not a measured reading-performance or all-platform claim.

Previous release tags and the original development workspace remain unchanged.
Earlier QA files describe their recorded prior versions; the `weighting-*`
reports and current `repository-validation.json` cover this adoption.
