"""Fit Transit Sans weight changes on Metropolitan Line's original quadratic points."""

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.varLib.models import VariationModel, normalizeLocation

from audit import shape_from_glyphs, spans
from code_weight_width_trial import name_trial, sanitize
from compatibility import cubic, curves_from_path
from derive_weights import topology
from font_feature_tools import expanded_variations
from specimens import ROOT


FAMILY = "Daikonic Transit Sans Outline Trial"
UPSTREAM = ROOT / "upstream/MetropolitanLine-Regular.ttf"
SOURCE = ROOT / "releases/2026.11.20/sans/VF"
PILOT = "eocags8QbdfmnpruCGOS23569"
RESTRAINT = 0.8
MAX_RAY = 55


def average(a, b):
    return {**{i: value / 2 for i, value in a.items()},
            **{i: value / 2 for i, value in b.items()}}


def interpolate(terms):
    result = {}
    for basis, multiplier in terms:
        for index, value in basis.items():
            result[index] = result.get(index, 0) + value * multiplier
    return result


def evaluate(basis, coords):
    return sum(coords[index] * coefficient for index, coefficient in basis.items())


def segments(glyph):
    """Return the TrueType segments, with implied knots defined by their storage points."""
    start = 0
    for end in glyph.endPtsOfContours:
        ring = list(range(start, end + 1))
        start = end + 1
        flags = glyph.flags
        on_curve = next((i for i in ring if flags[i] & 1), None)
        if on_curve is None:
            knot = average({ring[-1]: 1}, {ring[0]: 1})
        else:
            cut = ring.index(on_curve)
            ring = ring[cut + 1:] + ring[:cut + 1]
            knot = {on_curve: 1}
        first = knot
        contour = []
        control = None
        for i in ring:
            point = {i: 1}
            if flags[i] & 1:
                contour.append((knot, control, point))
                knot, control = point, None
            else:
                if control is not None:
                    implied = average(control, point)
                    contour.append((knot, control, implied))
                    knot = implied
                control = point
        if on_curve is None:
            contour.append((knot, control, first))
        yield contour


def target_edges(path):
    for contour in path.contours:
        for curve in curves_from_path(contour):
            last = curve[0]
            for i in range(1, 5):
                current = cubic(curve, i / 4)
                yield last, current - last
                last = current


def normal_distance(point, normal, edges):
    answer = None
    for start, edge in edges:
        delta = start - point
        determinant = (normal.conjugate() * edge).imag
        if abs(determinant) < 0.7071 * abs(edge) or not edge:
            continue
        t = -(normal.conjugate() * delta).imag / determinant
        if 0 <= t <= 1:
            candidate = (delta + t * edge).real * normal.real + (delta + t * edge).imag * normal.imag
            if answer is None or abs(candidate) < abs(answer):
                answer = candidate
    return answer


class EdgeGrid:
    """Only edges within the fit's ray distance can constrain a sample."""

    def __init__(self, target):
        self.cells = {}
        self.edges = list(target_edges(target))
        for i, (start, edge) in enumerate(self.edges):
            end = start + edge
            for cell in self.cover(start, end):
                self.cells.setdefault(cell, []).append(i)

    @staticmethod
    def cover(a, b):
        x0, x1 = sorted((math.floor(a.real / MAX_RAY), math.floor(b.real / MAX_RAY)))
        y0, y1 = sorted((math.floor(a.imag / MAX_RAY), math.floor(b.imag / MAX_RAY)))
        return ((x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1))

    def nearby(self, point):
        radius = complex(MAX_RAY, MAX_RAY)
        indices = {
            i for cell in self.cover(point - radius, point + radius)
            for i in self.cells.get(cell, ())
        }
        # Preserve the original tie order when two edges are equally close.
        return (self.edges[i] for i in sorted(indices))


class LeastSquares:
    def __init__(self, size):
        self.matrix = [{} for _ in range(size)]
        self.values = [0.0] * size

    def add(self, row, value, weight=1):
        for i, a in row.items():
            self.values[i] += weight * a * value
            for j, b in row.items():
                coefficients = self.matrix[i]
                coefficients[j] = coefficients.get(j, 0.0) + weight * a * b

    def solve(self):
        # Interleave x and y for each point so elimination stays local along
        # the contour. The shared positive restraint makes every pivot positive.
        half = len(self.matrix) // 2
        order = [index for i in range(half) for index in (i, half + i)]
        for index in order:
            row = self.matrix[index]
            pivot = row.pop(index)
            neighbors = list(row.items())
            for j, value in neighbors:
                adjacent = self.matrix[j]
                adjacent.pop(index)
                factor = value / pivot
                self.values[j] -= factor * self.values[index]
                for k, coefficient in neighbors:
                    adjacent[k] = adjacent.get(k, 0.0) - factor * coefficient
            self.values[index] /= pivot
            for j in row:
                row[j] /= pivot
        result = [0.0] * len(order)
        for i in reversed(order):
            result[i] = self.values[i] - sum(
                coefficient * result[j] for j, coefficient in self.matrix[i].items()
            )
        return result


