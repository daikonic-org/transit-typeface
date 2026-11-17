# Code: wider hyphen and k/K optical positioning

Builds on the heavier-underscore trial, retaining the selected i, delimiters,
flat-ended brace nose, full-cell baseline underscore and prior optical fitting.

The ASCII hyphen is 344 rather than 304 units wide at Book (+40, about13%).
Width expands about its cell center; original vertical position/thickness remain.
At other weights the same width scale applies, with integer rounding. Unicode
minus, en/em dashes and arrow drawings are unchanged. GSUB/operator shaping
is retained exactly, so the wider standalone hyphen does not alter arrow ligatures.

GPOS calt adds k and K to the existing diagonal/footed-letter fitting class
beside i/l, in either order. It adds focused ke/Ke/KE pairs: first letter +18,
second -18 horizontal placement. Both advances stay600, retaining code columns.
The uppercase scope is K-related pairs; AVATAR/To are unchanged control strings.
No lowercase/uppercase letter drawing or height changes. Positioning.fea is the
complete editable rule source, including previous pair rules.

Family Daikonic Transit Code Hyphen K Study: VF300–400/defaultBook350 and three
named snapshots. Four fonts pass OTS. Checks at11weights verify hyphen width,
centering within rounding, unchanged thickness/height, fixed600-unit cells,
unchanged glyph identities/advances, expected target pair offsets, retained
GSUB/GDEF/HVAR/cmap/fvar/STAT, and exact unrelated glyf/gvar/hmtx. This is a
focused optical study, not a complete uppercase or general lowercase kerning pass.

Comparison.png/pdf/svg covers Light/Book/Regular in light/dark polarity.
Browser.png shows actual loaded Book text at13/14/16px in Chrome157, device scale2.
Both font loads passed and images were opened for visual review. Editor/terminal
rendering remains unverified. The recipe is tools/code_hyphen_k_study.py in the
repository; recipe.py is its archived copy. Run from repo root with the existing
.venv. Previous underscore and delimiter trials are prerequisites and preserved.

Installed as canonical Daikonic Transit Code, version1.019 local preview, with
Book350 editor settings unchanged. Previous1.018 preview backed up; installation
paths and hash are retained in a local installation log excluded from Git. No repository commit or published release.
