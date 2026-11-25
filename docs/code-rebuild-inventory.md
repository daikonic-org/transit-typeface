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

### Construction sources

The scripts below record the methods to check against each rebuilt form. The study and package paths refer to the local Daikonic project archive. The [rebuild recipe](../recipes/code-rebuild.json) defines the current inputs.

| Forms | Earlier construction | Sans-derived rebuild |
| --- | --- | --- |
| Grid, weight and proportions | `build_600_family.py` translated the masters into 600-unit cells and separately widened `w`. `build_cell_trials.py` grew the heavier drawing from Book. See the [scaling lineage](scaling-lineage.md). | Anchor Code Medium at Sans Regular, size lowercase separately and apply the reviewed width classes. |
| `a s m w y` | The 550-unit `a` alignment script loaded a finished SVG. `build_lowercase_family.py` widened `s` toward `a`. Later [receiver construction](../tools/code_receiver_shapes.py) used Sans `m` and `w` as donors. | The reviewed `a` follows the `s` width scale. Keep the foundation `m`, `w` and `y` as the normal forms. Use the receiver script when adding the contextual widths. |
| `i j l` | `DaikonicTransitMono-Light600-v0.98/build_glyphs_update.py` imported the edited `i` and dotless body from Glyphs Mini. [The later baseline pass](../tools/code_i_baseline.py) raised the bottom bar. An early `j` extension in `build_lowercase_family.py` predates the decision to revert it. | Use the reviewed common hook copied from the lower `l` return, the raised `i` base and the shared accent components. |
| `f t r` | `DaikonicTransitMono-Light600-v0.99/build_ft_one.py` reflected `t` to obtain `f`. `build_lowercase_family.py` later widened the hooks and crossbars toward `n`. | Build the shared return at the current heights and width of `n`. The `r` rebuild trims the right leg of `n` below the shoulder. |
| `g` | `DaikonicTransitCode-v1.002/build_g.py` split the upper bowl at the connector, enlarged it and joined it to the fixed lower loop. The older script also held the ear terminal and compensated the counter independently. | Use the same split on the current donor. Scale the bowl and counter together, keep the top and optical center, and overlap the two editable pieces. |
| `I 0 1` | The Glyphs Mini import supplied `I` and `0` as finished artwork. `build_ft_one.py` sized the `1` pedestal from `I`. The later `finalize_one_choices.py` selected the 30° flag with a rounded interior for Code. | Reconstruct `I` and `1` with a shared pedestal and draw the flag from those dimensions. Center the family diamond in the existing `0` bowl. |
| `@ %` | The 550-unit symbol trial imported finished artworks. The later [`@` builder](../tools/code_at_c_shell_study.py) joins a two-storey `a` to a `c`-shaped shell with a tapered join and an upward turn at the lower terminal. | Apply the shell construction to the approved donor proportions. Check percent separately for uncompressed rings and a shorter, steeper slash. |
| Punctuation, delimiters and `k/K` placement | The [punctuation pass](../tools/code_punctuation_size.py) defines dot sizing, comma and semicolon centering, quote and lifetime length, tilde and caret. The [delimiter study](../tools/code_delimiter_study.py) extends the brace pinch and sets the underscore position. The [underscore](../tools/code_underscore_weight_study.py) and [hyphen and k](../tools/code_hyphen_k_study.py) passes set thickness, width and placement. | Construct the shared diamonds and comma parts before the dependent punctuation and operator forms. Carry the `k/K` adjustment into the placement rules. |
| Arrows, comparisons and logic symbols | `refine_code_arrows.py` grew arrowheads around a fixed shaft and centerline. [Compact operators](../tools/code_compact_operators.py), [logic symbols](../tools/code_logic_symbols.py) and [glyph naming](../tools/code_glyph_names.py) describe the final token geometry, advances and aliases. | Reuse Sans or System arrow drawings and assemble the comparisons and logic forms from the current base parts. Check each advance and caret against the shaping fixtures. |
| Repeated stems, generics, shortcuts and lifetimes | [Repeated stems](../tools/repeated_stems.py) places `ff tt ll` on the grid. [Angle pairs](../tools/code_angle_pairs.py) and [structural fitting](../tools/code_structural_fit.py) handle context and separate enclosures. [Shortcuts](../tools/code_logic_shortcuts.py), [pipe delimiters](../tools/code_bar_delimiters.py) and the [lifetime hook](../tools/code_lifetime_hook.py) define the other drawing and substitution rules. | Generate these from the rebuilt parts and verify paired, nested and unmatched cases and the feature interactions. |
| Texture Healing and Hairlining | [Texture Healing](../tools/code_texture_healing.py) builds the donor and receiver forms. The [hairline study](../tools/code_hairline_study.py) specifies 22-unit echoes and leaders. The [toggle builder](../tools/code_hairline_toggle.py) records default behavior and permanent lifetime ampersand placement. | Generate the contextual outlines from their rebuilt glyphs and check the default and opt-out shaping. |
| Accents and italic | The [shared layout helpers](../tools/font_feature_tools.py) assemble marks and position parts. The [italic companion](../tools/italic_companions.py), [letterforms](../tools/italic_letterforms.py) and [return splicing](../tools/italic_returns.py) supply the shear, single-storey `a`, `i` foot, descending `f` and cursive `g` methods. | Reuse base and mark components with refreshed anchors. Apply Code’s italic angle and review the reconstructed forms independently of upright. |

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

## Build the Code review package

The rebuild uses the current Transit Sans masters. The upright and 9° italic
share Book 350, Regular 400 and Medium 500. Narrow, Normal and Wide use
564-, 600- and 648-unit cells. The review package contains the two variable
fonts, static TTF and OTF snapshots, a collection of all 18 static faces,
WOFF2, editable TTX and visual proofs.

```sh
.venv/bin/python tools/build_code.py --layout --output .build/transit-code/upright
.venv/bin/python tools/build_code_italic.py --output .build/transit-code/italic
.venv/bin/python tools/package_code_rebuild.py \
  .build/transit-code/upright/DaikonicTransitCodeLayoutReview-VF.ttf \
  .build/transit-code/italic/DaikonicTransitCodeLayoutReview-Italic-VF.ttf \
  --output .build/transit-code/package --version 1.043
```

`proofs/Code-Specimen.pdf` and its matching PNG show the named weights,
widths, italics and shaping in code. The two proof viewers support comparing
either axis and inspecting a single glyph.

Hairlining is on by default in the upright and can be disabled with `ss07`.
Logic is enabled with `ss02`. Texture Healing is deferred along with the
investigation of using OpenType positioning for texture and operator
compaction.
