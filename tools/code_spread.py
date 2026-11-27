"""Set a two-cell ellipsis before an adjacent rest or spread operand."""

import unicodedata
from statistics import quantiles
from string import ascii_lowercase

from fontTools.misc.roundTools import otRound
import uharfbuzz as hb

from check_code_rebuild import shape
from code_compact_operators import delimiter_variants
from code_crossbar_alignment import profile
from code_syntax_build import BRACKET_SPREAD_SUFFIX, SPREAD_SUFFIX, syntax_names
from font_feature_tools import add_features, master_locations
from italic_returns import raw_outline


SPREAD_PREFIXES = "([{,"


def ink_edge(glyphs, name, y, side):
    """Sample the facing edge at the dots' centerline."""
    edges = profile(glyphs, name)
    level = min(edges, key=lambda level: abs(level - y))
    return edges[level][side]


def fit_spread_boundaries(font, dots, feature):
    """Balance the dot row between a prefix and a representative lowercase edge."""
    cmap = font.getBestCmap()
    spaces = sorted({cmap[cp] for cp in (9, 32, 0xA0) if cp in cmap})
    blank = f"[{' '.join(spaces)}]"
    prefixes = delimiter_variants((cmap[ord(ch)] for ch in SPREAD_PREFIXES), font["glyf"])
    _, locations = master_locations(font)
    masters = []
    count = len(dots)
    for location in locations:
        glyphs = font.getGlyphSet(location=location)
        cell = glyphs["period"].width
        left, bottom, right, top = raw_outline(glyphs, "period").bounds
        diameter = right - left
        level = otRound((bottom + top) / 2)
        # Prefer a stem-like leading edge so the row leaves clearance for closer operands.
        leading = [ink_edge(glyphs, cmap[ord(ch)], level, 0) for ch in ascii_lowercase]
        operand = 2 * cell + quantiles(leading, n=4)[0]
        edges = {name: ink_edge(glyphs, name, level, 1) - cell for name in prefixes}
        edges[None] = diameter / 2 - cell / count
        coordinate = ",".join(f"{tag}={value:g}" for tag, value in location.items())
        masters.append((coordinate, cell, diameter, operand, edges))

    def positions(prefix, extra_cells):
        values = [[] for _ in dots]
        for coordinate, cell, diameter, operand, edges in masters:
            edge = edges[prefix] - extra_cells * cell
            gap = (operand - edge - count * diameter) / (count + 1)
            for i, shifts in enumerate(values):
                target = edge + (i + 1) * gap + (i + .5) * diameter
                shift = otRound(target - (2 * i + 1) * cell / count)
                shifts.append(f"{coordinate}:{shift}")
        return " ".join(f"{dot}' <({' '.join(shifts)}) 0 0 0>"
                        for dot, shifts in zip(dots, values, strict=True))

    lines = ["languagesystem DFLT dflt;", "languagesystem latn dflt;", "lookup FitSpreadBoundary {"]
    for name in prefixes:
        lines.append(f"pos {name} {blank} {positions(name, 1)};")
        lines.append(f"pos {name} {positions(name, 0)};")
    # A leading blank without a recognized prefix can still lend one cell of ink space.
    lines.append(f"pos {blank} {positions(None, 1)};")
    lines.append("} FitSpreadBoundary;")
    for tag in ("kern", feature):
        lines.append(f"feature {tag} {{ lookup FitSpreadBoundary; }} {tag};")
    add_features(font, "\n".join(lines), variable=True)


def build_spread_context(font):
    ellipsis = syntax_names(font)["..."]
    spread = ellipsis + SPREAD_SUFFIX
    bracket = ellipsis + BRACKET_SPREAD_SUFFIX
    forms = [spread, bracket] if bracket in font["glyf"] else [spread]
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    definitions, rules, carets = [], [], []
    for name in forms:
        classes[name] = 2
        width = font["hmtx"][name][0]
        carets.append(f"LigatureCaretByPos {name} {width // 3} {2 * width // 3};")
    if bracket in forms:
        definitions.append(f"@SpreadBracket = [{bracket_openers(font)}];")
        rules.append(f"sub @SpreadBracket {ellipsis}' @SpreadOperand by {bracket};")
    rules.append(f"sub {ellipsis}' @SpreadOperand by {spread};")
    register_spread_context(
        font, ellipsis, "\n".join(rules), definitions=definitions,
        extra=["table GDEF {", *carets, "} GDEF;"],
    )


def bracket_openers(font):
    return " ".join(delimiter_variants(("bracketleft",), font["glyf"]))


def register_spread_context(font, ellipsis, rule, *, feature="calt", definitions=(), extra=(), marked=None):
    cmap = font.getBestCmap()
    operands = {name for cp, name in cmap.items() if unicodedata.category(chr(cp)).startswith("L")}
    operands.update(cmap[ord(ch)] for ch in "_$([{\"'`")
    order = set(font.getGlyphOrder())
    operands.update(delimiter_variants((cmap[ord(ch)] for ch in "([{"), order))
    prefixes = set(delimiter_variants((cmap[ord(ch)] for ch in SPREAD_PREFIXES), order))
    spaces = {cmap[cp] for cp in (9, 32, 0xA0) if cp in cmap}
    blockers = sorted(order - prefixes - spaces)
    marked = marked or f"{ellipsis}'"
    add_features(font, "\n".join([
        "languagesystem DFLT dflt;", "languagesystem latn dflt;",
        "@SpreadOperand = [" + " ".join(sorted(operands)) + "];",
        "@SpreadBlocker = [" + " ".join(blockers) + "];",
        "@SpreadSpace = [" + " ".join(sorted(spaces)) + "];",
        *definitions, f"feature {feature} {{ lookup RestSpreadEllipsis {{",
        "lookupflag IgnoreMarks;",
        *(f"ignore sub @SpreadBlocker{' @SpreadSpace' * count} {marked} @SpreadOperand;"
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
        if settings.get("even_spread"):
            centers = [(left + right) / 2 for left, _, right, _ in bounds]
            assert all(abs(center - factor * cell) <= 1
                       for center, factor in zip(centers, (1 / 3, 1, 5 / 3), strict=True))
        else:
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
