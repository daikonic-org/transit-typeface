"""Build the primary Code punctuation from the shared Sans diamond."""

from math import ceil

from fontTools.misc.roundTools import otRound
from fontTools.pens.ttGlyphPen import TTGlyphPen

from code_foundation import center, outline_bounds
from code_outlines import install, install_components, install_outline, move_return, polygon, refresh_bounds
from italic_returns import draw_segments, raw_outline, segments
from kern_clearance import ink_extents
from repeated_stems import horizontal_extent


DOT = "diamond.punctuation"
CROWN = "diamond.punctuation.crown"


def dot_at(x, y, sx=1):
    return DOT, (sx, 0, 0, 1, otRound(x), otRound(y))


def sentence_mark(font, name, radius, clearance, cell):
    """Keep the cap or descender end fixed and open a gap above or below the dot."""
    glyf = font["glyf"]
    body, old_dot = glyf[name].components
    donor = body.glyphName
    ink = glyf[donor]
    left, bottom, right, top = outline_bounds(ink, glyf)
    center_x = (left + right) / 2
    shift_x = cell / 2 - center_x - body.x
    if name.endswith("down"):
        fixed = bottom
        moving = top
        target = min(top, old_dot.y - radius - clearance - body.y)
    else:
        fixed = top
        moving = bottom
        target = max(bottom, old_dot.y + radius + clearance - body.y)
    factor = (fixed - target) / (fixed - moving)
    for index, (x, y) in enumerate(ink.coordinates):
        ink.coordinates[index] = (x, otRound(fixed + (y - fixed) * factor))
    refresh_bounds(font, donor)
    install_components(font, name, [(donor, (1, 0, 0, 1, otRound(body.x + shift_x), body.y)),
                                    dot_at(old_dot.x + shift_x, old_dot.y)], cell)


def build_compound_punctuation(font, cell, settings):
    glyf = font["glyf"]
    body, diamond = glyf["question"].components
    x_min, y_min, x_max, _ = outline_bounds(glyf[body.glyphName], glyf)
    body_center = (x_min + x_max) / 2
    scale = settings["double_question_body_scale"]
    # Keep the gap under the body and reuse the full-size diamond.
    compact_question = "question.compact"
    dot_offset = diamond.x - body.x - body_center
    install_components(font, compact_question, [
        (body.glyphName, (scale, 0, 0, scale, otRound(cell / 2 - scale * body_center),
                          otRound(body.y + (1 - scale) * y_min))),
        dot_at(cell / 2 + dot_offset * scale, diamond.y),
    ], cell)

    glyphs = font.getGlyphSet()
    outlines = {name: raw_outline(glyphs, name) for name in ("exclam", "question", compact_question)}
    edges = {name: ink_extents(outlines[name], step=1) for name in ("exclam", "question")}
    gap = settings["compound_pair_gap"]
    dot_left, _, dot_right, _ = outline_bounds(glyf[DOT], glyf)
    for name, left, right in (("exclamdbl", "exclam", "exclam"),
                              ("uni2047", compact_question, compact_question),
                              ("uni2048", "question", "exclam"),
                              ("uni2049", "exclam", "question")):
        if name == "exclamdbl":
            separation = cell / 2
        elif name == "uni2047":
            # Join the two arches while keeping their diamonds distinct.
            separation = max(settings["double_question_min_separation"], dot_right - dot_left + gap)
        else:
            left_edges, right_edges = edges[left], edges[right]
            # A mark can tuck under the other's wider sections without touching.
            facing = max(left_edges[row][1] - right_edges[row][0]
                         for row in left_edges.keys() & right_edges.keys())
            separation = ceil(facing) + gap
        start = otRound((cell - outlines[left].bounds[0] - outlines[right].bounds[2] - separation) / 2)
        install_components(font, name, [
            (left, (1, 0, 0, 1, start, 0)),
            (right, (1, 0, 0, 1, start + separation, 0)),
        ], cell)


def build_comma_forms(font, settings, cell, radius, period_y, upper_y):
    axis = otRound(cell / 2)
    glyf = font["glyf"]
    cap = font["OS/2"].sCapHeight
    resize_quote(font, "quoteright", cell, radius, cap, settings["quote_height"])
    donor, = raw_outline(font.getGlyphSet(), "quoteright").contours
    edges = segments(donor)
    apex = next(i for i, edge in enumerate(edges) if edge.start[1] == cap)
    tip_x, _ = edges[apex].start
    shoulder_y = cap - radius
    quote_center, _ = center(outline_bounds(glyf["quoteright"], glyf))
    scale = settings["comma_tail_scale_x"]
    dx = otRound(scale * (tip_x - quote_center))
    # Keep the donor curl below the straight sides of its diamond crown.
    curl = move_return(edges[apex + 2:] + edges[:apex - 2],
                       lambda point: (otRound(scale * (point[0] - tip_x) + dx), point[1] - shoulder_y))
    tip_edge = next(i for i, edge in enumerate(curl) if edge.operation == "lineTo")
    tail_x, tail_y = curl[tip_edge].start
    outer_x = curl[0].start[0]
    left_x, left_y = curl[-1].end

    pen = TTGlyphPen(None)
    pen.moveTo((-radius, 0))
    pen.lineTo((radius, 0))
    pen.qCurveTo(((radius + outer_x) / 2, tail_y), (tail_x, tail_y))
    draw_segments(pen, curl[tip_edge:])
    pen.qCurveTo((left_x, left_y / 2), (-radius, 0))
    pen.closePath()
    install(font, "comma.tail", pen.glyph(), 0)
    install_outline(font, CROWN, polygon(((-radius, 0), (0, radius), (radius, 0))), 0)
    install_components(font, "comma", [
        (name, (1, 0, 0, 1, axis, period_y)) for name in ("comma.tail", CROWN)
    ], cell)
    install_components(font, "semicolon", [("comma", (1, 0, 0, 1, 0, 0)), dot_at(axis, upper_y)], cell)


