"""Build composed Code drawings from the completed foundation masters."""

from collections import defaultdict
from copy import deepcopy

from fontTools.misc.roundTools import otRound
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import OVERLAP_COMPOUND
import pathops

from audit import shape_from_glyphs, spans
from code_foundation import map_attachment_anchors, outline_bounds
from code_receiver_shapes import HorizontalMapPen, remap
from italic_returns import lower_arc, raw_outline


SYMBOLS = {
    0x2200: "universal", 0x2203: "existential", 0x00AC: "logicalnot",
    0x2260: "notequal", 0x2264: "lessequal", 0x2265: "greaterequal",
}


def polygon(points):
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()
    return path


def shoulder(n, cut, cell):
    """Keep the stem and shoulder of n, trimming only the right leg."""
    _, bottom, right, _ = n.bounds
    split = cell / 2
    cutter = polygon(((split, bottom - 1), (split, cut), (right + 1, cut), (right + 1, bottom - 1)))
    return pathops.op(n, cutter, pathops.PathOp.DIFFERENCE, fix_winding=True, clockwise=True)


def equal_bars(equal):
    lower, upper = sorted((contour.bounds for contour in equal.contours), key=lambda box: box[1])
    return lower, upper


def logical_not(equal):
    lower, upper = equal_bars(equal)
    left, bar_bottom, right, top = upper
    bottom = lower[1]
    hook = right - (top - bar_bottom)
    return polygon(((left, top), (right, top), (right, bottom), (hook, bottom),
                    (hook, bar_bottom), (left, bar_bottom)))


def less_equal(angle, equal):
    """Use the angle's rise and the equals' bar weight and spacing."""
    lower, upper = equal_bars(equal)
    left, bar_bottom, right, bar_top = upper
    thickness = bar_top - bar_bottom
    half_bar = thickness / 2
    spacing = (bar_bottom + bar_top - lower[1] - lower[3]) / 2
    mid = (bar_top + lower[1] + spacing) / 2
    rise = (angle.bounds[3] - angle.bounds[1]) / 2
    tip = thickness / 4
    inset = (right - left) * (half_bar + tip) / (rise + tip)
    path = polygon((
        (left, mid + tip), (right, mid + rise + half_bar),
        (right, mid + rise - half_bar), (left + inset, mid),
        (right, mid - rise + half_bar), (right, mid - rise - half_bar), (left, mid - tip),
    ))
    rule_y = mid - spacing
    rule_rise = rise + tip
    path.addPath(polygon((
        (left, rule_y + half_bar), (right, rule_y - rule_rise + half_bar),
        (right, rule_y - rule_rise - half_bar), (left, rule_y - half_bar),
    )))
    return path


def install(font, name, glyph, advance):
    glyf = font["glyf"]
    if name not in glyf:
        font.setGlyphOrder(font.getGlyphOrder() + [name])
        font["GDEF"].table.GlyphClassDef.classDefs[name] = 1
    glyf[name] = glyph
    glyph.recalcBounds(glyf)
    font["hmtx"][name] = advance, glyph.xMin
    return glyph


def install_outline(font, name, shape, advance):
    pen = TTGlyphPen(None)
    shape.draw(pen)
    install(font, name, pen.glyph(), advance)


def install_components(font, name, parts, advance):
    pen = TTGlyphPen(font.getGlyphSet())
    for donor, transform in parts:
        pen.addComponent(donor, transform)
    glyph = install(font, name, pen.glyph(), advance)
    if len(parts) > 1:
        glyph.components[0].flags |= OVERLAP_COMPOUND


def refresh_bounds(font, name):
    glyf = font["glyf"]
    glyph = glyf[name]
    glyph.recalcBounds(glyf)
    advance, _ = font["hmtx"][name]
    font["hmtx"][name] = advance, glyph.xMin


def component_users(font, donors):
    glyf = font["glyf"]
    return [name for name in font.getGlyphOrder()
            if glyf[name].isComposite()
            and any(part.glyphName in donors for part in glyf[name].components)]


def retain_joined_donors(font, donors):
    """Keep the fitted spacing of compound letters while their individual donors change."""
    glyf = font["glyf"]
    metrics = font["hmtx"]
    for name in component_users(font, donors):
        glyph = glyf[name]
        if sum(bool(metrics[part.glyphName][0]) for part in glyph.components) <= 1:
            continue
        for part in glyph.components:
            if part.glyphName not in donors:
                continue
            donor = part.glyphName
            joined = donor + ".joined"
            if joined not in glyf:
                install(font, joined, deepcopy(glyf[donor]), metrics[donor][0])
            part.glyphName = joined
        refresh_bounds(font, name)


