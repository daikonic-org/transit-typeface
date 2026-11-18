# Diamond, box and mixed enclosure ligatures

Six calt sequences: <> becomes a closed diamond; [] becomes a closed box; <[ / ]> and [< / >] use joined compound opening/closing shapes. The two compound forms retain visible square and angled elements, joined by top/bottom rails. They work around content and in empty nested forms <[]> / [<>]. They share the full square-bracket vertical span, the one-step-heavier delimiter stems and diagonal weight, and retain1200-unit advances with a600-unit internal caret.

This is an additive study based on the frozen1.030source. All original glyph outlines, variations and metrics are unchanged. Existing coding ligatures run first, including the previously selected dollar/interpolation pairs. New sequences are appended to calt. ss01lifetime placement remains independent. Matched SVG/PNG/PDF proof shows actual on/off atLight,Book,Regular.

Validated11weights: all six substitutions, on/off,1200advance,600caret, bracket-height match, nesting, ss01independence and OTS. Existing pipe-delimiter contexts/operators and all4lifetime feature combinations also pass. Installable1.031preview includes canonicalVF and3namedTTFs; not installed or published. Installed/released1.027 unchanged.
