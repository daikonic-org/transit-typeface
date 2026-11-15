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

Equivalent inputs exist for System and Code. System’s source is large because it preserves compatible outlines across twelve weight/optical-size masters. Code's font-file stem includes `600` for its fixed cell width; its editable Glyphs file is `DaikonicTransitCode.glyphs`.

The existing `qa/<family>/native-source-rebuild.json` records the prior independent Glyphs/fontmake comparisons. `qa/repository-validation.json` records the portable master rebuild check in this repository. Native rebuilds can change point ordering or curve approximations slightly; do not require binary identity with an editor/compiler that uses a different conversion path.

## Panel exports

`specimens.py` uses HarfBuzz shaping and paths extracted from the actual distributed variable TTFs; no fallback fonts or synthetic styles are used. It creates editable outlined SVGs and a family board. The PNG exports are1500×1860 per panel; the PDF exports preserve vector paths. The board is4500×1860. SVG/PDF and PNG show the same composition.

To reproduce PNG/PDF, serve `specimens/` locally and render each SVG with Chromium at a500×620 viewport, device scale factor3. Export PDF at500×620CSS pixels with zero margins and backgrounds enabled. The board uses1500×620. Review the resulting images after rendering.

## Configurable source-design studies

See [scaling-lineage.md](scaling-lineage.md) and `recipes/weights.json` for the separate Regular-anchored weight-generation lane. `python tools/pipeline.py study --family all` generates sanitized experimental static weights for all three families from their declared Regular sources. It retains selected design overrides, records topology backoffs and never overwrites current releases. Geometry sizing/fitting probes are executable in `tools/scaling_study.py`.
