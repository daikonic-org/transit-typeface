"""Build the primary Code punctuation from the shared Sans diamond."""

from fontTools.misc.roundTools import otRound

from code_foundation import center, outline_bounds
from code_outlines import install_components, install_outline, polygon, refresh_bounds


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


def build_diamond_punctuation(font, recipe):
    settings = recipe["diamond_punctuation_review"]
    config = recipe["alphabet_review"]
    cell = config["cell"]
    glyf = font["glyf"]
    left, _, right, _ = outline_bounds(glyf["diamond.dot"], glyf)
    radius = otRound((right - left) * settings["diamond_scale"] / 2)
    install_outline(font, DOT, polygon(((0, radius), (radius, 0), (0, -radius), (-radius, 0))), 0)
    period_y = config["baseline"] + radius - otRound(radius * settings["period_overshoot"])
    install_components(font, "period", [dot_at(cell / 2, period_y)], cell)

    lower, upper = sorted(part.y for part in glyf["colon"].components)
    half_gap = (upper - lower) / 2
    lower_y = settings["colon_center"] - half_gap
    upper_y = settings["colon_center"] + half_gap
    install_components(font, "colon", [dot_at(cell / 2, lower_y), dot_at(cell / 2, upper_y)], cell)

    comma, old_dot = glyf["semicolon"].components
    comma_left, _, comma_right, _ = outline_bounds(glyf[comma.glyphName], glyf)
    left = min(comma_left + comma.x, old_dot.x - radius)
    right = max(comma_right + comma.x, old_dot.x + radius)
    shift = otRound((cell - left - right) / 2)
    install_components(font, "semicolon", [(comma.glyphName, (1, 0, 0, 1, comma.x + shift, comma.y)),
                                          dot_at(old_dot.x + shift, upper_y)], cell)

    dots = [dot_at(cell * (i + 0.5) / 3, period_y, settings["ellipsis_dot_x_scale"]) for i in range(3)]
    install_components(font, "ellipsis", dots, cell)

    _, mid_y = center(outline_bounds(glyf["periodcentered"], glyf))
    install_components(font, "periodcentered", [dot_at(cell / 2, mid_y)], cell)
    for name in ("exclam", "question", "exclamdown", "questiondown"):
        sentence_mark(font, name, radius, settings["sentence_dot_clearance"], cell)
