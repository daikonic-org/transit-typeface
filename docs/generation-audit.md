# Review of the supplied Gemini guidance

> Historical audit of the pre-adoption versions. The accepted 72% weighting and current versions are documented in [weighting-adoption.md](weighting-adoption.md).
Reviewed against the actual source pipeline and the distributed Sans 0.106, System 0.115 and Code 1.015 files on2026-11-15. This is an audit, not an instruction to regenerate or replace the approved drawings. Font versions and outlines are unchanged by this repository/specimen publication.

## Main finding

The broad approach is useful: derive weights carefully, preserve counters and diamond details, fit Code to a fixed grid, distinguish ambiguous glyphs, and validate real text. Our implementation already goes beyond the supplied scripts in variable-master compatibility, width-preserving ligatures, caret metadata and source rebuild checks. The important remaining differences concern optical weight/counter balance, Code mark positioning, and style coverage. The pasted Python is not a safe drop-in build.

## Sans and System weight generation

| Topic | Supplied guidance | Current implementation | Assessment |
| --- | --- | --- | --- |
| Starting face | Metropolitan Line Regular | The same original Regular, preserved in `upstream/` | Aligned; actual UPM is1000. |
| Weight method | FontForge counter-aware weight change, or anisotropic offset with `ratio_y=0.72` | Historical Sans recipe: nominal Light−25, Regular0, original Bold+60; isotropic miter offsets, vertical refitting, topology checks and per-glyph reduced offsets where needed | Genuine algorithmic difference. Anisotropic growth is not an explicit0.72 parameter in that recipe. |
| Actual horizontal compensation | Grow horizontal crossbars by70–75% of vertical-stem growth | On Sans `H`, 400→600 grows the verticals110→150 (+40) and the crossbar100→132 (+32): **80%** | The output already has some horizontal compensation due to vertical refitting. It is less than the suggested compensation on this control glyph, not completely absent. The percentage is not uniform across glyphs. |
| Counter handling | Preserve counter size | Keep counter/contour topology, reopen specific apertures, reduce weight when topology fails; do not hold all counter dimensions constant | **Topology preservation is not counter-area preservation.** Sans `o` counter area decreases69,371.83→48,490.17 units² from 400→600, about30.1%. That is measurable contraction, not evidence by itself of illegibility. |
| Widths and bearings | Globally stretch3%, then add a fixed bearing allowance | Weight-dependent shifts/advance changes and component handling in the original proportional recipe; later System spacing/lowercase changes are deliberate, separately reviewed edits | Intentional difference. A global3% stretch would alter the accepted Regular and the font's proportions. |
| Diamond dots | Miter joins to retain sharp corners | Miter joins plus explicit diamond construction, punctuation repairs and per-glyph spacing | More specific than a join-style choice alone. |
| Kerning and marks | Keep proportional `GPOS` | Sans and System retain pair-positioning and mark-positioning lookup types2,4,5,6; original weight generation adjusts anchors for shifts | Aligned in intent. Keeping old positioning bytes unchanged after arbitrary scaling would not itself prove correctness. |
| Weight range | Regular/Bold400/700 | Sans/System300–600;700 intentionally removed after visual review. Code300–400 | Project decision, not an omitted automatic build step. The600 master was taken from the earlier variable design, not relabeled700. |
| Italics |10.5° Sans shear;11° Code shear plus small tails | No italic axis or italic faces distributed | Real coverage difference, explicitly documented. We have not presented a mechanical oblique as a finished italic. |

