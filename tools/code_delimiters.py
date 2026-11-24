"""Build the Code enclosure marks from the current Sans curves."""

from fontTools.misc.roundTools import otRound
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

from audit import spans
from code_foundation import center, outline_bounds
from code_outlines import install, refresh_bounds
from italic_returns import draw_segments, raw_outline, segments


def extend_brace_nose(outline, reach, weight_ratio):
    """Extend the outer pinch with flat rails that follow the donor tangents."""
    contour, = outline.contours
    edges = segments(contour)
    tip = min(range(len(edges)), key=lambda index: edges[index].start[0])
    below, above, *remainder = edges[tip - 1:] + edges[:tip - 1]
    tip_x, tip_y = above.start
    _, bottom, _, top = outline.bounds
    left, right = spans(outline, bottom + (top - bottom) / 4, 1)[0]
    half = otRound((right - left) * weight_ratio / 2)
    lower, upper = tip_y - half, tip_y + half
    nose = tip_x - reach

    def tangent_at_y(point, control, y):
        x0, y0 = point
        x1, y1 = control
        return (x0 + (y - y0) * (x1 - x0) / (y1 - y0), y)

    pen = TTGlyphPen(None)
    pen.moveTo(below.start)
    pen.qCurveTo(tangent_at_y(below.start, below.controls[0], lower), (tip_x, lower))
    pen.lineTo((nose, lower))
    pen.lineTo((nose, upper))
    pen.lineTo((tip_x, upper))
    pen.qCurveTo(tangent_at_y(above.end, above.controls[-1], upper), above.end)
    draw_segments(pen, remainder)
    pen.closePath()
    return pen.glyph()


def build_delimiters(font, recipe):
    config = recipe["alphabet_review"]
    settings = recipe["delimiters_review"]
    cell = config["cell"]
    vertical_center = recipe["horizontal_punctuation_review"]["minus_center"]
    glyf = font["glyf"]
    for kind, inset in settings["insets"].items():
        opening = kind + "left"
        glyph = glyf[opening]
        if kind == "brace":
            outline = raw_outline(font.getGlyphSet(), opening)
            glyph = extend_brace_nose(outline, settings["brace_nose_reach"], settings["brace_nose_weight"])
        elif kind == "bracket":
            _, _, terminal, _ = outline_bounds(glyph, glyf)
            glyph.coordinates = GlyphCoordinates((x + settings["bracket_arm"], y) if x == terminal else (x, y)
                                                  for x, y in glyph.coordinates)
        _, current_center = center(outline_bounds(glyph, glyf))
        glyph.coordinates.translate((inset, otRound(vertical_center - current_center)))
        install(font, opening, glyph, cell)
        refresh_bounds(font, kind + "right")
