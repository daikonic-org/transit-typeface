"""Build composed Code drawings from the completed foundation masters."""

from collections import defaultdict
from copy import deepcopy
from math import pi, radians, sqrt, tan

from fontTools.misc.bezierTools import calcQuadraticBounds, splitLine, splitQuadratic, splitQuadraticAtT
from fontTools.misc.roundTools import otRound
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates, OVERLAP_COMPOUND, flagOnCurve
import pathops

from audit import shape_from_glyphs, spans
from code_foundation import center, map_attachment_anchors, outline_bounds
from code_receiver_shapes import HorizontalMapPen, remap
from italic_returns import Segment, lower_arc, raw_outline


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


def retain_joined_donors(font, donors, *, include_single_base=False):
    """Keep the fitted spacing of compound letters while their individual donors change."""
    glyf = font["glyf"]
    metrics = font["hmtx"]
    for name in component_users(font, donors):
        glyph = glyf[name]
        if not include_single_base and sum(bool(metrics[part.glyphName][0]) for part in glyph.components) <= 1:
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


def draw_return(pen, edges, *, reverse=False):
    pen.lineTo(edges[-1].end if reverse else edges[0].start)
    for edge in reversed(edges) if reverse else edges:
        points = (*reversed(edge.controls), edge.start) if reverse else (*edge.controls, edge.end)
        getattr(pen, edge.operation)(*points)


def move_return(edges, move):
    return [edge._replace(start=move(edge.start), end=move(edge.end), controls=tuple(map(move, edge.controls)))
            for edge in edges]


def trim_return_tip(edges, fraction):
    """Keep the curves on each side of a cut measured from the outer shaft."""
    right = max(calcQuadraticBounds(edge.start, *edge.controls, edge.end)[2]
                if edge.controls else max(edge.start[0], edge.end[0]) for edge in edges)
    shaft = edges[0].start[0]
    cut = otRound(right - (right - shaft) * fraction)
    entry_index = next(i for i, edge in enumerate(edges) if edge.end[0] > cut)
    exit_index = next(i for i in range(entry_index + 1, len(edges)) if edges[i].end[0] <= cut)

    def split_at_cut(edge):
        split = splitQuadratic if edge.controls else splitLine
        return [Segment(first, edge.operation, tuple(middle), last)
                for first, *middle, last in split(edge.start, *edge.controls, edge.end, cut, False)]

    approach = edges[:entry_index]
    departure = edges[exit_index + 1:]
    if edges[entry_index].start[0] < cut:
        approach = approach + split_at_cut(edges[entry_index])[:1]
    if edges[exit_index].end[0] < cut:
        departure = split_at_cut(edges[exit_index])[-1:] + departure
    return approach, departure


def subdivide_return(edges, length, *, at_end):
    """Match the number of points without refitting the retained curves."""
    missing = length - len(edges)
    if not missing:
        return edges
    edge = edges[-1 if at_end else 0]
    parameters = [i / (missing + 1) for i in range(1, missing + 1)]
    if edge.controls:
        parts = splitQuadraticAtT(edge.start, *edge.controls, edge.end, *parameters)
    else:
        dx = edge.end[0] - edge.start[0]
        dy = edge.end[1] - edge.start[1]
        points = [edge.start, *((edge.start[0] + t * dx, edge.start[1] + t * dy) for t in parameters),
                  edge.end]
        parts = zip(points, points[1:])
    pieces = [Segment(first, edge.operation, tuple(middle), last) for first, *middle, last in parts]
    return edges[:-1] + pieces if at_end else pieces + edges[1:]


def compatible_upper_returns(lower_returns, fraction):
    clipped = [trim_return_tip(edges, fraction) for edges in lower_returns]
    approach_count = max(len(approach) for approach, _ in clipped)
    departure_count = max(len(departure) for _, departure in clipped)
    result = []
    for approach, departure in clipped:
        approach = subdivide_return(approach, approach_count, at_end=True)
        departure = subdivide_return(departure, departure_count, at_end=False)
        cap = Segment(approach[-1].end, "lineTo", (), departure[0].start)
        result.append(approach + [cap] + departure)
    return result


