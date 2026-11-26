# Build and validation

Use Python 3.12 or newer. The checked production environment used Python 3.14, fontTools 4.68.0, skia-pathops 0.9.2, glyphsLib 6.17.2 and fontmake 3.12.2. Exact dependencies are in `requirements.lock`.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
python tools/build.py
python tools/validate.py --rebuilt
python tools/audit.py
python tools/specimens.py
python tools/release.py
```

`build.py` rebuilds each VF from the compatible TTF masters/designspace and `VariableMetadata.ttx` into `.build/`. Validation compares its outline, variation, metric, cmap and layout tables to the checked exports; sanitizes distributed TTF/WOFF2 files; verifies named static snapshots; and tests Code ligature widths, carets and System tabular figures. It does not overwrite released fonts.

The binary masters are the direct reproducible inputs for the current approved drawings. The preserved upstream Regular alone does not reproduce all subsequent manual letter, spacing, numeral, punctuation and arrow decisions.

Sans 0.109 adopts the selected hook ligatures with two explicit metric exceptions;
see [Sans hook sources and validation](sans-hooks.md). Its SOURCE archive includes
the same exceptions in the portable rebuild script.

## Transit Sans component baseline trial

Run from the repository root with the locked dependencies installed.

```sh
python tools/sans_baseline_trial.py .build/sans-component-baseline
```

The command rebuilds the reviewed upright variable font from the pinned Metropolitan Line Regular and [the Transit drawing and variation recipe](../sources/sans-component-baseline/TransitSans.ttx.gz). It verifies the variable font against the reviewed checksum and emits a Regular snapshot, the upstream reference, a component report and an outlined SVG specimen.

The recipe references upstream outlines and composites directly where their construction matches. It stores Transit-specific outlines, component definitions, weight deltas, metrics and shaping tables. The shared four-point `diamond.dot` supplies the dots in punctuation and accents. The `ai` and `li` construction starts with the `a`, `l` and `i` primitives, including the lower `l` hook that shapes the clearance under the `i`. [The ligature drawing script](../tools/hook_ligature_study.py) shows the joins and cuts. The recipe preserves the final outlines of those ligatures.

To refresh the recipe after approving a new component baseline, run `python tools/sans_baseline_trial.py --capture path/to/reviewed-VF.ttf`.

## Building the upright Sans candidate

```sh
python tools/build_sans.py .build/sans-upright
```

The builder starts from the Regular component baseline and moves its existing control points to generate the weight axis. It preserves square proportions, shared junctions and clearance. Subscript, superscript and other miniature forms use the same weighting rule with the weight change scaled by their Regular height relative to the full-size form. Relationships come from Unicode and OpenType substitutions. Pointed terminals retain their clearance where weighting would close an existing opening. When thinning breaks a terminal away, the builder restores its local taper. Archival artwork uses the Regular outline throughout the weight axis and follows the existing advance widths. Sans geometry classes live in `recipes/weights.json`. A class can select encoded characters with `codepoints` or source glyphs with `glyphs`. Standalone drawings can exclude the `wght` axis with `exclude_axes`. Use `exclude_transforms` to skip a shared pass, such as `aperture_clearance`, `contour_clearance` or `component_placement`.

Composites follow the weighted shapes they assemble. Facing edges guide component placement. Repeated components keep even spacing and the assembly retains its intended alignment. The comma and semicolon share their punctuation construction, approved mirror pairs share outlines, and minus, equals and division share a bar. The builder regenerates ligatures from current letters. Its outline audit compares structure across weights and reports changes for review.

The output includes the upright VF, static TTFs and OTFs, a TTC, WOFF2, rebuildable TTX source, a specimen and the glyph proof under `Proof/`. The italic and coordinated release have separate build steps.

## Glyph proofs

Sans, System, and Code use the same glyph-proof template. To generate a proof from any family’s TTF, run the shared proof builder.

```sh
python tools/glyph_proof.py path/to/Family-VF.ttf .build/glyph-proof
```

Pages compare the font’s named weights side by side, with guidelines for cap height, x-height, operator axis, baseline, descender, and advance or ink center. Categories cover uppercase, lowercase, numerals, applicable alternates, components, and composites of those components. Additional pages show ligatures and other punctuation, symbols, and numeral forms. The builder exports SVG and PNG pages and one vector PDF. Use `--review-glyph tcaron` to get a separate focused proof for a glyph under review.

Open `index.html` in the output folder to choose a page and zoom in the browser. Double-click a glyph row or choose a glyph from the **Glyph** menu to inspect it on its own. For the browser version and its SVG pages alone, use `--svg-only`. PNG and PDF exports use Chrome or the headless Chromium executable selected by `TRANSIT_CHROME`.

Add `--interactive-axes` to compare a variable font along any of its axes in the browser while choosing preset values or entering custom coordinates for the others. Choose **Type sample** to compare your own words with live OpenType shaping. **Show all presets** displays every combination of the proof’s axis stops. System builds enable this for both upright and italic. The PDF keeps its original coordinates.

The proof starts at the default optical size and width. Use `--axis opsz=12` for a different System optical size or `--axis wdth=94` for Code Narrow. Keep separate output folders for different styles or axis coordinates.

## Reviewing the upright Sans outlines

To review the complete outline pipeline without packaging a font, generate the proof and structural report:

```sh
python tools/build_sans.py .build/sans-direct-proof --direct-proof
```

## Building the upright-derived Sans Italic

```sh
python tools/build_sans_italic.py .build/sans-italic
```

The italic builder starts with the complete upright reconstruction, then applies the established 9° shear. Default and stylistic-set single-storey `a` share the same outline, with live accents. The cursive `g` joins the `q` bowl to a reflected `l` return whose tip continues along the curve approximately to the left edge of the slanted bowl. The descending `f` uses the reflected hook with its reach shortened by a fifth in `f`, `fi` and `fl`. The builder measures extra pair spacing around the longer return across the weight axis. The upright weight build pins authored x-height crossbar shoulders so the `fi` join stays level through interpolation. Live components retain their references through the shear. The output contains the variable TTF, a guided proof across the five weights, a text specimen and an audit of the components and advances.

## Checking pair clearance after outline construction

The local Sans builders run a shared kerning pass after the outlines, advances and existing positioning are ready. The same pass can run on the rebuilt System font.

```sh
python tools/kern_clearance.py input-vf.ttf review-vf.ttf
```

The pass checks all ordered pairs of spacing glyphs with ink, including alternates and ligatures. It honors each existing kerning route. It checks named instances and intervening weight and optical-size locations, adds positive clearance where outlines collide, and writes a JSON report beside the font. The changes use variable OpenType pair positioning. Outlines, advances, substitutions and mark positioning stay intact. The scan samples the continuous axes at the locations reported in JSON.

## Editing in Glyphs or UFO tools

Each `sources/<family>/` includes a `.glyphs` file, UFO masters and a native designspace. Open the Glyphs file directly, or independently compile it:

For the accepted weighting update, System's full Glyphs file is compressed as
`DaikonicTransitSystem.glyphs.zip`; extract it before opening. Its UFO/designspace
files are uncompressed. See [weighting-adoption.md](weighting-adoption.md) for
the frozen baseline and layout/metric preservation used by production rebuilds.

```sh
fontmake -g sources/sans/DaikonicTransitSans.glyphs -o variable \
  --production-names --overlaps-backend pathops \
  --master-dir .build/sans/native-masters \
  --instance-dir .build/sans/native-instances \
  --output-path .build/sans/Native-VF.ttf
