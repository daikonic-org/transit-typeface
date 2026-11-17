# Daikonic Transit Code 1.026 preview

Approved larger period-based normal diamond palette across weights. Equal bars widen horizontally by 8%. Adds optional-chaining/non-null, interpolation, range, assignment, turnstile, hash and Rust-lifetime ligatures; generic angle alternates stay within baseline/cap height. The ?. and !. pairs retain original internal spacing; only ?. shifts 60 units right. Adds a contextual apostrophe fit for Rust lifetimes and labels, preserving character literals through bounded nearby-character checks. The lifetime prime uses a diamond head, a22.5-degree tapered stroke at80% of the punctuation stem and a flat terminal just above x-height. The less-than sign is tall by default, but short between whitespace on both sides or lowercase/numeric operands; adjacent capitalized or mixed-case words preserve tall generic contexts, including Vec<u8>. All glyph drawings, weights and advances are unchanged from1.025.

Also includes the balanced i,
stronger inward delimiters, extended brace pinch, heavier full-width baseline
underscore, wider hyphen, and optical placement for selected lowercase/K pairs.
The normal lowercase a is unchanged. Sans and System are unchanged.

Install VF/DaikonicTransitCode-VF.ttf for variable weights300–400, defaultBook350.
TTF/ contains named-weight snapshots of the same VF. Install either format.
The menu family is simply Daikonic Transit Code. Existing Book350 editor settings
continue to work; restart applications after replacing a font.

All Code characters retain 600-unit cells; ligatures preserve the width of their input and caret positions. Existing arrow ligatures, optical positioning and mark attachment remain intact. Bullets remain separate. Repeated
@@/@@@ use a compact contextual alternate to avoid touching.
Enable calt/ligatures for this fitting and the existing operator ligatures.
Browser proofs were reviewed; editor/terminal rendering still needs a smoke test.

This cut is packaged as a preview, separately from stable font releases. The released Code font
and native sources/code/ remain1.017. Compatible trial sources/scripts and their
validation records are in previews/code-1.026/study/ and tools/.
Production native-source adoption remains pending. Earlier studies and released fonts are preserved.

All4preview fonts pass OTS; VF drawing/variation/layout/metrics tables exactly
match the selected trial. See selection.json and the trial validation.json for
11weight interpolation, fixed-advance, repeat-fitting and operator checks.
Specimens show enlarged comparisons and all3weights in light/dark polarity.

Rebuild with python tools/package_code_preview.py --version 1.026.
Add --install to back up and replace the current user font. OFL.txt/NOTICE.txt apply.
