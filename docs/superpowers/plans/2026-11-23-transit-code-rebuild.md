# Daikonic Transit Code Rebuild Implementation Plan

**Goal**

Build a reviewable upright and italic Transit Code from the released 1.0.0 Sans curves while retaining the typography and shaping behavior of Code 1.042.

**Architecture**

Build the Code alphabet from released Sans curves and reusable letter parts. Reuse the shared arrow drawings from released Sans or System. Treat Code 1.042 as the reference for geometry, advance widths, feature defaults, and shaped output. Review alphabet construction, Code-specific forms, and OpenType layout in sequence, then add the width axis and validate the compiled fonts.

**Tools**

Use the repository’s pinned Python environment, FontTools, HarfBuzz, OpenType Sanitizer, and the shared Transit inline glyph proof.

## Release contract

| Property | Measured Code 1.042 baseline |
| --- | --- |
| Character coverage | 433 encoded characters in each style. Includes all 427 Sans characters plus `¬ ∀ ∃ ≠ ≤ ≥`. |
| Design units and proportions | 1043 UPM, declared cap height 700 and x-height 530. Released Regular ink heights are 676 for `H` and 506 for `x`, versus 700 and 475 in Sans at 1000 UPM. Released vertical metrics are 950/−253 in both Code styles. |
| Weight anchor | The rebuild uses Sans Regular 400 as the drawing anchor for Code Medium 500 and derives Code Regular and Book from it. |
| Styles | Upright and a separately calibrated Code Italic. The 1.042 binary declares −9°, and measured long stems run close to 9° from vertical. Review the intended Code-specific slant against that baseline. Combining marks have zero advance and depend on `mark` and `mkmk`. |
| Intentional advance differences | At Normal width, `::` is one cell upright and two italic. `===` is two cells upright and three italic. `=>` is two in both styles. `\forall` takes seven cells in both styles. Carets and trailing text must follow the actual shaped width. |

Use 1.042 as the feature contract and as the comparison for ink size, apparent weight, and centering. Treat its released vertical metrics as the initial target and report any clipping that would justify changing them. Check ordinary grid advances, contextual offsets, and shortened ligature clusters against their respective reference behavior. Carry forward the two-axis design, stylistic-set IDs, and existing editor defaults.

### Axis inventory

| Tag | Upright and italic range, with default in bold | Named locations and behavior |
| --- | --- | --- |
| `wght` | 350–500, **400** | Book 350, Regular 400, Medium 500. The regular italic instance is named Italic. Audit stroke, counters, mark positioning, and ligature components. |
| `wdth` | 94–108, **100** | Narrow 94, Normal 100, Wide 108 with 564/600/648-unit cells. The variable fonts’ named `fvar` instances use Normal width. The static package supplies the nine weight/width combinations per style. Audit outline compensation, cell advances, offsets, and carets. |

Italic is a separate face identified by `ital=1` in its `STAT` table. The adjustable controls come from `fvar` and are the same for both faces.

### OpenType feature inventory

The 1.042 tables register these tags in both the `DFLT` and `latn` default language systems. Record default behavior from shaping, including where an application controls activation of a standard feature.

| Tag | Where it is registered | Behavior to record |
| --- | --- | --- |
| `ccmp` | GSUB, both styles | Glyph composition and decomposition with precomposed and combining character controls. |
| `calt` | GSUB and GPOS, both styles | Contextual substitutions and positioning, including generic angles, lifetime marks, delimiter alternates, and shortcuts. Compare the default run with the tag disabled. |
| `liga` | GSUB, both styles | Standard ligatures, paired stems, and supported programming sequences. Compare input clusters, advances, and carets with the tag on and off. |
| `kern` | GPOS, italic | Italic pair adjustments and their effect on offsets and advances. |
| `mark`, `mkmk` | GPOS, both styles | Base and ligature mark attachment, stacked marks, and variable anchors. |
| `ss02` | GSUB and GPOS, both styles | Opt-in Logic enclosures and logical negation. Test comparisons, literals, and macros as controls. |
| `ss03` / `ss04` | GSUB, upright | Texture Healing enable and disable controls. Texture Healing also runs by default. |
| `ss05` / `ss07` | `ss05` in GSUB and GPOS; `ss07` in GSUB, upright | Hairlining enable and disable controls. Hairlining also runs by default. |
| `ss06` | GSUB, upright | Opt-in Loose Equality and its one-cell advances. |