def upper_return(lower_l, left, top, floor):
    """Rotate the clipped copy of the lower return into the upper hook."""
    dx = otRound(left) + lower_l[0].start[0]
    dy = top + floor
    return move_return(lower_l, lambda point: (dx - point[0], dy - point[1]))


def i_outline(settings, cell, baseline, top, thickness, lower_l, floor):
    center = cell / 2 + settings["shaft_offset"]
    left, right = center - thickness / 2, center + thickness / 2
    bar = thickness * settings["bar_ratio"]
    foot_left, foot_right = left - settings["left_foot"], right + settings["right_foot"]
    pen = TTGlyphPen(None)
    pen.moveTo((foot_left, baseline))
    for point in ((foot_left, baseline + bar), (left, baseline + bar)):
        pen.lineTo(point)
    draw_return(pen, upper_return(lower_l, left, top, floor))
    for point in ((right, baseline + bar), (foot_right, baseline + bar), (foot_right, baseline)):
        pen.lineTo(point)
    pen.closePath()
    return pen


def lower_return(lower, settings, cell, thickness, y_shift=0, *, reflected=False):
    edges, (donor_left, donor_right) = lower
    center = cell / 2 + settings["shaft_offset"]
    direction = -1 if reflected else 1

    def move(point):
        x, y = point
        if x > donor_right:
            distance = thickness / 2 + (x - donor_right) * settings["return_reach"]
        else:
            distance = (x - donor_left) * thickness / (donor_right - donor_left) - thickness / 2
        return otRound(center + direction * distance), otRound(y + y_shift)

    return move_return(edges, move)


def return_letter(lower_l, lower, top, floor, *, reflected=False):
    pen = TTGlyphPen(None)
    left_join = lower[0].start if reflected else lower[-1].end
    pen.moveTo(left_join)
    draw_return(pen, upper_return(lower_l, left_join[0], top, floor))
    draw_return(pen, lower, reverse=reflected)
    pen.closePath()
    return pen.glyph()


def adjust_marks(font, donor, dx, dy, upper_zone, *, shift_lower=False):
    glyf = font["glyf"]
    changed = {donor}
    for name in component_users(font, {donor}):
        glyph = glyf[name]
        for part in glyph.components:
            if not font["hmtx"][part.glyphName][0]:
                _, bottom, _, _ = outline_bounds(glyf[part.glyphName], glyf)
                if bottom + part.y >= upper_zone:
                    part.x += dx
                    part.y += dy
                elif shift_lower:
                    part.x += dx
        changed.add(name)
        refresh_bounds(font, name)

    def mark_shift(x, y):
        if y >= upper_zone:
            return x + dx, y + dy
        return x + (dx if shift_lower else 0), y

    anchors = defaultdict(lambda: lambda x, y: (x, y), dict.fromkeys(changed, mark_shift))
    map_attachment_anchors(font, anchors)


def prepare_hook_donor(font, recipe):
    config = recipe["alphabet_review"]
    settings = recipe["custom_lowercase_review"]
    cell, baseline = config["cell"], config["baseline"]
    x_height = font["OS/2"].sxHeight
    glyphs = font.getGlyphSet()
    n = shape_from_glyphs(glyphs, "n")
    left, right = spans(n, baseline + (x_height - baseline) / 3, 1)[0]
    thickness = right - left
    donor = raw_outline(glyphs, "l")
    _, floor, _, top = donor.bounds
    lower = lower_arc(donor, (floor + top) / 2)
    lower_l = lower_return(lower, settings["l"], cell, thickness)
    return thickness, lower, lower_l, floor, top


