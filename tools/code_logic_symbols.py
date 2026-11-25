"""Transit math symbols and optional prefix-not rendering for Code Logic."""

from itertools import product
from pathlib import Path
import unicodedata
import pathops
from fontTools.ttLib import TTFont
from audit import shape_from_glyphs, spans
from font_feature_tools import compose, from_paths, master_locations, add_features
from specimens import ROOT, DATA, Panel, specimen_families
from code_balance_study import bind
from check_syntax_numerals import run
from code_logic_sequences import OUT as SOURCE

OUT = ROOT / "sources/code-logic-symbols/DaikonicTransitCodeLogicSymbols-VF.ttf"
SYMBOLS = {0x00AC: "logicalnot", 0x2200: "universal", 0x2203: "existential"}


def check(path):
    f = TTFont(path)
    assert all(f.getBestCmap().get(cp) == name for cp, name in SYMBOLS.items())
    for weight, calt, compact, logic in product(
        range(300, 401, 10), [False, True], [False, True], [False, True]
    ):
        features = {"calt": calt, "ss01": compact, "ss02": logic}
        for text in ["!x", "!(a)", "!!x"]:
            result = run(path, text, {"wght": weight}, features)
            names = [p[0] for p in result]
            assert names.count("logicalnot") == (text.count("!") if logic else 0), (
                text,
                features,
                names,
            )
            assert sum(p[1] for p in result) == len(text) * 600
        for text in ["a != b", "a !== b", "a!.b", "panic!()", "n!", "'!'", '"!"']:
            before = run(path, text, {"wght": weight}, {**features, "ss02": False})
            after = run(path, text, {"wght": weight}, features)
            assert before == after, (text, features, after)
        result = run(path, "∀x ∃y ¬p", {"wght": weight}, features)
        assert all(name != ".notdef" for name, *_ in result)
        assert sum(p[1] for p in result) == len("∀x ∃y ¬p") * 600
    for weight in range(300, 401, 10):
        gs = f.getGlyphSet(location={"wght": weight})
        equal = shape_from_glyphs(gs, "equal")
        negation = shape_from_glyphs(gs, "logicalnot")
        assert max(abs(a - b) for a, b in zip(equal.bounds, negation.bounds)) < 1
        assert f["hmtx"]["universal"][0] == f["hmtx"]["existential"][0] == 600
    print(
        "Logic symbols: Unicode coverage, 11 weights, eight toggles, prefix-not and protected syntax verified",
        flush=True,
    )


def add_logic_not(font):
    words = sorted(
        {
            name
            for cp, name in font.getBestCmap().items()
            if unicodedata.category(chr(cp)).startswith("L")
            or chr(cp).isdigit()
            or chr(cp) == "_"
        }
    )
    add_features(
        font,
        "\n".join(
            [
                "languagesystem DFLT dflt;",
                "languagesystem latn dflt;",
                "@LogicWord=[" + " ".join(words) + "];",
                "feature ss02 { lookup LogicNot { lookupflag IgnoreMarks;",
                "ignore sub @LogicWord exclam';",
                "ignore sub [quotesingle quotedbl] exclam';",
                "ignore sub exclam' [equal period quotesingle quotedbl];",
                "sub exclam' by logicalnot;",
                "} LogicNot; } ss02;",
            ]
        ),
    )


def main():
    font = TTFont(SOURCE, recalcTimestamp=False)
    cap = font["OS/2"].sCapHeight
    compose(font, "universal", [("A", -1, -1, 600, cap)], 600, metric_source="A")
    compose(font, "existential", [("E", -1, 1, 600, 0)], 600, metric_source="E")
    _, locations = master_locations(font)
    paths = []
    for location in locations:
        gs = font.getGlyphSet(location=location)
        equal = shape_from_glyphs(gs, "equal")
        left, bottom, right, top = equal.bounds
        bars = spans(equal, (left + right) / 2, 0)
        thickness = bars[-1][1] - bars[-1][0]
        path = pathops.Path()
        pen = path.getPen()
        points = [
            (left, top),
            (right, top),
            (right, bottom),
            (right - thickness, bottom),
            (right - thickness, top - thickness),
            (left, top - thickness),
        ]
        pen.moveTo(points[0])
        for point in points[1:]:
            pen.lineTo(point)
        pen.closePath()
        paths.append(path)
    from_paths(font, "logicalnot", locations, paths, 600)
    for table in font["cmap"].tables:
        if table.isUnicode() and table.format in (4, 12):
            table.cmap.update(SYMBOLS)
    font["OS/2"].recalcUnicodeRanges(font)
    add_logic_not(font)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    font.save(OUT)
    check(OUT)


def proof():
    from copy import deepcopy
    from fontTools.varLib.instancer import instantiateVariableFont

    vf = TTFont(ROOT / specimen_families()["code"]["font"])
    parts = []
    for row, (weight, label) in enumerate(
        [(300, "Light"), (350, "Book"), (400, "Regular")]
    ):
        font = instantiateVariableFont(deepcopy(vf), {"wght": weight}, inplace=True)
        for col, logic in enumerate([True, False]):
            p = Panel(
                "logic-symbols-" + str(weight) + str(col), DATA["families"]["code"]
            )
            bind(p, font)
            x, y = 25 + 650 * col, 40 + row * 190
            p.text(
                label + " / Logic " + ("on" if logic else "off"),
                x,
                y,
                23,
                400,
                "#194454",
            )
            for line, text in enumerate(
                ["!p  !!p  p != q  p !== q", "∀x ∃y : !(p(x) == y)"]
            ):
                p.text(
                    text,
                    x,
                    y + 65 + 65 * line,
                    32,
                    400,
                    "#101712",
                    features={"calt": True, "ss02": logic},
                    max_width=610,
                )
            parts.append(p.body())
    (ROOT / "specimens/features/Logic-Symbols.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="600" viewBox="0 0 1300 600"><rect width="1300" height="600" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--proof", action="store_true")
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    if args.proof:
        proof()
    elif args.check:
        check((args.font or OUT).resolve())
    else:
        main()
