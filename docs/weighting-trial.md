# Weighting recommendations: all-weight trial, 2026-11-15

> Historical trial before adoption. See [weighting-adoption.md](weighting-adoption.md) for the adopted variable fonts and preserved punctuation/symbols.
The corrected PathOps implementation of the supplied weighting approach was run
for every currently named weight: Sans and System 300/350/400/500/600, and Code
300/350/400. System was generated separately at opsz 10, 14 and 36. That is 23
weight/profile combinations per alternative, 46 experimental static TTFs total.
Regular 400 is the unchanged source anchor, not a newly weighted drawing.

## Reproduce

```sh
python tools/pipeline.py study --family all --ratio-y 1
python tools/pipeline.py study --family all --ratio-y 0.72
python tools/weighting_proof.py
```

Open `.build/weighting-review/index.html` through a local web server. It links
six outlined SVG sheets: an overview, Sans, Code, and each System optical-size
profile. Current and experimental outlines are rendered at identical font sizes,
with no width fitting, fallback fonts or synthetic bold. HarfBuzz shaping is
applied before conversion to SVG paths. Samples cover H/n/o/a/e/s/f/t, words,
figures, accents, punctuation and Code ligatures, in both polarities.

PNG/PDF exports for this review used Chromium 157.0.8103.78, 1600 CSS-pixel
sheet width, device scale factor 1.5 for PNG and exact SVG dimensions for PDF
with zero margins and backgrounds enabled. This is local rendered evidence,
not a cross-platform reading-performance test.

## What was carried over from the recommendation

- Anisotropic offset: horizontal expansion ratio 0.72 versus the control 1.0.
- Sharp miter joins, limit 3, plus overlap removal through path operations.
- Counter-topology checks and reduced-offset backoffs when an offset would
  destroy a counter or merge contours. Counter **area** is measured, not fixed.
- Direct derivation from each family's Regular source rather than serially
  deriving one new weight from another.

Offsets are calibrated to the existing target H stems, rather than applying
the same arbitrary +34 to every family. Medium 500 targets 130 units between
the 110-unit Regular and 150-unit SemiBold. Code retains its current calibration.
The other targets are declared in `recipes/weights.json`.

The pasted script required API and composite-glyph corrections; see
[generation-audit.md](generation-audit.md). Its optional global width stretch
and added tracking were excluded from this weighting-only comparison. Current
advances, layout tables, and declared selected-glyph locks are retained.
In particular, selected numerals, i/j/l, y, arrow glyphs and Code ligatures use
the approved target-weight drawings. This trial does not reweight those locked
shapes. It tests the remaining repertoire at every named weight.

## Measurements and local review

At the same Sans/System H stem of 150, the 72% trial's H crossbar is 123 units
versus the current 132. Sans o counter area increases about 4.9%; System opsz14
about 3.7%. Conversely, during Light thinning the ratio retains more horizontal
material: H crossbar 84 versus current 77 in Sans/System. Code Light measures
83 versus current 76. Therefore "72%" does not mean every horizontal becomes
thinner at every weight. Height refitting further changes the effective ratio.

All six PNGs were opened and inspected. In the shown strings, weight and counter
balance are locally acceptable for comparative trials; the 72% Medium/SemiBold
shows lighter horizontal mass and more open bowls. Light/Book appears subtly
sturdier horizontally. No clipping or collisions were observed in the proof
corpus. Spacing, selected-glyph locks and Regular rows remain recognizable as
the current design. This does not approve every generated contour: the 72%
Sans600 still needed 51 topology backoffs, and System600 needed 43–44 depending
on optical size. The control required 83 and 66–67 respectively.

All 46 trial files passed OTS. Every advance was checked against its matched
approved instance, retained GSUB/GPOS/GDEF tables were compared, and all twelve
Code ligatures were shaped at each trial weight with exact 600-unit cell totals.
See the generated `checks.json`, `measurements.json` and per-alternative
`fonts/*/report.json` for evidence, input hashes and glyph-level backoffs.

The production font files, installations and published releases were unchanged.
These are independently named static studies, not a compatible variable master
family. Recommend visual selection before transferring any changes into the
editable production masters and rebuilding an interpolating VF.