def build_hook_letters(font, recipe, donor, clipped):
    config = recipe["alphabet_review"]
    settings = recipe["custom_lowercase_review"]
    cell, baseline = config["cell"], config["baseline"]
    x_height = font["OS/2"].sxHeight
    thickness, lower, lower_l, floor, top = donor
    glyphs = font.getGlyphSet()
    dotless_j = shape_from_glyphs(glyphs, "uni0237")
    old_j_left, old_j_right = spans(dotless_j, (x_height + baseline) / 2, 1)[0]
    j_dx = otRound(cell / 2 + settings["j"]["shaft_offset"] - (old_j_left + old_j_right) / 2)
    l_top = font["OS/2"].sCapHeight + settings["l"]["above_cap_height"]
    l_dx = otRound(cell / 2 + settings["l"]["shaft_offset"] - sum(lower[1]) / 2)
    zone = (x_height + baseline) / 2

    retain_joined_donors(font, {"dotlessi", "uni0237", "l"})
    lower_j = lower_return(lower, settings["j"], cell, thickness, dotless_j.bounds[1] - floor, reflected=True)
    install(font, "dotlessi", i_outline(settings["i"], cell, baseline, x_height, thickness, clipped, floor).glyph(), cell)
    install(font, "uni0237", return_letter(clipped, lower_j, x_height, floor, reflected=True), cell)
    install(font, "l", return_letter(clipped, lower_l, l_top, floor), cell)
    adjust_marks(font, "dotlessi", settings["i"]["shaft_offset"], 0, zone)
    adjust_marks(font, "uni0237", j_dx, 0, zone)
    adjust_marks(font, "l", l_dx, otRound(l_top - top), zone, shift_lower=True)


def build_custom_letters(fonts, recipe):
    fonts = list(fonts)
    donors = [prepare_hook_donor(font, recipe) for font in fonts]
    clipped = compatible_upper_returns([donor[2] for donor in donors],
                                       recipe["custom_lowercase_review"]["upper_hook_trim"])
    for font, donor, upper in zip(fonts, donors, clipped, strict=True):
        build_hook_letters(font, recipe, donor, upper)


def build_g(font, recipe):
    """Scale the upper bowl as one piece and overlap it with the original connector."""
    settings = recipe["custom_lowercase_review"]["g"]
    glyphs = font.getGlyphSet()
    donor = font["glyf"]["g"]
    coordinates = donor.coordinates
    outer_end, first_end, second_end = donor.endPtsOfContours
    counters = (range(outer_end + 1, first_end + 1), range(first_end + 1, second_end + 1))
    lower_counter, upper_counter = sorted(counters, key=lambda indices: min(coordinates[i][1] for i in indices))
    start, end = settings["connector_points"]
    assert donor.flags[start] & donor.flags[end] & flagOnCurve

    def piece(outer, inner, move):
        indices = (*outer, *inner)
        glyph = deepcopy(donor)
        glyph.numberOfContours = 2
        glyph.endPtsOfContours = [len(outer) - 1, len(indices) - 1]
        glyph.coordinates = GlyphCoordinates(move(*coordinates[i]) for i in indices)
        glyph.flags = bytearray(donor.flags[i] & flagOnCurve for i in indices)
        return glyph

    outline = raw_outline(glyphs, "g")
    counter_y = [coordinates[i][1] for i in upper_counter]
    bowl = spans(outline, (min(counter_y) + max(counter_y)) / 2, 1)
    left, right = bowl[0][0], bowl[-1][1]
    a_left, _, a_right, _ = shape_from_glyphs(glyphs, "a").bounds
    target = (a_right - a_left) * settings["a_width_ratio"]
    scale = min(settings["maximum_bowl_scale"], target / (right - left))
    center = (left + right) / 2
    top = outline.bounds[3]

    # Store both pieces with the overlap flag so the original curves interpolate intact.
    advance = font["hmtx"]["g"][0]
    lower = piece(range(start, end + 1), lower_counter, lambda x, y: (x, y))
    upper = piece((*range(end, outer_end + 1), *range(start + 1)), upper_counter,
                  lambda x, y: (otRound(center + scale * (x - center)), otRound(top + scale * (y - top))))
    install(font, "g.lower", lower, advance)
    install(font, "g.upper", upper, advance)
    identity = (1, 0, 0, 1, 0, 0)
    install_components(font, "g", [("g.lower", identity), ("g.upper", identity)], advance)
    for name in component_users(font, {"g"}):
        refresh_bounds(font, name)


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


