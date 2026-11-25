"""Construct Code math signs and operator ligatures from current drawing parts."""

from copy import deepcopy
from math import hypot

from fontTools.misc.roundTools import otRound
from fontTools.otlLib.builder import buildLigCaretList
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

from audit import spans
from code_foundation import clear_hints
from code_outlines import install, install_components, install_outline, logical_not, polygon
from code_punctuation import DOT
from code_receiver_shapes import HorizontalMapPen, remap
from font_feature_tools import add_features
from italic_returns import draw_segments, raw_outline, segments


SYMBOL_SAMPLES = ("+ − × ÷ =", "< > ≤ ≥ ≠", "* ~ ^  ¬∀∃")
ARROW_FAMILIES = ("→↔↑↕←↓", "⇒⇔⇑⇕⇐⇓")
COMPARISONS = {
    "==": "equal_equal.liga", "===": "equal_equal_equal.liga",
    "!=": "exclam_equal.liga", "!==": "exclam_equal_equal.liga",
    "<=": "less_equal.liga", ">=": "greater_equal.liga",
}
ARROWS = {
    "->": "hyphen_greater.liga", "->>": "hyphen_greater_greater.liga",
    "<-": "less_hyphen.liga", "<<-": "less_less_hyphen.liga", "=>": "equal_greater.liga",
}


def translated(name, x=0, y=0):
    return name, (1, 0, 0, 1, otRound(x), otRound(y))


def reflect(cell):
    return -1, 0, 0, 1, cell, 0


def fit_box(path, width, height, cx, cy):
    left, bottom, right, top = path.bounds
    sx, sy = width / (right - left), height / (top - bottom)
    return path.transform(sx, 0, 0, sy, cx - sx * (right + left) / 2, cy - sy * (top + bottom) / 2)


def chevron(left, right, axis, rise, thickness):
    """Build an angle whose exposed terminal cuts are vertical."""
    bevel = thickness / 5
    slope = (rise - bevel) / (right - left)
    depth = thickness * hypot(1, slope)
    inset = (depth - bevel) / slope
    upper, lower = axis + rise, axis - rise
    outline = polygon(((left, axis + bevel), (right, upper), (right, upper - depth),
                       (left + inset, axis), (right, lower + depth), (right, lower),
                       (left, axis - bevel)))
    return outline, bevel, depth


def bar_stack(font, name, bar, cell, pitch, count, slash=None):
    center = (count - 1) / 2
    parts = [translated(bar, y=(i - center) * pitch) for i in range(count)]
    if slash:
        parts.append(slash)
    install_components(font, name, parts, cell)