def fit(glyph, target, *, x_offset=0, shared_left_stem=False):
    coords = [complex(x + x_offset, y) for x, y in glyph.coordinates]
    n = len(coords)
    fit = LeastSquares(2 * n)
    edges = EdgeGrid(target)

    def vector_constraint(basis, weight, axes=(0, 1)):
        for axis in axes:
            fit.add({index + axis * n: value for index, value in basis.items()}, 0, weight)

    def normal_constraint(basis, direction, weight, value=0):
        normal = direction * 1j / abs(direction)
        row = {i: coefficient * normal.real for i, coefficient in basis.items()}
        row.update({i+n: coefficient * normal.imag for i, coefficient in basis.items()})
        fit.add(row, value, weight)

    for index in range(2 * n):
        fit.add({index: 1}, 0, RESTRAINT)
    for contour in segments(glyph):
        for index, (start, control, end) in enumerate(contour):
            # Preserve exact horizontal or vertical lines. Keep smooth joins smooth
            # by preserving the original ratio of the incoming and outgoing tangents.
            incoming = contour[index - 1][1] or contour[index - 1][0]
            outgoing = control or end
            incoming_basis = interpolate(((start, 1), (incoming, -1)))
            outgoing_basis = interpolate(((outgoing, 1), (start, -1)))
            u = evaluate(incoming_basis, coords)
            v = evaluate(outgoing_basis, coords)
            for basis, direction in ((incoming_basis, u), (outgoing_basis, v)):
                if direction:
                    normal_constraint(basis, direction, 12)
            if u and v and (u.conjugate() * v).real > 0 and abs((u.conjugate() * v).imag) / abs(u * v) < 0.025:
                ratio = abs(u) / (abs(u) + abs(v))
                vector_constraint(interpolate(((incoming, 1-ratio), (start, -1), (outgoing, ratio))), 32)
            if control is None:
                difference = interpolate(((end, 1), (start, -1)))
                line = evaluate(difference, coords)
                if abs(line) <= 45:
                    vector_constraint(difference, 24)
                for axis, value in enumerate((line.real, line.imag)):
                    if value == 0:
                        vector_constraint(interpolate(((end, 1), (start, -1))), 300, (axis,))
            for i in range(17):
                t = i / 16
                if control is None:
                    basis = interpolate(((start, 1-t), (end, t)))
                    tangent = interpolate(((end, 1), (start, -1)))
                else:
                    basis = interpolate(((start, (1-t)**2), (control, 2*t*(1-t)), (end, t*t)))
                    tangent = interpolate(((start, t-1), (control, 1-2*t), (end, t)))
                point, direction = evaluate(basis, coords), evaluate(tangent, coords)
                if direction:
                    normal = direction * 1j / abs(direction)
                    offset = normal_distance(point, normal, edges.nearby(point))
                    if offset is not None and abs(offset) < MAX_RAY:
                        normal_constraint(basis, direction, 1, offset)
    if shared_left_stem:
        # These three Johnston glyphs store the upper stem and its foot on
        # the same two x values, with a break at the shoulder.
        (left, right), *_ = spans(target, 100, 1)
        end = glyph.endPtsOfContours[0]
        for indices, x in (((0, 1), left), ((2, 3, end-1, end), right)):
            assert len({coords[i].real for i in indices}) == 1
            for i in indices:
                fit.add({i: 1}, x - coords[i].real, 10000)
        # Keep the notch ordered as the inside stem edge moves. Otherwise
        # the normal rays can catch the shoulder rather than the short leg.
        stem_top = spans(target, (left + right) / 2, 0)[-1][1]
        rise = stem_top - coords[2].imag
        for i in (1, 2, 3, 4):
            fit.add({n + i: 1}, rise, 10000)
        fit.add({4: 1}, right - coords[3].real, 10000)
    shifts = fit.solve()
    return GlyphCoordinates((otRound(z.real + shifts[i]), otRound(z.imag + shifts[i+n]))
                            for i,z in enumerate(coords))


