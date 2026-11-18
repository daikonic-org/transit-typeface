"""Keep adjacent angle pairs ordinary unless both qualify as delimiters."""

from pathlib import Path
import json
from fontTools.ttLib import TTFont
from font_feature_tools import add_features
from specimens import ROOT, DATA, Panel
from code_balance_study import bind
from check_syntax_numerals import run

SOURCE = ROOT / "previews/code-1.032/VF/DaikonicTransitCode-VF.ttf"
OUT = ROOT / "releases/2026.11.18/code"


def check(path):
    source = TTFont(SOURCE)
    font = TTFont(path)
    for tag in ["glyf", "gvar", "GPOS", "GDEF", "hmtx", "HVAR", "cmap", "fvar"]:
        assert source.getTableData(tag) == font.getTableData(tag), tag
    cases = [
        "<>",
        "a<>b",
        "<>T",
        "Vec<>",
        "<>",
        "Vec<T>",
        "Vec<u8>",
        "a<b",
        "a > b",
        "Vec<Vec<T>>",
        "-> ->> => <= >=",
        "&'a <'a>",
    ]
    for weight in range(300, 401, 10):
        for calt in [False, True]:
            for compact in [False, True]:
                for logic in [False, True]:
                    features = {"calt": calt, "ss01": compact, "ss02": logic}
                    for text in cases:
                        before = run(SOURCE, text, {"wght": weight}, features)
                        after = run(path, text, {"wght": weight}, features)
                        assert sum(p[1] for p in after) == len(text) * 600
                        if "<>" not in text or logic or not calt:
                            assert before == after, (text, features)
                        else:
                            names = [p[0] for p in after]
                            start = text.index("<>")
                            pair = names[start : start + 2]
                            assert pair in (
                                ["less", "greater"],
                                ["less.generic", "greater.generic"],
                            ), (text, pair)
    assert [
        p[0] for p in run(path, "<>", {"wght": 350}, {"calt": True, "ss02": False})
    ] == ["less", "greater"]
    print(
        "Angle pairs: 11 weights, eight toggle combinations, retained drawings and unrelated syntax verified",
        flush=True,
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    font = TTFont(SOURCE, recalcTimestamp=False)
    add_features(
        font,
        """
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        feature calt {
            lookup BalancedEmptyLeft {
                lookupflag IgnoreMarks;
                sub less.generic' greater by less;
            } BalancedEmptyLeft;
            lookup BalancedEmptyRight {
                lookupflag IgnoreMarks;
                sub less greater.generic' by greater;
            } BalancedEmptyRight;
        } calt;
    """,
    )
    for record in font["name"].names:
        text = record.toUnicode()
        if record.nameID == 3:
            text = "DaikonicTransitCode-VF 1.034"
        elif record.nameID == 5:
            text = "Version 1.034"
        elif record.nameID == 10:
            text = "Daikonic Transit Code; balanced angle pairs, independent Logic and lifetime features."
        record.string = text.encode(record.getEncoding())
    font["head"].fontRevision = 1.034
    target = OUT / "VF/DaikonicTransitCode-VF.ttf"
    target.parent.mkdir(exist_ok=True)
    font.save(target)
    (OUT / "selection.json").write_text(
        json.dumps(
            {
                "family": "Daikonic Transit Code",
                "version": "1.034",
                "status": "release",
                "weight_range": [300, 400],
            },
            indent=2,
        )
        + "\n"
    )
    check(target)
    p = Panel("angle-pairs", DATA["families"]["code"])
    from fontTools.varLib.instancer import instantiateVariableFont

    bind(p, instantiateVariableFont(TTFont(target), {"wght": 350}, inplace=True))
    for row, (label, features) in enumerate(
        [("Logic off", {"ss02": False}), ("Logic on", {"ss02": True})]
    ):
        p.text(label, 25, 40 + row * 150, 22, 400, "#194454")
        p.text(
            "<>  a<>b  <>T  Vec<>  Vec<T>  a<b",
            25,
            105 + row * 150,
            34,
            400,
            "#101712",
            features={"calt": True, **features},
        )
    (ROOT / "specimens/features/Angle-Pairs.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1250" height="310" viewBox="0 0 1250 310"><rect width="1250" height="310" fill="#EEECD9"/>'
        + p.body()
        + "</svg>"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check(OUT / "VF/DaikonicTransitCode-VF.ttf") if args.check else main()
