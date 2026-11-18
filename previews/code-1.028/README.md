# Daikonic Transit Code 1.028 preview

Rust lifetimes use the existing opening single quote at its normal size and weight. The standard calt form keeps the marker in its own600-unit cell. Stylistic set ss01, Boundary-centered Rust lifetimes, independently enables a quote centered on the following cell boundary and shifts an adjoining < or & exactly one cell right. Compact placement is off by default; it also works when calt is disabled. Character literals retain their ordinary quotes, and all input advances stay600units.

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
validation records are in previews/code-1.028/specimens/ and tools/.
Production native-source adoption remains pending. Earlier studies and released fonts are preserved.

All4preview fonts pass OTS; VF drawing/variation/layout/metrics tables exactly
match the selected trial. See selection.json and the trial validation.json for
11weight interpolation, fixed-advance, repeat-fitting and operator checks.
Specimens show enlarged comparisons and all3weights in light/dark polarity.

Rebuild with python tools/package_code_preview.py --version 1.028.
Add --install to back up and replace the current user font. OFL.txt/NOTICE.txt apply.