def inherit_width_scales(font, scales, followers):
    """Apply trial scales after calibration, including dependent accented forms."""
    glyf = font["glyf"]
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        base = glyph.components[0].glyphName if glyph.isComposite() else name
        if base in followers and (base == name or all(
                font["hmtx"][part.glyphName][0] == 0 for part in glyph.components[1:])):
            scales[name] = scales[followers[base]]


def hook_curves(donor):
    """Extract the inside and outside of an upright lower return."""
    _, floor, _, top = donor.bounds
    edges, (left, right) = lower_arc(donor, (floor + top) / 2)
    inner_start = next(i for i, edge in enumerate(edges) if edge.end[0] > right)
    inner_end = next(i for i in range(inner_start, len(edges))
                     if edges[i].controls and edges[i].controls[-1][1] == edges[i].end[1])
    outer_start = next(i for i in range(inner_end + 1, len(edges))
                       if edges[i].start[1] == floor and edges[i].end[1] > floor)
    outer_end = next(i for i in range(outer_start, len(edges)) if edges[i].end[0] == left)
    return edges[inner_start:inner_end + 1], edges[outer_start:outer_end + 1]


def draw_hook_curve(pen, edges, start, end):
    """Rotate and fit a donor curve between the supplied horizontal and vertical joins."""
    x, y = edges[0].start
    far_x, far_y = edges[-1].end
    sx, sy = (end[0] - start[0]) / (far_x - x), (end[1] - start[1]) / (far_y - y)

    def fit(point):
        return start[0] + (point[0] - x) * sx, start[1] + (point[1] - y) * sy

    for edge in edges:
        pen.qCurveTo(*map(fit, (*edge.controls, edge.end)))


def i_outline(font, settings, cell, baseline):
    top = font["OS/2"].sxHeight
    glyphs = font.getGlyphSet()
    rebuilt_n = shape_from_glyphs(glyphs, "n")
    left, right = spans(rebuilt_n, baseline + (top - baseline) / 3, 1)[0]
    thickness = right - left
    center = cell / 2 + settings["shaft_offset"]
    left, right = center - thickness / 2, center + thickness / 2
    bar = thickness * settings["bar_ratio"]
    flag_left = left - settings["left_flag"]
    foot_left, foot_right = left - settings["left_foot"], right + settings["right_foot"]
    inner, outer = hook_curves(raw_outline(glyphs, settings["hook_donor"]))
    radius = thickness * settings["inner_hook_ratio"]
    inner_start, inner_end = (left, top - bar - radius), (left - radius, top - bar)
    outer_start, outer_end = (left - thickness / 4, top), (right, top - 1.2 * bar)
    pen = TTGlyphPen(None)
    pen.moveTo((foot_left, baseline))
    for point in ((foot_left, baseline + bar), (left, baseline + bar), inner_start):
        pen.lineTo(point)
    draw_hook_curve(pen, inner, inner_start, inner_end)
    for point in ((flag_left, top - bar), (flag_left, top), outer_start):
        pen.lineTo(point)
    draw_hook_curve(pen, outer, outer_start, outer_end)
    for point in ((right, baseline + bar), (foot_right, baseline + bar), (foot_right, baseline)):
        pen.lineTo(point)
    pen.closePath()
    return pen


def build_custom_letters(font, recipe):
    config = recipe["alphabet_review"]
    settings = recipe["custom_lowercase_review"]["i"]
    cell, baseline = config["cell"], config["baseline"]
    glyf = font["glyf"]
    retain_joined_donors(font, {"dotlessi"})
    install(font, "dotlessi", i_outline(font, settings, cell, baseline).glyph(), cell)
    changed = {"dotlessi"}
    upper_zone = baseline + (font["OS/2"].sxHeight - baseline) / 2
    shift = settings["shaft_offset"]
    for name in component_users(font, {"dotlessi"}):
        glyph = glyf[name]
        for part in glyph.components:
            if not font["hmtx"][part.glyphName][0]:
                _, bottom, _, _ = outline_bounds(glyf[part.glyphName], glyf)
                if bottom + part.y >= upper_zone:
                    part.x += shift
        changed.add(name)
        refresh_bounds(font, name)

    def mark_shift(x, y):
        return x + (shift if y >= upper_zone else 0), y

    anchors = defaultdict(lambda: lambda x, y: (x, y), dict.fromkeys(changed, mark_shift))
    map_attachment_anchors(font, anchors)


