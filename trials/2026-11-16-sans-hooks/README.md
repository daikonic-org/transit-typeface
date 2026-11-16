# Sans hook interaction trial — 2026-11-16

This separately named installable study explores `ai` and `li` with ordinary,
ligatureless letter origins, pair widths and surrounding kerning. The `a` gets
the standalone `l` hook construction; each hook extends beneath the ordinary
position of `i`. The curved whitespace band follows the existing `li` design.
The standalone `i` dot and upper shaft are unchanged.

Five static weights: Light 300, Book 350, Regular 400, Medium 500, Semibold 600.
Comparison columns: production ligatures / ordinary letters / new hook trial.
The proof shows Book through Semibold at display and text sizes.

This is a design trial, separate from the released and installed Sans 0.108 VF.
It does not alter System or Code. Compatibility and interpolation of this new
construction have not yet been established; these are static trial fonts.

All five fonts passed OpenType Sanitizer. HarfBuzz verifies equal ligature-on/off
advances for ai, li, Daikonic, daily, liquid and mailing at every trial weight.
The JSON report records exact values. PNG and vector PDF share the outlined SVG.

Reproduce from the repository root:

```sh
.venv/bin/python tools/hook_ligature_study.py
.venv/bin/python tools/render_svg.py --scale 2 .build/hook-ligatures/Comparison.svg
```

Editable construction: `tools/hook_ligature_study.py`, drawing from the production
Sans variable font and existing `l`/`i` outlines. The SVG is also editable vector
artwork. Trial fonts and derivations retain the repository OFL and NOTICE.
