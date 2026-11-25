"""Closed diamond/box and joined mixed delimiter ligatures for Code."""

from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import tempfile
import ots
import pathops
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from audit import shape_from_glyphs, spans
from font_feature_tools import (
    add_features,
    from_paths,
    master_locations,
    expanded_variations,
    label_stylistic_set,
)
from code_balance_study import bind
from specimens import ROOT, DATA, Panel

OUT = ROOT / "trials/2026-11-18-restored-joined-pairs"
SOURCE = (
    ROOT / "previews/code-1.030/source/DaikonicTransitCodeDelimiterWeightStudy-VF.ttf"
)
TOKENS = {
    "<>": "code.enclosureDiamond",
    "[]": "code.enclosureBox",
    "<[": "code.angleSquareOpen",
    "]>": "code.angleSquareClose",
    "[<": "code.squareAngleOpen",
    ">]": "code.squareAngleClose",
}


def polygon(points):
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()
    return path


def rectangle(l, b, r, t):
    return polygon([(l, b), (r, b), (r, t), (l, t)])


def union(*paths):
    result = paths[0]
    for path in paths[1:]:
        result = pathops.op(result, path, pathops.PathOp.UNION)
    return result


def left_angle(left, right, bottom, top, thickness):
    mid = (top + bottom) / 2
    slope = (top - mid) / (right - left)
    cut = thickness * math.sqrt(1 + slope * slope)
    return polygon(
        [
            (right, top),
            (left, mid),
            (right, bottom),
            (right, bottom + cut),
            (left + cut / slope, mid),
            (right, top - cut),
        ]
    )


def closed_enclosures(gs, cell=600):
    bracket = shape_from_glyphs(gs, "bracketleft")
    l, b, r, t = bracket.bounds
    mid = (b + t) / 2
    stem = spans(bracket, mid, 1)[0]
    vertical = stem[1] - stem[0]
    rails = spans(bracket, (stem[1] + r) / 2, 0)
    horizontal = rails[-1][1] - rails[-1][0]
    angle = shape_from_glyphs(gs, "less.generic")
    a = angle.bounds
    slope = (a[3] - a[1]) / 2 / (a[2] - a[0])
    interval = spans(angle, 400, 0)[-1]
    diagonal = (interval[1] - interval[0]) / math.sqrt(1 + slope * slope)
    outer = polygon([(cell / 5, mid), (cell, t), (9 * cell / 5, mid), (cell, b)])
    rx, ry = 4 * cell / 5, (t - b) / 2
    ix = rx - diagonal * math.sqrt(1 + (rx / ry) ** 2)
    iy = ry - diagonal * math.sqrt(1 + (ry / rx) ** 2)
    assert ix > 0 and iy > 0
    inner = polygon(
        [(cell - ix, mid), (cell, mid + iy), (cell + ix, mid), (cell, mid - iy)]
    )
    diamond = pathops.op(outer, inner, pathops.PathOp.DIFFERENCE)
    right = 2 * cell - l
    box = pathops.op(
        rectangle(l, b, right, t),
        rectangle(l + vertical, b + horizontal, right - vertical, t - horizontal),
        pathops.PathOp.DIFFERENCE,
    )
    return diamond, box, (bracket, l, b, r, t, horizontal, diagonal)