def resize_quote(font, name, cell, radius, cap, height):
    """Scale the donor to the shared crown and fit its tail to the quote height."""
    glyf = font["glyf"]
    ink = glyf[name]
    left, bottom, right, top = outline_bounds(ink, glyf)
    tip = next(i for i, (_, y) in enumerate(ink.coordinates) if y == top)
    before, after = ink.coordinates[tip - 1], ink.coordinates[(tip + 1) % len(ink.coordinates)]
    crown_depth = top - (before[1] + after[1]) / 2
    scale = 2 * radius / abs(after[0] - before[0])
    tail_scale = (height - radius) / (top - bottom - crown_depth)
    source_center = (left + right) / 2
    for i, (x, y) in enumerate(ink.coordinates):
        depth = top - y
        scaled = min(crown_depth, depth) * radius / crown_depth
        scaled += max(0, depth - crown_depth) * tail_scale
        ink.coordinates[i] = (otRound(cell / 2 + (x - source_center) * scale),
                              otRound(cap - scaled))

    apex_x = ink.coordinates[tip][0]
    shoulder_y = cap - radius
    for i, point in ((tip - 1, before), ((tip + 1) % len(ink.coordinates), after)):
        x = apex_x - radius if point[0] < (before[0] + after[0]) / 2 else apex_x + radius
        ink.coordinates[i] = (x, shoulder_y)
    refresh_bounds(font, name)


def build_quotes(font, recipe, radius):
    settings = recipe["diamond_punctuation_review"]
    cell = recipe["alphabet_review"]["cell"]
    cap = font["OS/2"].sCapHeight
    glyf = font["glyf"]
    _, bottom, _, top = outline_bounds(glyf["comma"], glyf)
    low_shift = settings["low_quote_top"] - cap
    reduction = settings["straight_quote_size_reduction"]
    resize_quote(font, "quotesingle", cell, radius - reduction / 2, cap, settings["quote_height"] - reduction)
    install_components(font, "quoteright", [("comma", (1, 0, 0, 1, 0, cap - top))], cell)
    install_components(font, "quoteleft", [("comma", (-1, 0, 0, -1, cell, cap + bottom))], cell)
    for single, double in (("quotesingle", "quotedbl"), ("quoteleft", "quotedblleft"),
                           ("quoteright", "quotedblright")):
        outline = raw_outline(font.getGlyphSet(), single)
        separation = horizontal_extent(outline) + settings["quote_pair_gap"]
        mid, _ = center(outline.bounds)
        positions = [otRound((cell + direction * separation) / 2 - mid) for direction in (-1, 1)]
        parts = [(single, (1, 0, 0, 1, x, 0)) for x in positions]
        install_components(font, double, parts, cell)
    install_components(font, "quotesinglbase", [("quoteright", (1, 0, 0, 1, 0, low_shift))], cell)
    install_components(font, "quotedblbase", [("quotedblright", (1, 0, 0, 1, 0, low_shift))], cell)


def build_diamond_punctuation(font, recipe):
    settings = recipe["diamond_punctuation_review"]
    config = recipe["alphabet_review"]
    cell = config["cell"]
    glyf = font["glyf"]
    left, _, right, _ = outline_bounds(glyf["diamond.dot"], glyf)
    radius = otRound((right - left) * settings["diamond_scale"] / 2)
    install_outline(font, DOT, polygon(((0, radius), (radius, 0), (0, -radius), (-radius, 0))), 0)
    overshoot = otRound(radius * settings["period_overshoot"])
    period_y = config["baseline"] + radius - overshoot
    install_components(font, "period", [dot_at(cell / 2, period_y)], cell)

    lower, upper = sorted(part.y for part in glyf["colon"].components)
    half_gap = (upper - lower) / 2
    lower_y = settings["colon_center"] - half_gap
    upper_y = settings["colon_center"] + half_gap
    install_components(font, "colon", [dot_at(cell / 2, lower_y), dot_at(cell / 2, upper_y)], cell)

    build_comma_forms(font, settings, cell, radius, period_y, upper_y)
    build_quotes(font, recipe, radius)

    dots = [dot_at(cell * (i + 0.5) / 3, period_y, settings["ellipsis_dot_x_scale"]) for i in range(3)]
    install_components(font, "ellipsis", dots, cell)

    _, mid_y = center(outline_bounds(glyf["periodcentered"], glyf))
    install_components(font, "periodcentered", [dot_at(cell / 2, mid_y)], cell)
    for name in ("exclam", "question", "exclamdown", "questiondown"):
        sentence_mark(font, name, radius, settings["sentence_dot_clearance"], cell)
    build_compound_punctuation(font, cell, settings)
