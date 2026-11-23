# Daikonic Transit System rebuild

## 1. Lowercase proportions

The approved proof applies the same 112% enlargement to the lowercase width and height in each named Sans weight. It compensates for the stroke gain with the same curve-preserving adjustment throughout the alphabet. The x-height is 532 units and the cap height is 700.

[Approved lowercase proportions proof](Lowercase-Proportions.pdf) · [Source hash and measurements](Lowercase-Proportions.json)

```sh
mkdir -p .build/system-rebuild
python tools/system_proportions.py releases/2026.11.22/sans/VF/DaikonicTransitSans-VF.ttf .build/system-rebuild/Lowercase-Proportions.svg
inkscape .build/system-rebuild/Lowercase-Proportions.svg --export-filename=.build/system-rebuild/Lowercase-Proportions.pdf
```

## 2. Primary y

System’s lowercase alphabet and dotless bases use the curves from the proportions proof. The primary `y` places the fork near the baseline, keeps both upper tips at x-height, and continues into the original hook. The existing accented `y` forms use that same body. The local review build keeps System’s current advances, optical-size axis, and layout tables.

[Lowercase and primary y proof](System-Lowercase-Curves.pdf)

```sh
python tools/build_system.py releases/2026.11.20/system/VF/DaikonicTransitSystem-VF.ttf releases/2026.11.22/sans/VF/DaikonicTransitSans-VF.ttf .build/system-rebuild --outline-only
inkscape .build/system-rebuild/System-Lowercase-Curves.svg --export-filename=.build/system-rebuild/System-Lowercase-Curves.pdf
```

The review build covers upright basic lowercase and the `y` family. The wider inventory, remaining accent compositions, and italic rebuild are tracked separately.

## 3. Kerning clearance

The System build runs the same outline-based pair check as Sans after rebuilding the outlines. Run the build command above without `--outline-only` to generate a spaced review font and proof. Use `--named-instances` for a faster review at the 15 named weight and optical-size combinations. The default also checks intermediate sizes and weights. The JSON report records the locations and pair adjustments. See [build notes](../../docs/build.md#checking-pair-clearance-after-outline-construction).

## 4. Lowercase accents

The build reuses the Sans component recipes for 85 lowercase accented letters. They use System’s rebuilt letterforms and shared marks. The single dot and both diaeresis dots come from the same diamond. The weight masters preserve the clearance of separate marks and the joins of attached marks. The review keeps the existing advances and mark positioning. The custom, shortened crossbar of `ť` is part of a separate drawing.

[Lowercase accent proof across five weights](System-Lowercase-Accents.pdf)

Run the same System build with `--named-instances` and export `System-Lowercase-Accents.svg` to reproduce the proof.
