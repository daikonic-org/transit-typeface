"""Check contextual pipe delimiters and render current-design feature proofs."""

from copy import deepcopy
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import ots
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from audit import shape_from_glyphs, spans
from code_balance_study import bind
from specimens import ROOT, DATA, Panel

OUT = ROOT / "trials/2026-11-17-bar-delimiters"
POSITIVE = [
    "|x|",
    "| x |",
    "map(|x| x + 1)",
    "let f = |x, y| x+y",
    "move |x| x",
    "async |x| x",
    "do |x| x",
    "{ |x| x }",
    "let f = || 42",
    "|x: &T| x",
    "|x: &'a T| x",
    "|x: Foo::Bar| x",
]
NEGATIVE = [
    "a | b",
    "a|b",
    "a | b | c",
    "a|b|c",
    "a || b",
    "||",
    "flags |= mask",
    "|-",
    "cat | sort | uniq",
]


def main(font_path=None, check_only=False):
    OUT.mkdir(exist_ok=True)
    source = (
        ROOT
        / "trials/2026-11-17-syntax-numerals/code/DaikonicTransitCodeSyntaxStudy-VF.ttf"
    )
    target = (font_path or source) if check_only else OUT / source.name
    if not check_only:
        shutil.copy2(source, target)
    vf = TTFont(target)
    h = hb.Font(hb.Face(target.read_bytes()))
    h.scale = (1000, 1000)
    baseline = ROOT / "previews/code-1.028/VF/DaikonicTransitCode-VF.ttf"
    old = TTFont(baseline)
    old_h = hb.Font(hb.Face(baseline.read_bytes()))
    old_h.scale = (1000, 1000)

    def run(font, engine, text, calt=True, compact=False):
        b = hb.Buffer()
        b.add_str(text)
        b.guess_segment_properties()
        hb.shape(engine, b, {"calt": calt, "ss01": compact})
        return [
            (font.getGlyphName(g.codepoint), p.x_advance, p.x_offset, p.y_offset)
            for g, p in zip(b.glyph_infos, b.glyph_positions)
        ]

    records = []
    for weight in range(300, 401, 10):
        h.set_variations({"wght": weight})
        old_h.set_variations({"wght": weight})
        for compact in (False, True):
            for text in POSITIVE:
                result = run(vf, h, text, compact=compact)
                assert [
                    n for n, a, x, y in result if n.startswith("bar.delimiter")
                ] == ["bar.delimiterOpen", "bar.delimiterClose"], (
                    weight,
                    text,
                    compact,
                    result,
                )
                assert sum(a for n, a, x, y in result) == 600 * len(text)
                off = run(vf, h, text, calt=False, compact=compact)
                assert not any(n.startswith("bar.delimiter") for n, a, x, y in off)
            for text in NEGATIVE + [
                "-> ->> => == === != !== <= >= ::",
                "?. !.",
                "&'a <'a> 'static",
            ]:
                assert run(vf, h, text, compact=compact) == run(
                    old, old_h, text, compact=compact
                ), (weight, text, compact)
        gs = vf.getGlyphSet(location={"wght": weight})
        parent = shape_from_glyphs(gs, "parenleft")
        lo, hi = parent.bounds[1], parent.bounds[3]
        stem = spans(parent, (lo + hi) / 2, 1)[0]
        thickness = stem[1] - stem[0]
        geometry = {}
        for name, center in [("bar.delimiterOpen", 314), ("bar.delimiterClose", 286)]:
            box = shape_from_glyphs(gs, name).bounds
            assert abs(box[1] - lo) < 1 and abs(box[3] - hi) < 1
            assert abs((box[2] - box[0]) - thickness) < 1.1
            assert abs((box[0] + box[2]) / 2 - center) < 1
            assert vf["hmtx"][name][0] == 600
            geometry[name] = list(box)
        records.append(
            {
                "weight": weight,
                "delimiter_span": [lo, hi],
                "stem_width": thickness,
                "bounds": geometry,
            }
        )
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [ots.OTS_SANITIZE, str(target), str(Path(tmp) / "check.ttf")],
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr.decode()
    if check_only:
        print(
            "Contextual pipe delimiters checked:11weights,paired contexts,preserved operators and lifetime toggle independence"
        )
        return
    (OUT / "validation.json").write_text(
        json.dumps(
            {
                "positive": POSITIVE,
                "negative": NEGATIVE,
                "weights": records,
                "feature": "calt",
                "lifetime_ss01": "on/off tested",
                "sanitizer": "passed",
                "context_limit": 48,
            },
            indent=2,
        )
        + "\n"
    )
    parts = []
    for row, (weight, label) in enumerate(
        [(300, "Light"), (350, "Book"), (400, "Regular")]
    ):
        font = instantiateVariableFont(deepcopy(vf), {"wght": weight}, inplace=True)
        for col, (title, enabled) in enumerate(
            [("Delimiter fitting / on", True), ("Delimiter fitting / off", False)]
        ):
            p = Panel("bar-" + label + str(col), DATA["families"]["code"])
            bind(p, font)
            x, y = 25 + 650 * col, 40 + 260 * row
            p.text(label + " / " + title, x, y, 21, 400, "#194454")
            for index, text in enumerate(
                [
                    "(|x|) [|x|] {|x|}",
                    "let f = |x, y| x + y;",
                    "map(|x| x)   a | b   a || b",
                ]
            ):
                p.text(
                    text,
                    x,
                    y + 65 + 65 * index,
                    32,
                    400,
                    "#101712",
                    features={"calt": enabled},
                    max_width=610,
                )
            parts.append(p.body())
    (OUT / "Bar-Delimiters.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="820" viewBox="0 0 1300 820"><title>Contextual pipe delimiters across weights</title><rect width="1300" height="820" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    print(
        "Pipe delimiters: contexts, operator preservation, lifetime toggle independence and geometry passed at11weights; OTS passed"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    main(args.font, args.check)
