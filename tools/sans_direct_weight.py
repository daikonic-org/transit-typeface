"""Apply weight directly to the stored TrueType control points."""

from collections import defaultdict

from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

from sans_aperture import preserve_apertures


def offset_corner(previous, point, following, amount, miter):
    incoming, outgoing = point - previous, following - point
    if not incoming or not outgoing:
        return point
    incoming_normal = 1j * incoming / abs(incoming)
    outgoing_normal = 1j * outgoing / abs(outgoing)
    normal_sum = incoming_normal + outgoing_normal
    if not normal_sum:
        return point
    direction = normal_sum / abs(normal_sum)
    projection = (direction.conjugate() * incoming_normal).real
    distance = amount / max(projection, 1 / miter)
    return point + direction * distance


def near_square_symmetry(glyph):
    points = {(x, y, flag & 1) for (x, y), flag in zip(glyph.coordinates, glyph.flags)}
    xs, ys = zip(*glyph.coordinates)
    x_low, x_high, y_low, y_high = min(xs), max(xs), min(ys), max(ys)
    if x_high == x_low or abs((x_high - x_low) - (y_high - y_low)) > 1:
        return False
    for x, y, kind in points:
        reflections = ((x_low + x_high - x, y), (x, y_low + y_high - y))
        if any(not any((rx + dx, ry + dy, kind) in points
                       for dx, dy in ((0, 0), (0, 1), (0, -1), (1, 0), (-1, 0)))
               for rx, ry in reflections):
            return False
    return True


def separation(first, second):
    """Find the clearest axis that separates two sets of ink."""
    options = [
        (second[axis] - first[axis + 2], axis, 1)
        for axis in (0, 1)
    ] + [
        (first[axis] - second[axis + 2], axis, -1)
        for axis in (0, 1)
    ]
    gap, axis, sign = max(options)
    return (axis, sign, gap) if gap > 0 else None


def signed_gap(first, second, axis, sign):
    if sign > 0:
        return second[axis] - first[axis + 2]
    return first[axis] - second[axis + 2]


def convex_hull(points):
    def half(sequence):
        hull = []
        for point in sequence:
            while len(hull) >= 2 and ((hull[-1] - hull[-2]).conjugate() *
                                      (point - hull[-1])).imag <= 0:
                hull.pop()
            hull.append(point)
        return hull

    ordered = sorted(set(points), key=lambda p: (p.real, p.imag))
    return half(ordered)[:-1] + half(reversed(ordered))[:-1]


def projected_interval(points, direction):
    values = [(direction.conjugate() * point).real for point in points]
    return min(values), max(values)


def diagonal_separation(first, second):
    """Find a positive separating projection when the bounding boxes overlap."""
    hulls = [convex_hull(ring) for ring in (first, second)]
    options = []
    for hull in hulls:
        for start, end in zip(hull, hull[1:] + hull[:1]):
            edge = end - start
            direction = 1j * edge / abs(edge)
            a, b = (projected_interval(part, direction) for part in hulls)
            if b[0] > a[1]:
                options.append((b[0] - a[1], direction))
            elif a[0] > b[1]:
                options.append((a[0] - b[1], -direction))
    return max(options, key=lambda option: option[0]) if options else None


def contour_clearance(first, second, first_box, second_box):
    horizontal = separation(first_box, second_box)
    if horizontal:
        axis, sign, minimum = horizontal
        direction = (1 if axis == 0 else 1j) * sign
        return minimum, direction, direction
    diagonal = diagonal_separation(first, second)
    if diagonal is None:
        return None
    minimum, direction = diagonal
    # Keep rows and stacks on their original alignment when possible.
    x_delta = second_box[0] + second_box[2] - first_box[0] - first_box[2]
    y_delta = second_box[1] + second_box[3] - first_box[1] - first_box[3]
    if abs(y_delta) <= 1 < abs(x_delta) and abs(direction.real) >= 0.5:
        movement = 1 if direction.real > 0 else -1
    elif abs(x_delta) <= 1 < abs(y_delta) and abs(direction.imag) >= 0.5:
        movement = 1j if direction.imag > 0 else -1j
    else:
        movement = direction
    return minimum, direction, movement