Inventory `GDEF` alongside the feature tags. Both styles have glyph classes, ligature carets, and a variation store. Cross-reference these with the layout features that use them.

## Implementation stages

### 1. Record the reference before changing any drawings

The [Stage 1 inventory](../../code-rebuild-inventory.md) records the released baseline, the donor generators, and the pair positioning checks. The reproducible output includes a sortable per-glyph index.

**Files**

Add `tools/check_code_rebuild.py` and `recipes/code-rebuild.json`. Read the paired Sans VFs at `releases/1.0.0/sans/VF/`, the shared arrow donors in `releases/1.0.0/system/VF/`, and Code VFs at `releases/2026.11.20/code/VF/`. Keep reference and candidate reports under `.build/code-from-sans/`.

- [ ] Record input SHA-256s and actual binary metadata. Inventory Unicode, mark classes, and glyph roles by style.
- [ ] Record each axis’s source, range, default, named coordinates, `STAT` labels, and mapping. Identify what varies at the endpoints and between masters, which controls affect outlines or advances, and which positioning data is axis-dependent.
- [ ] For each feature, record its tag and label, style and script coverage, lookup order and dependencies, default or optional activation, affected glyphs or collections, and interaction with coordinates and other features. Attach a shaping example and a control that exercises the same text with the relevant toggle changed. Record the corresponding advance, offsets, and caret behavior where applicable.
- [ ] Produce a glyph construction inventory grouped by how each drawing comes from Sans. Use groups for direct donors; donors with changed proportions, stroke, placement, or advance; drawings assembled from parts; Code-authored forms; and generated contextual forms or lookup states. Place the shared Sans/System arrows under reused drawings. Group glyphs that share the same recipe and list exceptions individually.
- [ ] For each glyph or collection, list the output names and style, exact donor glyphs and family, the parts and transformations in order, and its dependent accents, variants, or ligatures. Label source history that can be verified and identify proposed reconstructions separately. For example, list Code `r` as a letter assembled from Code `n`, with a link back to `n`’s Sans-derived construction and a note on where the `r` terminal is cut.
- [ ] Capture HarfBuzz results by input, style, weight, width, and feature settings. Record source cluster, glyph role, cell span, advance, and offset. Compare by role and Unicode so renamed glyphs remain testable. Capture a literal control for every contextual rule.
- [ ] Include ordinary code, accented text, protected character literals, lifetimes, matched and unmatched generics, long/nested generics, empty groups, operator sequences, symbol shortcuts, and independent feature toggles. Include one run of ordinary text after a compact operator to catch displaced columns or carets.
- [ ] Confirm the report detects an altered cell advance, a missing combining anchor, and an unexpected default substitution using temporary copies. Verify that a reference-versus-itself comparison passes before introducing the candidate.

**First output**

A construction map grouped by derivation, an axis inventory, an OpenType feature inventory, and the 1.042 shaping reference. Cross-reference the feature cases to the affected glyph collections and the axis coordinates where they are checked.

### 2. Build the core Code alphabet with shared rules

**Files**

Add `tools/build_code.py` as the orchestration entry point and `tools/code_foundation.py` for letter construction, weight calibration, and grid metrics. Reuse the outline and variation utilities in `tools/font_feature_tools.py` and the recorded lineage in `docs/scaling-lineage.md`.

- [ ] Establish Sans Regular 400 as the curve and weight anchor for Code Medium 500. Use the compatible Sans weight deltas for Code Regular and Book. Apply the same Code construction rules independently at each master, then interpolate the resulting compatible outlines. Compare `H n o` stems, counters, and rendered code in the three weights.
- [ ] Construct uppercase and lowercase Code forms on the normal 600-unit cell. Apply the 1043 UPM design-size calibration and the lowercase x-height adjustment as separate decisions. Compare actual `x n o` ink against the baseline and capital ink against `H`; review the lowercase-to-capital relationship and the effect at the same nominal pixel size. Use the declared metrics for layout validation and measured ink for outline construction.
- [ ] Use the same horizontal stroke-compensation primitive as the System width axis when a drawing needs narrowing. Solve for the width the Code cell can hold at each master. Use this pass to evaluate the shared rules before the custom letters.
- [ ] Produce a core upright candidate for reviewing the alphabet and grid. Compare capitals, lowercase, digits and accents at 12–16 px over Book, Regular and Medium. Include `I l 1 i j g a y w m n r s f t 0 O` and identify any alternate or punctuation work that follows in stage 3.
- [ ] Verify one-cell ordinary advances, zero-advance combining marks, equivalent NFC/NFD placement, interpolation, and bounds. Retain Code-specific sidebearing and advance exceptions only when the measured release or the review explains them.