def build_signs(font, cell, axis, settings):
    glyphs = font.getGlyphSet()
    left, bottom, right, top = raw_outline(glyphs, "minus").bounds
    thickness = top - bottom
    rule = fit_box(raw_outline(glyphs, "minus"), right - left, thickness, cell / 2, axis)
    install_outline(font, "minus", rule, cell)
    left, bottom, right, top = raw_outline(font.getGlyphSet(), "minus").bounds
    middle = cell / 2
    stem_left, stem_right = middle - thickness / 2, middle + thickness / 2
    plus_rise = settings["plus_height"] / 2
    install_outline(font, "plus", polygon((
        (left, bottom), (left, top), (stem_left, top), (stem_left, axis + plus_rise),
        (stem_right, axis + plus_rise), (stem_right, top), (right, top), (right, bottom),
        (stem_right, bottom), (stem_right, axis - plus_rise), (stem_left, axis - plus_rise),
        (stem_left, bottom),
    )), cell)

    pitch = settings["rule_pitch"]
    equal_width = right - left + settings["equal_extra_width"]
    equal_bar = "operator.equalBar"
    install_outline(font, equal_bar, fit_box(rule, equal_width, thickness, middle, axis), 0)
    bar_stack(font, "equal", equal_bar, cell, pitch, 2)
    install_outline(font, "logicalnot", logical_not(raw_outline(font.getGlyphSet(), "equal")), cell)
    dot_scale = settings["division_dot_scale"]
    dot_offset = settings["division_dot_offset"]
    install_components(font, "divide", [
        translated("minus"), *((DOT, (dot_scale, 0, 0, dot_scale, otRound(middle), axis + dy))
                               for dy in (-dot_offset, dot_offset)),
    ], cell)

    angle_width = right - left
    rise = settings["angle_height"] / 2
    for name, width, height in (("less", angle_width, rise),
                                ("less.generic", settings["tall_angle_width"], settings["tall_angle_height"] / 2)):
        outline, _, _ = chevron(middle - width / 2, middle + width / 2, axis, height, thickness)
        install_outline(font, name, outline, cell)
        opposite = name.replace("less", "greater")
        install_components(font, opposite, [(name, reflect(cell))], cell)

    left, right = middle - equal_width / 2, middle + equal_width / 2
    chevron_axis = axis + pitch / 2
    comparison, bevel, depth = chevron(left, right, chevron_axis, rise, thickness)
    low_left, low_right = chevron_axis - bevel - pitch, chevron_axis - rise - pitch
    comparison.addPath(polygon(((left, low_left), (left, low_left + depth),
                                (right, low_right + depth), (right, low_right))))
    install_outline(font, "lessequal", comparison, cell)
    install_components(font, "greaterequal", [("lessequal", reflect(cell))], cell)

    for name, height, extra_width in (("multiply", settings["multiply_height"], 16),
                                       ("asterisk", settings["asterisk_height"], 8),
                                       ("asciitilde", settings["tilde_height"], None)):
        donor = raw_outline(glyphs, name)
        width = (donor.bounds[2] - donor.bounds[0] + extra_width if extra_width is not None
                 else angle_width + settings["tilde_extra_width"])
        install_outline(font, name, fit_box(donor, width, height, middle, axis), cell)
    caret, _, _ = chevron(0, settings["caret_height"], 0, settings["caret_width"] / 2, thickness)
    install_outline(font, "asciicircum", caret.transform(0, -1, 1, 0, middle,
                    axis + settings["caret_raise"] + settings["caret_height"] / 2), cell)

    slash = raw_outline(glyphs, "slash")
    x0, y0, x1, y1 = slash.bounds

    def strike(advance, scale):
        return "slash", (1, 0, 0, scale, otRound((advance - x0 - x1) / 2),
                         otRound(axis - scale * (y0 + y1) / 2))

    ordinary_strike = settings["strike_scale"]
    install_components(font, "notequal", [translated("equal"), strike(cell, ordinary_strike)], cell)
    for token in ("<=", ">="):
        donor = "lessequal" if token == "<=" else "greaterequal"
        install_components(font, COMPARISONS[token], [translated(donor)], cell)
    advance = 2 * cell
    wide_bar = "operator.wideBar"
    install_outline(font, wide_bar,
                    fit_box(rule, advance - 2 * settings["wide_sidebearing"], thickness, cell, axis), 0)
    for token, count in (("==", 2), ("===", 3), ("!=", 2), ("!==", 3)):
        scale = ordinary_strike if count == 2 else settings["strict_strike_scale"]
        bar_stack(font, COMPARISONS[token], wide_bar, advance, pitch, count,
                  strike(advance, scale) if token.startswith("!") else None)
    return thickness


def fit_arrow(donor, glyph, left, right, axis, rise, thickness, pitch, head_span, *, paired=False, vertical=False):
    """Adjust shaft length independently of the concave Sans arrowhead."""
    x0, y0, x1, y1 = donor.bounds
    shaft = spans(donor, (x0 + x1) / 2, 0)
    centers = (-pitch / 2, pitch / 2) if len(shaft) == 2 else (0,)
    old_y = (y0, *(edge for pair in shaft for edge in pair), y1)
    new_y = (axis - rise, *(axis + c + s * thickness / 2 for c in centers for s in (-1, 1)), axis + rise)
    cut = x1 - head_span
    head_width = min(head_span, (right - left) * 0.41) if paired else head_span
    if paired:
        old_x = (x0, x0 + head_span, cut, x1)
        new_x = (left, left + head_width, right - head_width, right)
    elif glyph is None:
        old_x, new_x = (cut, x1), (right - head_width, right)
    else:
        old_x, new_x = (x0, cut, x1), (left, right - head_width, right)

    def project(x, y):
        return remap(x, old_x, new_x), remap(y, old_y, new_y)

    if glyph is None:
        lower, upper = shaft[0]
        contour, = donor.contours
        edges = segments(contour)
        start = next(i for i, edge in enumerate(edges) if edge.start[1] == edge.end[1] == lower)
        end = max(i for i, edge in enumerate(edges) if edge.start[1] == edge.end[1] == upper)
        head = edges[end + 1:] + edges[:start]
        target = TTGlyphPen(None)
        pen = HorizontalMapPen(target, lambda x: remap(x, old_x, new_x), lambda y: remap(y, old_y, new_y))
        pen.moveTo(head[0].start)
        draw_segments(pen, head)
        pen.closePath()
        return target.glyph()

    fitted = deepcopy(glyph)
    middle = (left + right) / 2
    points = [project(x, y) for x, y in glyph.coordinates]
    if vertical:
        points = [(middle + axis - y, axis - middle + x) for x, y in points]
    fitted.coordinates = GlyphCoordinates((otRound(x), otRound(y)) for x, y in points)
    clear_hints(fitted)
    return fitted