def main():
    OUT.mkdir(exist_ok=True)
    original = TTFont(SOURCE)
    font = deepcopy(original)
    _, locations = master_locations(font)
    paths = {name: [] for name in TOKENS.values()}
    for location in locations:
        f = instantiateVariableFont(deepcopy(original), location, inplace=True)
        gs = f.getGlyphSet()
        diamond, box, (bracket, l, b, r, t, horizontal, diagonal) = closed_enclosures(gs)
        paths[TOKENS["<>"]].append(diamond)
        paths[TOKENS["[]"]].append(box)
        left_outer = left_angle(120, 600, b, t, diagonal)
        bracket_inner = bracket.transform(1, 0, 0, 1, 600, 0)
        angle_square = union(
            left_outer,
            bracket_inner,
            rectangle(600, b, 600 + r, b + horizontal),
            rectangle(600, t - horizontal, 600 + r, t),
        )
        square_angle = union(
            bracket,
            left_angle(600, 1080, b, t, diagonal),
            rectangle(r, b, 1080, b + horizontal),
            rectangle(r, t - horizontal, 1080, t),
        )
        for token, path in [("<[", angle_square), ("[<", square_angle)]:
            paths[TOKENS[token]].append(path)
            closing = "]>" if token == "<[" else ">]"
            paths[TOKENS[closing]].append(path.transform(-1, 0, 0, 1, 1200, 0))
    for name, master_paths in paths.items():
        from_paths(font, name, locations, master_paths, 1200)
    rules = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "@EnclosureLess=[less less.generic];",
        "@EnclosureGreater=[greater greater.generic];",
        "feature ss02 {",
    ]
    # Mixed pairs take priority in nested empty forms such as <[]> and [<>].
    rules += [
        "sub @EnclosureLess bracketleft by " + TOKENS["<["] + ";",
        "sub bracketright @EnclosureGreater by " + TOKENS["]>"] + ";",
        "sub bracketleft @EnclosureLess by " + TOKENS["[<"] + ";",
        "sub @EnclosureGreater bracketright by " + TOKENS[">]"] + ";",
        "sub @EnclosureLess @EnclosureGreater by " + TOKENS["<>"] + ";",
        "sub bracketleft bracketright by " + TOKENS["[]"] + ";",
        "} ss02;",
        "table GDEF {",
    ]
    rules += ["LigatureCaretByPos " + name + " 600;" for name in TOKENS.values()]
    rules += ["} GDEF;"]
    add_features(font, "\n".join(rules))
    label_stylistic_set(font, "ss02", "Logic")
    family = font["name"].getDebugName(16)
    study = "Daikonic Transit Code Enclosure Study"
    for record in font["name"].names:
        record.string = (
            record.toUnicode()
            .replace(family, study)
            .replace(family.replace(" ", ""), study.replace(" ", ""))
            .encode(record.getEncoding())
        )
    font.recalcTimestamp = False
    target = OUT / "DaikonicTransitCodeEnclosureStudy-VF.ttf"
    font.save(target)
    actual = TTFont(target)
    restored = TTFont(
        ROOT / "previews/code-1.032/source/DaikonicTransitCodeEnclosureStudy-VF.ttf"
    )
    for name in TOKENS.values():
        assert actual["glyf"][name].compile(actual["glyf"]) == restored["glyf"][
            name
        ].compile(restored["glyf"]), (name, "restored outline")
        assert expanded_variations(actual, name) == expanded_variations(
            restored, name
        ), (name, "restored variation")
    for name in original.getGlyphOrder():
        assert original["glyf"][name].compile(original["glyf"]) == actual["glyf"][
            name
        ].compile(actual["glyf"]), name
        assert expanded_variations(original, name) == expanded_variations(
            actual, name
        ), name
        assert original["hmtx"][name] == actual["hmtx"][name], name
    for tag in ("GPOS", "cmap", "fvar", "STAT"):
        assert original.getTableData(tag) == actual.getTableData(tag), tag
    h = hb.Font(hb.Face(target.read_bytes()))
    h.scale = (1000, 1000)
    examples = {
        text: (
            [TOKENS["<["], TOKENS["]>"]]
            if text.startswith("<[")
            else [TOKENS["[<"], TOKENS[">]"]]
        )
        for text in ("<[T]>", "[<T>]", "<[]>", "[<>]")
    }

    def run(text, on=True, compact=False, calt=True):
        b = hb.Buffer()
        b.add_str(text)
        b.guess_segment_properties()
        hb.shape(h, b, {"calt": calt, "ss01": compact, "ss02": on})
        return [
            (actual.getGlyphName(g.codepoint), p.x_advance)
            for g, p in zip(b.glyph_infos, b.glyph_positions)
        ]

    for weight in range(300, 401, 10):
        h.set_variations({"wght": weight})
        gs = actual.getGlyphSet(location={"wght": weight})
        for token, name in TOKENS.items():
            for calt in (False, True):
                for compact in (False, True):
                    assert run(token, compact=compact, calt=calt) == [(name, 1200)], (
                        weight,
                        token,
                        calt,
                        compact,
                    )
                    assert len(run(token, on=False, compact=compact, calt=calt)) == 2
            box = shape_from_glyphs(gs, name).bounds
            parent = shape_from_glyphs(gs, "bracketleft").bounds
            assert abs(box[1] - parent[1]) < 1.1 and abs(box[3] - parent[3]) < 1.1, (
                weight,
                token,
                box,
            )
        for text, expected in examples.items():
            result = run(text)
            got = [n for n, a in result if n in TOKENS.values()]
            assert got == expected, (weight, text, result)
            assert sum(a for n, a in result) == len(text) * 600
        for calt in (False, True):
            for compact in (False, True):
                for text in (
                    "-> ->> => <- <<-",
                    "== === != !== <= >=",
                    "?. !. ::",
                    "&'a <'a> 'static",
                    "|x| x",
                    "a | b",
                ):
                    assert run(text, on=False, compact=compact, calt=calt) == run(
                        text, on=True, compact=compact, calt=calt
                    ), (weight, text, calt, compact, "logic independence")
        carets = actual["GDEF"].table.LigCaretList
        for name in TOKENS.values():
            index = carets.Coverage.glyphs.index(name)
            assert [v.Coordinate for v in carets.LigGlyph[index].CaretValue] == [600]
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [ots.OTS_SANITIZE, str(target), str(Path(tmp) / "check.ttf")],
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr.decode()
    (OUT / "validation.json").write_text(
        json.dumps(
            {
                "feature": "ss02",
                "label": "Logic",
                "default": "off",
                "independent": "all eight calt/ss01/ss02 combinations checked",
                "tokens": TOKENS,
                "examples": examples,
                "weights": list(range(300, 401, 10)),
                "advance": 1200,
                "caret": 600,
                "height": "full square-bracket span for all six forms",
                "restoration": "outlines and variation data exactly match approved joined1.032forms",
                "stroke": "existing one-step-heavier delimiter stems/diagonals",
                "unchanged": "all existing outlines,variations,metrics and positioning",
                "sanitizer": "passed",
            },
            indent=2,
        )
        + "\n"
    )
    parts = []
    for row, (weight, label) in enumerate(
        [(300, "Light"), (350, "Book"), (400, "Regular")]
    ):
        f = instantiateVariableFont(deepcopy(actual), {"wght": weight}, inplace=True)
        for col, (title, on) in enumerate(
            [("Logic on / ss02", True), ("Logic off / ss02", False)]
        ):
            p = Panel("enclosure-" + label + str(col), DATA["families"]["code"])
            bind(p, f)
            x, y = 25 + 650 * col, 40 + 280 * row
            p.text(label + " / " + title, x, y, 22, 400, "#194454")
            for line, text in enumerate(
                ["<>  []  <[T]>  [<T>]", "<[]>  [<>]", "Vec<T>  Vec<[T]>  [<T>]"]
            ):
                p.text(
                    text,
                    x,
                    y + 70 + 75 * line,
                    36 if line < 2 else 27,
                    400,
                    "#101712",
                    features={"calt": True, "ss02": on},
                    max_width=610,
                )
            parts.append(p.body())
    (OUT / "Enclosure-Ligatures.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="880" viewBox="0 0 1300 880"><title>Diamond, box and mixed enclosure ligatures</title><rect width="1300" height="880" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    print(
        "Six enclosure ligatures checked at11weights: fixed1200advances,600carets,nesting,independentLogic/calt/lifetime toggles,retained drawings; OTS passed"
    )


if __name__ == "__main__":
    main()