```

Equivalent inputs exist for System and Code. System’s source is large because it preserves compatible outlines across twelve weight/optical-size masters. Code's font-file stem is `DaikonicTransitCode`; its editable Glyphs file is `DaikonicTransitCode.glyphs`.

The existing `qa/<family>/native-source-rebuild.json` records the prior independent Glyphs/fontmake comparisons. `qa/repository-validation.json` records the portable master rebuild check in this repository. Native rebuilds can change point ordering or curve approximations slightly; do not require binary identity with an editor/compiler that uses a different conversion path.

## Panel exports

`specimens.py` uses HarfBuzz shaping and paths extracted from the actual distributed variable TTFs; no fallback fonts or synthetic styles are used. It creates editable outlined SVGs and a family board. The PNG exports are1500×1860 per panel; the PDF exports preserve vector paths. The board is4500×1860. SVG/PDF and PNG show the same composition.

To reproduce PNG/PDF, serve `specimens/` locally and render each SVG with Chromium at a500×620 viewport, device scale factor3. Export PDF at500×620CSS pixels with zero margins and backgrounds enabled. The board uses1500×620. Review the resulting images after rendering.

## Configurable source-design studies

See [scaling-lineage.md](scaling-lineage.md) and `recipes/weights.json` for the separate Regular-anchored weight-generation lane. `python tools/pipeline.py study --family all` generates sanitized experimental static weights for all three families from their declared Regular sources. It retains selected design overrides, records topology backoffs and never overwrites current releases. Geometry sizing/fitting probes are executable in `tools/scaling_study.py`.

### Current specimen font selection

`specimens/font-selections.json` selects the coordinated release fonts for the panels and feature samples. The specimen packager resolves the same selection and verifies its font hashes.

```sh
python tools/specimens.py
python tools/code_detail_specimen.py
python tools/render_svg.py --scale 3 specimens/TransitSans.svg specimens/TransitSystem.svg specimens/TransitCode.svg specimens/Transit-Family.svg specimens/TransitCode-Details.svg
```

Review the rendered images before updating qa/specimen-rendering.json and
packaging a dated specimen revision with tools/specimen_release.py.

### Code preview packages

`recipes/code-previews.json` selects the working Code cut and preserves earlier selections. `python tools/package_code_preview.py` builds the canonical named preview and snapshots; `--check` verifies source fidelity, checksums, shaping and the vertical at-symbol terminal cut across eleven weights. `--install` backs up and replaces the local user font.

`python tools/package_code_preview_assets.py` creates format-separated preview archives in `.dist/code-preview/`. Its SOURCE archive contains the complete editable TTX font and a portable rebuild script. The XML roundtrip is verified against outline, variation, metric and layout tables and sanitized. The design recipe for 1.022 is `python tools/code_at_c_taper_study.py --upturn`. Native released Glyphs/UFO sources retain their separately documented versions.

See [positioning, OTF exports and optical-size trials](layout-optical.md) for the new shared layout and CFF pipelines and the separate default-preserving optical review fonts.

### Feature tables and Code 1.032

`python tools/readme_features.py` renders README On/Off cells from the selected actual fonts, then updates the marked tables. `--check` verifies source hashes, shaping differences, generated SVGs and README content. Permanent character designs show the current Book and Regular weights.

The initial dot and syntax stage uses `dot_palette.py` then `syntax_numeral_study.py --family code`; frozen inputs and the final per-token positions are in `recipes/syntax-numeral-trial.json`. `check_dot_palette.py` and `check_syntax_numerals.py` verify the variable shapes, preserved metrics, glyph bodies, fixed-cell ligatures and optional proportional-family numeral studies. Sans/System numeral and dot studies remain review fonts; only the Code study is selected for the current preview.

`export_otf.py --family code` exports the selected Code cut, and `package_code_preview_assets.py` includes OTF with VF/TTF/WOFF2, editable TTX and specimens. Native released Glyphs/UFO sources retain their separately documented versions.

The lifetime and pipe stage is generated by `syntax_numeral_study.py --family code`; the selected source additionally includes the delimiter-weight and enclosure stages below. Joined hash rails are checked geometrically; `check_rust_lifetimes.py` checks paired marks, protected literals and fixed advances across weights. Each preview keeps frozen source inputs. README samples show current-font On/Off features and Book/Regular permanent designs; SVG is the primary format.

The selected 1.032 preview freezes the opening-quote lifetime and contextual pipe work, applies the delimiter-only weight step with `code_delimiter_weight_study.py`, then builds joined enclosures with `code_enclosure_ligatures.py`. The latter verifies exact enclosure outlines and variation data against the selected frozen source. `ss01` and `ss02` are independently labeled and disabled by default. Native Code sources remain at 1.017; preview SOURCE packages provide editable TTX and a portable rebuild.

## Coordinated releases

`recipes/bundle-release.json` selects the families, source cuts, versions and tag for a stable release. `python tools/stage_typography.py` builds the selected variable fonts and updates the specimen selection.

Regenerate the panels with `python tools/specimens.py` and `python tools/code_detail_specimen.py`, then update the README feature images with `python tools/readme_features.py`. Use `python tools/glyph_proof.py FONT OUTPUT` to generate printable glyph proofs. Run `python tools/bundle_release.py build` to generate and validate the named TTF and OTF styles, TTC collections, WOFF2 and editable source. `python tools/bundle_release.py package` assembles the archives and checksums in `.dist/bundle/<version>/`, including the interactive site used by the Pages workflow.

The Fonts workflow runs `python tools/bundle_release.py check` against the committed artifacts. The SOURCE archive contains complete editable TTX for the current release. The native Code Glyphs and UFO sources capture Code 1.017.

Code 1.040 derives upright Code from the frozen 1.039 font with `tools/code_compact_operators.py`. The bundle check verifies the intended changes against that source and confirms that other glyphs retain their outlines and metrics. Run `python tools/code_compact_operators.py releases/<version>/specimens --proof` to regenerate the self-aligning ligature and Loose Equality specimens from the selected release.

Code angle matching resolves innermost pairs first, preserving nesting depth in temporary glyph forms, then propagates a generic parent’s style only inside its matched closing boundary. Cleanup restores ordinary glyphs for unmatched angles. The finite font lookup system supports 16 levels and 60 non-mark glyphs per pair. The normal and compact lifetime opener preserve their existing positioning; unmatched compact openers use an ordinary short angle in the shifted cell.

`code_logic_sequences.py` gives `[<>]` and `<[]>` priority over shorter Logic tokens, using four-cell ligatures with three internal caret positions. It reuses the existing closed box and diamond. The angle-pair stage then derives the current Code font from that source, so enclosing generic pairs recognize these Logic forms as content. Coordinated patch release 2026.11.18.1 contains Code 1.035 with unchanged Sans/System.

`code_logic_symbols.py` adds Unicode logical-not (U+00AC), universal (U+2200) and existential (U+2203) glyphs before the paired-angle stage. Quantifiers derive from the existing capital A/E; negation uses the equals sign’s bounds and horizontal stroke. Logic maps prefix bang to logical-not, preserving !=, !==, !., postfix/macros and simple quoted bangs.

`code_logic_shortcuts.py` derives Code 1.036 from the frozen 1.035 release. It adds complete-command calt substitutions independently of ss02: \forall, \exists, \not, \box, \diamond. Commands retain 600 units per input character, all internal caret positions and unchanged symbol outlines, right-aligned within their original advances. Longer command-like identifiers and doubled backslashes stay literal. Release 2026.11.18.2 packages all three families together.

The Rust generic base is generated by `code_angle_pairs.py` into `sources/code-rust-generics/`; `code_lifetime_hook.py` derives left-hook lifetime marks, `code_structural_fit.py` fits mixed enclosures and nested closers, and `code_logic_shortcuts.py` adds standard commands to the selected Code release. Inference `_` and `[_]` and scope/turbofish intent are classified before paired matching. Turbofish GPOS moves the scope +18/+50 and the tall opener -18/0 with zero advance adjustment; the vertical centers meet at350 units. Unfinished angles remain short.

Lifetime hooks use the selected small horizontal-l silhouette, redrawn with a rounded corner and full-size `l` stem thickness at each master. Geometry size and stroke weight are controlled separately. The normal form remains in its own cell. The retired `ss01` study extended the straight stroke to x680 while retaining the left hook. An opt-in GPOS adjustment moves the marker and preceding `&`/`<` +40x/+45y toward the letter. Contextual vertical clearance protects taller letters; all advances remain600. Rebuild with `python tools/code_lifetime_hook.py` then `python tools/code_structural_fit.py` and `python tools/code_logic_shortcuts.py`. The glyph proof and review sources are in `trials/2026-11-18-lifetime-designs/`.

`system_tabular_one.py` derives System0.118 from the preserved System0.117 VF and current Sans VF. Only `one.tnum` changes: Sans geometry is reused unscaled and centered in each existing variable tabular cell; original HVAR width functions are retained. Checks cover91 weight/optical locations and all ten tabular advances. Named TTFs and TTC faces are snapshots of the selected VF.

The final Code stage is `code_structural_fit.py`, between lifetime hooks and shortcuts. It removes only mixed-pair substitutions, forces separate tall mixed angles and applies symmetric30-unit inward offsets, preserves four-character empty Logic ordering, composes tighter generic closer runs with600-unit carets, and centers interpolation dollars by50units. Structural checks cover all11Codeweights and feature toggles. The `\diamond` shortcut retains its eight input cells.