def build_crossbar_letters(font, recipe):
    config = recipe["alphabet_review"]
    settings = recipe["custom_lowercase_review"]["ft"]
    cell, baseline = config["cell"], config["baseline"]
    x_height = font["OS/2"].sxHeight
    glyphs = font.getGlyphSet()
    t, n, f = (shape_from_glyphs(glyphs, name) for name in ("t", "n", "f"))
    left, floor, right, t_top = t.bounds
    n_left, _, n_right, _ = n.bounds
    target_width = n_right - n_left
    cut = otRound(baseline + (x_height - baseline) * settings["return_cut_ratio"])
    stem_left, stem_right = spans(t, cut, 1)[0]
    crossbar, = spans(t, left + (stem_left - left) / 2, 0)
    bar_bottom, bar_top = crossbar
    t_height = x_height + settings["t_above_x_height"]
    f_height = font["OS/2"].sCapHeight + settings["f_above_cap_height"]
    x_from = (left, stem_left, stem_right, right)
    x_to = ((cell - target_width) / 2, stem_left, stem_right, (cell + target_width) / 2)

    def t_y(y):
        if y <= bar_top:
            return y
        return remap(y, (bar_top, t_top), (bar_top, t_height))

    retain_joined_donors(font, {"f", "t"})
    pen = TTGlyphPen(None)
    raw_outline(font.getGlyphSet(), "t").draw(HorizontalMapPen(
        pen, lambda x: remap(x, x_from, x_to), t_y
    ))
    install(font, "t", pen.glyph(), cell)

    # Reflect the entire hook rigidly, then move the straight stem and
    # crossbar to the required heights. The bends keep their original curves.
    f_fold = floor + f_height
    y_from = (floor, cut, bar_bottom, bar_top, t_height)
    y_to = (f_height, f_fold - cut, bar_top, bar_bottom, baseline)
    pen = TTGlyphPen(None)
    raw_outline(font.getGlyphSet(), "t").draw(HorizontalMapPen(
        ReverseContourPen(pen), lambda x: x, lambda y: remap(y, y_from, y_to)
    ))
    install(font, "f", pen.glyph(), cell)

    dependents = component_users(font, {"f", "t"})
    for name in dependents:
        refresh_bounds(font, name)

    def f_anchor(x, y):
        return x, y + (f_height - f.bounds[3] if y >= x_height else 0)

    anchors = defaultdict(lambda: lambda x, y: (x, y), {"t": lambda x, y: (x, t_y(y)), "f": f_anchor})
    map_attachment_anchors(font, anchors)


def build_composed(font, recipe):
    """Construct each review glyph before variable compilation."""
    metrics = font["OS/2"]
    baseline = recipe["alphabet_review"]["baseline"]
    cell = recipe["alphabet_review"]["cell"]
    glyphs = font.getGlyphSet()
    n, equal, angle, slash = (shape_from_glyphs(glyphs, name) for name in ("n", "equal", "less", "slash"))

    r_recipe = recipe["constructed_forms"]["r"]
    cut = otRound(baseline + (metrics.sxHeight - baseline) * r_recipe["cut_at_x_height"])
    install_outline(font, "r", shoulder(n, cut, cell), cell)
    for name in font.getGlyphOrder():
        glyph = font["glyf"][name]
        if glyph.isComposite() and any(part.glyphName == "r" for part in glyph.components):
            refresh_bounds(font, name)

    reflected = (-1, 0, 0, 1, cell, 0)
    install_components(font, "universal", [("A", (-1, 0, 0, -1, cell, metrics.sCapHeight + baseline))], cell)
    install_components(font, "existential", [("E", reflected)], cell)
    install_outline(font, "logicalnot", logical_not(equal), cell)

    # Use a fixed scale so the component relationship survives interpolation.
    # The slash keeps its horizontal weight and is centered on the bars.
    slash_scale = 9 / 16
    l, b, r, t = slash.bounds
    equal_center_y = (equal.bounds[1] + equal.bounds[3]) / 2
    sx, sy = otRound((cell - l - r) / 2), otRound(equal_center_y - (b + t) / 2 * slash_scale)
    install_components(font, "notequal", [
        ("equal", (1, 0, 0, 1, 0, 0)),
        ("slash", (1, 0, 0, slash_scale, sx, sy)),
    ], cell)
    install_outline(font, "lessequal", less_equal(angle, equal), cell)
    install_components(font, "greaterequal", [("lessequal", reflected)], cell)

    for table in font["cmap"].tables:
        if table.isUnicode() and table.format in (4, 12):
            table.cmap.update(SYMBOLS)
    metrics.recalcUnicodeRanges(font)
