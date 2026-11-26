# Code: fresh @ drawing

A new review candidate drawn from a smooth spiral and a separate double-storey
a bowl. The previous edited outline is not used as drawing geometry. The open
loop flows into the a stem and upper arch; stroke width tapers continuously at
the junction. The bowl joins the stem to make the sole enclosed counter.

Outer silhouette is590x597units, centered against o. At Book the compiled bounds
are x5..595,y-33..564, about35units beyond o above/below. The proportions closely
follow o's near-circular proportions rather than stretching the old @. This is
about13.5% larger than Book o, and larger than the preceding optical @ trial.
All weights keep the600-unit advance and fit within the cell.

The outer stroke uses80% of o's corresponding vertical/horizontal weight, and
the inner a uses45%. Book nominal widths are76/71.2 for the outer loop and
42.75/40.05 for the a. The construction uses an elliptical pen, preserving the
family's slight directional compensation. Cubic approximation tolerance .025
font units controls the varying-width stroke. The source centerline is explicit
arcs and Bézier curves. The TrueType masters use compatible points derived from that centerline.

Daikonic Transit Code Redrawn At Study: VF300–400/defaultBook350 plus Light,
Book and Regular snapshots. Four binaries pass OpenType Sanitizer. At11weights,
checks verify one connected outline and one counter, cell bounds/advance,
vertical extents and interpolated outline fidelity to the direct construction
within1.5% raster coverage difference. All unrelated glyphs, variation functions,
layout and metrics are retained exactly; at's sidebearing follows its new bounds.

Book.png/pdf/svg is the enlarged Book comparison with o guide lines.
Comparison.png/pdf/svg covers all three named weights in both polarities.
Browser.png uses actual loaded fonts at13/14/16px in Chrome157, device scale2;
both loads passed. Images were opened and visually reviewed: the larger, lighter
fresh spiral has smoother joins than the previous edited outline, and clearer
separation of the interior a. Editor/terminal use remains unverified.

Editable recipe: tools/code_at_redraw.py in the repository. Its archived copy
and shared tools/code_at_study.py builder are included. Run from repository root
with .venv/bin/python tools/code_at_redraw.py; existing tools/ shared helpers and
prior trial binaries are prerequisites. SVG specimens are editable; snapshots
are editable TTF outlines. Previous trials remain preserved. No install, commit
or release occurred. Installed Code remains local preview1.020. Licenses and
attribution are in OFL.txt/NOTICE.txt.