def keep_contour_gaps(glyph, points):
    """Preserve clearance between separate positive contours and carry their counters."""
    def bounds(ring):
        return (min(p.real for p in ring), min(p.imag for p in ring),
                max(p.real for p in ring), max(p.imag for p in ring))

    original_points = [complex(x, y) for x, y in glyph.coordinates]
    rings = []
    start = 0
    for end in glyph.endPtsOfContours:
        coords = original_points[start:end + 1]
        area = sum((a.conjugate() * b).imag for a, b in zip(coords, coords[1:] + coords[:1]))
        rings.append((start, end + 1, area, bounds(coords)))
        start = end + 1
    bodies = [i for i, (_, _, area, _) in enumerate(rings) if area < 0]
    if len(bodies) < 2:
        return

    followers = defaultdict(list)
    for i, (_, _, area, inner) in enumerate(rings):
        if area <= 0:
            continue
        enclosures = []
        for j in bodies:
            _, _, _, outer = rings[j]
            if all(outer[k] <= inner[k] and inner[k + 2] <= outer[k + 2] for k in (0, 1)):
                enclosures.append(((outer[2] - outer[0]) * (outer[3] - outer[1]), j))
        if enclosures:
            followers[min(enclosures)[1]].append(i)

    for order, i in enumerate(bodies):
        start, end, _, original = rings[i]
        for j in bodies[:order]:
            prior_start, prior_end, _, prior_original = rings[j]
            first = original_points[prior_start:prior_end]
            second = original_points[start:end]
            relation = contour_clearance(first, second, prior_original, original)
            if relation is None:
                continue
            minimum, direction, movement = relation
            _, prior_high = projected_interval(points[prior_start:prior_end], direction)
            low, _ = projected_interval(points[start:end], direction)
            current = low - prior_high
            if current >= minimum:
                continue
            projection = (direction.conjugate() * movement).real
            shift = movement * (minimum - current) / projection
            a, b = projected_interval(first, direction)
            c, d = projected_interval(second, direction)
            if len(bodies) == 2 and abs((b - a) - (d - c)) <= 1:
                shifts = ((j, -shift / 2), (i, shift / 2))
            else:
                shifts = ((i, shift),)
            for body, amount in shifts:
                for member in [body, *followers[body]]:
                    low, high, _, _ = rings[member]
                    for index in range(low, high):
                        points[index] += amount


def on_curve_edges(glyph):
    start = 0
    for end in glyph.endPtsOfContours:
        for i in range(start, end + 1):
            j = start if i == end else i + 1
            if glyph.flags[i] & glyph.flags[j] & 1:
                yield start, i, j
        start = end + 1


def keep_junctions(glyph, points, reach):
    """Preserve shared knots and stop short contour edges from reversing."""
    source = [complex(x, y) for x, y in glyph.coordinates]
    edges = list(on_curve_edges(glyph))
    for _, a, b in edges:
        direction = source[b] - source[a]
        if 0 < abs(direction) <= reach:
            axis = direction / abs(direction)
            current = ((points[b] - points[a]).conjugate() * axis).real
            if current < 1:
                correction = axis * (abs(direction) - current) / 2
                points[a] -= correction
                points[b] += correction

    lines = defaultdict(list)
    for ring, a, b in edges:
        first, last = source[a], source[b]
        if first.real == last.real and first.imag != last.imag:
            lines[(ring, True, first.real, 1 if last.imag > first.imag else -1)].append((a, b))
        elif first.imag == last.imag and first.real != last.real:
            lines[(ring, False, first.imag, 1 if last.real > first.real else -1)].append((a, b))
    for (_, vertical, _, sign), spans in lines.items():
        axis = 1j if vertical else 1
        direction = axis * sign
        def along(point):
            return (point.conjugate() * direction).real

        def across(point):
            return (point.conjugate() * axis * 1j).real

        order = sorted(spans, key=lambda edge: along(source[edge[0]]))
        for (a, b), (c, d) in zip(order, order[1:]):
            gap = along(source[c]) - along(source[b])
            if not 0 <= gap <= reach:
                continue
            current = along(points[c]) - along(points[b])
            if current < 1:
                correction = direction * (gap - current) / 2
                points[b] -= correction
                points[c] += correction
            indices = {a, b, c, d}
            common = sum(across(points[i]) for i in indices) / len(indices)
            for i in indices:
                points[i] += axis * 1j * (common - across(points[i]))

    knots = defaultdict(list)
    for i, (point, flag) in enumerate(zip(source, glyph.flags)):
        if flag & 1:
            knots[point].append(i)
    for group in knots.values():
        if len(group) > 1:
            average = sum(points[i] for i in group) / len(group)
            for i in group:
                points[i] = average


