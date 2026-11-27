# Daikonic Transit specimens

| Typeface | Word | Letter samples | Preview | Vector PDF |
| --- | --- | --- | --- | --- |
| Daikonic Transit Sans | Wayfinder | Aa Gg Rr | [PNG](TransitSans.png) | [PDF](TransitSans.pdf) |
| Daikonic Transit System | Context Menu | Hh Ee Yy | [PNG](TransitSystem.png) | [PDF](TransitSystem.pdf) |
| Daikonic Transit Code | snake_case | Ii Ll O0 | [PNG](TransitCode.png) | [PDF](TransitCode.pdf) |

[Combined family board](Transit-Family.png) · [Family board PDF](Transit-Family.pdf)

Both main numeral rows in System use its default proportional figures. The
hooked `1` appears only in the separately labeled **optional tabular** example;
it is selected with the OpenType `tnum` feature.

The lower bands also demonstrate Sans's standard/custom ligatures and Code's
coding ligatures. The outlined SVG versions sit beside the PNG/PDF files.

The System heading uses Book 350, matching its default UI weight.

## Current font cuts

The current specimens show Sans, System and Code 1.1.3.
The [Sans upright glyph proof](../releases/1.1.3/specimens/Sans-Upright-Glyph-Proof.pdf)
and [Sans italic glyph proof](../releases/1.1.3/specimens/Sans-Italic-Glyph-Proof.pdf)
show every named weight.

[Code detail sheet PNG](TransitCode-Details.png) · [Code detail sheet PDF](TransitCode-Details.pdf)
shows all three Code weights with email and decorator samples, repeated `@` fitting,
`snake_case`, delimiters, spacing pairs and arrow and comparison ligatures. The [Code feature table](features/code-Features.pdf) compares contextual and coding features on and off. The [code samples](features/Code-Characters.pdf) show those settings in Rust, TypeScript and logic. The [delimiter, arrow and lifetime proof](../releases/1.1.3/specimens/Code-Delimiters.pdf) shows the revised forms in upright and italic.

The font selection is explicit in font-selections.json; manifest.json records
versions and exact source hashes. PNG/PDF/SVG exports share the same composition.

All three families are included in each coordinated release. The [angle-pair study](features/Angle-Pairs.pdf) records the earlier Logic and generic-angle trial.

[Logic sequence order](features/Logic-Order.pdf) shows the optional box/diamond order across weights.

[Logic symbols](features/Logic-Symbols.pdf) shows negation and Unicode quantifiers across the three Code weights.

[Standard Logic shortcuts](features/Logic-Shortcuts.pdf) shows the same shortcut rendering with Logic off and on.

The [Rust inference and turbofish study](features/Rust-Generics.pdf) includes enlarged forms and 14px reading-size samples with `calt` on and off.