def build_arrows(font, sans, cell, axis, thickness, settings):
    source = sans.getGlyphSet()
    source_cmap = sans.getBestCmap()
    cmap = font.getBestCmap()
    pitch, span = settings["rule_pitch"], settings["arrow_head_span"]
    rise = settings["arrow_height"] / 2
    middle = cell / 2
    for east, both, north, vertical, west, south in ARROW_FAMILIES:
        for horizontal, rotated in ((east, north), (both, vertical)):
            two_tips = horizontal == both
            name = source_cmap[ord(horizontal)]
            donor, original = raw_outline(source, name), sans["glyf"][name]
            width = settings["paired_arrow_width"] if two_tips else settings["arrow_width"]
            spread = settings["paired_arrow_height"] / 2 if two_tips else rise
            for ch, is_vertical in ((horizontal, False), (rotated, True)):
                half_width = settings["vertical_arrow_height"] / 2 if is_vertical else width / 2
                outer_rise = rise if is_vertical else spread
                glyph = fit_arrow(donor, original, middle - half_width, middle + half_width, axis,
                                  outer_rise, thickness, pitch, span, paired=two_tips, vertical=is_vertical)
                install(font, cmap[ord(ch)], glyph, cell)
        install_components(font, cmap[ord(west)], [(cmap[ord(east)], reflect(cell))], cell)
        install_components(font, cmap[ord(south)], [(cmap[ord(north)], (1, 0, 0, -1, 0, 2 * axis))], cell)

    advance = 2 * cell
    left, right = settings["wide_sidebearing"], advance - settings["wide_sidebearing"]
    for token, ch in (("->", "→"), ("=>", "⇒")):
        name = source_cmap[ord(ch)]
        glyph = fit_arrow(raw_outline(source, name), sans["glyf"][name], left, right, axis, rise, thickness, pitch, span)
        install(font, ARROWS[token], glyph, advance)
    name = source_cmap[ord("→")]
    single = raw_outline(source, name)
    head_name, leading_name = "operator.arrowHead", "operator.arrowLeading"
    head = install(font, head_name, fit_arrow(single, None, left, right, axis, rise, thickness, pitch, span), 0)
    end = head.xMin - settings["repeated_head_gap"]
    leading = fit_arrow(single, sans["glyf"][name], left, end, axis, rise, thickness, pitch, span)
    install(font, leading_name, leading, 0)
    install_components(font, ARROWS["->>"], [translated(leading_name), translated(head_name)], advance)
    for token, source_token in (("<-", "->"), ("<<-", "->>")):
        install_components(font, ARROWS[token], [(ARROWS[source_token], reflect(advance))], advance)


def register_operators(font):
    cmap = font.getBestCmap()
    gdef = font["GDEF"].table
    carets = {}
    rules = []
    for token, name in (COMPARISONS | ARROWS).items():
        sequence = " ".join(cmap[ord(char)] for char in token)
        rules.append(f"sub {sequence} by {name};")
        gdef.GlyphClassDef.classDefs[name] = 2
        advance = font["hmtx"][name][0]
        carets[name] = [advance * index // len(token) for index in range(1, len(token))]
    existing = gdef.LigCaretList
    if existing:
        for name, record in zip(existing.Coverage.glyphs, existing.LigGlyph, strict=True):
            carets[name] = [caret.Coordinate for caret in record.CaretValue]
    gdef.LigCaretList = buildLigCaretList(carets, {}, font.getReverseGlyphMap())
    add_features(font, "languagesystem DFLT dflt; languagesystem latn dflt; feature liga { "
                 + " ".join(rules) + " } liga;")


def build_math(font, sans, recipe):
    cell = recipe["alphabet_review"]["cell"]
    axis = recipe["horizontal_punctuation_review"]["minus_center"]
    settings = recipe["math_review"]
    thickness = build_signs(font, cell, axis, settings)
    build_arrows(font, sans, cell, axis, thickness, settings)
    register_operators(font)
