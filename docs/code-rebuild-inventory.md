# Transit Code rebuild inventory

This is the Stage 1 reference for Code 1.042 upright and italic. The [rebuild recipe](../recipes/code-rebuild.json) names Sans 1.0.0 as the letter donor and lists the available generator scripts. Code 1.042 provides the released character map, grid, and shaping behavior.

## Glyphs by construction

The machine-readable inventory lists all **691 upright** and **634 italic** glyphs, including the **433 encoded characters** in each face. Each entry records the proposed construction, available Sans counterpart, planned donor or Code parts, known generator, and dependent glyphs. Compiled substitution inputs identify layout dependencies. The construction recipe identifies outline dependencies.

| Construction group | Upright | Italic | How to build it |
| --- | ---: | ---: | --- |
| Sans base donors | 219 | 219 | Start from the named Sans drawing. Apply the Code weight, proportions, and cell rules. Use the separate x-height treatment for lowercase. |
| Canonical composites | 173 | 173 | Rebuild accents from the base and mark drawings. Resolve dotless bases and placement with the compiled layout and the NFC/NFD controls. |
| Combining marks | 16 | 16 | Adapt the shared marks and generate zero-advance glyphs, attachment anchors, and mark stacking. |
| Drawings assembled from parts | 7 | 7 | Build `r` from the stem and shoulder of Code `n` with a Code terminal. Build `∀` from `A`, `∃` from `E`, `¬` from the equals bar geometry, and `≠ ≤ ≥` from the comparison drawings. |
| Code-specific base drawings | 41 | 41 | Carry forward the distinct `i l I 1 0`, the underscore, delimiters, and other reviewed letter and punctuation constructions. |
| Shared Sans or System arrows | 25 | 25 | Reuse arrow drawings or their shafts and heads. Place them on the Code operator axis and set each character or ligature’s advance. |
| Derived ligatures and symbol shortcuts | 44 | 38 | Assemble the approved parts and attach carets for the actual input span. |
| Generated generic states | 110 | 95 | Generate matching aliases from short and tall angle drawings and lifetime openers. Build closer runs from the tall right angle. |
| Texture Healing forms | 18 | 0 | Generate contextual donor and receiver shapes from the rebuilt letters. |
| Hairline forms | 18 | 0 | Apply the appropriate echo or lifetime leader to the base form. |
| Contextual forms and supporting glyphs | 16 | 16 | Build remaining alternates and internal forms from their layout dependencies. |
| Spacing and empty glyphs | 4 | 4 | Assign the recorded advances to spacing and control glyphs. |

All six Code-only encoded characters are in the assembled group. The seventh entry is `r`. The source recipe marks `r` as the approved rebuild construction. The table groups the 1.042 glyph inventory by how we intend to rebuild it, including outlines whose earlier manual steps are only partially recorded.

### Donor generators

| Work | Implementation evidence |
| --- | --- |
| Grid and historical weight | `build_600_family.py:make_masters` translates the existing edited masters for the 600-unit grid and rebuilds the widened `w` group. `build_cell_trials.py:raw_masters` grows the old heavier drawing from Book. Both are historical scripts documented in the [scaling lineage](scaling-lineage.md). The new build uses Sans Regular 400 as Code Medium 500 and applies the lowercase adjustment when constructing the alphabet. |
| `m`, `w`, and texture variants | [Receiver construction](../tools/code_receiver_shapes.py) maps Sans `m` onto the Code stem geometry and selects a Sans `w` by stroke measurement. [Texture Healing](../tools/code_texture_healing.py) builds the contextual donor and receiver variants. |
| Shared arrows and operator families | The inventory records the named Sans and System arrow donors. [Compact operators](../tools/code_compact_operators.py) supplies the established code-token bounds and advances. |
| Code-only symbols and repeated letters | [Logic symbols](../tools/code_logic_symbols.py) and [Unicode comparisons](../tools/code_glyph_names.py) supply construction recipes. [Repeated stems](../tools/repeated_stems.py) builds the fixed-cell `ff`, `tt`, and `ll` forms. |
| Remaining custom forms | The [recipe](../recipes/code-rebuild.json) links the existing `i`, hyphen, `@`, underscore, delimiter, punctuation, and italic scripts. The core rebuild needs a Sans-first entry point that invokes the selected generators and explicitly implements constructions such as `n` → `r`. |

## Axes

Both faces expose `wght` **350–500** with default **400**, and `wdth` **94–108** with default **100**. The named variable instances are Book, Regular, and Medium at Normal width, with the corresponding italic names in the italic file. Italic has a separate font file and `ital=1` in `STAT`. The reference records `fvar`, `STAT`, and axis mapping data for each face.

| Width coordinate | 94 | 97 | 100 | 104 | 108 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Space advance in design units | 564 | 582 | 600 | 624 | 648 |

Shaping was sampled at all five widths and at weights 350, 375, 400, 450, and 500, in both faces.

## OpenType features

Both faces register features under the `DFLT` and `latn` default language systems. The reference records their lookup order, called lookups, glyph coverage, and on/off shaping runs.

| Feature | Upright | Italic |
| --- | --- | --- |
| Composition and ligatures | `ccmp`, `liga` | `ccmp`, `liga` |
| Contextual substitutions and positioning | `calt` | `calt` |
| Pair-specific clearance | `calt` | `calt` and `kern` |
| Mark attachment and stacking | `mark`, `mkmk` | `mark`, `mkmk` |
| Logic | Opt-in `ss02` | Opt-in `ss02` |
| Texture Healing | On by default. Explicit enable `ss03`, opt-out `ss04`. | |
| Hairlining | On by default. Explicit enable `ss05`, opt-out `ss07`. | |
| Loose Equality | Opt-in `ss06` | |

The fixture matrix includes matched and unmatched delimiters, generic nesting, Rust lifetimes and character literals, programming tokens, independent toggle combinations, and combining marks. Each shaped glyph records its source cluster, name, advance, and offsets. GDEF declares ligature caret data for **87 upright** and **62 italic** glyphs. Full GDEF and layout table exports accompany the inventory.

## Kerning and placement

All nonzero GPOS value records in the two released faces are placement adjustments. At Regular 400 and Normal 100 the samples below each use two 600-unit cells. The 250 paired on/off checks across weights and widths all preserved the total advance.

| Face | Feature | Input | Horizontal offsets with feature on |
| --- | --- | --- | --- |
| Upright | `calt` | `ke`, `Ke`, `KE`, `vi` | First glyph +18, second glyph −18 |
| Upright | `calt` | `il` | Both 0 |
| Italic | `kern` | `_m`, `_p`, `_Z` | Second glyph +20, +8, +6 respectively |
| Italic | `kern` | `@f` | Second glyph +24 |
| Italic | `kern` | `_b` | Both 0 |

Both faces also use contextual placement for operators, generic delimiters, and lifetimes. The machine report and GPOS exports preserve those rules; the `kern` and `calt` rows above are compact examples. Substitutions such as upright `::` get their shorter advance from the substituted glyph. That behavior is checked separately from GPOS.

## Reproduce the reference

Run from the repository root with the pinned font tools.

```sh
.venv/bin/python tools/check_code_rebuild.py --record .build/code-from-sans/reference.json
.venv/bin/python tools/check_code_rebuild.py --check .build/code-from-sans/reference.json
```

The command records exact input hashes and writes the glyph, axis, feature, kerning, and shaping inventory to `reference.json`. The same directory contains a sortable `glyphs.csv` and the compressed `layout-upright.ttx.gz` and `layout-italic.ttx.gz` exports.
