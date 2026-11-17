# Daikonic Transit

Three companion typefaces for text, interfaces and code. Daikonic Transit brings the humanist proportions and diamond details of Johnston-inspired lettering into a shared family: **Daikonic Transit Sans**, **Daikonic Transit System** and **Daikonic Transit Code**.

![Daikonic Transit Sans, System and Code](specimens/Transit-Family.png)

[Download the fonts](https://github.com/daikonic-org/transit-typeface/releases) · [Browse specimens](specimens/)

The current [Code 1.022 preview](previews/code-1.022/) includes the selected two-storey `@` with a tapered, gently upturned c-style wrap, refined delimiters, underscore and hyphen, and optical spacing adjustments. It is an installable working cut; [preview packages](https://github.com/daikonic-org/transit-typeface/releases/tag/Code-1.022-preview) separate VF, TTF, WOFF2, editable TTX sources and specimens. Published stable releases remain available above.

## Daikonic Transit Sans

The proportional foundation of the family. Based on [Metropolitan Line](https://github.com/cyrealtype/metropolitan-line), an open-source interpretation of Edward Johnston’s London Underground lettering, Sans retains its humanist character, rounded forms and distinctive diamond details while extending it into a range of weights.

Use it for identity, headings, signage, editorial work and general proportional text.

- Five named weights: **Light, Book, Regular, Medium and SemiBold**, available individually or through a variable weight range of 300–600.
- Proportional spacing, kerning and accented-character positioning.
- Standard `fi` and `fl` ligatures, plus custom `ai` and `li` combinations. A curved hook beneath the `i` and a separating band of whitespace connect the forms optically. The `ai` keeps ordinary spacing; `li` uses a matching stem gap.
- Shared diamond details and the Transit arrow family.

## Daikonic Transit System

The interface companion to Daikonic Transit Sans. System develops Sans’s forms with a larger lowercase, adjusted spacing and an optical-size range for smaller interface text. Its capital-height proportions remain consistent with Sans.

Use it for application interfaces, navigation, controls, dashboards and short passages of screen text.

- Five named weights: **Light, Book, Regular, Medium and SemiBold**, with a variable weight range of 300–600.
- An independent **optical-size axis, 10–36**, with Caption, Text and Display presets. It adapts the design to its intended text size without selecting a different weight.
- Proportional figures for running text and optional **tabular figures** for aligned values, tables and clocks (`pnum` / `tnum`). The tabular `1` has a curved hook and no pedestal.
- `fi` and `fl` ligatures. `ai` and `li` remain separate letters for interface text.
- The shared diamond details and arrow family, with lowercase proportions and spacing tailored to the System design.

## Daikonic Transit Code

The monospaced companion to Daikonic Transit Sans. Code carries Sans’s Johnston-derived character into a fixed-width design, with reworked letters, numerals and operators for programming and aligned text.

Use it in source editors, terminals, code examples and other settings where character columns need to line up.

- Three named weights: **Light, Book and Regular**, with a variable weight range of 300–400. **Book** is the default.
- Fixed-width characters and coding ligatures that occupy the same total width as their original character sequences.
- Distinct `I`, `l` and `1` forms, a diamond-dotted zero, enlarged lowercase and diamond punctuation.
- A raised, full-width inline `_` aligned with the lowercase baseline for clearer `snake_case`, with a heavier stroke and gapless repeated underscores.
- Arrow ligatures: `->`, `->>`, `=>`, `<-`, `<<-`.
- Comparison ligatures: `==`, `===`, `!=`, `!==`, `<=`, `>=`.
- A balanced `::` ligature. Contextual alternates (`calt`) provide all twelve coding ligatures; enable font ligatures in your editor to use them.
- Ligature caret positions for editors that support positioning the cursor inside a ligature.

All three typefaces include the same family of pointed, concave arrowheads, including the Unicode arrows **← ↑ → ↓ ↔ ↕ ⇐ ⇑ ⇒ ⇓ ⇔ ⇕**.

## Downloads and release packages

Each typeface has its own [release](https://github.com/daikonic-org/transit-typeface/releases) and version number. Download the package for the format you need:

| Package | Contents | Use |
| --- | --- | --- |
| **VF** | One variable TrueType font | Adjustable weights in applications that support variable fonts; System also includes optical size. |
| **TTF** | Individual named-weight TrueType fonts | Applications that use separate font styles. System includes Caption, Text and Display cuts. |
| **WOFF2** | Variable webfont and a CSS example | Websites and web applications. |
| **SOURCE** | Editable Glyphs and UFO sources, designspaces and rebuild inputs | Editing or building the typefaces. System’s large Glyphs file is supplied inside a ZIP. |
| **SPECIMEN** | Matching PNG, PDF and SVG specimens | Previewing and comparing the designs. |
| **SHA256SUMS** | Download checksums | Checking that an archive downloaded intact. |

Archives are named by format, family and version—for example, `VF-daikonic-transit-code-1.017R.zip`. Font-menu names are simply **Daikonic Transit Sans**, **Daikonic Transit System** and **Daikonic Transit Code**.

Choose either the variable font or the individual static styles when installing a family. The available releases contain upright styles. [Editor setup](docs/editor-setup.md) and [source/build instructions](docs/build.md) are available separately.

## Credits and tools

Daikonic Transit is a Daikonic typeface project, based on the open-source work of the **Metropolitan Line authors**. Its lineage includes **Justin Howes, Greg Fleming, Alexei Vanyashin and Michael Voronin**, and ultimately Edward Johnston’s original lettering. Original author records are preserved in [AUTHORS.txt](upstream/AUTHORS.txt) and [NOTICE.txt](NOTICE.txt).

The project uses:

- [Glyphs Mini](https://glyphsapp.com/glyphs-mini) for font editing.
- [Python](https://www.python.org/), [FontTools](https://github.com/fonttools/fonttools), [fontmake](https://github.com/googlefonts/fontmake), [glyphsLib](https://github.com/googlefonts/glyphsLib) and [ufoLib2](https://github.com/fonttools/ufoLib2) for scripted transformations, editable-source conversion and font builds.
- [Skia PathOps](https://github.com/fonttools/skia-pathops) for outline geometry, [HarfBuzz](https://github.com/harfbuzz/harfbuzz) for text shaping, and [OpenType Sanitizer](https://github.com/khaledhosny/ots) for font-file validation.
- [FreeType](https://freetype.org/), [Pillow](https://python-pillow.org/), [ReportLab](https://www.reportlab.com/), [Chromium](https://www.chromium.org/) and [Playwright](https://playwright.dev/) for proofs, comparisons and specimen exports.

Development, scripting and documentation were assisted by OpenAI ChatGPT/Codex. Additional weighting guidance was explored from Google Gemini. The format-based release layout takes inspiration from [Adobe Source Sans](https://github.com/adobe-fonts/source-sans/releases).

## License

The fonts are distributed under the [SIL Open Font License 1.1](OFL.txt). Original copyright and reserved-name notices are retained in [NOTICE.txt](NOTICE.txt).
