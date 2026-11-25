"""Compose the remaining fixed-advance Code syntax ligatures."""

from math import isclose

from fontTools.misc.roundTools import otRound
import pathops
import uharfbuzz as hb

from audit import shape_from_glyphs, spans
from check_code_rebuild import shape
from code_glyph_names import sequence_name
from code_math import fit_box, translated
from code_outlines import equal_bars, install_components, install_outline, polygon
from code_structural_fit import interpolation_parts
from italic_returns import raw_outline
from syntax_numeral_study import TOKENS, register_syntax_tokens


REBUILT_TOKENS = {token: f"code.syntax{index:02d}" for index, token in enumerate(TOKENS)
                  if token not in ("?.", "!.", "<'", "&'")}


def syntax_names(font):
    cmap = font.getBestCmap()
    return {token: sequence_name(cmap, original) for token, original in REBUILT_TOKENS.items()}


def hash_rails(outline, cell):
    """Find the two horizontal bars where the donor meets a bridge on either side."""
    left = spans(outline, cell / 6, 0)
    right = spans(outline, 5 * cell / 6, 0)
    bands = [(max(lo, bottom), min(hi, top))
             for lo, hi in left for bottom, top in right if max(lo, bottom) < min(hi, top)]
    assert len(bands) == 2, bands
    return bands


def build_syntax_glyphs(font, recipe):
    cell = recipe["alphabet_review"]["cell"]
    axis = recipe["horizontal_punctuation_review"]["minus_center"]
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    names = syntax_names(font)

    def outline(name):
        return raw_outline(glyphs, name)

    def center(name):
        left, bottom, right, top = outline(name).bounds
        return (left + right) / 2, (bottom + top) / 2

    period_x, period_y = center("period")

    def place_period(x, y):
        return translated("period", x - period_x, y - period_y)

    for token in ("..", ".=", "..="):
        parts = [place_period(cell / 2 + i * cell, axis) if char == "."
                 else translated("equal", i * cell) for i, char in enumerate(token)]
        install_components(font, names[token], parts, len(token) * cell)

    install_components(font, names["..."], [place_period(cell * factor, period_y)
                                             for factor in (.7, 1.5, 2.3)], 3 * cell)
    for token in ("${", "$[", "$("):
        delimiter = cmap[ord(token[1])]
        dy = otRound(center(delimiter)[1] - center("dollar")[1])
        parts = interpolation_parts(delimiter, cell, dy)
        install_components(font, names[token], [translated(name, x, y) for name, _, _, x, y in parts], 2 * cell)

    equal = outline("equal")
    dots = [place_period(cell * 7 / 12, (bottom + top) / 2)
            for _, bottom, _, top in equal_bars(equal)]
    install_components(font, names[":="], [*dots, translated("equal", cell * 11 / 12)], 2 * cell)

    bar_left, bar_bottom, bar_right, bar_top = outline("bar").bounds
    pivot = cell * 3 / 4
    height = 500
    sy = height / (bar_top - bar_bottom)
    stem = ("bar", (1, 0, 0, sy, otRound(pivot - (bar_left + bar_right) / 2),
                    otRound(axis - sy * (bar_bottom + bar_top) / 2)))
    install_components(font, names["|="], [stem, translated("equal", pivot - equal.bounds[0])], 2 * cell)

    rule = "operator.turnstileRule"
    minus = outline("minus")
    rule_width = 550
    install_outline(font, rule, fit_box(minus, rule_width, minus.bounds[3] - minus.bounds[1],
                                        pivot + rule_width / 2, axis), 0)
    install_components(font, names["|-"], [stem, translated(rule)], 2 * cell)

    bridge = "operator.hashBridge"
    half_width = cell / 6
    rails = pathops.Path()
    for bottom, top in hash_rails(outline("numbersign"), cell):
        rails.addPath(polygon(((-half_width, bottom), (-half_width, top),
                               (half_width, top), (half_width, bottom))))
    install_outline(font, bridge, rails, 0)
    for token, name in names.items():
        if token.startswith("#"):
            count = len(token)
            hashes = [translated("numbersign", i * cell) for i in range(count)]
            bridges = [translated(bridge, i * cell) for i in range(1, count)]
            install_components(font, name, hashes + bridges, count * cell)


def build_syntax_context(font, cell):
    names = syntax_names(font)
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    for name in names.values():
        classes[name] = 2
    register_syntax_tokens(font, names, cell)


def verify_syntax(font, path, recipe, weights):
    cell = recipe["alphabet_review"]["cell"]
    axis = recipe["horizontal_punctuation_review"]["minus_center"]
    names = syntax_names(font)
    cmap = font.getBestCmap()
    engine = hb.Font(hb.Face(path.read_bytes()))
    for weight in weights:
        engine.set_variations({"wght": weight})
        glyphs = font.getGlyphSet(location={"wght": weight})
        for token, name in names.items():
            rows = shape(engine, token, {})
            literal = shape(engine, token, {"calt": False})
            assert len(rows) == 1 and rows[0][:3] == [name, 0, len(token) * cell], (weight, token, rows)
            assert [row[0] for row in literal] == [cmap[ord(ch)] for ch in token]
            following = shape(engine, token + "x", {})
            assert following[1][:3] == ["x", len(token), cell]
            outline = raw_outline(glyphs, name)
            if token.startswith("#"):
                base = hash_rails(raw_outline(glyphs, "numbersign"), cell)
                for index in range(1, len(token)):
                    rail = spans(shape_from_glyphs(glyphs, name), index * cell, 0)
                    assert rail == base, (weight, token, index, rail)
            elif token.startswith("$"):
                dollar, *enclosure = outline.contours
                dollar_center = (dollar.bounds[1] + dollar.bounds[3]) / 2
                assert isclose(dollar_center, axis, abs_tol=.5), (weight, token, dollar_center)
                assert isclose((min(p.bounds[1] for p in enclosure) + max(p.bounds[3] for p in enclosure)) / 2,
                               axis, abs_tol=.5)

        for text, expected in (("...=", [names["..."], "equal"]),
                               ("..=", [names["..="]]), ("....", [names["..."], "period"]),
                               ("x?...y", ["x", "question_period.liga", names[".."], "y"])):
            assert [row[0] for row in shape(engine, text, {})] == expected, (weight, text)

    table = font["GDEF"].table.LigCaretList
    values = {name: [point.Coordinate for point in record.CaretValue]
              for name, record in zip(table.Coverage.glyphs, table.LigGlyph, strict=True)}
    for token, name in names.items():
        assert values[name] == list(range(cell, len(token) * cell, cell)), token
    return {"tokens": list(names), "weights": weights, "advance": "one cell per input character"}
