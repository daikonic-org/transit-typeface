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

specimens/font-selections.json can select an approved preview via its
selection.json without changing the released-font configuration in family.json.
The main Code panel currently uses preview1.032 and labels that status. The
specimen packager resolves the same selection and verifies its font hash.

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

Publish all three fonts together as normal releases; do not create preview releases. `recipes/bundle-release.json` records the release version and tag. `python tools/code_angle_pairs.py` derives Code 1.034 from the preserved 1.032 font without changing drawings. `python tools/bundle_release.py build` freezes the selected fonts, creates named-weight TTC collections and editable TTX snapshots, and checks reconstruction and collection parity. Regenerate specimens and OTFs from the selected fonts, then `python tools/release.py` packages all families by format. `python tools/bundle_release.py check` is the release CI gate. SOURCE archives contain full editable TTX; native Code Glyphs/UFO adoption beyond 1.017 remains pending.

Code angle matching resolves innermost pairs first, preserving nesting depth in temporary glyph forms, then propagates a generic parent’s style only inside its matched closing boundary. Cleanup restores ordinary glyphs for unmatched angles. The finite font lookup system supports 16 levels and 60 non-mark glyphs per pair. The normal and compact lifetime opener preserve their existing positioning; unmatched compact openers use an ordinary short angle in the shifted cell.

`code_logic_sequences.py` gives `[<>]` and `<[]>` priority over shorter Logic tokens, using four-cell ligatures with three internal caret positions. It reuses the existing closed box and diamond. The angle-pair stage then derives the current Code font from that source, so enclosing generic pairs recognize these Logic forms as content. Coordinated patch release 2026.11.18.1 contains Code 1.035 with unchanged Sans/System.

`code_logic_symbols.py` adds Unicode logical-not (U+00AC), universal (U+2200) and existential (U+2203) glyphs before the paired-angle stage. Quantifiers derive from the existing capital A/E; negation uses the equals sign’s bounds and horizontal stroke. Logic maps prefix bang to logical-not, preserving !=, !==, !., postfix/macros and simple quoted bangs.

`code_logic_shortcuts.py` derives Code 1.036 from the frozen 1.035 release. It adds complete-command calt substitutions independently of ss02: \forall, \exists, \not, \box, \dia. Commands retain 600 units per input character, all internal caret positions and unchanged symbol outlines, right-aligned within their original advances. Longer command-like identifiers and doubled backslashes stay literal. Release 2026.11.18.2 packages all three families together.