**Review point**

Approve the built alphabet, the x-height and weight calibrations, and the normal grid before building punctuation or contextual features. This is the first candidate worth comparing directly to 1.042.

The shared-rules candidate and 12–16 px comparison are available under `.build/code-from-sans/alphabet/`. Run `.venv/bin/python tools/build_code.py --output .build/code-from-sans/alphabet --render` to reproduce them. The candidate carries the three weight masters and the Normal-width grid. Code 1.042 enters the build command at the measurement and proof stages.

### 3. Rebuild Code drawings and their dependents

**Files**

Add `tools/code_outlines.py` as the Code drawing stage. Reuse compatible constructions from `tools/code_punctuation_size.py`, `tools/code_receiver_shapes.py`, `tools/repeated_stems.py`, `tools/italic_companions.py`, and the existing delimiter, lifetime, and operator tools.

- [ ] Build custom alphabet shapes through the construction inventory. Build `n` before `r`, reuse the relevant stem and shoulder from `n`, and draw and proof the terminal in the Code cell. Apply each construction at the individual masters and build accented and contextual dependents from the reviewed letters.
- [ ] Finish the Code numeral and character distinctions around the reviewed alphabet, including the diamond-centered zero, raised gapless underscore, open two-storey `@`, widened hyphen, and revised punctuation and delimiters.
- [ ] Reuse the released Sans/System arrows for Code’s Unicode arrows and, where applicable, the same arrowheads and shafts for operator ligatures. Choose the donor per arrow family in the inventory and adapt placement and advance to Code. Review optical balance at the operator axis and keep the established cell counts and carets for each token.
- [ ] Build the six Code-only characters, tall angles, contextual pipe forms, delimiter echoes, Rust lifetime marks, and non-arrow operators from the reviewed base drawings. Use components for repeated primitives and derive ligature contours from those parts. Review custom paths individually against 1.042.
- [ ] Set up an angle proof for Code Italic before producing its full masters. Measure long stems against 1.042 and show a Code-specific slant comparison with `H I n r`, upright/italic code text, punctuation and overhangs. Use the approved Code angle across its drawings and metadata. Adapt the released Sans Italic curves and reuse the Code alphabet constructions, cell and accent rules. Preserve the Code italic forms and grid-aligned `ff`, `tt`, and `ll` pairs.
- [ ] Review base drawings, figures, punctuation, symbols and accents in the shared proof. Check outlines for clipping, detached parts, unwanted intersections, and unexpected weight jumps. Apply corrections to the shared primitive or class when it has the same defect across dependents.

The composed review builds `r`, `∀ ∃ ¬ ≠ ≤ ≥` before compiling the variable font. Run `.venv/bin/python tools/build_code.py --composed --output .build/code-from-sans/composed --render` for the alphabet and composed-glyph proofs. The comparison symbols use the foundation operators for this review and will pick up their revised proportions when those operators are rebuilt.

The lowercase review adds the Code `i` with its shared dotless body and both upper hook curves taken from the lower return of `l`. The approved `a` uses the calibrated width scale of `s`. The normal `m` and `w` keep their foundation drawings. Run `.venv/bin/python tools/build_code.py --letters --output .build/code-from-sans/custom-lowercase-rounded-hook --render` for the alphabet and detail proofs.

The crossbar proof widens `t` to the ink width of `n` and builds `f` from the vertically flipped `t` return. Joined letters retain their own donors until the shaping review. Run the same `--letters` build with `--output .build/code-from-sans/custom-lowercase-ft` for the full review set.

**Review point**