def keep_crossbar_height(glyph, points, height):
    """Hold an authored x-height crossbar shoulder on its original line."""
    if height is None:
        return
    start = 0
    for end in glyph.endPtsOfContours:
        for index in range(start, end + 1):
            nxt = start if index == end else index + 1
            before = end if index == start else index - 1
            after = start if nxt == end else nxt + 1
            if not all(glyph.flags[i] & 1 for i in (before, index, nxt, after)):
                continue
            x0, y0 = glyph.coordinates[before]
            x1, y = glyph.coordinates[index]
            x2, y2 = glyph.coordinates[nxt]
            x3, y3 = glyph.coordinates[after]
            if abs(y - height) <= 1 and y2 == y and x0 == x1 and x2 == x3 and (y - y0) * (y3 - y) > 0:
                points[index] = complex(points[index].real, y)
                points[nxt] = complex(points[nxt].real, y)
        start = end + 1


def direct_points(glyph, change, ratio, miter, x_shift, *, apertures=(), contour_gaps=True, x_height=None):
    """Move each point using only its contour's adjacent directions."""
    if not change:
        if not x_shift:
            return glyph.coordinates
        return GlyphCoordinates((otRound(x + x_shift), y) for x, y in glyph.coordinates)
    x_offset = change / 2
    result = []
    start = 0
    for end in glyph.endPtsOfContours:
        ring = [complex(x, y / ratio) for x, y in glyph.coordinates[start:end + 1]]
        start = end + 1
        # Duplicate positions are common in liturgical ornaments and inherited
        # paths. Keep them coincident by using the same distinct neighbors.
        for i, point in enumerate(ring):
            previous = next((ring[i - k] for k in range(1, len(ring))
                             if ring[i - k] != point), point)
            following = next((ring[(i + k) % len(ring)] for k in range(1, len(ring))
                              if ring[(i + k) % len(ring)] != point), point)
            result.append(offset_corner(previous, point, following, x_offset, miter))
    result = [complex(p.real, p.imag * ratio) for p in result]
    xs, ys = zip(*glyph.coordinates)
    low, high = min(ys), max(ys)
    new_low, new_high = min(p.imag for p in result), max(p.imag for p in result)
    if near_square_symmetry(glyph):
        original_width = max(xs) - min(xs)
        width = max(p.real for p in result) - min(p.real for p in result)
        height = (high - low) * width / original_width
        center = (low + high) / 2
        low, high = center - height / 2, center + height / 2
    scale_y = (high - low) / (new_high - new_low) if new_high > new_low else 0
    result = [complex(p.real + x_shift, low + (p.imag - new_low) * scale_y) for p in result]
    keep_junctions(glyph, result, abs(change) * miter)
    if contour_gaps:
        keep_contour_gaps(glyph, result)
    result = preserve_apertures(glyph, result, change, x_shift, apertures)
    keep_crossbar_height(glyph, result, x_height)
    return GlyphCoordinates((otRound(p.real), otRound(p.imag)) for p in result)
