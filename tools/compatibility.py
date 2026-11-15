"""Shared curve matching from the first Daikonic variable master build."""

from bisect import bisect_right
import math
from munkres import Munkres
import pathops
from fontTools.pens.basePen import BasePen
from fontTools.pens.cu2quPen import Cu2QuMultiPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

CURVE_ERROR = 0.15


def point(z):
    return z.real, z.imag


def cubic(c, t):
    s = 1 - t
    return (
        s * s * s * c[0]
        + 3 * s * s * t * c[1]
        + 3 * s * t * t * c[2]
        + t * t * t * c[3]
    )


def split(c, t):
    a, b, d = ((1 - t) * c[i] + t * c[i + 1] for i in range(3))
    e, f = (1 - t) * a + t * b, (1 - t) * b + t * d
    g = (1 - t) * e + t * f
    return (c[0], a, e, g), (g, f, d, c[3])


def section(c, lo, hi):
    if hi < 1:
        c = split(c, hi)[0]
    if lo > 0:
        c = split(c, lo / hi)[1]
    return c


def top_start(curves):
    choices = []
    for i, c in enumerate(curves):
        y = [z.imag for z in c]
        a = 3 * (-y[0] + 3 * y[1] - 3 * y[2] + y[3])
        b = 2 * (3 * y[0] - 6 * y[1] + 3 * y[2])
        d = 3 * (y[1] - y[0])
        roots = []
        if abs(a) < 1e-9:
            if abs(b) > 1e-9:
                roots = [-d / b]
        else:
            disc = b * b - 4 * a * d
            if disc >= 0:
                roots = [
                    (-b - math.sqrt(disc)) / (2 * a),
                    (-b + math.sqrt(disc)) / (2 * a),
                ]
        for t in [0] + [t for t in roots if 0 < t < 1]:
            z = cubic(c, t)
            choices.append((z.imag, z.real, i, t))
    ymax = max(v[0] for v in choices)
    _, _, index, t = min((v for v in choices if ymax - v[0] < 1e-5), key=lambda v: v[1])
    if t < 1e-8:
        return curves[index:] + curves[:index]
    left, right = split(curves[index], t)
    return [right] + curves[index + 1 :] + curves[:index] + [left]


class CubicCollector(BasePen):
    def __init__(self):
        super().__init__(None)
        self.curves = []
        self.start = None

    def _moveTo(self, p):
        self.start = complex(*p)

    def _lineTo(self, p):
        current = complex(*self._getCurrentPoint())
        end = complex(*p)
        self.curves.append(
            (
                current,
                current + (end - current) / 3,
                current + 2 * (end - current) / 3,
                end,
            )
        )

    def _curveToOne(self, p1, p2, p3):
        self.curves.append(
            (
                complex(*self._getCurrentPoint()),
                complex(*p1),
                complex(*p2),
                complex(*p3),
            )
        )

    def _qCurveToOne(self, p1, p2):
        current, control, end = (
            complex(*self._getCurrentPoint()),
            complex(*p1),
            complex(*p2),
        )
        self.curves.append(
            (
                current,
                current + 2 * (control - current) / 3,
                end + 2 * (control - end) / 3,
                end,
            )
        )

    def _closePath(self):
        current = complex(*self._getCurrentPoint())
        if abs(current - self.start) > 1e-8:
            self._lineTo(point(self.start))


def curves_from_path(contour):
    pen = CubicCollector()
    contour.draw(pen)
    return top_start([c for c in pen.curves if max(abs(z - c[0]) for z in c) > 1e-8])


def shape_for(glyphs, name):
    shape = pathops.Path()
    glyphs[name].draw(shape.getPen(glyphs))
    return pathops.simplify(shape, fix_winding=True, clockwise=True)


def signature(shape):
    contours = list(shape.contours)
    return sum(c.clockwise for c in contours), sum(not c.clockwise for c in contours)


def normalize_contacts(shape):
    edge = pathops.Path()
    edge.addPath(shape)
    edge.stroke(0.1, pathops.LineCap.BUTT_CAP, pathops.LineJoin.MITER_JOIN, 3)
    edge.convertConicsToQuads(0.01)
    return pathops.op(
        shape, edge, pathops.PathOp.UNION, fix_winding=True, clockwise=True
    )


def contour_center(contour):
    x0, y0, x1, y1 = contour.bounds
    return complex((x0 + x1) / 2, (y0 + y1) / 2)