Approve the recognizable Code drawings and italic at Normal width. Compare preview VFs side by side with 1.042 before tuning optional features.

### 4. Rebuild the order-sensitive shaping layers

**Files**

Add `tools/code_layout.py` as the candidate layout entry point. Reuse the existing rule construction in `tools/code_angle_pairs.py`, `tools/code_lifetime_hook.py`, `tools/code_structural_fit.py`, `tools/code_logic_shortcuts.py`, `tools/code_compact_operators.py`, `tools/code_texture_healing.py`, and `tools/code_hairline_toggle.py`. The candidate checker lives in `tools/check_code_rebuild.py`.

- [ ] Parameterize the reusable stages to accept the candidate and stable glyph roles. Some current helpers take historical paths or assert exact old curve data. Keep those archival checks and reuse their shaping cases in the candidate comparison.
- [ ] Wire base substitutions and mark attachment, then matched delimiters and Rust lifetimes, operator compaction and Logic, then texture and hairline variants. Use the release traces to establish lookup priority and preserve existing interactions, including mixed enclosures, turbofish and compact scope, logical-not and inequality, protected literals, and opt-out substitutions.
- [ ] Rebuild variant substitutions, positioning and GDEF carets together. Check exact consumed cells, text clusters, following-character placement, and caret order. Measure positioning against the grid and require unchanged behavior for literal controls. For offsets affected by a redesigned outline, record the measured difference in the candidate report for review.
- [ ] Run the released feature cases for both styles and verify opt-outs independently and in combination. Explicitly test generic nesting through depth 16 and the 60-glyph boundary, plus inputs just beyond those limits. Verify spaces and line breaks do not pull adjacent source columns out of alignment.
- [ ] Proof narrow overlap cases such as `|_|`, `|w|`, `|K|`, `[K]`, `{K}`, repeated `@`, nested closers, and lifetime/quote neighbors. Test shaped offsets and ink intersections. Resolve spacing collisions without importing proportional-font kerning or erasing intentional inline strokes and joins.

**Review point**

Approve the behavior and the code-text proofs. Give special attention to the default/opt-out comparisons and upright-versus-italic advance differences.

### 5. Add width, validate installed formats, and prepare the release

**Files**

Reuse `tools/transit_width_trial.py`, `tools/code_weight_width_trial.py`, `tools/system_metrics.py`, `tools/glyph_proof.py`, and `tools/proof_site.py`. Stage with `tools/stage_typography.py` and `tools/bundle_release.py` after the candidate is approved.

- [ ] Add the 94–108 width axis with Normal 100 as the default. Preserve the approved Normal outlines. Verify 564/600/648 advances, intermediate widths, x-offsets, ink clearances, mark anchors, and caret scaling. Carry existing stroke compensation where it passes the updated drawings.
- [ ] Verify both styles at weights 350, 375, 400, 450 and 500 across widths 94, 100 and 108, plus intermediate width instances. Capture ascent/descent extremes and confirm the same usable line metrics in both faces. Run OpenType Sanitizer and compare variable, static and webfont shaping at their common coordinates.
- [ ] Generate a local inline proof with the rebuilt VFs and open the coverage groups, individual glyphs, and axis comparisons. Add sample code in its intended styles and widths. Test actual selection, cursor placement and column alignment in a browser/editor and in a fixed-grid terminal; include Narrow Regular as the established Ghostty configuration.
- [ ] After approval, stage Code as a separately identified release candidate. Check nine static weight/width combinations per style, all 18 TTC faces, the editable TTX rebuild and the package checksums. Verify current-head GitHub checks and the installed font names and axes before publishing the approved candidate and switching the hosted Code proof.

## Proposed review build

The following are the planned entry points for the candidate. Each stage should be invocable with review artifacts without changing release selections.

```sh
.venv/bin/python tools/check_code_rebuild.py --record .build/code-from-sans/reference.json
.venv/bin/python tools/build_code.py --recipe recipes/code-rebuild.json --output .build/code-from-sans
.venv/bin/python tools/check_code_rebuild.py --reference .build/code-from-sans/reference.json --candidate .build/code-from-sans
```

Use a separate commit for each reviewed stage. Leave the 1.042 download and its local comparison available through the candidate review.
