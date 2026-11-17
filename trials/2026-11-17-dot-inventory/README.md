# Solid-dot inventory

Read-only measurements of the preserved Metropolitan Line Regular and Transit Sans0.109 at Light300, Book350, Regular400, Medium500 and SemiBold600. All figures use1000units per em. No inspected or installed fonts were modified by this inventory.

Only isolated solid dots are counted: i/j tittles, punctuation dots, bullets, division dots, spacing/combining accent dots, precomposed accented letters and relevant ligatures/localized variants. Comma/quote tails, rings and other diamond motifs are excluded.

## What the measurements show

- Metropolitan Line uses a100×97 square for the period, colon, semicolon, middle dot and ellipsis. Its black area is9700squareunits.
- Its i/j and accent diamonds are140×141, about9870squareunits. Question/exclamation dots are141–142units wide, with about10000squareunits of ink. These are nearly the same ink weight despite different bounding boxes.
- Transit Sans Regular turns the period group into140×139 diamonds with9684squareunits of ink: essentially an ink-preserving square-to-diamond conversion. It is not a40% emboldening.
- Transit Sans weights diverge: at SemiBold the i/j dot is180×180, the period172×171, combining dot190×140 and combining diaeresis164×141. The accent glyphs are not all following the same shape/weight function.
- The earlier shared punctuation script preserves area with sqrt(2*area) when converting squares. It explicitly shrinks one-cell Code ellipsis dots to93% of the period diameter; question/exclamation dots are not part of that conversion list.
- Code1.023 Book shows the selective punctuation pattern: period/colon are156×157, while question/exclamation dots are roughly133×130. See the Code crosscheck for exact areas.

## Palette proposal for discussion

Use one shared standard-dot master per weight for i/j, punctuation, spacing/combining accents and precomposed dotted forms. Anchor the Regular standard to the original approximately140×141 diamond; keep the bullet as a separate larger role (198×198 at Regular, approximately twice the ink area). Preserve intentional optical placement differences. Decide the weight progression and whether tiny original1–2unit differences should survive before changing fonts.

Dot-Inventory and Accent-Dots are same-scale PNG/PDF/SVG specimens. All-Dot-Usages.csv and inventory.json contain the full contour-level inventory; Core-Dot-Metrics.csv and Code-Crosscheck.csv summarize common usages.
