"""Construct Code math signs and operator ligatures from current drawing parts."""

from math import asin, atan, ceil, cos, hypot, radians, sin
from typing import NamedTuple

from fontTools.misc.roundTools import otRound
from fontTools.misc.transform import Transform
from fontTools.otlLib.builder import buildLigCaretList
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
import pathops

from audit import spans
from code_foundation import center
from code_outlines import install, install_components, install_outline, logical_not, polygon
from code_punctuation import DOT
from font_feature_tools import add_features
from italic_returns import raw_outline
from kern_clearance import ink_extents
from sans_baseline_trial import subset_contours


SYMBOL_SAMPLES = ("+ − × ÷ =", "< > ≤ ≥ ≠", "* % ~ ^  ¬∀∃")
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
BIDIRECTIONAL_ARROWS = {"<->": "less_hyphen_greater.liga", "<=>": "less_equal_greater.liga"}


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


def build_signs(font, cell, axis, settings, *, asterisk_scale):
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

    minus_width = right - left
    rise = settings["angle_height"] / 2
    left, right = middle - equal_width / 2, middle + equal_width / 2
    comparison, bevel, depth = chevron(left, right, axis, rise, thickness)
    install_outline(font, "less", comparison, cell)
    install_components(font, "greater", [("less", reflect(cell))], cell)

    tall_width = settings["tall_angle_width"]
    tall, _, _ = chevron(middle - tall_width / 2, middle + tall_width / 2, axis,
                         settings["tall_angle_height"] / 2, thickness)
    install_outline(font, "less.generic", tall, cell)
    install_components(font, "greater.generic", [("less.generic", reflect(cell))], cell)

    lift = otRound(pitch / 2)
    chevron_axis = axis + lift
    low_left, low_right = chevron_axis - bevel - pitch, chevron_axis - rise - pitch
    rule_name = "operator.comparisonRule"
    install_outline(font, rule_name, polygon(((left, low_left), (left, low_left + depth),
                                               (right, low_right + depth), (right, low_right))), 0)
    install_components(font, "lessequal", [translated("less", y=lift), translated(rule_name)], cell)
    install_components(font, "greaterequal", [("lessequal", reflect(cell))], cell)

    for name, height, extra_width, scale in (("multiply", settings["multiply_height"], 16, 1),
                                             ("asterisk", settings["asterisk_height"], 8, asterisk_scale),
                                             ("asciitilde", settings["tilde_height"], None, 1)):
        donor = raw_outline(glyphs, name)
        width = (donor.bounds[2] - donor.bounds[0] + extra_width if extra_width is not None
                 else minus_width + settings["tilde_extra_width"])
        install_outline(font, name, fit_box(donor, width * scale, height * scale, middle, axis), cell)
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


def build_percent(font, sans, cell, axis, thickness, settings):
    """Set the two Sans rings around a compact, weighted slash."""
    contours = list(raw_outline(sans.getGlyphSet(), "percent").contours)
    top_ring = {max((i for i, part in enumerate(contours) if part.clockwise == clockwise),
                    key=lambda i: contours[i].bounds[1]) for clockwise in (True, False)}
    donor = sans["glyf"]["percent"]
    ring_glyph, _ = subset_contours(donor, {end for i, end in enumerate(donor.endPtsOfContours)
                                            if i not in top_ring})
    ring = pathops.Path()
    ring_glyph.draw(ring.getPen(), sans["glyf"])
    cx, cy = center(ring.bounds)
    scale = settings["ring_scale"]
    ring = ring.transform(scale, 0, 0, scale, -scale * cx, -scale * cy)

    angle = radians(settings["slash_angle"])
    ux, uy = cos(angle), sin(angle)
    dx = settings["ring_offset_x"]
    half_stroke = thickness * settings["slash_weight_ratio"] / 2
    ring_low = ring.transform(ux, -uy, uy, ux, 0, 0).bounds[1]
    clearance_rise = (half_stroke + settings["clearance"] + 1 - ring_low - uy * dx) / ux
    dy = ceil(max(settings["nominal_height"] / 2 - ring.bounds[3], clearance_rise))
    half_length = (dx - ring.bounds[0] - half_stroke * uy) / ux

    corners = ((-half_length, half_stroke), (half_length, half_stroke),
               (half_length, -half_stroke), (-half_length, -half_stroke))
    slash = polygon(tuple((cell / 2 + t * ux - n * uy, axis + t * uy + n * ux) for t, n in corners))
    ring_glyph.coordinates = GlyphCoordinates((otRound(scale * (x - cx)), otRound(scale * (y - cy)))
                                               for x, y in ring_glyph.coordinates)
    install(font, "percent.ring", ring_glyph, 0)
    install_outline(font, "percent.rule", slash, 0)
    install_components(font, "percent", [
        translated("percent.ring", cell / 2 - dx, axis + dy),
        ("percent.ring", (-1, 0, 0, -1, otRound(cell / 2 + dx), axis - dy)),
        translated("percent.rule"),
    ], cell)


class ArrowHead(NamedTuple):
    name: str
    rows: dict[int, tuple[float, float]]


def arrow_slopes(donor):
    """Estimate the Sans head tangents away from the tiny tip and terminal bevel."""
    _, bottom, _, top = donor.bounds
    center, rise = (bottom + top) / 2, (top - bottom) / 2

    def slope(start, end):
        a, b = center + start * rise, center + end * rise
        xa, xb = (spans(donor, y, 1)[-1][1] for y in (a, b))
        return atan((xa - xb) / (b - a))

    return slope(.02, .14), slope(.82, .98)


