# Daikonic Transit

Three related Johnston-inspired typefaces derived from Metropolitan Line: **Transit Sans** for proportional text, **Transit System** for interfaces, and **Transit Code** for source code and terminals.

![Transit Sans, System and Code specimen panels](specimens/Transit-Family.png)

| Family | Current version | Variable axes | Default | Installed family name |
| --- | --- | --- | --- | --- |
| Transit Sans | 0.107 | Weight 300–600 | Regular 400 | Daikonic Transit Sans |
| Transit System | 0.116 | Weight 300–600; optical size 10–36 | Book 350 / Text 14 | Daikonic Transit System |
| Transit Code | 1.016 | Weight 300–400; 600-unit cells | Book 350 | Daikonic Transit Code 600 |

## Download

[Releases](https://github.com/daikonic-org/transit-typeface/releases) provide separate **TTF**, **VF**, **WOFF2**, **SOURCE** and **SPECIMEN** archives, following the format-based layout used by Adobe Source Sans. Family-specific tags avoid collisions between the independently versioned faces: `Sans-0.107R`, `System-0.116R`, `Code-1.016R`.

Install the variable TTF for a family **or** its static TTF snapshots. Installing both can produce duplicate styles. The current releases contain upright styles; there are no italic or 700-weight faces. No OTF or legacy WOFF builds are advertised.

The versioned releases and files in this repository contain the same reviewed drawings. The original development workspace retains earlier studies and versions.

## The families

- **Sans** retains the proportional Metropolitan/Johnston character, including its accepted `ai` and `li` ligatures. Named weights: Light 300, Book 350, Regular 400, Medium 500, SemiBold 600.
- **System** enlarges the lowercase and adjusts spacing for UI text while retaining the capitals. Its independent optical-size axis and optional `tnum` figures include the selected curved, pedestal-free tabular `1`. The selected `y` with its clean hook connection extends across weights, optical sizes and accented forms. `ai`/`li` are separate letters.
- **Code** preserves 600-unit cells, a diamond-dotted zero, distinct `I/l/1`, enlarged lowercase and reviewed punctuation. Twelve coding ligatures retain exact cell totals and carry GDEF caret positions: `->`, `->>`, `=>`, `<-`, `<<-`, `==`, `===`, `!=`, `!==`, `<=`, `>=`, `::`.

All three share the approved concave, acute, extended-wing arrow family, including `← ↑ → ↓ ↔ ↕ ⇐ ⇑ ⇒ ⇓ ⇔ ⇕`. Font-specific letter, numeral and spacing decisions are retained.

## Accepted weighting

The current versions adopt the reviewed **72% horizontal-expansion** approach across all named weights and System optical profiles. Selected glyphs, tuned punctuation/symbols, spacing and layout are preserved. [Construction and interpolation checks](docs/weighting-adoption.md) document the frozen inputs, compatible masters and independent editor-source rebuilds.

## Specimens and design notes

[Individual PNG, PDF and outlined SVG panels](specimens/) use the actual exported fonts. Their lower sections use the existing Daikonic palette: Sans deep blue `#194454`, System orange `#FA994A`, Code red `#F03630`. Panel headings show real available weights, never synthetic bold. System’s second numeral row uses tabular figures.

- [Review of the supplied Gemini generation guidance](docs/generation-audit.md)
- [Deep scaling lineage and configurable generation](docs/scaling-lineage.md)
- [Measured stems, counters and metadata](docs/measurements.md) · [complete data](docs/measurements.json)
- [Build and validation](docs/build.md)
- [Release format and packaging](docs/releases.md)
- [Editor configuration examples](docs/editor-setup.md)

## Source and license

`sources/` contains editable Glyphs/UFO/designspace sources (extract System’s `.glyphs.zip` before opening) and compatible TTF masters. `upstream/` preserves the original Metropolitan Line inputs and author records. Build scripts reconstruct the current variable fonts from the compatible masters; named static weights are snapshots of those VFs.

The fonts are licensed under the [SIL Open Font License 1.1](OFL.txt), with original notices retained in [NOTICE.txt](NOTICE.txt). Daikonic Transit is a modified derivative, not an upstream Metropolitan Line release. The TfL screenshot was stylistic reference only; no proprietary Johnston100 font binaries or outlines were used. Brand artwork and documents do not become font software merely by using an OFL font.
