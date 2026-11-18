# Contextual pipe delimiters

Delimiter bars use the parentheses’ vertical bounds and midpoint stem thickness at every weight master. Opening bars move14units right; closing bars move14units left. Each keeps its600-unit advance. These context alternates are enabled by calt and independent of lifetime-placement ss01.

Recognizes paired bars at a text-run start, after closure-introducing punctuation (with up to2spaces), or after move/async/do. The interior allows up to48parameter-like glyphs, including identifiers, commas, type punctuation, scopes and lifetime forms. Context recognition is typographic, not a language parser. Ordinary a|b, a|b|c, logical||, |=, |- and shell pipelines are preserved in tested cases. Empty|| is styled only after an explicit introduction such as assignment.

Bar-Delimiters.svg/png/pdf show actual on/off behavior at Light, Book and Regular. validation.json covers11weights, positive/negative contexts, unchanged operators, exact delimiter span, matching thickness and inward placement. Both ss01 states are checked, including typed lifetime parameters. OTS passed; every existing outline, variation and advance matches the1.028input. The new glyphs and calt lookups are additive. Rebuild using syntax_numeral_study.py --family code, then code_bar_proof.py and render_svg.py. code_bar_proof.py --check verifies without rewriting proofs; --font can verify a packaged font.

Installable1.029preview includes these delimiter forms and the independent lifetime option. Installed/published1.027 remains unchanged.
