"""Apply the existing Code context rules to the rebuilt variable glyphs."""

from math import isclose

from fontTools.misc.roundTools import otRound
from fontTools.pens.ttGlyphPen import TTGlyphPen
import uharfbuzz as hb

from check_code_rebuild import shape
from code_angle_pairs import ANGLE_CASES, build_angle_pairs
from code_outlines import refresh_bounds
from code_structural_fit import build_structural_angles
from font_feature_tools import append_glyph
from italic_returns import raw_outline


def align_pipe(font, axis):
    _, bottom, _, top = raw_outline(font.getGlyphSet(), "bar").bounds
    font["glyf"]["bar"].coordinates.translate((0, otRound(axis - (top + bottom) / 2)))
    refresh_bounds(font, "bar")


def build_layout(font, recipe):
    cell = recipe["alphabet_review"]["cell"]
    settings = recipe["layout_review"]
    depth = settings["angle_depth"]

    def install(name, parts, advance):
        pen = TTGlyphPen(font.getGlyphSet())
        for donor, sx, sy, x, y in parts:
            pen.addComponent(donor, (sx, 0, 0, sy, otRound(x), otRound(y)))
        append_glyph(font, name, pen.glyph(), [], advance)

    def alias(name, donor):
        install(name, [(donor, 1, 1, 0, 0)], cell)

    build_angle_pairs(font, depth, settings["angle_span"], cell, alias=alias)
    build_structural_angles(font, cell, depth, shift=settings["mixed_angle_shift"],
                            install_closer=install)


def angle_styles(rows):
    styles = []
    for name, *_ in rows:
        if name in ("less", "greater"):
            styles.append(False)
        elif name in ("less.generic", "greater.generic"):
            styles.append(True)
        elif name.startswith("code.genericClose"):
            styles.extend([True] * int(name.removeprefix("code.genericClose")))
    return styles


def verify_layout(font, path, recipe, weights):
    cell = recipe["alphabet_review"]["cell"]
    axis = recipe["horizontal_punctuation_review"]["minus_center"]
    settings = recipe["layout_review"]
    depth, span = settings["angle_depth"], settings["angle_span"]
    engine = hb.Font(hb.Face(path.read_bytes()))
    examples = {
        **ANGLE_CASES,
        "a < b > c": [False, False], "a<b>c": [False, False],
        "Vec<\nT>": [False, False], "<'a>": [True, True], "a >> b": [False, False],
        "Vec<" + "T" * span + ">": [True, True],
        "Vec<" + "T" * (span + 1) + ">": [False, False],
        "A<" * depth + "T" + ">" * depth: [True] * (depth * 2),
        "A<" * (depth + 1) + "T" + ">" * (depth + 1): [False] + [True] * (depth * 2) + [False],
    }
    mixed = ("<[T]>", "[<T>]", "<[T", "[<T", "T]>", "T>]")
    delicate = "a >= b <= c -> d ->> e <- f <<- g => h"
    shift = settings["mixed_angle_shift"]
    for weight in weights:
        engine.set_variations({"wght": weight})
        glyphs = font.getGlyphSet(location={"wght": weight})
        delimiters = ("parenleft", "parenright", "bracketleft", "bracketright",
                      "braceleft", "braceright", "bar", "less.generic", "greater.generic")
        bounds = {name: raw_outline(glyphs, name).bounds for name in delimiters}
        assert all(isclose((box[1] + box[3]) / 2, axis, abs_tol=.5) for box in bounds.values()), (weight, bounds)
        assert bounds["bar"][1::2] == bounds["parenleft"][1::2], (weight, bounds)
        for text, expected in examples.items():
            for enabled in (True, False):
                rows = shape(engine, text, {"calt": enabled})
                assert angle_styles(rows) == (expected if enabled else [False] * len(expected)), (weight, text, rows)
                assert sum(row[2] for row in rows) == len(text) * cell, (weight, text, rows)
        for text in mixed:
            rows = shape(engine, text, {})
            assert len(rows) == len(text) and all(row[2] == cell for row in rows), rows
            assert angle_styles(rows) == [True] * sum(char in "<>" for char in text), rows
            if text.startswith(("<[", "[<")):
                assert [row[4] for row in rows[:2]] == [shift, -shift], (text, rows)
            if text.endswith(("]>", ">]")):
                assert [row[4] for row in rows[-2:]] == [shift, -shift], (text, rows)
        assert shape(engine, delicate, {}) == shape(engine, delicate, {"calt": False}), weight
        for count in range(2, depth + 1):
            text = "A<" * count + "T" + ">" * count + " tail"
            rows = shape(engine, text, {})
            assert rows[2 * count + 1][:3] == [f"code.genericClose{count}", 2 * count + 1, count * cell], rows
            assert sum(row[2] for row in rows[:2 * count + 2]) == (3 * count + 1) * cell, rows

    carets = font["GDEF"].table.LigCaretList
    values = {name: record.CaretValue for name, record in zip(carets.Coverage.glyphs, carets.LigGlyph, strict=True)}
    for count in range(2, depth + 1):
        assert [value.Coordinate for value in values[f"code.genericClose{count}"]] == list(range(cell, count * cell, cell))
    return {"delimiter_center": axis, "angle_depth": depth, "angle_span": span,
            "mixed_angle_offset": shift, "weights": weights, "mixed_angle_advances": cell}
