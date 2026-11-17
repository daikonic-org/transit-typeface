"""Derive all isolated normal dots from each face's selected variable master."""

from copy import deepcopy
from itertools import product
import json
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.misc.roundTools import otRound
from font_feature_tools import expanded_variations
from fontTools.varLib.models import supportScalar, VariationModel
from fontTools.misc.vector import Vector
from dot_inventory import dots
from specimens import ROOT
from audit import spans
import pathops

OUT = ROOT / "trials/2026-11-17-dot-palette"


def indices(font, name):
    glyph = font["glyf"][name]
    if glyph.numberOfContours <= 0:
        return []
    found = [
        (p, m)
        for p, m in dots(font.getGlyphSet(), name)
        if m["form"] in ("diamond", "square")
    ]
    offset = font["hmtx"][name][1] - glyph.xMin
    result = []
    start = 0
    for end in glyph.endPtsOfContours:
        ix = list(range(start, end + 1))
        start = end + 1
        pts = [glyph.coordinates[i] for i in ix]
        box = (
            min(x for x, y in pts) + offset,
            min(y for x, y in pts),
            max(x for x, y in pts) + offset,
            max(y for x, y in pts),
        )
        if any(
            max(abs(a - b) for a, b in zip(box, m["bounds"])) < 0.1 for _, m in found
        ):
            result.append(ix)
    return result


def anchor_indices(coords, ix):
    pts = [coords[i] for i in ix]
    lo = [min(p[k] for p in pts) for k in (0, 1)]
    hi = [max(p[k] for p in pts) for k in (0, 1)]
    # Cardinal diamond vertices define a stable integer origin, even when the
    # two halves differ by one grid unit. Averaging all points biases curves.
    return [
        [i for i in ix if coords[i][1 - k] in (lo[1 - k], hi[1 - k])] for k in (0, 1)
    ]


def center(coords, ai):
    return tuple(sum(coords[i][k] for i in ai[k]) / len(ai[k]) for k in (0, 1))


