# Independently switchable lifetime placement

Both modes use the existing opening single quote at its normal size and weight. With calt enabled, normal lifetimes keep this quote in its own cell. Stylistic set ss01 (Boundary-centered Rust lifetimes) independently enables the quote centered on the following cell boundary and shifts < / & exactly600units. ss01 is off by default and also works when calt is disabled. Character literals retain ordinary apostrophes.

Enable ss01=1 in HarfBuzz/WezTerm, "ss01" 1 in CSS font-feature-settings, or the named stylistic set in applications with a feature menu. Set ss01=0 to retain normal placement. Keep other desired ligature settings enabled.

Lifetime-Toggle.svg/png/pdf show the actual feature off/on in Light, Book and Regular. Lifetime-Boundary.svg/png/pdf show the compact cell grid.26lifetime/literal contexts pass at11weights for all4calt/ss01 combinations. Other coding features are identical with ss01 on or off. Compact collision checks cover54initials with3prefixes at11weights.

Canonical installable VF and named Light/Book/Regular TTF snapshots are prepared under previews/code-1.028/. This local preview is not installed or published; released/installed1.027 remains unchanged.
