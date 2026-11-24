"""Build the primary Code punctuation from the shared Sans diamond."""

from fontTools.misc.roundTools import otRound

from code_foundation import center, outline_bounds
from code_outlines import install_components, install_outline, polygon, refresh_bounds
from italic_returns import raw_outline
from repeated_stems import horizontal_extent


DOT = "diamond.punctuation"


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


def build_comma_forms(font, cell, comma_tip_y, upper_y):
    glyf = font["glyf"]
    axis = otRound(cell / 2)
    x, y = max(glyf["quoteright"].coordinates, key=lambda point: point[1])
    install_components(font, "comma", [("quoteright", (1, 0, 0, 1, axis - x, comma_tip_y - y))], cell)
    install_components(font, "semicolon", [("comma", (1, 0, 0, 1, 0, 0)), dot_at(axis, upper_y)], cell)


def resize_quote(font, name, cell, radius, cap, height):
    """Scale the donor to the shared crown and fit its tail to the quote height."""
    glyf = font["glyf"]
    ink = glyf[name]
    left, bottom, right, top = outline_bounds(ink, glyf)
    direction = 1 if name == "quoteleft" else -1
    tip_y = bottom if direction == 1 else top
    tip = next(i for i, (_, y) in enumerate(ink.coordinates) if y == tip_y)
    before, after = ink.coordinates[tip - 1], ink.coordinates[(tip + 1) % len(ink.coordinates)]
    crown_depth = abs((before[1] + after[1]) / 2 - tip_y)
    scale = 2 * radius / abs(after[0] - before[0])
    tail_scale = (height - radius) / (top - bottom - crown_depth)
    target_y = cap - height if direction == 1 else cap
    source_center = (left + right) / 2
    for i, (x, y) in enumerate(ink.coordinates):
        depth = direction * (y - tip_y)
        scaled = min(crown_depth, depth) * radius / crown_depth
        scaled += max(0, depth - crown_depth) * tail_scale
        ink.coordinates[i] = (otRound(cell / 2 + (x - source_center) * scale),
                              otRound(target_y + direction * scaled))

    apex_x = ink.coordinates[tip][0]
    shoulder_y = target_y + direction * radius
    for i, point in ((tip - 1, before), ((tip + 1) % len(ink.coordinates), after)):
        x = apex_x - radius if point[0] < (before[0] + after[0]) / 2 else apex_x + radius
        ink.coordinates[i] = (x, shoulder_y)
    refresh_bounds(font, name)


def build_quotes(font, recipe, radius):
    settings = recipe["diamond_punctuation_review"]
    cell = recipe["alphabet_review"]["cell"]
    cap = font["OS/2"].sCapHeight
    low_shift = settings["low_quote_top"] - cap
    for single, double in (("quotesingle", "quotedbl"), ("quoteleft", "quotedblleft"),
                           ("quoteright", "quotedblright")):
        resize_quote(font, single, cell, radius, cap, settings["quote_height"])
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

    build_quotes(font, recipe, radius)
    build_comma_forms(font, cell, period_y + radius - overshoot, upper_y)

    dots = [dot_at(cell * (i + 0.5) / 3, period_y, settings["ellipsis_dot_x_scale"]) for i in range(3)]
    install_components(font, "ellipsis", dots, cell)

    _, mid_y = center(outline_bounds(glyf["periodcentered"], glyf))
    install_components(font, "periodcentered", [dot_at(cell / 2, mid_y)], cell)
    for name in ("exclam", "question", "exclamdown", "questiondown"):
        sentence_mark(font, name, radius, settings["sentence_dot_clearance"], cell)