def normalize(font, master_name):
    originals = deepcopy(font)
    ig = originals["glyf"][master_name]
    mi = indices(originals, master_name)
    assert len(mi) == 1
    mi = mi[0]
    ma = anchor_indices(ig.coordinates, mi)
    mc = tuple(otRound(v) for v in center(ig.coordinates, ma))
    master = [(x - mc[0], y - mc[1]) for x, y in (ig.coordinates[i] for i in mi)]
    mv = expanded_variations(originals, master_name)
    mv = {
        k: [(v[i][0] - center(v, ma)[0], v[i][1] - center(v, ma)[1]) for i in mi]
        for k, v in mv.items()
    }
    report = {}
    for name in originals.getGlyphOrder():
        if name == "bullet":
            continue
        di = indices(originals, name)
        if not di:
            continue
        old = originals["glyf"][name]
        ov = expanded_variations(originals, name)
        anchors = [anchor_indices(old.coordinates, ix) for ix in di]
        centers = [
            tuple(otRound(v) for v in center(old.coordinates, ai)) for ai in anchors
        ]
        # Open only horizontal dot groups that would otherwise touch. Model
        # this clearance separately so the source's full variation survives.
        groups = []
        for j, c in enumerate(centers):
            group = next((g for g in groups if abs(centers[g[0]][1] - c[1]) < 3), None)
            if group is None:
                groups.append([j])
            else:
                group.append(j)
        groups = [sorted(g, key=lambda j: centers[j][0]) for g in groups if len(g) > 1]
        supports = set(ov) | set(mv)
        axis_values = {a.axisTag: {0.0} for a in font["fvar"].axes}
        for key in supports:
            for tag, region in key:
                axis_values[tag].add(region[1])
        locs = [
            {k: v for k, v in zip(axis_values, values) if v}
            for values in product(*[sorted(v) for v in axis_values.values()])
        ]

        def evaluated(base, variations, loc):
            result = list(base)
            for key, values in variations.items():
                scalar = supportScalar(loc, dict(key))
                if scalar:
                    result = [
                        (x + scalar * dx, y + scalar * dy)
                        for (x, y), (dx, dy) in zip(result, values)
                    ]
            return result

        shifts = []
        vertical_side = (
            (
                -1
                if name
                in ("question", "exclam", "uni2049", "exclamdbl", "uni2047", "uni2048")
                else (
                    1
                    if name in ("questiondown", "exclamdown")
                    else 2 if name == "divide" else 0
                )
            )
            if master_name == "period"
            else 0
        )
        needs_body_clearance = name in ("ldot", "Ldot") or bool(vertical_side)
        for loc in locs if groups or needs_body_clearance else [{}]:
            mp = evaluated(master, mv, loc)
            width = max(x for x, y in mp) - min(x for x, y in mp)
            op = evaluated(list(old.coordinates) + [(0, 0)] * 4, ov, loc)
            cs = [center(op, ai) for ai in anchors]
            shift = [0.0] * (2 * len(di))
            for group in groups:
                xs = [cs[j][0] for j in group]
                new = [xs[0]]
                for x in xs[1:]:
                    new.append(max(x, new[-1] + width + max(12, width * 0.08)))
                recenter = (sum(new) - sum(xs)) / len(xs)
                for j, x, n in zip(group, xs, new):
                    shift[2 * j] = n - recenter - x
            if name in ("ldot", "Ldot"):
                bodyglyph = deepcopy(old)
                bodyglyph.coordinates = GlyphCoordinates(op[:-4])
                path = pathops.Path()
                bodyglyph.draw(path.getPen(), originals["glyf"])
                # The original dot lies to the right of the l stem. Measure
                # crossings at its center; only the interval left of the dot
                # belongs to the stem, and the dot's own interval is skipped.
                for j, (cx, cy) in enumerate(cs):
                    intervals = [
                        (a, b) for a, b in spans(path, cy, 1) if (a + b) / 2 < cx - 2
                    ]
                    if intervals:
                        shift[2 * j] = max(
                            shift[2 * j],
                            max(b for a, b in intervals)
                            + 12
                            - (cx + min(x for x, y in mp)),
                        )
            if vertical_side:
                dotpoints = {i for ix in di for i in ix}
                ys = [y for i, (x, y) in enumerate(op[:-4]) if i not in dotpoints]
                for j, (cx, cy) in enumerate(cs):
                    if vertical_side < 0 or (
                        vertical_side == 2 and cy < (min(ys) + max(ys)) / 2
                    ):
                        shift[2 * j + 1] = min(
                            0, min(ys) - 12 - cy - max(y for x, y in mp)
                        )
                    else:
                        shift[2 * j + 1] = max(
                            0, max(ys) + 12 - cy - min(y for x, y in mp)
                        )
            shifts.append(Vector(shift))
        if groups or needs_body_clearance:
            model = VariationModel(locs, axisOrder=list(axis_values))
            sd = model.getDeltas(shifts)
            shift_default = shifts[locs.index({})]
            sv = {
                tuple(sorted(s.items())): v
                for s, v in zip(model.supports, sd)
                if s and any(abs(x) > 0.001 for x in v)
            }
        else:
            shift_default = [0] * (2 * len(di))
            sv = {}
        glyph = Glyph()
        glyph.coordinates = GlyphCoordinates()
        glyph.flags = bytearray()
        glyph.endPtsOfContours = []
        dot_ends = {ix[-1] for ix in di}
        body = []
        start = 0
        for end in old.endPtsOfContours:
            if end not in dot_ends:
                body.extend(range(start, end + 1))
                glyph.coordinates.extend(old.coordinates[start : end + 1])
                glyph.flags.extend(old.flags[start : end + 1])
                glyph.endPtsOfContours.append(len(glyph.coordinates) - 1)
            start = end + 1
        for j, c in enumerate(centers):
            glyph.coordinates.extend(
                [
                    (
                        otRound(x + c[0] + shift_default[2 * j]),
                        otRound(y + c[1] + shift_default[2 * j + 1]),
                    )
                    for x, y in master
                ]
            )
            glyph.flags.extend(ig.flags[i] for i in mi)
            glyph.endPtsOfContours.append(len(glyph.coordinates) - 1)
        glyph.numberOfContours = len(glyph.endPtsOfContours)
        glyph.program = Program()
        glyph.program.fromBytecode(b"")
        variations = []
        for key in supports | set(sv):
            v = ov.get(key, [(0, 0)] * (len(old.coordinates) + 4))
            m = mv.get(key, [(0, 0)] * len(master))
            ds = sv.get(key, [0] * (2 * len(di)))
            values = [v[i] for i in body]
            for j, ai in enumerate(anchors):
                cx, cy = center(v, ai)
                values.extend(
                    [
                        (otRound(x + cx + ds[2 * j]), otRound(y + cy + ds[2 * j + 1]))
                        for x, y in m
                    ]
                )
            values += v[-4:]
            if any(x or y for x, y in values):
                variations.append(TupleVariation(dict(key), values))
        glyph.recalcBounds(font["glyf"])
        advance, lsb = originals["hmtx"][name]
        font["glyf"][name] = glyph
        font["gvar"].variations[name] = variations
        font["hmtx"][name] = (advance, glyph.xMin - (old.xMin - lsb))
        report[name] = {
            "dots": len(di),
            "clearance_adjusted": bool(sv or any(shift_default)),
        }
    return {
        "master": f"existing {master_name} dot; complete variable shape; centers retained except minimum paired-dot clearance",
        "bullet": "unchanged separate master",
        "glyphs": report,
    }


def main():
    OUT.mkdir(exist_ok=True)
    recipe = json.loads((ROOT / "recipes/syntax-numeral-trial.json").read_text())
    paths = {}
    reports = {}
    for key, entry in recipe["inputs"].items():
        source = ROOT / entry["font"]
        font = TTFont(source)
        font.recalcTimestamp = False
        import hashlib

        assert hashlib.sha256(source.read_bytes()).hexdigest() == entry["sha256"]
        reports[key] = normalize(font, recipe["dots"]["master_glyphs"][key])
        path = OUT / (key + "-dot-palette-VF.ttf")
        font.save(path)
        paths[key] = str(path.relative_to(ROOT))
        print(key, len(reports[key]["glyphs"]), "dot usages normalized", flush=True)
    (OUT / "fonts.json").write_text(json.dumps(paths, indent=2) + "\n")
    (OUT / "report.json").write_text(json.dumps(reports, indent=2) + "\n")


if __name__ == "__main__":
    main()
