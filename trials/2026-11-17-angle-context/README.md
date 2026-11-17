# Less-than context review

Local review font only. Published and installed Code1.025 are unchanged.

Use tall < by default. Keep the short comparison form with whitespace on both sides, or lowercase/digit/underscore operands on both sides. A capital anywhere in an adjacent word (bounded32glyph lookback/lookahead) keeps the tall generic form: Vec<T>, Vec<u8>, HashMap<key,value>, get<T>, and nested generics. Explicit ::< contexts remain tall. Greater-than policy and existing operator ligatures are unchanged. This is font context matching, not a parser.

All existing glyph drawings, full variable outline functions, advances, GPOS, GDEF carets, fvar, STAT and cmap match the frozen1.025 source; only GSUB context changes. check_syntax_numerals.py checks word/number, whitespace, generic and operator examples across weights; check_rust_lifetimes.py retains lifetime/literal coverage.

Rebuild: tools/syntax_numeral_study.py --family code, then tools/angle_context_proof.py. The frozen source record for1.025 in recipes/code-previews.json preserves the published cut.
