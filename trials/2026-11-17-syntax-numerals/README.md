# Syntax and numeral review fonts

Local review fonts, not installed or published. Each face has a distinct “Syntax Study” family name and version 0.001. Sources are frozen by path and SHA256 in recipes/syntax-numeral-trial.json. All fonts incorporate the shared normal-dot palette documented in ../2026-11-17-dot-palette/README.md.

Code: equal bars widen 8% horizontally; thickness and vertical spacing remain unchanged. Adds ?. !. ${ $[ $( .. .= ..= ... := |= |- ## ### #### and <' contextual ligatures. Three ASCII periods retain three cells; Unicode ellipsis retains one. Token ligatures retain their input advance and 600-unit carets. The ?. pair restores its original internal spacing (Book diamond gap 342 units) and shifts both parts 60 units right from their original positions. The !. pair also restores its original spacing and placement (Book gap 329 units), without a right shift. Punctuation-Pairs.png/PDF/SVG compare original spacing with and without the right shift across Light, Book and Regular. Existing arrows, operators and combining marks remain supported.

Sans and System: optional frac, numr and dnom features reuse the source-designed superscript/subscript figures; multi-digit fractions work. Includes 18 Unicode vulgar fractions with matching variable advance functions. Fractions are off by default.

Sans: optional onum old-style figures, with lnum restoring lining forms. Old-style 0 derives from o, 6/8 retain ascenders, and 3/4/5/7/9 descend. Lining figures remain the default. System retains its existing tabular-number feature and proportional default 1.

Code, Fractions and Oldstyle are matched PNG/PDF/SVG specimens. Fonts are variable TTF review builds. Editing/rebuilding is script-based; the current production native Glyphs/UFO sources have not been overwritten. See recipe-report.json and validation.json for generated feature and check results.

All three VFs pass OTS. Shaping is checked at 61 weight/optical locations, including all requested syntax groups, existing operators, generic contexts, carets, combining marks, optional numerals, tabular figures and Unicode fraction metrics. HarfBuzz integer advance rounding may differ by up to 2 units between a single Unicode fraction and a three-glyph feature fraction; the underlying variable metric functions agree within 0.01 units.

Rebuild steps, tools and attribution are documented in the adjacent dot-palette README; font licensing and original attribution remain in OFL.txt and NOTICE.txt at the repository root.

Rust lifetimes use a diamond-headed prime with a22.5-degree down-left tail,80% of the bar stem thickness, a horizontally cut terminal18units above x-height, and a right-aligned600-unit cell. Common lifetime/label forms use calt; quoted identifier/character sequences up to32characters stay ordinary. This is a bounded neighboring-glyph heuristic, not a Rust parser; it may also activate inside comments or strings. The source recipe and check_rust_lifetimes.py are the design/check references. Rust-Lifetimes.png/PDF/SVG cover all three named weights and literal exclusions.
