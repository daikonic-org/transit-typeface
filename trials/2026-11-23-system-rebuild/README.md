# Daikonic Transit System rebuild

## 1. Lowercase proportions

The approved proof applies the same 112% enlargement to the lowercase width and height in each named Sans weight. It compensates for the stroke gain with the same curve-preserving adjustment throughout the alphabet. The x-height is 532 units and the cap height is 700.

[Approved lowercase proportions proof](Lowercase-Proportions.pdf) · [Source hash and measurements](Lowercase-Proportions.json)

```sh
mkdir -p .build/system-rebuild
python tools/system_proportions.py releases/2026.11.22/sans/VF/DaikonicTransitSans-VF.ttf .build/system-rebuild/Lowercase-Proportions.svg
inkscape .build/system-rebuild/Lowercase-Proportions.svg --export-filename=.build/system-rebuild/Lowercase-Proportions.pdf
```