def contour_pairs(a, b):
    pairs = []
    for clockwise in (True, False):
        ca = [c for c in a.contours if c.clockwise == clockwise and c.area > 1e-5]
        cb = [c for c in b.contours if c.clockwise == clockwise and c.area > 1e-5]
        count = max(len(ca), len(cb))
        if not count:
            continue

        def cost(i, j):
            if i >= len(ca):
                return 10 + math.sqrt(cb[j].area) / 10
            if j >= len(cb):
                return 10 + math.sqrt(ca[i].area) / 10
            distance = abs(contour_center(ca[i]) - contour_center(cb[j])) / 50
            size = abs(math.log((ca[i].area + 1) / (cb[j].area + 1)))
            return distance + size

        costs = [[cost(i, j) for j in range(count)] for i in range(count)]
        for i, j in Munkres().compute(costs):
            pairs.append(
                (ca[i] if i < len(ca) else None, cb[j] if j < len(cb) else None)
            )
    return pairs


class ArcContour:
    """Approximate arc length locates exact subdivisions on the original cubics."""

    def __init__(self, curves):
        self.curves = curves
        self.starts = [0.0]
        self.tables = []
        for curve in curves:
            values = [0.0]
            prior = curve[0]
            for i in range(1, 65):
                current = cubic(curve, i / 64)
                values.append(values[-1] + abs(current - prior))
                prior = current
            self.tables.append(values)
            self.starts.append(self.starts[-1] + values[-1])
        self.length = self.starts[-1]
        assert self.length > 0
        self.breaks = [v / self.length for v in self.starts]

    def portion(self, lo, hi):
        midpoint = (lo + hi) / 2 * self.length
        index = min(bisect_right(self.starts, midpoint) - 1, len(self.curves) - 1)

        def at(value):
            target = max(
                0, min(self.tables[index][-1], value * self.length - self.starts[index])
            )
            table = self.tables[index]
            sample = min(max(0, bisect_right(table, target) - 1), 63)
            width = table[sample + 1] - table[sample]
            return (
                (sample + (target - table[sample]) / width) / 64
                if width
                else sample / 64
            )

        return section(self.curves[index], at(lo), at(hi))


def corner_landmarks(arc):
    xs = [z.real for c in arc.curves for z in c]
    ys = [z.imag for c in arc.curves for z in c]
    left, bottom = min(xs), min(ys)
    width, height = max(xs) - left, max(ys) - bottom
    result = []
    for i, current in enumerate(arc.curves):
        if i == 0:
            continue
        previous = arc.curves[i - 1]
        incoming = next(
            (
                previous[-1] - z
                for z in reversed(previous[:-1])
                if abs(previous[-1] - z) > 1e-6
            ),
            0,
        )
        outgoing = next(
            (z - current[0] for z in current[1:] if abs(z - current[0]) > 1e-6), 0
        )
        if not incoming or not outgoing:
            continue
        cosine = max(
            -1,
            min(
                1,
                (incoming.conjugate() * outgoing).real
                / (abs(incoming) * abs(outgoing)),
            ),
        )
        angle = math.acos(cosine)
        if angle > 0.2:
            cross = (incoming.conjugate() * outgoing).imag
            turn = angle if cross >= 0 else -angle
            z = complex(
                (current[0].real - left) / max(width, 1),
                (current[0].imag - bottom) / max(height, 1),
            )
            result.append((arc.breaks[i], z, turn))
    return result


def matched_landmarks(a, b):
    ca, cb = corner_landmarks(a), corner_landmarks(b)
    n, m = len(ca), len(cb)
    gap = 0.45
    costs = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = {}
    for i in range(1, n + 1):
        costs[i][0] = i * gap
        back[i, 0] = (i - 1, 0, False)
    for j in range(1, m + 1):
        costs[0][j] = j * gap
        back[0, j] = (0, j - 1, False)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            u, p, angle = ca[i - 1]
            v, q, other_angle = cb[j - 1]
            match = 3 * abs(p - q) + abs(u - v) + abs(angle - other_angle) / math.pi
            options = (
                (costs[i - 1][j - 1] + match, (i - 1, j - 1, True)),
                (costs[i - 1][j] + gap, (i - 1, j, False)),
                (costs[i][j - 1] + gap, (i, j - 1, False)),
            )
            costs[i][j], back[i, j] = min(options, key=lambda option: option[0])
    matches = []
    i, j = n, m
    while i or j:
        ni, nj, matched = back[i, j]
        if matched:
            matches.append((ca[i - 1][0], cb[j - 1][0]))
        i, j = ni, nj
    return [(0.0, 0.0)] + list(reversed(matches)) + [(1.0, 1.0)]


