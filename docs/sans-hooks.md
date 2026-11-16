# Sans 0.109: selected hook ligatures

The selected R2 `ai` and `li` constructions are now production drawings across
Sans's 300–600 weight axis. The old `a` foot is replaced by a curved join into
the hook. The `ai` retains ordinary spacing; the `li` stem gap matches `ai`,
moving its `i` 135 units left relative to ordinary `li`. Outer kerning is retained.
Standalone letters and the other ligatures are unchanged. System and Code
retain their existing versions and designs.

The five selected static trials remain in `trials/2026-11-16-sans-hooks-r2`.
`tools/promote_sans_hooks.py` records their adoption into compatible TTF masters,
UFOs and Glyphs. The prior production VF is preserved as
`sources/ligature-baseline/sans-0.108-VF.ttf`.

Production rebuilds use `tools/build.py`. Its layout preservation allows only
`a_i` and `l_i` to use revised advance-variation functions. The constant kerning
correction lookup is appended to the original GPOS, preserving original mark
positioning and all existing variation functions. The exceptions are explicit
in `family.json` and included in the portable source package's rebuild script.

```sh
python tools/pipeline.py approved
python tools/check_weighting.py all --production
python tools/sans_hook_proof.py
python tools/render_svg.py --scale 2 qa/sans/Hooks-Named/Comparison.svg qa/sans/Hooks-Intermediate/Comparison.svg
python tools/release.py --family sans
```

`check_sans_hooks.py` checks 13 weights, contour topology, fidelity to the selected
construction, unchanged unrelated outline/variation data and 9,023 unrelated
ASCII pair positions per weight. Named-weight advances match the selected
construction exactly. At intermediate weights, rounding a combined ligature
advance can differ by one unit from separately rounding each ordinary letter.

The independent Glyphs rebuild was checked at all five named weights:

```sh
fontmake -g sources/sans/DaikonicTransitSans.glyphs -o variable --production-names \
  --overlaps-backend pathops --master-dir .build/sans/hook-native-masters \
  --instance-dir .build/sans/hook-native-instances --output-path .build/sans/Hook-Native-VF.ttf
python tools/check_sans_hooks.py --native .build/sans/Hook-Native-VF.ttf
```

Reports are in `qa/sans/hook-*.json`. Named and intermediate PNG/PDF/SVG proofs
are included in Sans's specimen archive. They use the actual release VF and
were visually reviewed at display and text sizes. Core Text/app rendering and
physical printing were not re-tested for this release.
