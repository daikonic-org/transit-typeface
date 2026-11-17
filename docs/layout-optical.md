# Positioning, OTF exports and optical-size trials

The working Code update is **1.023**. It retains the selected 1.022 drawings and
adds variable mark attachment, mark-to-mark stacking, zero-advance combining
marks, and matching dotless i/j bodies. Canonically equivalent precomposed and
decomposed accents use the same base and mark through `ccmp`. Attached cedillas
and ogoneks use separate anchor classes from floating below marks. Existing
Code contextual positioning, operator ligatures, carets and repeated-at fitting
are retained; ordinary characters keep their 600-unit advances.

Sans and System already contained `kern`, `mark` and `mkmk`, including variable
anchors. These remain intact. This work covers marks already present in the
fonts; it does not claim complete Unicode combining-mark coverage. For example,
U+0323 (combining dot below) remains absent in all three current character maps.

## CFF OpenType exports

`python tools/export_otf.py` exports static CFF `.otf` snapshots of all named
weights: five Sans, fifteen System weight/optical combinations, and three Code.
The Code exports use the 1.023 positioning update. OTF is an additional outline
format; the existing variable TTFs remain the variable-font distribution.

Each OTF is built from the fully instantiated TTF. Quadratic segments become
cubic segments without integer rounding; lossless CFF subroutinization keeps
System's detailed outlines within CFF1 instruction limits. Each font passes
OpenType Sanitizer. Character maps, metrics, GSUB, GPOS and GDEF match its TTF
instance, and every glyph's bounds agree within 0.05 font units. No independent
OTF drawing or spacing master is introduced.

## Sans and Code optical-size trials

Separate, explicitly named **Optical Study** fonts add `opsz` 10–36, default14.
They are review candidates; the installed Code update retains its weight-only
axis until the optical endpoints are selected. System retains its existing
10–36 axis. At the sampled weights, System's existing optical profiles primarily
adjust spacing rather than letter outlines.

The new trials preserve the default outlines exactly, and default advances at
all checked weights. Compatible optical deltas add modest small-text stroke
changes, counter relief, c/e/s aperture opening and punctuation compensation.
Sans also gains eight units of tracking at the small endpoint and loses six at
the display endpoint. Code never changes the character grid. Its variable mark
anchors are regenerated over both weight and optical size. Selected hook
ligatures, arrows and the approved at symbol are protected. X-height and
capital-height extents are retained.

These are scripted starting points for optical design, not a claim that a
universal offset algorithm replaces visual judgment. Review the actual-size
light/dark text in the PNG/PDF and browser proofs before adopting the endpoints.
The default14 drawings are the current faces, not enlarged or reduced masters.

## Rebuild and verify

The frozen inputs and hashes are in `recipes/layout-sources.json`; optical
parameters are in `recipes/optical-trial.json`. The Code positioning rebuild
uses the pinned 1.022 cut rather than whichever preview is currently selected.

```sh
python tools/layout_extensions.py
python tools/optical_study.py
python tools/check_layout_optical.py
python tools/layout_optical_proofs.py
python tools/optical_playground.py
python tools/export_otf.py
python tools/export_otf.py --optical
```

`trials/2026-11-17-layout-optical/` contains the variable fonts, anchor feature
source, validation report, matched PNG/PDF and editable outlined SVG specimens.
`exports/otf/current/` and `exports/otf/optical-trial/` contain the OTFs and
source/location/hash manifests. Optical OTFs include all weight/size combinations;
System's unchanged OTFs are reused rather than rebuilt in the trial lane.

The validation covers Code mark attachment and stacking at seven weights and
five optical sizes, canonical equivalence, operator advances, optical pair
placement, repeated-at fitting, default outlines/advances, representative counter
topology at70 optical/weight locations, and preservation of existing proportional
positioning. Broader script/language coverage and native Glyphs/UFO adoption
remain separate work.