def corresponding_cubics(a, b):
    arcs = [ArcContour(curves_from_path(c)) if c is not None else None for c in (a, b)]
    landmarks = matched_landmarks(*arcs) if all(arcs) else [(0.0, 0.0), (1.0, 1.0)]
    curves = [[], []]
    center = contour_center(a if a is not None else b)
    for lower, upper in zip(landmarks, landmarks[1:]):
        breaks = {0.0, 1.0}
        for i, arc in enumerate(arcs):
            if arc:
                breaks.update(
                    (u - lower[i]) / (upper[i] - lower[i])
                    for u in arc.breaks
                    if lower[i] < u < upper[i]
                )
        merged = [0.0]
        for u in sorted(breaks)[1:]:
            if u - merged[-1] > 1e-8:
                merged.append(u)
        merged[-1] = 1.0
        for lo, hi in zip(merged, merged[1:]):
            for i, arc in enumerate(arcs):
                if arc:
                    start = lower[i] + lo * (upper[i] - lower[i])
                    end = lower[i] + hi * (upper[i] - lower[i])
                    curves[i].append(arc.portion(start, end))
                else:
                    curves[i].append((center,) * 4)
    return curves


def compatible_glyphs(a, b):
    records = [[], []]
    pens = [
        TTGlyphPen(None, outputImpliedClosingLine=True),
        TTGlyphPen(None, outputImpliedClosingLine=True),
    ]
    multi = Cu2QuMultiPen(pens, CURVE_ERROR)
    degenerate = 0
    for ca, cb in contour_pairs(a, b):
        curves = corresponding_cubics(ca, cb)
        degenerate += ca is None or cb is None
        multi.moveTo([(point(c[0][0]),) for c in curves])
        for c, d in zip(*curves):
            multi.curveTo(
                [tuple(point(z) for z in c[1:]), tuple(point(z) for z in d[1:])]
            )
        multi.closePath()
        for record, parts in zip(records, curves):
            record.append(parts)
    glyphs = [pen.glyph(dropImpliedOnCurves=False) for pen in pens]
    assert glyphs[0].endPtsOfContours == glyphs[1].endPtsOfContours, (
        glyphs[0].endPtsOfContours,
        glyphs[1].endPtsOfContours,
    )
    assert glyphs[0].flags == glyphs[1].flags
    return glyphs, records, degenerate


def key(contour):
    return contour.bounds, round(contour.area, 5)


def map_value(value, pairs, reverse=False):
    if reverse:
        pairs = [(b, a) for a, b in pairs]
    for (a, b), (d, e) in zip(pairs, pairs[1:]):
        if value <= d + 1e-9:
            return b + (value - a) * (e - b) / (d - a) if d > a else b
    return 1.0


def compatible_masters(shapes):
    """Match contours and corners to a shared reference arc, then convert together."""
    records = [[] for _ in shapes]
    pens = [TTGlyphPen(None, outputImpliedClosingLine=True) for _ in shapes]
    multi = Cu2QuMultiPen(pens, 0.15)
    missing = 0
    for clockwise in (True, False):
        groups = [
            [v for v in s.contours if v.clockwise == clockwise and v.area > 50]
            for s in shapes
        ]
        ref_index = max(range(len(shapes)), key=lambda i: len(groups[i]))
        reference = groups[ref_index]
        if not reference:
            continue
        mappings = []
        refshape = pathops.Path()
        for contour in reference:
            refshape.addPath(contour)
        for group in groups:
            other = pathops.Path()
            for contour in group:
                other.addPath(contour)
            mappings.append(
                {key(a): b for a, b in contour_pairs(refshape, other) if a is not None}
            )
        for ref in reference:
            aligned = [m.get(key(ref)) for m in mappings]
            arcs = [
                ArcContour(curves_from_path(v)) if v is not None else None
                for v in aligned
            ]
            anchor = arcs[ref_index]
            landmarks = [
                matched_landmarks(anchor, a) if a else [(0.0, 0.0), (1.0, 1.0)]
                for a in arcs
            ]
            cuts = {0.0, 1.0}
            for arc, lm in zip(arcs, landmarks):
                cuts.update(a for a, b in lm)
                if arc:
                    cuts.update(map_value(v, lm, reverse=True) for v in arc.breaks)
            merged = [0.0]
            for v in sorted(cuts):
                if v - merged[-1] > 1e-7:
                    merged.append(v)
            merged[-1] = 1.0
            center = contour_center(ref)
            curves = [[] for _ in shapes]
            for lo, hi in zip(merged, merged[1:]):
                for i, (arc, lm) in enumerate(zip(arcs, landmarks)):
                    curves[i].append(
                        arc.portion(map_value(lo, lm), map_value(hi, lm))
                        if arc
                        else (center,) * 4
                    )
            multi.moveTo([(point(v[0][0]),) for v in curves])
            for parts in zip(*curves):
                multi.curveTo([tuple(point(z) for z in v[1:]) for v in parts])
            multi.closePath()
            for row, parts in zip(records, curves):
                row.append(parts)
            missing += sum(a is None for a in aligned)
    glyphs = [p.glyph(dropImpliedOnCurves=False) for p in pens]
    assert all(
        g.endPtsOfContours == glyphs[0].endPtsOfContours and g.flags == glyphs[0].flags
        for g in glyphs
    )
    return glyphs, missing
