"""Join a donor's return to an existing stem without overlapping contours."""

from typing import NamedTuple

import pathops
from fontTools.pens.basePen import decomposeQuadraticSegment
from fontTools.pens.recordingPen import RecordingPen

from audit import spans


class Segment(NamedTuple):
    start: tuple[float, float]
    operation: str
    controls: tuple[tuple[float, float], ...]
    end: tuple[float, float]


def segments(contour):
    recorder = RecordingPen()
    contour.draw(recorder)
    first = current = recorder.value[0][1][0]
    result = []
    for operation, points in recorder.value[1:-1]:
        if operation == "qCurveTo":
            for control, end in decomposeQuadraticSegment(points):
                result.append(Segment(current, operation, (control,), end))
                current = end
        else:
            result.append(Segment(current, operation, points[:-1], points[-1]))
            current = points[-1]
    if first != current:
        result.append(Segment(current, "lineTo", (), first))
    return result


def stem_ends(edges, cut, sides):
    cuts = {}
    for index, segment in enumerate(edges):
        start, end = segment.start, segment.end
        if not min(start[1], end[1]) < cut < max(start[1], end[1]):
            continue
        if segment.operation != "lineTo" and (
            start[0] != end[0] or any(x != start[0] or not min(start[1], end[1]) <= y <= max(start[1], end[1])
                                      for x, y in segment.controls)
        ):
            continue
        x = start[0] + (end[0] - start[0]) * (cut - start[1]) / (end[1] - start[1])
        if any(abs(x - side) < 0.1 for side in sides):
            cuts[end[1] > cut] = index, (x, cut)
    return cuts if len(cuts) == 2 else None


def arc(edges, start, end):
    """Take a section of a contour between two intersections on straight edges."""
    first, entry = start
    last, exit_point = end
    result = [Segment(entry, "lineTo", (), edges[first].end)]
    index = (first + 1) % len(edges)
    while index != last:
        result.append(edges[index])
        index = (index + 1) % len(edges)
    result.append(Segment(edges[last].start, "lineTo", (), exit_point))
    return result


def raw_outline(glyphs, name):
    path = pathops.Path()
    glyphs[name].draw(path.getPen(glyphs))
    return path


def lower_arc(source, cut):
    sides, = spans(source, cut, 1)
    contour, = source.contours
    edges = segments(contour)
    ends = stem_ends(edges, cut, sides)
    if ends is None:
        raise ValueError("Donor return must meet two straight stem edges")
    return arc(edges, ends[False], ends[True]), sides


def transformed_return(donor, donor_floor, target_sides, cut, floor, reach, *, reflect, reach_factor):
    loan, (left, right) = donor
    if reflect:
        loan = [Segment(edge.end, edge.operation, edge.controls[::-1], edge.start) for edge in reversed(loan)]
        left, right = -right, -left
    else:
        loan = list(loan)
    donor_cut = loan[0].start[1]
    target_left, target_right = target_sides
    stem_scale = (target_right - target_left) / (right - left)
    reach_scale = stem_scale * reach_factor
    if reach is not None:
        tip = min((-edge.start[0] if reflect else edge.start[0]) for edge in loan)
        reach_scale = (reach - (target_right - target_left)) / (left - tip)
    vertical_scale = (cut - floor) / (donor_cut - donor_floor)

    def move(point):
        x, y = point
        x = -x if reflect else x
        scale = reach_scale if x < left else stem_scale
        return target_left + (x - left) * scale, floor + (y - donor_floor) * vertical_scale

    return [Segment(move(p.start), p.operation, tuple(map(move, p.controls)), move(p.end)) for p in loan]


def extend_return_tip(loan, distance):
    """Continue the upward turn and carry its existing terminal along with it."""
    def upright_rising(edge):
        return (edge.end[1] > edge.start[1]
                and all(x == edge.start[0] for x, _ in (*edge.controls, edge.end)))

    start = min((i for i, edge in enumerate(loan) if upright_rising(edge)),
                key=lambda i: loan[i].start[0])
    stop = start
    while stop < len(loan) and upright_rising(loan[stop]):
        stop += 1
    outer, cap, inner = loan[:start], loan[start:stop], loan[stop:]
    end_x, end_y = outer[-1].end
    control_x, control_y = outer[-1].controls[-1]
    tangent = (end_y - control_y) / (control_x - end_x)
    near_x, near_y = outer[-2].start
    run = near_x - end_x
    secant = (end_y - near_y) / run
    rise = distance * (tangent + (tangent - secant) * distance / run)

    def move(point):
        return point[0] - distance, point[1] + rise

    extended_cap = [
        Segment(move(edge.start), edge.operation, tuple(map(move, edge.controls)), move(edge.end))
        for edge in cap
    ]
    out_control = (end_x - distance / 2, end_y + tangent * distance / 2)
    lead = Segment(outer[-1].end, "qCurveTo", (out_control,), extended_cap[0].start)

    # Start the inner continuation from its first curve with an established
    # tangent, beyond the tiny corner segment at the donor's terminal.
    inner_x, inner_y = inner[0].end
    control_x, control_y = inner[0].controls[-1]
    inner_tangent = (control_y - inner_y) / (inner_x - control_x)
    inner_run = inner_x - extended_cap[-1].end[0]
    in_control = (inner_x - inner_run / 2, inner_y + inner_tangent * inner_run / 2)
    trail = Segment(extended_cap[-1].end, "qCurveTo", (in_control,), inner[0].end)
    return outer + [lead] + extended_cap + [trail] + inner[1:]


def join_straight_edges(first, second):
    left, right = first[-1], second[0]
    if left.operation == right.operation == "lineTo" and abs(left.start[0] - right.end[0]) < 0.02:
        first[-1] = left._replace(end=right.end)
        return first + second[1:]
    return first + second


def splice_return(
    source, donor, *, cut, donor_cut, floor, reach=None, reflect=False, reach_factor=1, extension=0,
):
    """Keep the original upper contour and replace only its stem's lower arc."""
    sides = spans(source, cut, 1)[0 if reflect else -1]
    loan = transformed_return(
        lower_arc(donor, donor_cut), donor.bounds[1], sides, cut, floor, reach,
        reflect=reflect, reach_factor=reach_factor,
    )
    if extension:
        loan = extend_return_tip(loan, extension)
    output = pathops.Path()
    joined = False
    for contour in source.contours:
        edges = segments(contour)
        ends = stem_ends(edges, cut, sides)
        if ends is None:
            output.addPath(contour)
            continue
        if joined:
            raise ValueError("Return must replace exactly one stem")
        upper = arc(edges, ends[True], ends[False])
        if any(abs(a - b) > 0.02 for p, q in ((upper[-1].end, loan[0].start),
                                               (loan[-1].end, upper[0].start))
               for a, b in zip(p, q)):
            raise ValueError("Donor and host stem endpoints did not meet")
        flattened = join_straight_edges(upper, loan)
        if (flattened[-1].operation == flattened[0].operation == "lineTo"
                and abs(flattened[-1].start[0] - flattened[0].end[0]) < 0.02):
            flattened[-1] = flattened[-1]._replace(end=flattened[0].end)
            flattened = flattened[1:]
        pen = output.getPen()
        pen.moveTo(flattened[0].start)
        for segment in flattened:
            getattr(pen, segment.operation)(*segment.controls, segment.end)
        pen.closePath()
        joined = True
    if not joined:
        raise ValueError("No straight host stem for the donor return")
    return output
