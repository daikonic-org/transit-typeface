# Daikonic Transit Code 1.021 preview

Approved working preview with the single-storey a inside @, its larger smooth
outer loop and matching inner/outer stroke weights. Also includes the balanced i,
stronger inward delimiters, extended brace pinch, heavier full-width baseline
underscore, wider hyphen, and optical placement for selected lowercase/K pairs.
The normal lowercase a is unchanged. Sans and System are unchanged.

Install VF/DaikonicTransitCode-VF.ttf for variable weights300–400, defaultBook350.
TTF/ contains named-weight snapshots of the same VF. Install either format.
The menu family is simply Daikonic Transit Code. Existing Book350 editor settings
continue to work; restart applications after replacing a font.

The larger @ has slight ink overhang but retains its600-unit advance. Repeated
@@/@@@ use an equal-weight compact contextual alternate to avoid touching.
Enable calt/ligatures for this fitting and the existing operator ligatures.
Browser proofs were reviewed; editor/terminal rendering still needs a smoke test.

This preview has not been published as a GitHub release. The released Code font
and native sources/code/ remain1.017. Compatible trial sources/scripts and their
validation records are in trials/2026-11-16-code-at-single-storey/ and tools/.
Production native-source adoption, including accented/dotless i alignment, remains
pending. Earlier studies and released fonts are preserved.

All4preview fonts pass OTS; VF drawing/variation/layout/metrics tables exactly
match the selected trial. See selection.json and the trial validation.json for
11weight interpolation, fixed-advance, repeat-fitting and operator checks.
Specimens show enlarged comparisons and all3weights in light/dark polarity.

Rebuild with python tools/package_code_preview.py --version 1.021.
Add --install to back up and replace the current user font. OFL.txt/NOTICE.txt apply.
