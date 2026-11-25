"""Restore the optional Logic set and independent backslash shortcuts."""

from itertools import product

import uharfbuzz as hb

from check_code_rebuild import shape
from code_enclosure_ligatures import closed_enclosures
from code_glyph_names import sequence_name
from code_logic_sequences import SEQUENCES
from code_logic_shortcuts import COMMANDS, add_commands, glyph_name
from code_logic_symbols import add_logic_not
from font_feature_tools import add_features, from_paths, label_stylistic_set, master_locations


def build_logic(font, cell, install):
    cmap = font.getBestCmap()
    diamond, box = (sequence_name(cmap, name) for name in ("code.enclosureDiamond", "code.enclosureBox"))
    symbols = {"code.enclosureDiamond": diamond, "code.enclosureBox": box}
    _, locations = master_locations(font)
    outlines = [closed_enclosures(font.getGlyphSet(location=location), cell) for location in locations]
    for index, name in enumerate((diamond, box)):
        from_paths(font, name, locations, [item[index] for item in outlines], 2 * cell)
    for name, parts in SEQUENCES.values():
        install(name, [(symbols[part], 1, 1, 2 * cell * index, 0)
                       for index, part in enumerate(parts)], 4 * cell)

    rules = [
        "languagesystem DFLT dflt;", "languagesystem latn dflt;",
        "@LogicLess=[less less.generic];", "@LogicGreater=[greater greater.generic];",
        "feature ss02 {",
        "sub bracketleft @LogicLess @LogicGreater bracketright by code.logicBoxDiamond;",
        "sub @LogicLess bracketleft bracketright @LogicGreater by code.logicDiamondBox;",
        f"sub @LogicLess @LogicGreater by {diamond};",
        f"sub bracketleft bracketright by {box};",
        "} ss02;", "table GDEF {",
    ]
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    for name, advance in ((diamond, 2), (box, 2), *((name, 4) for name, _ in SEQUENCES.values())):
        classes[name] = 2
        carets = " ".join(str(index * cell) for index in range(1, advance))
        rules.append(f"LigatureCaretByPos {name} {carets};")
    rules.append("} GDEF;")
    add_features(font, "\n".join(rules))
    add_logic_not(font)
    label_stylistic_set(font, "ss02", "Logic")
    commands = {command: symbols.get(name, name) for command, name in COMMANDS.items()}
    aliases = {command: sequence_name(cmap, glyph_name(command)) for command in commands}
    add_commands(font, commands, aliases, cell, install=install)


def verify_logic(font, path, cell, weights):
    cmap = font.getBestCmap()
    engine = hb.Font(hb.Face(path.read_bytes()))
    tokens = {"<>": sequence_name(cmap, "code.enclosureDiamond"),
              "[]": sequence_name(cmap, "code.enclosureBox"),
              **{token: name for token, (name, _) in SEQUENCES.items()}}
    for weight, logic, context in product(weights, (True, False), (True, False)):
        engine.set_variations({"wght": weight})
        features = {"ss02": logic, "calt": context}
        for token, name in tokens.items():
            rows = shape(engine, token, features)
            assert sum(row[2] for row in rows) == len(token) * cell
            assert (len(rows) == 1 and rows[0][0] == name) == logic, (weight, token, features, rows)
        for text, expected in (("!p", 1), ("!!p", 2), ("'!'", 0),
                               ("panic!()", 0), ("a != b !== c!.d", 0)):
            assert sum(row[0] == "logicalnot" for row in shape(engine, text, features)) == int(logic) * expected
        for command in COMMANDS:
            name = sequence_name(cmap, glyph_name(command))
            result = shape(engine, command + " x", features)
            assert (result[0][0] == name) == context
            assert sum(row[2] for row in result) == (len(command) + 2) * cell
            for text in ("x" + command, "\\" + command, command + "2", command + "_name"):
                assert all(row[0] != name for row in shape(engine, text, features))
    return {"logic": "ss02", "shortcuts": list(COMMANDS), "weights": weights}
