# Transit Code — original a / open upper-hook study

Review trial, not installed or adopted. The installed 1.021 preview remains intact.

The original Metropolitan Line two-storey a is the starting outline. Its upper hook extends left and below the bowl, then returns upward on the right, remaining open at the top. The original bowl, counter and right stem are retained before uniform scaling; there is no selective horizontal bowl stretch. At Book the whole construction is uniformly scaled to 80%. This is taller and narrower than the installed at symbol.

The Light/Book/Regular masters use raw offsets -25/0/+25 with 72% directional compensation, then compatible interpolation. Four binaries passed OTS; 11 weight samples passed construction, topology, shaping and advance checks. Regular has a small four-unit overhang on each side of its 600-unit cell. The compact contextual alternate is retained for adjacent at signs.

Book.png/PDF compare the installed shape with this trial. NamedWeights.png/PDF show all three weights. SVG files are editable outline specimens. source-a-provenance.json records original-source fidelity; validation.json records checks.

Rebuild from the transit-typeface repository using its existing Python environment:
    .venv/bin/python tools/code_at_source_a_study.py
    .venv/bin/python tools/render_svg.py --scale 2 trials/2026-11-17-code-at-source-a/Book.svg trials/2026-11-17-code-at-source-a/NamedWeights.svg trials/2026-11-17-code-at-source-a/Comparison.svg

The included recipe depends on the repository shared font pipeline and upstream Metropolitan Line source. See OFL.txt and NOTICE.txt for licensing and attribution.
