"""Build Code's tapered at sign from the pre-width-class a and c."""

from itertools import accumulate, pairwise

from fontTools.misc.bezierTools import calcQuadraticArcLength, splitQuadraticAtT
from fontTools.misc.transform import Transform
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

from code_foundation import center
from code_outlines import install, move_return
from italic_returns import Segment, draw_segments, raw_outline, segments


def point_tangent(curve, t):
    start, control, end = curve
    left = start + t * (control - start)
    right = control + t * (end - control)
    return left + t * (right - left), right - left


def cut_at_join(curve, join):
    """End the outside arc where its normal meets the inner a arch."""
    lo, hi = 0, 1
    for _ in range(24):
        t = (lo + hi) / 2
        point, tangent = point_tangent(curve, t)
        if ((point - join) * tangent.conjugate()).real < 0:
            lo = t
        else:
            hi = t
    t = (lo + hi) / 2
    point, tangent = point_tangent(curve, t)
    return curve[0], point - t * tangent, point


def tapered_wall(outside, terminal, join, join_tangent, terminal_ratio):
    """Derive one inner wall with decreasing thickness and shared tangents."""
    def xy(z):
        return z.real, z.imag

    curves = [tuple(complex(*point) for point in terminal)]
    curves.extend(tuple(complex(*point) for point in (edge.start, *edge.controls, edge.end))
                  for edge in outside)
    ending = cut_at_join(curves[-1], join)
    # Reserve the last quarter of the cut segment for the tangent-matched join.
    curves[-1:] = [tuple(complex(*p) for p in piece)
                   for piece in splitQuadraticAtT(*map(xy, ending), 0.75)]
    lengths = (calcQuadraticArcLength(*map(xy, curve)) for curve in curves)
    distances = list(accumulate(lengths, initial=0))
    join_width = abs(join - curves[-1][-1])
    start_width = terminal_ratio * join_width

    def offset(curve, t, distance):
        point, tangent = point_tangent(curve, t)
        width = start_width + (join_width - start_width) * distance / distances[-1]
        return point - 1j * tangent / abs(tangent) * width

    points = [offset(curve, 0, s) for curve, s in zip(curves, distances[:-1], strict=True)]
    points.append(join)
    incoming, outgoing = [], []
    for curve, (s0, s1) in zip(curves, pairwise(distances), strict=True):
        step = (s1 - s0) * 0.001
        outgoing.append(offset(curve, 0.001, s0 + step) - offset(curve, 0, s0))
        incoming.append(offset(curve, 1, s1) - offset(curve, 0.999, s1 - step))
    tangents = [outgoing[0]]
    tangents.extend(a / abs(a) + b / abs(b) for a, b in zip(incoming[:-1], outgoing[1:], strict=True))
    tangents.append(join_tangent)

    # Extend the tapered inner curve along its tangent to the vertical cut.
    extension = (terminal[0][0] - points[0].real) / tangents[0].real
    start = points[0] + extension * tangents[0]
    wall = [Segment(xy(start), "lineTo", (), xy(points[0]))]
    for (a, b), (ta, tb) in zip(pairwise(points[:-1]), pairwise(tangents[:-1]), strict=True):
        # The intersection makes both quadratics at a knot share its tangent.
        fraction = ((b - a).conjugate() * tb).imag / (ta.conjugate() * tb).imag
        wall.append(Segment(xy(a), "qCurveTo", (xy(a + fraction * ta),), xy(b)))

    # The donor's arch can turn more steeply than the preceding wall. Use two
    # quadratic pieces here to match the tangent without doubling back.
    a, b = points[-2:]
    ta, tb = tangents[-2:]
    reach = abs(b - a) / 4
    first = a + reach * ta / abs(ta)
    last = b - reach * tb / abs(tb)
    middle = (first + last) / 2
    wall.extend((Segment(xy(a), "qCurveTo", (xy(first),), xy(middle)),
                 Segment(xy(middle), "qCurveTo", (xy(last),), xy(b))))
    return wall


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
    donor_tip = c_edges[-1]
    fraction = (donor_tip.controls[0][0] - donor_tip.end[0]) / (donor_tip.start[0] - donor_tip.end[0])
    outer_floor_x, _ = c_outline[0].start
    rise = settings["terminal_rise"]
    tip = (tip_x, floor + rise)
    tip_control = (outer_floor_x + (tip_x - outer_floor_x) * fraction, floor)
    join = complex(*a_edges[9].start)
    join_tangent = complex(*a_edges[8].controls[-1]) - join
    wall = tapered_wall(c_outline, (tip, tip_control, c_outline[0].start), join, join_tangent,
                        settings["terminal_to_join_ratio"])

    pen = TTGlyphPen(None)
    pen.moveTo(a_edges[0].start)
    draw_segments(pen, a_edges[:9])
    draw_segments(pen, wall, reverse=True)
    pen.lineTo(tip)
    pen.qCurveTo(tip_control, c_outline[0].start)
    draw_segments(pen, c_outline)
    pen.lineTo(a_edges[14].start)
    draw_segments(pen, a_edges[14:])
    pen.closePath()
    counter_x, counter_y = center(a_counter.bounds)
    counter_scale = settings["a_counter_scale"]
    counter = body.transform(Transform(counter_scale, 0, 0, counter_scale,
                                       (1 - counter_scale) * counter_x, (1 - counter_scale) * counter_y))
    a_counter.draw(TransformPen(pen, counter))
    install(font, "at", pen.glyph(), cell)
