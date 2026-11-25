"""Standard Code backslash commands, independent of the optional Logic set."""

from pathlib import Path
from itertools import product
from copy import deepcopy
import json
import unicodedata
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from font_feature_tools import compose, add_features
from check_syntax_numerals import run
from specimens import ROOT, DATA, Panel, specimen_families
from code_balance_study import bind

SOURCE = ROOT / "sources/code-structural-fit/VF/DaikonicTransitCode-VF.ttf"
OUT = ROOT / "releases/2026.11.18.2/code"
COMMANDS = {
    r"\forall": "universal",
    r"\exists": "existential",
    r"\not": "logicalnot",
    r"\box": "code.enclosureBox",
    r"\diamond": "code.enclosureDiamond",
}


def glyph_name(command):
    return "code.command." + command[1:]


def check(path):
    font = TTFont(path)
    source = TTFont(SOURCE)
    for name in source.getGlyphOrder():
        assert font["glyf"][name].compile(font["glyf"]) == source["glyf"][name].compile(
            source["glyf"]
        ), name
        assert font["gvar"].variations.get(name) == source["gvar"].variations.get(
            name
        ), name
        assert font["hmtx"][name] == source["hmtx"][name], name
    carets = dict(
        zip(
            font["GDEF"].table.LigCaretList.Coverage.glyphs,
            font["GDEF"].table.LigCaretList.LigGlyph,
        )
    )
    for weight, enabled, logic in product(
        range(300, 401, 10), [False, True], [False, True]
    ):
        features = {"calt": enabled, "ss02": logic}
        for command, original in COMMANDS.items():
            for text in [command, command + " x", command + "(x)"]:
                actual = run(path, text, {"wght": weight}, features)
                names = [p[0] for p in actual]
                assert (glyph_name(command) in names) == enabled, (
                    text,
                    weight,
                    features,
                    names,
                )
                assert sum(p[1] for p in actual) == len(text) * 600
                assert actual == run(
                    path, text, {"wght": weight}, {**features, "ss02": not logic}
                )
            for text in [
                command + "x",
                command + "_name",
                command + "2",
                "x" + command,
                "\\" + command,
            ]:
                actual = run(path, text, {"wght": weight}, features)
                assert glyph_name(command) not in [p[0] for p in actual], (
                    text,
                    features,
                    actual,
                )
            assert [
                v.Coordinate for v in carets[glyph_name(command)].CaretValue
            ] == list(range(600, len(command) * 600, 600))
            gs = font.getGlyphSet(location={"wght": weight})
            from audit import shape_from_glyphs

            before = shape_from_glyphs(gs, original).bounds
            after = shape_from_glyphs(gs, glyph_name(command)).bounds
            shift = len(command) * 600 - font["hmtx"][original][0]
            assert (
                max(
                    abs(a - b)
                    for a, b in zip(
                        after,
                        (before[0] + shift, before[1], before[2] + shift, before[3]),
                    )
                )
                < 1
            )
    for text in ["∀x ∃y ¬p", "[<>] <[]>", "!p != q !== r", "Vec<Vec<T>>", "&'a <'a>"]:
        for logic in [False, True]:
            assert run(path, text, {"wght": 350}, {"calt": True, "ss02": logic}) == run(
                SOURCE, text, {"wght": 350}, {"calt": True, "ss02": logic}
            )
    print(
        "Five standard shortcuts: 11 weights, Logic independence, word/escape guards, widths and carets verified",
        flush=True,
    )


def add_commands(font, commands, names, cell=600, *, install=None):
    cmap = font.getBestCmap()
    words = sorted(
        {
            name
            for cp, name in cmap.items()
            if unicodedata.category(chr(cp)).startswith("L")
            or chr(cp).isdigit()
            or chr(cp) == "_"
        }
    )
    tokens = {command: [cmap[ord(ch)] for ch in command] for command in commands}
    for command, original in commands.items():
        advance = len(command) * cell
        shift = advance - font["hmtx"][original][0]
        parts = [(original, 1, 1, shift, 0)]
        if install is None:
            compose(font, names[command], parts, advance)
        else:
            install(names[command], parts, advance)
        font["GDEF"].table.GlyphClassDef.classDefs[names[command]] = 2
    rules = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "@CommandWord=[" + " ".join(words) + "];",
        "lookup CommandForms {",
    ]
    for command, letters in tokens.items():
        rules.append("sub " + " ".join(letters) + " by " + names[command] + ";")
    rules += [
        "} CommandForms;",
        "feature calt { lookup CommandContext {",
        "ignore sub [backslash @CommandWord] backslash';",
    ]
    for command, letters in tokens.items():
        rules.append("ignore sub backslash' " + " ".join(letters[1:]) + " @CommandWord;")
    for command, letters in tokens.items():
        rules.append("sub backslash' lookup CommandForms " + " ".join(letters[1:]) + ";")
    rules += ["} CommandContext; } calt;", "table GDEF {"]
    for command in commands:
        rules.append(
            "LigatureCaretByPos "
            + names[command]
            + " "
            + " ".join(str(n) for n in range(cell, len(command) * cell, cell))
            + ";"
        )
    rules.append("} GDEF;")
    add_features(font, "\n".join(rules))


def main():
    font = TTFont(SOURCE, recalcTimestamp=False)
    add_commands(font, COMMANDS, {command: glyph_name(command) for command in COMMANDS})
    for record in font["name"].names:
        if record.nameID in (3, 5, 10):
            text = {
                3: "DaikonicTransitCode-VF 1.036",
                5: "Version 1.036",
                10: "Daikonic Transit Code; standard logic shortcuts and independent Logic toggle.",
            }[record.nameID]
            record.string = text.encode(record.getEncoding())
    font["head"].fontRevision = 1.036
    (OUT / "VF").mkdir(parents=True, exist_ok=True)
    target = OUT / "VF/DaikonicTransitCode-VF.ttf"
    font.save(target)
    (OUT / "selection.json").write_text(
        json.dumps(
            {
                "family": "Daikonic Transit Code",
                "version": "1.036",
                "status": "release",
                "weight_range": [300, 400],
            },
            indent=2,
        )
        + "\n"
    )
    check(target)


def proof():
    vf = TTFont(ROOT / specimen_families()["code"]["font"])
    parts = []
    for row, (weight, label) in enumerate(
        [(300, "Light"), (350, "Book"), (400, "Regular")]
    ):
        f = instantiateVariableFont(deepcopy(vf), {"wght": weight}, inplace=True)
        for col, logic in enumerate([False, True]):
            p = Panel("commands-" + str(weight) + str(col), DATA["families"]["code"])
            bind(p, f)
            x, y = 25 + 850 * col, 40 + row * 240
            p.text(
                label + " / Logic " + ("on" if logic else "off"),
                x,
                y,
                22,
                400,
                "#194454",
            )
            for line, text in enumerate(
                [r"\forall x \exists y", r"\not p \box p \diamond p", "∀x ∃y ¬p"]
            ):
                p.text(
                    text,
                    x,
                    y + 65 + 65 * line,
                    31,
                    400,
                    "#101712",
                    features={"calt": True, "ss02": logic},
                    max_width=800,
                )
            parts.append(p.body())
    (ROOT / "specimens/features/Logic-Shortcuts.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1700" height="760" viewBox="0 0 1700 760"><rect width="1700" height="760" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--proof", action="store_true")
    args = parser.parse_args()
    if args.proof:
        proof()
    elif args.check:
        check(OUT / "VF/DaikonicTransitCode-VF.ttf")
    else:
        main()
