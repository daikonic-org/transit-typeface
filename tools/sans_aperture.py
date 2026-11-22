"""Keep pointed terminals from closing or breaking away during weighting."""

from copy import copy
from typing import NamedTuple

import pathops
from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

from derive_weights import topology


class Aperture(NamedTuple):
    tip: int
    neighborhood: tuple[tuple[int, float], ...]
    facing_edge: tuple[int, int, float]
    clearance: float
    direction: complex


def dot(first, second):
    return (first.conjugate() * second).real


def apertures_for(glyph, reach):
    """Find convex acute tips with a nearby, nonadjacent edge facing them."""
    points = [complex(x, y) for x, y in glyph.coordinates]
    start = 0
    apertures = []
    for end in glyph.endPtsOfContours:
        indices = list(range(start, end + 1))
        start = end + 1
        size = len(indices)
        edges = list(zip(indices, indices[1:] + indices[:1]))
        arc = [0.0]
        for a, b in edges:
            arc.append(arc[-1] + abs(points[b] - points[a]))
        for slot, index in enumerate(indices):
            if not glyph.flags[index] & 1:
                continue
            point = points[index]
            before = next((points[indices[slot - step]] - point for step in range(1, size)
                           if points[indices[slot - step]] != point), 0)
            after = next((points[indices[(slot + step) % size]] - point for step in range(1, size)
                          if points[indices[(slot + step) % size]] != point), 0)
            if not before or not after:
                continue
            turn = before.conjugate() * after / (abs(before) * abs(after))
            if turn.real <= 0.5 or turn.imag <= 0:
                continue

            travel = [abs(distance - arc[slot]) for distance in arc[:-1]]
            neighborhood = tuple((i, min(d, arc[-1] - d)) for i, d in zip(indices, travel))
            candidates = []
            for edge_index, (a, b) in enumerate(edges):
                if index in (a, b):
                    continue
                edge = points[b] - points[a]
                if not edge:
                    continue
                t = min(1, max(0, dot(edge, point - points[a]) / abs(edge) ** 2))
                gap = point - (points[a] + edge * t)
                clearance = abs(gap)
                if not 1 <= clearance <= reach or neighborhood[edge_index][1] < 3 * clearance + 15:
                    continue
                if dot(gap, 1j * edge / abs(edge)) >= 0.7 * clearance:
                    candidates.append((clearance, a, b, t, gap / clearance))
            if candidates:
                clearance, a, b, t, direction = min(candidates, key=lambda candidate: candidate[0])
                apertures.append(Aperture(index, neighborhood, (a, b, t), clearance, direction))
    return apertures


def outline(glyph, points):
    proxy = copy(glyph)
    proxy.coordinates = GlyphCoordinates((otRound(p.real), otRound(p.imag)) for p in points)
    path = pathops.Path()
    proxy.draw(path.getPen(), None)
    return pathops.simplify(path, fix_winding=True, clockwise=True)


def distance_from_box(point, bounds):
    x0, y0, x1, y1 = bounds
    return abs(complex(max(x0 - point.real, 0, point.real - x1),
                       max(y0 - point.imag, 0, point.imag - y1)))


def preserve_apertures(glyph, points, change, x_shift, apertures):
    if not apertures:
        return points
    regular = [complex(x, y) for x, y in glyph.coordinates]
    original = topology(outline(glyph, regular))
    weighted = outline(glyph, points)
    ink, holes = topology(weighted)
    if (ink, holes) == original:
        return points

    corrected = points.copy()
    local_extent = 2 * abs(change)
    fragments = sorted((contour for contour in weighted.contours if contour.clockwise and contour.area > 50),
                       key=lambda contour: contour.area)[:max(0, ink - original[0])]
    for aperture in apertures:
        radius = local_extent
        a, b, t = aperture.facing_edge
        facing = points[a] + t * (points[b] - points[a])
        gap = dot(points[aperture.tip] - facing, aperture.direction)
        if change > 0 and holes > original[1] and gap < 2:
            move = (aperture.clearance - gap) * aperture.direction
            radius = max(radius, 3 * abs(move))
            preserve_tip = False
        elif change < 0 and any(distance_from_box(points[aperture.tip], part.bounds) < radius
                                for part in fragments):
            move = 0
            preserve_tip = True
        else:
            continue
        for i, distance in aperture.neighborhood:
            if distance >= radius:
                continue
            t = distance / radius
            influence = 1 - t * t * (3 - 2 * t)
            displacement = regular[i] + x_shift - points[i] if preserve_tip else move
            corrected[i] += displacement * influence
    if corrected != points and topology(outline(glyph, corrected)) == original:
        return corrected
    return points
