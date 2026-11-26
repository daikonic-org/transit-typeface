# Historical outline and layout audit

Measurements from November 15, 2026 cover Sans 0.106, System 0.115, and Code 1.015. The subsequent weighting method is documented in [Weighting adoption](weighting-adoption.md). See [Positioning and optical size](layout-optical.md) for later work on Code mark attachment and optical sizing.

## Sans and System

Both families used the 1,000 UPM Metropolitan Line Regular as their starting point. The historical Sans recipe used nominal outline offsets of −25, 0, and +60 units. It applied miter joins and refitted vertical bounds. Weight-dependent advances and anchor shifts carried through to spacing and mark positioning.

| Measurement | Result |
| --- | --- |
| Sans `H`, weight 400 to 600 | Vertical stems grew from 110 to 150 units. The crossbar grew from 100 to 132 units, giving 80% as much growth as the vertical stems on this glyph. |
| Sans `o`, weight 400 to 600 | Counter area fell from 69,371.83 to 48,490.17 square units, a 30.1% decrease. |
| Weight range | Sans and System ran from 300 to 600. Code ran from 300 to 400. |
| Layout | Sans and System retained pair positioning and mark positioning. All three families shipped upright styles at these versions. |

The build checked counter and contour topology, reduced offsets when necessary, and reopened selected apertures. Those checks keep counters from closing completely. The `o` measurement shows how much their area can still change. [FontForge style transformations](https://fontforge.org/docs/ui/dialogs/Styles.html)

## Code

Code used a 600-unit cell on a 1,000 UPM grid. Wide glyphs were fitted with horizontal scaling and compensating outline offsets, with a scale-only fallback. The variable font reported an average character width of 600. Some static snapshots reported 620 because the calculation also counted unencoded multi-cell ligatures. Ordinary character advances remained 600 units. [OpenType OS/2 table](https://learn.microsoft.com/en-us/typography/opentype/spec/os2#xavgcharwidth)

The design distinguished `I`, `l`, and `1` and used a diamond-dotted zero. Concave arrowheads, aligned operators, and larger punctuation were drawn for the coding grid. Operator ligatures occupied two or three cells. Twelve ligatures provided internal carets at 600 units or at 600 and 1,200 units. [OpenType GDEF table](https://learn.microsoft.com/en-us/typography/opentype/spec/gdef)

Code 1.015 shipped without GPOS. HarfBuzz shaped decomposed `a` plus acute as `aacute` with a 600-unit advance. For `q` plus acute, it returned a 600-unit base and a zero-advance mark at offset (−602, 22) using fallback positioning. Code 1.023 added variable mark attachment and stacking. [OpenType GPOS table](https://learn.microsoft.com/en-us/typography/opentype/spec/gpos)

## Outline processing

PathOps strokes mutate a path, so the build strokes a copy and retains the original fill. TrueType composites have negative contour counts and need their component transforms preserved. The build converts conics and cubics to compatible quadratic outlines across masters. Bounds are checked after offsetting because the outline offset changes overshoots as well as stroke weight. [Skia PathOps](https://github.com/fonttools/skia-pathops/tree/main/src/pathops)

For the evolution of the master sources and weight recipes, see [Scaling lineage](scaling-lineage.md). The original geometry measurements are in [measurements.json](measurements.json).