FontForge’s own documentation describes heuristic weight changes and says results need visual examination. Its Change Glyphs tools also distinguish stem changes from counter changes. The supplied description overstates how automatically a generic filter solves optical design. [FontForge: stylistic transformations](https://fontforge.org/docs/ui/dialogs/Styles.html), [Element menu](https://fontforge.org/docs/ui/menus/elementmenu.html).

The historical generation details above were inspected in the development pipeline’s `build_sans_family.py`, `build_cell_trials.py`, `polish_family.py` and `cap_transit_weight.py`. This repository starts from the resulting compatible current masters; the measured claims are reproducible with `python tools/audit.py`. Its portable rebuild does not pretend to regenerate all historical manual choices from a single upstream Regular.

## Code engineering

| Topic | Current evidence | Assessment relative to the guidance |
| --- | --- | --- |
| Fixed grid |1000UPM,600-unit cell, `post.isFixedPitch=1`, VF `OS/2.xAvgCharWidth=600`; shaping tests cover each operator sequence | Aligned. Ligature glyphs intentionally have1200/1800-unit advances. |
| Wide glyphs | Stroke-aware horizontal fitting uses scale plus compensating outline expansion and topology checks; the historical fitter has an explicit simple-scale fallback | More careful than the pasted uniform compression, but historical fallback use is a genuine item for targeted review. Do not claim every outline received identical compensation. The currently distributed600-cell family is the reviewed result. |
| Narrow glyphs | Reviewed `i`, retained `l/j`, widened `s/f/t`, barred `I`, selected flag/pedestal `1` | Already addressed by drawing, not merely centering a narrow shape. |
| Zero | Three contours, including a diamond dot; `O` has two | The requested diamond-dotted disambiguation is already present. |
| Ligature implementation | `calt` contains direct, full-span ligature substitutions. Twelve ligatures have GDEF carets at600, or600/1200 | No zero-width `LIG` placeholder is required. A multi-cell ligature does not inherently shrink the line. Caret behavior also depends on the application; it is not guaranteed by a placeholder trick. [OpenType GDEF](https://learn.microsoft.com/en-us/typography/opentype/spec/gdef). |
| Arrows | User-selected concave, acute, extended-wing heads; double rails match equals clearance; `->>` keeps two successive heads | Intentional departure from the guide's generic45° geometric chevrons. Preserve the selected design. |
| Punctuation/operators | Larger, separately reviewed symbols, consistent equals/triple-equals gaps, operator alignment and diamond punctuation | Already implemented through design and shaping tests rather than a blanket15–20% scale. |
| Positioning | Current Code has no `GPOS`. Precomposed accents are present; HarfBuzz composes `a+acute` and uses fallback positioning for `q+acute` | **A genuine limitation to review.** Removing all `GPOS` loses mark attachments as well as kerning. A future change should consider retaining/adding mark positioning while suppressing pair kerning, with tests across clients. [OpenType GPOS](https://learn.microsoft.com/en-us/typography/opentype/spec/gpos). |
| PANOSE | Family type0 and proportion0, rather than a Latin-text monospaced classification | Optional classification is unknown, not a missing mandatory monospace flag. The font is already recognized as fixed-pitch by tested clients. A metadata cleanup could supply a coherent PANOSE classification; do not blindly set one field while leaving its family type unknown. |

The current Book 350 shaping probe returns `aacute` with advance600 for decomposed `a+acute`; `q+acute` returns `q` advance600 and a zero-advance mark with offset(−602,22). Thus it would also be wrong to claim that every decomposed accent necessarily consumes two cells. These observations are HarfBuzz-specific, not proof of equivalent placement in every editor.

## Concrete problems in the pasted scripts

1. **Unsupported stroke call.** Installed skia-pathops 0.9.2 exposes `Path.stroke(width, cap, join, miter_limit, dash_array=None, dash_offset=0)`. The pasted `pen=` keyword raises `TypeError`. Stroking mutates a path: use a copy for the edge and retain the original fill. Our historical implementation does that. [skia-pathops source](https://github.com/fonttools/skia-pathops/tree/main/src/pathops).
2. **Composite glyphs are not empty glyphs.** TrueType composites have negative contour counts. Skipping every `numberOfContours<=0` bypasses their geometry and component transforms, even though the scripts change widths and component bases. Our proportional builder handles components recursively; current masters contain the reviewed compatible result.
3. **Curve conversion is underspecified.** PathOps stroke output can need conic/cubic handling before conventional quadratic `glyf` output. Our build uses explicit conic conversion and `Cu2QuPen`, then compatibility conversion across masters.
4. **`glyf` is not every OTF.** These examples address TrueType-outline fonts; a CFF/CFF2 OTF needs a separate outline path. Our checked inputs/outputs are TrueType outlines.
5. **Counter preservation is not delivered by a3% stretch.** It expands existing strokes/counters horizontally but offsets still reduce counters. The claimed exact baseline/cap-height restoration also needs actual bounds refitting after offsetting; inverse scaling alone does not undo the new overshoot.
6. **Deleting all `GPOS` is too broad.** This is a shared limitation of the current Code build, not just a fault in the example. Review positioning types separately.
7. **Fixed italic kerning is not automatically correct.** Shearing/scaling outlines while leaving anchors or pair values untouched can change placement and clearances. An oblique is a useful trial, not a completed optical review. [FontForge: italic versus oblique](https://fontforge.org/docs/ui/dialogs/Styles.html#italic).
8. **Partial naming edits can collide.** Family/subfamily edits need consistent unique/full/PostScript identities, style bits and variable metadata. The small scripts update only subsets of these; later attachment examples improve this but still lack the current multi-master validation.
9. **Numeric settings are starting points.**32units,72%,3%,315-axis and45° should not override actual glyph measurements or the accepted design. At2048UPM, exact scaling is×2.048; a600/1000 cell becomes1228.8 units before rounding.

## Recommended next work, without replacing this release

1. If600 still feels dense, make a controlled anisotropic/counter-opening trial for Sans/System at fixed perceived vertical weight. Compare `a/e/o/s` and acute joins against the current400/600 exports. Measure counter apertures and look at 14–18px text before choosing a recipe.
2. Review Code combining marks and PANOSE metadata in a separate version. Preserve the existing600-unit ordinary cells, ligature widths/carets and reviewed symbols.
3. Treat italics as a separate design task. Do not publish synthetic700 or italic files just to fill a four-style template.

For the deeper source/weight chain and new executable Regular-anchored recipes, see [scaling lineage](scaling-lineage.md). Code static snapshots have `xAvgCharWidth=620` because fontTools averages unencoded multi-cell ligatures too; every encoded ordinary character still advances600. That summary field is not the cell-width test. [OpenType OS/2](https://learn.microsoft.com/en-us/typography/opentype/spec/os2#xavgcharwidth).

The reference panels are visual specimens, not claims of reading-speed testing, full-language coverage, hinting parity with mature coding fonts or all-platform compatibility. Binary/source/shaping evidence is in `qa/`; measured geometry is in [measurements.json](measurements.json).