def arrow_head(font, name, slopes, rise, thickness):
    """Draw concentric edges and cut the terminal on their shared radius."""
    tip, cap = slopes
    outer = rise / (sin(tip) - sin(cap))
    inner = outer + thickness
    cx, cy = outer * cos(tip), outer * sin(tip)
    notch = asin(cy / inner)

    def point(radius, angle, direction):
        return cx - radius * cos(angle), direction * (cy - radius * sin(angle))

    def arc(radius, start, end, direction):
        step = (end - start) / 4
        for index in range(4):
            angle = start + index * step
            control = point(radius / cos(step / 2), angle + step / 2, direction)
            pen.qCurveTo(control, point(radius, angle + step, direction))

    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    arc(outer, tip, cap, -1)
    pen.lineTo(point(inner, cap, -1))
    arc(inner, cap, notch, -1)
    arc(inner, notch, cap, 1)
    pen.lineTo(point(outer, cap, 1))
    arc(outer, cap, tip, 1)
    pen.closePath()
    install(font, name, pen.glyph(), 0)
    return ArrowHead(name, ink_extents(raw_outline(font.getGlyphSet(), name), step=1))


def install_arrow(font, name, head, bands, advance, axis, length, *, paired=False, vertical=False, gap=None):
    left, right = (advance - length) / 2, (advance + length) / 2
    tip = right
    if gap is not None:
        width = max(x1 - x0 for x0, x1 in head.rows.values())
        tip -= otRound(width + gap)

    # Insert each shaft just far enough to cover the head's inside edge.
    joins = [ceil(max(x0 for row, (x0, _) in head.rows.items() if bottom <= row < top)) + 2
             for bottom, top in bands]
    shaft_name = name + ".shaft"
    shaft = pathops.Path()
    for (bottom, top), start_join, end_join in zip(bands, reversed(joins), joins, strict=True):
        start = left - start_join if paired else left
        end = tip + end_join
        shaft.addPath(polygon(((start, bottom), (start, top), (end, top), (end, bottom))))
    install_outline(font, shaft_name, shaft, 0)

    parts = [translated(shaft_name, y=axis), translated(head.name, tip, axis)]
    if paired:
        # A half-turn keeps the mirrored head's winding consistent with the shaft.
        parts.append((head.name, (-1, 0, 0, -1, otRound(left), axis)))
    if gap is not None:
        parts.append(translated(head.name, right, axis))
    if vertical:
        middle = advance / 2
        rotate = Transform(0, 1, -1, 0, middle + axis, axis - middle)
        parts = [(part, rotate.transform(transform)) for part, transform in parts]
    install_components(font, name, parts, advance)


def build_arrows(font, sans, cell, axis, thickness, settings, *, bidirectional=False):
    source_name = sans.getBestCmap()[ord("→")]
    slopes = arrow_slopes(raw_outline(sans.getGlyphSet(), source_name))
    standard = arrow_head(font, "operator.arrowHead", slopes, settings["arrow_height"] / 2, thickness)
    short = arrow_head(font, "operator.arrowHead.short", slopes, settings["paired_arrow_height"] / 2, thickness)
    pitch = settings["rule_pitch"]
    single_bands = [(otRound(-thickness / 2), otRound(thickness / 2))]
    double_bands = [(otRound(center - thickness / 2), otRound(center + thickness / 2))
                    for center in (-pitch / 2, pitch / 2)]
    cmap = font.getBestCmap()
    for family, bands in zip(ARROW_FAMILIES, (single_bands, double_bands), strict=True):
        east, both, north, vertical, west, south = (cmap[ord(ch)] for ch in family)
        for name, head, length, paired, rotated in (
            (east, standard, settings["arrow_width"], False, False),
            (both, short, settings["paired_arrow_width"], True, False),
            (north, standard, settings["vertical_arrow_height"], False, True),
            (vertical, standard, settings["vertical_arrow_height"], True, True),
        ):
            install_arrow(font, name, head, bands, cell, axis, length, paired=paired, vertical=rotated)
        install_components(font, west, [(east, reflect(cell))], cell)
        install_components(font, south, [(north, (1, 0, 0, -1, 0, 2 * axis))], cell)

    advance = 2 * cell
    length = advance - 2 * settings["wide_sidebearing"]
    install_arrow(font, ARROWS["->"], standard, single_bands, advance, axis, length)
    install_arrow(font, ARROWS["=>"], standard, double_bands, advance, axis, length)
    install_arrow(font, ARROWS["->>"], standard, single_bands, advance, axis, length, gap=pitch - thickness)
    for token, source_token in (("<-", "->"), ("<<-", "->>")):
        install_components(font, ARROWS[token], [(ARROWS[source_token], reflect(advance))], advance)
    if bidirectional:
        for name, bands in zip(BIDIRECTIONAL_ARROWS.values(), (single_bands, double_bands), strict=True):
            install_arrow(font, name, standard, bands, advance, axis, length, paired=True)


def register_operators(font, *, bidirectional=False):
    cmap = font.getBestCmap()
    gdef = font["GDEF"].table
    carets = {}
    rules = []
    operators = COMPARISONS | ARROWS
    if bidirectional:
        operators.update(BIDIRECTIONAL_ARROWS)
    for token, name in operators.items():
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
    bidirectional = recipe["layout_review"].get("delimiter_revision", False)
    thickness = build_signs(font, cell, axis, settings,
                            asterisk_scale=recipe["diamond_punctuation_review"]["diamond_scale"])
    build_percent(font, sans, cell, axis, thickness, settings["percent"])
    build_arrows(font, sans, cell, axis, thickness, settings, bidirectional=bidirectional)
    register_operators(font, bidirectional=bidirectional)
