"""Set a two-cell ellipsis before an adjacent rest or spread operand."""

import unicodedata

import uharfbuzz as hb

from check_code_rebuild import shape
from code_compact_operators import delimiter_variants
from code_syntax_build import SPREAD_SUFFIX, syntax_names
from font_feature_tools import add_features
from italic_returns import raw_outline


def build_spread_context(font):
    ellipsis = syntax_names(font)["..."]
    spread = ellipsis + SPREAD_SUFFIX
    advance = font["hmtx"][spread][0]
    font["GDEF"].table.GlyphClassDef.classDefs[spread] = 2
    register_spread_context(
        font, ellipsis, f"sub {ellipsis}' @SpreadOperand by {spread};",
        extra=[f"table GDEF {{ LigatureCaretByPos {spread} {advance // 3} {2 * advance // 3}; }} GDEF;"],
    )


def register_spread_context(font, ellipsis, rule, *, feature="calt", definitions=(), extra=()):
    cmap = font.getBestCmap()
    operands = {name for cp, name in cmap.items() if unicodedata.category(chr(cp)).startswith("L")}
    operands.update(cmap[ord(ch)] for ch in "_$([{\"'`")
    order = set(font.getGlyphOrder())
    operands.update(delimiter_variants((cmap[ord(ch)] for ch in "([{"), order))
    prefixes = set(delimiter_variants((cmap[ord(ch)] for ch in "([{,"), order))
    spaces = {cmap[cp] for cp in (9, 32, 0xA0) if cp in cmap}
    blockers = sorted(order - prefixes - spaces)
    add_features(font, "\n".join([
        "languagesystem DFLT dflt;", "languagesystem latn dflt;",
        "@SpreadOperand = [" + " ".join(sorted(operands)) + "];",
        "@SpreadBlocker = [" + " ".join(blockers) + "];",
        "@SpreadSpace = [" + " ".join(sorted(spaces)) + "];",
        *definitions, f"feature {feature} {{ lookup RestSpreadEllipsis {{",
        "lookupflag IgnoreMarks;",
        *(f"ignore sub @SpreadBlocker{' @SpreadSpace' * count} {ellipsis}' @SpreadOperand;"
          for count in range(9)),
        rule, f"}} RestSpreadEllipsis; }} {feature};", *extra,
    ]))


def verify_spread(font, path, recipe, weights):
    cell = recipe["alphabet_review"]["cell"]
    settings = recipe["layout_review"]
    gap, sidebearing = settings["spread_dot_gap"], settings["spread_sidebearing"]
    ellipsis = syntax_names(font)["..."]
    spread = ellipsis + SPREAD_SUFFIX
    engine = hb.Font(hb.Face(path.read_bytes()))
    cases = ("...args", "f(...args)", "[...values]", "{...record}", "f(x, ...tail)", "[...[1, 2]]",
             "{...{key: 1}}", "f(...(values))", "[...\"abc\"]", "  ...items", "[..._items]")
    controls = ("wait... later", "…value", "1...2", "a...b", "1..=2", "a....b", "......items",
                "...", "f(... args)", "x?...y", "a ... b", "a ...b", "{...}")
    for weight in weights:
        engine.set_variations({"wght": weight})
        gs = font.getGlyphSet(location={"wght": weight})
        ink = raw_outline(gs, spread)
        bounds = [contour.bounds for contour in ink.contours]
        assert len(bounds) == 3
        assert all(abs(next_dot[0] - dot[2] - gap) <= 1 for dot, next_dot in zip(bounds, bounds[1:]))
        assert abs(2 * cell - bounds[-1][2] - sidebearing) <= 1
        for sample in cases:
            active = shape(engine, sample, {})
            literal = shape(engine, sample, {"calt": False})
            assert not any(row[0] == spread for row in literal)
            index, = (i for i, row in enumerate(active) if row[0] == spread)
            mark, following = active[index:index + 2]
            assert mark[2] == 2 * cell and following[1] == mark[1] + 3, (sample, active)
            assert mark[4] == following[4] == 0
            assert sum(row[2] for row in active) == sum(row[2] for row in literal) - cell
        for sample in controls:
            assert all(row[0] != spread for row in shape(engine, sample, {})), (weight, sample)
    table = font["GDEF"].table.LigCaretList
    record = table.LigGlyph[table.Coverage.glyphs.index(spread)]
    assert [point.Coordinate for point in record.CaretValue] == [2 * cell // 3, 4 * cell // 3]
    return {"advance": 2 * cell, "dot_gap": gap, "right_sidebearing": sidebearing, "weights": weights}
