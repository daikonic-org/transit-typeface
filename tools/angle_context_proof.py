"""Review lowercase/number comparison exceptions without replacing published fonts."""

from copy import deepcopy
import json
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from specimens import ROOT, DATA, Panel
from code_balance_study import bind
from font_feature_tools import expanded_variations
from check_syntax_numerals import run

OUT = ROOT / "trials/2026-11-17-angle-context"
ROWS = [
    "a<b   x<2   12<34",
    "a < b   a <b   a< b",
    "Vec<T>   Vec<u8>",
    "HashMap<key,value>",
    "Vec<Vec<T>>",
    "foo::<u8>   get<T>",
    "fn get<'a>(x: &'a T)",
    "<   <=   <<-   ->   =>",
]


def main():
    OUT.mkdir(exist_ok=True)
    recipe = json.loads((ROOT / "recipes/code-previews.json").read_text())
    source = (
        ROOT
        / "trials/2026-11-17-syntax-numerals/code/DaikonicTransitCodeSyntaxStudy-VF.ttf"
    )
    old_source = ROOT / recipe["versions"]["1.025"]["source"]
    previous = TTFont(old_source)
    candidate = TTFont(source)
    assert previous.getGlyphOrder() == candidate.getGlyphOrder()
    for n in previous.getGlyphOrder():
        assert previous["glyf"][n].compile(previous["glyf"]) == candidate["glyf"][
            n
        ].compile(candidate["glyf"]), (n, "drawing")
        assert expanded_variations(previous, n) == expanded_variations(candidate, n), (
            n,
            "variation",
        )
    for tag in ["hmtx", "HVAR", "GPOS", "GDEF", "fvar", "STAT", "cmap"]:
        assert previous[tag].compile(previous) == candidate[tag].compile(candidate), tag
    path = OUT / "DaikonicTransitCodeAngleContextStudy-VF.ttf"
    old = candidate["name"].getDebugName(16)
    family = "Daikonic Transit Code Angle Context Study"
    for record in candidate["name"].names:
        text = (
            record.toUnicode()
            .replace(old, family)
            .replace(old.replace(" ", ""), family.replace(" ", ""))
        )
        record.string = text.encode(record.getEncoding())
    candidate.recalcTimestamp = False
    candidate.save(path)
    examples = {text: [g[0] for g in run(path, text, {"wght": 350})] for text in ROWS}
    (OUT / "validation.json").write_text(
        json.dumps(
            {
                "source": str(old_source.relative_to(ROOT)),
                "glyphs_and_variation": "all unchanged",
                "metrics_gpos_carets": "unchanged",
                "changed": "GSUB less-than context only; greater-than policy retained",
                "examples": examples,
            },
            indent=2,
        )
        + "\n"
    )
    parts = []
    for col, (label, file) in enumerate(
        [
            (
                "Published 1.025",
                ROOT / "previews/code-1.025/VF/DaikonicTransitCode-VF.ttf",
            ),
            ("Lowercase/number rule", path),
        ]
    ):
        p = Panel("angles-review" + str(col), DATA["families"]["code"])
        bind(p, instantiateVariableFont(TTFont(file), {"wght": 350}, inplace=True))
        x = 25 + 650 * col
        p.text(label, x, 38, 23, 400, "#194454")
        for row, text in enumerate(ROWS):
            p.text(text, x, 108 + 70 * row, 33, 400, "#101712", max_width=605)
        parts.append(p.body())
    (OUT / "Comparison.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="670"><rect width="1300" height="670" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    (OUT / "README.md").write_text(
        """# Less-than context review

Local review font only. Published and installed Code1.025 are unchanged.

Use tall < by default. Keep the short comparison form with whitespace on both sides, or lowercase/digit/underscore operands on both sides. A capital anywhere in an adjacent word (bounded32glyph lookback/lookahead) keeps the tall generic form: Vec<T>, Vec<u8>, HashMap<key,value>, get<T>, and nested generics. Explicit ::< contexts remain tall. Greater-than policy and existing operator ligatures are unchanged. This is font context matching, not a parser.

All existing glyph drawings, full variable outline functions, advances, GPOS, GDEF carets, fvar, STAT and cmap match the frozen1.025 source; only GSUB context changes. check_syntax_numerals.py checks word/number, whitespace, generic and operator examples across weights; check_rust_lifetimes.py retains lifetime/literal coverage.

Rebuild: tools/syntax_numeral_study.py --family code, then tools/angle_context_proof.py. The frozen source record for1.025 in recipes/code-previews.json preserves the published cut.
"""
    )
    print(
        "New angle-context font/proof built; all drawings, variation and metrics identical to published source"
    )


if __name__ == "__main__":
    main()
