# Shared diamond-dot palette and bounded generic angles

Review build, 17 November 2026. Current installed and published fonts remain unchanged.

Normal dots derive from Code’s existing larger variable period, and from Sans/System’s existing variable i dot, including period, colon, semicolon top, question/exclamation marks, middle dots, division, ellipsis, combining/spacing accents, precomposed characters and existing dotted ligatures. Code retains its stronger punctuation emphasis; its i/j/accent dots also follow the larger period master. Sans and System retain their existing i-dot proportions. Bullets remain separate and unchanged. Comma and quotation tails are outside this dot-only change. Code’s dotted-zero marker follows its normal dot master; the small ring in the numero sign is preserved.

Paired dots retain their centers unless they need clearance: minimum 12 units or 8% of dot width. Catalan ldot/Ldot retain clearance from the stem. Code question/exclamation and division dots shift vertically only where needed to retain 12 units of clearance from their bodies, including inverted and doubled forms. At Book, the Code period retains its original 156×157-unit size. The normal dot shape and weight curve have one implementation, reused throughout. Actual font outlines are flattened compatible copies for application support.

Generic angles in the combined Code study have a height halfway between comparison signs and brackets, capped to cap height and centered at half cap height. In Book, the generic bounds are y=22–678 (cap=700), compared with y=83–517 for ordinary < and y=-139–740 for the bracket. Vertical terminal cuts and equals-based stroke thickness are preserved. Adjacent identifiers invoke generic forms through calt; spaced comparisons keep comparison signs. This is a typographic heuristic, not a language parser: a<b also receives the generic form.

Comparison.png/PDF show current and revised normal dots. Angles.png/PDF show final combined-study generic forms. SVGs contain editable vector outlines. Intermediate dot-palette TTFs retain original names and are build inputs; use the separately named Syntax Study fonts for installation trials.

Validation: all three VFs passed OTS; 61 weight/optical locations checked. Non-dot raw points and variation deltas, advances, phantom metrics, bullets and GSUB/GPOS/GDEF/HVAR are preserved. Normal dot dimensions agree within rounding tolerance, and paired-dot clearance survives intermediate weights.

Rebuild from the repository root:

    .venv/bin/python tools/dot_palette.py
    .venv/bin/python tools/check_dot_palette.py
    .venv/bin/python tools/syntax_numeral_study.py
    .venv/bin/python tools/check_syntax_numerals.py
    .venv/bin/python tools/dot_palette_proofs.py
    .venv/bin/python tools/syntax_numeral_proofs.py

Render SVGs using tools/render_svg.py. Frozen source paths and checksums are in recipes/syntax-numeral-trial.json. This build uses FontTools for variable outlines/OpenType tables, Skia PathOps for geometry, HarfBuzz for shaping, OTS for font validation and Chromium for matched PNG/vector PDF output. Metropolitan Line attribution and OFL remain in the root NOTICE.txt and OFL.txt.
