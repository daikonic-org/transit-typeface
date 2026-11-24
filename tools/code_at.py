"""Build Code's tapered at sign from the pre-width-class a and c."""

from fontTools.misc.transform import Transform
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

from code_outlines import install, move_return
from italic_returns import draw_segments, raw_outline, segments


def build_at(font, recipe):
    settings = recipe["at_review"]
    glyphs = font.getGlyphSet()
    a, c, o = (raw_outline(glyphs, name) for name in ("a", "c", "o"))
    a_outer, a_counter = sorted(a.contours, key=lambda contour: not contour.clockwise)
    c_outer, = c.contours
    a_edges, c_edges = segments(a_outer), segments(c_outer)
    if len(a_edges) != 23 or len(c_edges) != 21:
        raise ValueError("The Sans a or c contours changed. Review the at sign's join points.")

    cell = recipe["alphabet_review"]["cell"]
    floor = o.bounds[1] - settings["below_o"]
    crown = o.bounds[3] + settings["above_o"]
    c_left, c_floor, c_right, c_crown = c.bounds
    sx = settings["shell_width_ratio"]
    sy = (crown - floor) / (c_crown - c_floor)
    shell_left = (cell - (c_right - c_left) * sx) / 2
    tip_x = cell - shell_left
    shell = Transform(sx, 0, 0, sy, shell_left - sx * c_left, floor - sy * c_floor)

    scale = settings["a_scale"]
    body = Transform(scale, 0, 0, scale, tip_x - scale * a.bounds[2], crown - scale * a.bounds[3])
    a_edges = move_return(a_edges, body.transformPoint)
    c_outline = move_return(c_edges[:6], shell.transformPoint)
    c_inside = move_return(c_edges[14:17], shell.transformPoint)

    pen = TTGlyphPen(None)
    pen.moveTo(a_edges[0].start)
    draw_segments(pen, a_edges[:9])
    # Match the a arch's tangent at the join and the c's vertical tangent at the left.
    arch_x, arch_y = a_edges[9].start
    control_x, control_y = a_edges[8].controls[-1]
    inner_x, inner_y = c_inside[0].start
    slope = (arch_y - control_y) / (arch_x - control_x)
    pen.qCurveTo((inner_x, arch_y + (inner_x - arch_x) * slope), (inner_x, inner_y))
    draw_segments(pen, c_inside)

    # Use the donor c's lower turn on both sides of the vertical terminal.
    terminal = c_edges[-1]
    fraction = (terminal.controls[0][0] - terminal.end[0]) / (terminal.start[0] - terminal.end[0])
    inner_floor_x, inner_floor = c_inside[-1].end
    outer_floor_x, _ = c_outline[0].start
    rise = settings["terminal_rise"]
    pen.qCurveTo((inner_floor_x + (tip_x - inner_floor_x) * fraction, inner_floor),
                 (tip_x, inner_floor + rise))
    pen.lineTo((tip_x, floor + rise))
    pen.qCurveTo((outer_floor_x + (tip_x - outer_floor_x) * fraction, floor), (outer_floor_x, floor))
    draw_segments(pen, c_outline)
    pen.lineTo(a_edges[14].start)
    draw_segments(pen, a_edges[14:])
    pen.closePath()
    a_counter.draw(TransformPen(pen, body))
    install(font, "at", pen.glyph(), cell)
