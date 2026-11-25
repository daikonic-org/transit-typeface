"""Assemble one-cell Code operators from the rebuilt component glyphs."""

import pathops
import uharfbuzz as hb

from audit import shape_from_glyphs
from check_code_rebuild import shape
from code_compact_operators import (
    ACCESS, LOOSE, PAIRS, caret_positions, compact_access_parts, paired_offsets, register_compact_context,
)
from code_math import COMPARISONS, bar_stack, translated
from code_outlines import install_components
from italic_returns import raw_outline


SCOPE = "colon_colon.liga"
DIRECT = {"::": SCOPE, "?.": "question_period.liga", "!.": "exclam_period.liga"}
CONTEXT_PAIRS = {"//": "slash_slash.liga", "||": "bar_bar.liga"}
LOOSE_NAMES = {token: COMPARISONS[token] + ".loose" for token in ("==", "!=", "===", "!==")}


def build_compact_glyphs(font, recipe):
    cell = recipe["alphabet_review"]["cell"]
    axis = recipe["horizontal_punctuation_review"]["minus_center"]
    pitch = recipe["math_review"]["rule_pitch"]
    wide_width = 2 * (cell - recipe["math_review"]["wide_sidebearing"])
    settings = recipe["layout_review"]
    distance = settings["scope_column_distance"]
    install_components(font, SCOPE, [translated("colon", dx) for dx in (-distance / 2, distance / 2)], cell)

    glyphs = font.getGlyphSet()
    for token, (_, mark) in ACCESS.items():
        parts = compact_access_parts(glyphs, mark, cell, min_dot_gap=settings["access_dot_gap"])
        install_components(font, DIRECT[token], [translated(name, x, y) for name, _, _, x, y in parts], cell)
    for token, (base, _, separation) in PAIRS.items():
        offsets = paired_offsets(raw_outline(glyphs, base), separation, cell)
        install_components(font, CONTEXT_PAIRS[token], [translated(base, dx) for dx in offsets], cell)

    equal = raw_outline(glyphs, "equal")
    tilde = raw_outline(glyphs, "asciitilde")
    rise = raw_outline(glyphs, "notequal").bounds[3] + 24 - tilde.bounds[1]
    dy = axis - (equal.bounds[1] + tilde.bounds[3] + rise) / 2
    for token, base in (("==", "equal"), ("!=", "notequal")):
        install_components(font, LOOSE_NAMES[token], [translated(base, y=dy), translated("asciitilde", y=dy + rise)],
                           cell)

    scale = settings["compact_strict_width"] / wide_width
    bar = "operator.compactStrictBar"
    install_components(font, bar, [("operator.wideBar", (scale, 0, 0, 1, round(cell / 2 - scale * cell), 0))], 0)
    donor, transform = font["glyf"][COMPARISONS["!=="]].components[-1].getComponentInfo()
    stroke = (donor, (*transform[:4], transform[4] - cell // 2, transform[5]))
    bar_stack(font, LOOSE_NAMES["==="], bar, cell, pitch, 3)
    bar_stack(font, LOOSE_NAMES["!=="], bar, cell, pitch, 3, stroke)


def build_compact_context(font, cell):
    pairs = {token: (base, CONTEXT_PAIRS[token], distance) for token, (base, _, distance) in PAIRS.items()}
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    for name in (DIRECT | CONTEXT_PAIRS).values():
        classes[name] = 2
    for name in LOOSE_NAMES.values():
        classes[name] = 2
    register_compact_context(font, COMPARISONS, LOOSE_NAMES, pairs, direct=DIRECT, cell=cell)


def verify_compact(font, path, recipe, weights):
    cell = recipe["alphabet_review"]["cell"]
    settings = recipe["layout_review"]
    inset = settings["turbofish_inset"]
    engine = hb.Font(hb.Face(path.read_bytes()))
    tokens = DIRECT | CONTEXT_PAIRS
    samples = {"::": "a::b", "?.": "obj?.value", "!.": "obj!.value", "//": "x // note", "||": "a || b"}
    for weight in weights:
        engine.set_variations({"wght": weight})
        glyphs = font.getGlyphSet(location={"wght": weight})
        for token, text in samples.items():
            name = tokens[token]
            compact = shape(engine, text, {})
            literal = shape(engine, text, {"calt": False, "liga": False})
            assert [row[2] for row in compact if row[0] == name] == [cell], (weight, text, compact)
            assert sum(row[2] for row in literal[:-1]) - sum(row[2] for row in compact[:-1]) == cell
            assert [row[1] for row in literal[-1:]] == [row[1] for row in compact[-1:]]
            left, _, right, _ = raw_outline(glyphs, name).bounds
            assert 0 <= left < right <= cell, (weight, token, left, right)
        for token in ACCESS:
            ink = raw_outline(glyphs, DIRECT[token])
            first, second = sorted(box for box in (c.bounds for c in ink.contours) if box[1] < 0)
            assert second[0] - first[2] >= settings["access_dot_gap"] - .5, (weight, token, first, second)
        for name in CONTEXT_PAIRS.values():
            first, second = raw_outline(glyphs, name).contours
            assert pathops.op(first, second, pathops.PathOp.INTERSECTION).area == 0, (weight, name)
        for text in ("a:::b", "a::::b", "map(|| f(x))", "let f = || 1", "a ||| b", "https://host", "/// note"):
            assert all(row[0] not in tokens.values() for row in shape(engine, text, {})), (weight, text)

        complete = shape(engine, "::<T>", {})
        assert [row[0].removesuffix(".hairline") for row in complete] == [SCOPE, "less.generic", "T", "greater.generic"]
        assert [row[2:] for row in complete[:2]] == [[cell, 0, inset, 0], [cell, 0, -inset, 0]]
        assert [[name.removesuffix(".hairline"), *rest] for name, *rest in complete] == shape(
            engine, "::<T>", {"ss07": True})
        assert [row[0:5] for row in shape(engine, "::<", {})] == [
            [SCOPE, 0, cell, 0, 0], ["less", 2, cell, 0, 0]]
        scope = shape_from_glyphs(glyphs, SCOPE)
        assert len(list(scope.contours)) == 4
        assert scope.bounds[2] + inset < cell + raw_outline(glyphs, "less.generic").bounds[0] - inset

        for token, name in LOOSE_NAMES.items():
            text = f"a {token} b"
            standard = shape(engine, text, {})
            compact = shape(engine, text, {LOOSE: True})
            assert compact[2][:3] == [name, 2, cell], (weight, text, compact)
            assert standard[2][:3] == [COMPARISONS[token], 2, 2 * cell]
            assert sum(row[2] for row in standard[:-1]) - sum(row[2] for row in compact[:-1]) == cell
            ink = shape_from_glyphs(glyphs, name)
            assert 0 <= ink.bounds[0] < ink.bounds[2] <= cell
            if len(token) == 2:
                *lower, upper = sorted((contour.bounds for contour in ink.contours), key=lambda box: box[1])
                assert upper[1] - max(box[3] for box in lower) >= 23, (weight, token)

    carets = font["GDEF"].table.LigCaretList
    values = {name: [point.Coordinate for point in record.CaretValue]
              for name, record in zip(carets.Coverage.glyphs, carets.LigGlyph, strict=True)}
    for token, name in (tokens | LOOSE_NAMES).items():
        assert values[name] == caret_positions(token, cell), (token, values[name])
    return {"one_cell_ligatures": list(tokens), "loose_equality": LOOSE,
            "turbofish_offsets": [inset, -inset], "weights": weights}