def install(font, name, template, targets, locations, axis):
    # Preserve the advance variation carried in the four TrueType phantom points.
    old_variations = expanded_variations(font, name)
    original = deepcopy(template)
    original.program = Program()
    original.program.fromBytecode(b"")
    model = VariationModel([normalizeLocation(loc, axis) for loc in locations])
    default_advance = font["hmtx"][name][0]
    coords = [
        original.coordinates if loc["wght"] == 400 else fit(
            original, target, x_offset=(advance - default_advance) / 2,
            shared_left_stem=name in {"m", "n", "r"},
        )
        for loc, (target, advance) in zip(locations, targets)
    ]
    deltas = model.getDeltas(coords)
    by_support = {
        tuple(sorted(support.items())): [(otRound(x), otRound(y)) for x,y in delta] + [(0,0)]*4
        for support, delta in zip(model.supports, deltas) if support
    }
    for support, old in old_variations.items():
        row = by_support.setdefault(support, [(0,0)]*(len(original.coordinates)+4))
        row[-4:] = old[-4:]
    font["glyf"][name] = original
    original.recalcBounds(font["glyf"])
    font["hmtx"][name] = (font["hmtx"][name][0], original.xMin)
    font["gvar"].variations[name] = [TupleVariation(dict(support), delta) for support, delta in by_support.items()]


def build(output, *, glyphs=PILOT):
    output.mkdir(parents=True, exist_ok=True)

    upstream = TTFont(UPSTREAM)
    source = SOURCE / "DaikonicTransitSans-VF.ttf"
    current = TTFont(source, recalcTimestamp=False)
    edited = TTFont(source, recalcTimestamp=False)
    axis = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in current["fvar"].axes}
    weights = sorted({item.coordinates["wght"] for item in current["fvar"].instances})
    locations = [{"wght": weight} for weight in weights]
    samples = [{"wght": weight} for weight in range(300, 601, 25)]
    original_sets = [current.getGlyphSet(location=loc) for loc in samples]
    report = {}
    for character in dict.fromkeys(glyphs):
        name = current.getBestCmap()[ord(character)]
        source_name = upstream.getBestCmap()[ord(character)]
        template = upstream["glyf"][source_name]
        if template.isComposite() or not template.numberOfContours:
            continue
        old = (edited["glyf"][name], edited["hmtx"][name], edited["gvar"].variations[name])
        targets = [
            (shape_from_glyphs(gs, name), gs[name].width)
            for gs in (current.getGlyphSet(location=loc) for loc in locations)
        ]
        install(edited, name, template, targets, locations, axis)
        topology_changes = []
        for loc, reference in zip(samples, original_sets):
            instance = edited.getGlyphSet(location=loc)
            assert abs(instance[name].width - reference[name].width) < 1e-6
            before = shape_from_glyphs(reference, name)
            candidate = shape_from_glyphs(instance, name)
            if topology(before) != topology(candidate):
                topology_changes.append(loc["wght"])
        accepted = not topology_changes
        if not accepted:
            edited["glyf"][name], edited["hmtx"][name], edited["gvar"].variations[name] = old
        else:
            assert edited["glyf"][name].coordinates == template.coordinates
        report[character] = {"accepted": accepted, "old_points": len(old[0].coordinates),
                             "template_points": len(template.coordinates),
                             "topology_change_weights": topology_changes,
                             "restraint": RESTRAINT}
        print(character, report[character], flush=True)

    for instance in edited["fvar"].instances:
        style = edited["name"].getDebugName(instance.subfamilyNameID).replace(" ", "")
        instance.postscriptNameID = edited["name"].addName(FAMILY.replace(" ", "") + "-" + style)
    name = name_trial(edited, FAMILY, variable=True)
    out = output / (name + ".ttf")
    edited.save(out)
    sanitize(out)
    result = TTFont(out)
    for tag in ("GSUB", "GPOS", "GDEF", "HVAR", "cmap", "STAT"):
        assert current.getTableData(tag) == result.getTableData(tag), tag
    for name in current.getGlyphOrder():
        assert current["hmtx"][name][0] == result["hmtx"][name][0], name
    (output / "fit-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--glyphs", default=PILOT)
    args = parser.parse_args()

    build(args.output, glyphs=args.glyphs)


if __name__ == "__main__":
    main()