def build_distinct_figures(font, recipe):
    """Use the current I stem for the shared bars and the family diamond for zero."""
    settings = recipe["distinct_figures_review"]
    glyphs = font.getGlyphSet()
    stem = shape_from_glyphs(glyphs, "I")
    left, base, right, cap = stem.bounds
    thickness = right - left
    bar = otRound(thickness * settings["bar_stem_ratio"])
    bar_left = left - settings["bar_overhang"]
    bar_right = right + settings["bar_overhang"]
    base_top = base + bar
    cap_bottom = cap - bar
    cell = recipe["alphabet_review"]["cell"]

    install_outline(font, "I", polygon((
        (bar_left, base), (bar_left, base_top), (left, base_top), (left, cap_bottom),
        (bar_left, cap_bottom), (bar_left, cap), (bar_right, cap), (bar_right, cap_bottom),
        (right, cap_bottom), (right, base_top), (bar_right, base_top), (bar_right, base),
    )), cell)
    for name in component_users(font, {"I"}):
        refresh_bounds(font, name)

    apex = right - otRound(thickness * settings["flag_top_stem_ratio"])
    tip = otRound(cap - tan(radians(settings["flag_angle"])) * (apex - bar_left))
    radius = thickness * settings["flag_radius_ratio"]
    tangent = radius * tan(pi / 8)
    middle = radius * (1 - sqrt(0.5))
    pen = TTGlyphPen(None)
    pen.moveTo((bar_left, base))
    pen.lineTo((bar_left, base_top))
    pen.lineTo((left, base_top))
    pen.lineTo((left, tip - radius))
    pen.qCurveTo((left, tip - radius + tangent), (left - middle, tip - middle))
    pen.qCurveTo((left - radius + tangent, tip), (left - radius, tip))
    for point in ((bar_left, tip), (apex, cap), (right, cap), (right, base_top),
                  (bar_right, base_top), (bar_right, base)):
        pen.lineTo(point)
    pen.closePath()
    install(font, "one", pen.glyph(), cell)

    glyf = font["glyf"]
    diamond = "diamond.dot"
    counter, = [part for part in shape_from_glyphs(glyphs, "zero").contours if not part.clockwise]
    counter_x, counter_y = center(counter.bounds)
    dot_x, dot_y = center(outline_bounds(glyf[diamond], glyf))
    scale = settings["zero_diamond_scale"]
    install(font, "zero.bowl", deepcopy(glyf["zero"]), cell)
    install_components(font, "zero", [
        ("zero.bowl", (1, 0, 0, 1, 0, 0)),
        (diamond, (scale, 0, 0, scale, otRound(counter_x - scale * dot_x), otRound(counter_y - scale * dot_y))),
    ], cell)


def build_horizontal_punctuation(font, recipe):
    """Place the underscore, text hyphen, and minus on their Code heights."""
    settings = recipe["horizontal_punctuation_review"]
    config = recipe["alphabet_review"]
    cell = config["cell"]
    baseline = config["baseline"]
    glyphs = font.getGlyphSet()
    stem_left, stem_right = spans(shape_from_glyphs(glyphs, "H"), config["cap_height"] / 4, 1)[0]
    underline_weight = settings["underscore_weight_ratio"]
    hyphen_height = otRound((stem_right - stem_left) / underline_weight)
    underscore_height = otRound(hyphen_height * underline_weight)
    left, bottom, right, top = shape_from_glyphs(glyphs, "hyphen").bounds
    hyphen_width = otRound((right - left) * settings["hyphen_width_ratio"])
    hyphen_left = (cell - hyphen_width) // 2
    hyphen_bottom = otRound((bottom + top - hyphen_height) / 2)

    retain_joined_donors(font, {"hyphen", "minus"}, include_single_base=True)
    for name, left, bottom, width, height in (
        ("underscore", 0, baseline, cell, underscore_height),
        ("hyphen", hyphen_left, hyphen_bottom, hyphen_width, hyphen_height),
    ):
        install_outline(font, name, polygon((
            (left, bottom), (left, bottom + height),
            (left + width, bottom + height), (left + width, bottom),
        )), cell)

    glyf = font["glyf"]
    minus = glyf["minus"]
    _, height = center(outline_bounds(minus, glyf))
    minus.coordinates.translate((0, otRound(settings["minus_center"] - height)))
    refresh_bounds(font, "minus")


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
