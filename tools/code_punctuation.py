"""Build the primary Code punctuation from the shared Sans diamond."""

from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

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


def build_comma_forms(font, cell, baseline, period_top, upper_y, radius):
    glyf = font["glyf"]
    ink = glyf["comma"]
    left, _, right, top = outline_bounds(ink, glyf)
    old_center = (left + right) / 2
    scale = 2 * radius / (right - left)
    top_shift = min(0, period_top - (baseline + (top - baseline) * scale))
    axis = otRound(cell / 2)
    apex = max(range(len(ink.coordinates)), key=lambda i: ink.coordinates[i][1])
    points = [(otRound(axis + (x - old_center) * scale),
               otRound(baseline + (y - baseline) * scale + top_shift))
              for x, y in ink.coordinates]
    tip_y = points[apex][1]
    shoulder_y = tip_y - radius
    # Ease the left shoulder into the existing vertical start of the tail.
    join_x, join_y = points[apex - 2]
    ink.coordinates = GlyphCoordinates([
        *points[:apex - 1], (join_x, otRound((join_y + shoulder_y) / 2)),
        (axis - radius, shoulder_y), (axis, tip_y), (axis + radius, shoulder_y),
        *points[apex + 2:],
    ])
    ink.flags.insert(apex - 1, 0)
    ink.endPtsOfContours[0] += 1
    refresh_bounds(font, "comma")
    install_components(font, "semicolon", [("comma", (1, 0, 0, 1, 0, 0)), dot_at(axis, upper_y)], cell)


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

    build_comma_forms(font, cell, config["baseline"], period_y + radius, upper_y, radius)

    dots = [dot_at(cell * (i + 0.5) / 3, period_y, settings["ellipsis_dot_x_scale"]) for i in range(3)]
    install_components(font, "ellipsis", dots, cell)

    _, mid_y = center(outline_bounds(glyf["periodcentered"], glyf))
    install_components(font, "periodcentered", [dot_at(cell / 2, mid_y)], cell)
    for name in ("exclam", "question", "exclamdown", "questiondown"):
        sentence_mark(font, name, radius, settings["sentence_dot_clearance"], cell)
