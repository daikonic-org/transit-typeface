"""Repair ink collisions in left-to-right proportional fonts with OpenType kerning."""

import argparse
from bisect import bisect_right
from collections import defaultdict
from functools import lru_cache
from itertools import product
import json
from math import ceil
from pathlib import Path

import pathops
from fontTools.misc.roundTools import otRound
from fontTools.otlLib.builder import buildLookup, buildPairPosGlyphs, buildValue
from fontTools.pens.boundsPen import ControlBoundsPen
from fontTools.ttLib import TTFont
from fontTools.varLib.builder import buildVarDevTable
from fontTools.varLib.models import VariationModel
from fontTools.varLib.varStore import OnlineVarStoreBuilder, VarStoreInstancer

from audit import Samples, shape_from_glyphs
from font_feature_tools import append_layout_variations
from italic_returns import raw_outline
from sans_complete_rebuild import intersects


def overlaps(left, right, *, tolerance=None):
    try:
        return intersects(left, right)
    except pathops.PathOpsError:
        # Rare near-tangencies can defeat the outline Boolean operation.
        start = ceil(max(left.bounds[1], right.bounds[1]) - 0.5)
        stop = ceil(min(left.bounds[3], right.bounds[3]) - 0.5)
        scan_edges = []
        for path in (left, right):
            pen = Samples(tolerance=tolerance)
            path.draw(pen)
            by_row = defaultdict(list)
            for a, b in pen.lines:
                lo, hi = sorted((a[1], b[1]))
                for row in range(max(start, ceil(lo - 0.5)), min(stop, ceil(hi - 0.5))):
                    by_row[row].append((a, b))
            scan_edges.append(by_row)
        for row in scan_edges[0].keys() & scan_edges[1].keys():
            first, second = (Samples.spans_from_edges(edges[row], row + 0.5, 1)
                             for edges in scan_edges)
            if any(min(r1, r2) - max(l1, l2) > 0.02
                   for l1, r1 in first for l2, r2 in second):
                return True
        return False


def axis_locations(font, *, weight_step=None):
    if "fvar" not in font:
        return [{}]
    coordinates = []
    axes = font["fvar"].axes
    if weight_step is None:
        weight_step = 12.5 if len(axes) == 1 else 25
    for axis in axes:
        tag = axis.axisTag
        knots = sorted({axis.minValue, axis.defaultValue, axis.maxValue}
                       | {i.coordinates[tag] for i in font["fvar"].instances})
        values = set(knots)
        for a, b in zip(knots, knots[1:]):
            steps = max(1, ceil((b - a) / weight_step)) if tag == "wght" else 2
            values.update(a + (b - a) * i / steps for i in range(1, steps))
        coordinates.append(sorted(values))
    return [dict(zip((axis.axisTag for axis in axes), row)) for row in product(*coordinates)]


def kern_features(font):
    """Keep each script's kerning independent, even when lookups are shared."""
    layout = font["GPOS"].table
    if "kern" in font or getattr(layout, "FeatureVariations", None):
        raise ValueError("Clearance requires non-contextual OpenType pair kerning")
    features = [record.Feature for record in layout.FeatureList.FeatureRecord
                if record.FeatureTag == "kern"]
    if not features:
        raise ValueError("The font must have an OpenType kern feature")
    return features


def lookup_rows(lookup, variations, pairs=None):
    """Find the advance lookup for a left glyph and a lower bound on its values."""
    if lookup.LookupType not in (2, 9) or lookup.LookupFlag & ~8:
        raise ValueError("Clearance supports horizontal pair lookups with optional IgnoreMarks")

    def advance(value):
        if value is None:
            return 0
        amount = getattr(value, "XAdvance", 0)
        device = getattr(value, "XAdvDevice", None)
        if device is not None:
            if device.DeltaFormat != 0x8000 or variations is None:
                raise ValueError("Clearance requires design-unit kerning adjustments")
            amount += otRound(variations[(device.StartSize << 16) | device.EndSize])
        return amount

    rows = defaultdict(list)
    for wrapped in lookup.SubTable:
        if lookup.LookupType == 9 and wrapped.ExtensionLookupType != 2:
            raise ValueError("Clearance supports pair-positioning extensions only")
        table = getattr(wrapped, "ExtSubTable", wrapped)
        if table.ValueFormat1 & ~0x44 or table.ValueFormat2:
            raise ValueError("Clearance requires kerning expressed as first-glyph advances")
        if table.Format == 1:
            for left, pair_set in zip(table.Coverage.glyphs, table.PairSet):
                if pairs is not None and left not in pairs:
                    continue
                records = {r.SecondGlyph: advance(r.Value1) for r in pair_set.PairValueRecord
                           if pairs is None or r.SecondGlyph in pairs[left]}
                if records:
                    rows[left].append((records.get, min(records.values())))
        elif table.Format == 2:
            classes = table.ClassDef2.classDefs
            advances = [[advance(item.Value1) for item in row.Class2Record]
                        for row in table.Class1Record]
            for left in table.Coverage.glyphs:
                if pairs is not None and left not in pairs:
                    continue
                row = advances[table.ClassDef1.classDefs.get(left, 0)]
                rows[left].append((lambda right, row=row, classes=classes: row[classes.get(right, 0)],
                                   min(row)))
        else:
            raise ValueError(f"Unsupported pair positioning format {table.Format}")
    return rows


def adjustment(rows, right):
    for read, _ in rows:
        value = read(right)
        if value is not None:
            return value
    return 0


def ink_extents(path, *, step=2, tolerance=.2):
    """Measure the two outside edges at the same horizontal slices for each glyph."""
    pen = Samples(tolerance=tolerance)
    path.draw(pen)
    edges = {}
    offset = min(step / 2, .5)
    for a, b in pen.lines:
        low, high = sorted((a[1], b[1]))
        for row in range(ceil((low - offset) / step), ceil((high - offset) / step)):
            y = row * step + offset
            x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            left, right = edges.get(row, (x, x))
            edges[row] = (min(left, x), max(right, x))
    return edges


def clearance(left, right, origin, first, second, padding):
    # Clear the whole facing contour. Choosing the first non-overlapping
    # placement can tuck a glyph into a pocket in a long overhang, so further
    # positive kerning can make that pair collide again during interpolation.
    needed = max((first[row][1] - second[row][0] - origin
                  for row in first.keys() & second.keys()), default=0)
    x_min, _, x_max, _ = right.bounds
    bound = left.bounds[2] - origin - x_min
    if needed > (x_max - x_min) / 2:
        needed = max(needed, bound)
    move = max(1, ceil(needed) + padding)
    while overlaps(left, right.transform(translateX=origin + move), tolerance=.2):
        move += 1
    return move


def scan(font, features, locations, padding, *, involving=None):
    """Measure all positive-advance, ink-bearing pairs at each axis location."""
    layout = font["GPOS"].table
    gdef = font["GDEF"].table
    marks = {name for name, group in gdef.GlyphClassDef.classDefs.items() if group == 3}
    names = [name for name in font.getGlyphOrder() if name not in marks and name != ".notdef"]
    routes = [tuple(sorted(set(feature.LookupListIndex))) for feature in features]
    lookup_ids = sorted({index for route in routes for index in route})
    store = getattr(gdef, "VarStore", None)
    fixes = {route: {} for route in routes}
    pair_count = 0

    for index, location in enumerate(locations):
        glyphs = font.getGlyphSet(location=location)
        bounds = {}
        widths = {}
        for name in names:
            width = otRound(glyphs[name].width)
            if width <= 0:
                continue
            pen = ControlBoundsPen(glyphs)
            glyphs[name].draw(pen)
            if pen.bounds:
                bounds[name] = pen.bounds
                widths[name] = width
        right_order = sorted(bounds, key=lambda name: bounds[name][0])
        left_edges = [bounds[name][0] for name in right_order]
        scoped_order = [name for name in right_order if involving and name in involving]
        scoped_edges = [bounds[name][0] for name in scoped_order]
        normalized = font.normalizeLocation(location) if location else {}
        variations = VarStoreInstancer(store, font["fvar"].axes, normalized) if store else None
        lookups = {number: lookup_rows(layout.LookupList.Lookup[number], variations)
                   for number in lookup_ids}

        @lru_cache(None)
        def outline(name):
            try:
                return shape_from_glyphs(glyphs, name)
            except pathops.PathOpsError:
                return raw_outline(glyphs, name)

        @lru_cache(None)
        def extents(name):
            return ink_extents(outline(name))

        for route, result in fixes.items():
            for left, (_, bottom, right_edge, top) in bounds.items():
                if involving is not None and left not in involving:
                    order, edges = scoped_order, scoped_edges
                else:
                    order, edges = right_order, left_edges
                pair_count += len(order)
                advance = widths[left]
                active = [lookups[number][left] for number in route if left in lookups[number]]
                minimum = sum(min(0, *(value for _, value in rows)) for rows in active)
                end = bisect_right(edges, right_edge - advance - minimum)
                for right in order[:end]:
                    x, y, _, high = bounds[right]
                    if high <= bottom or y >= top:
                        continue
                    origin = advance + sum(adjustment(rows, right) for rows in active)
                    if x + origin >= right_edge:
                        continue
                    first = outline(left)
                    second = outline(right)
                    if overlaps(first, second.transform(translateX=origin), tolerance=.2):
                        values = result.setdefault((left, right), [0] * len(locations))
                        values[index] = clearance(first, second, origin, extents(left), extents(right), padding)
    return fixes, pair_count


def cover_interpolation(fixes, locations):
    """Carry clearance across a cell where the required move changes rapidly."""
    axes = list(locations[0])
    if not axes:
        return
    nodes = {tuple(loc[tag] for tag in axes): index for index, loc in enumerate(locations)}
    columns = [sorted({loc[tag] for loc in locations}) for tag in axes]
    neighbors = []
    for point in nodes:
        adjacent = []
        for axis, samples in enumerate(columns):
            position = samples.index(point[axis])
            for near in samples[max(0, position - 1):position + 2]:
                adjacent.append(nodes[point[:axis] + (near,) + point[axis + 1:]])
        neighbors.append(sorted(set(adjacent)))
    for pairs in fixes.values():
        for pair, values in pairs.items():
            # Keep near-constant and light corrections local. A fast change can
            # occur where a long overhang crosses the tip of another glyph.
            pairs[pair] = [max(value, max(values[j] for j in nearby) - 2)
                           for value, nearby in zip(values, neighbors)]


def install(font, features, fixes, locations):
    variable = "fvar" in font
    tags = [axis.axisTag for axis in font["fvar"].axes] if variable else []
    gdef = font["GDEF"].table
    original = getattr(gdef, "VarStore", None)
    outer = len(original.VarData) if original else 0
    builder = OnlineVarStoreBuilder(tags) if variable else None
    if builder:
        normalized = [{tag: value for tag, value in font.normalizeLocation(loc).items() if value}
                      for loc in locations]
        builder.setModel(VariationModel(normalized, axisOrder=tags))

    lookup_list = font["GPOS"].table.LookupList
    ids = {}
    glyph_map = font.getReverseGlyphMap()
    for route, pairs in fixes.items():
        if not pairs:
            continue
        positions = {}
        for pair, values in sorted(pairs.items()):
            data = {"XAdvance": values[0]}
            if builder and len(set(values)) > 1:
                base, variation = builder.storeMasters(values, round=otRound)
                data = {"XAdvance": base, "XAdvDevice": buildVarDevTable((outer << 16) + variation)}
            positions[pair] = (buildValue(data), None)
        subtables = buildPairPosGlyphs(positions, glyph_map)
        ids[route] = len(lookup_list.Lookup)
        lookup_list.Lookup.append(buildLookup(subtables, flags=8, table="GPOS", extension=True))
    lookup_list.LookupCount = len(lookup_list.Lookup)
    for feature in features:
        route = tuple(sorted(set(feature.LookupListIndex)))
        if route in ids:
            feature.LookupListIndex.append(ids[route])
            feature.LookupCount = len(feature.LookupListIndex)

    if builder:
        append_layout_variations(font, builder.finish())


def max_pair_adjustments(fixes):
    maxima = {}
    for pairs in fixes.values():
        for pair, values in pairs.items():
            maxima[pair] = max(maxima.get(pair, 0), max(values))
    return {" ".join(pair): amount for pair, amount in sorted(maxima.items())}


def repair_kerning(font, *, locations=None, padding=None, involving=None):
    """Add only the clearance needed by colliding pairs, without moving any outlines."""
    if locations is None:
        locations = axis_locations(font)
    features = kern_features(font)
    if padding is None:
        padding = max(1, otRound(font["head"].unitsPerEm * .004))
    fixes, checked = scan(font, features, locations, padding, involving=involving)
    if any(fixes.values()):
        cover_interpolation(fixes, locations)
        install(font, features, fixes, locations)
    return {
        "locations": locations, "comparisons": checked, "clearance_padding": padding,
        "corrected_pairs": max_pair_adjustments(fixes),
    }


def pair_clearances(font, features, locations, pairs, limit):
    """Measure the closest facing edges of selected pairs with current GPOS applied."""
    by_left = defaultdict(set)
    for left, right in pairs:
        by_left[left].add(right)
    layout = font["GPOS"].table.LookupList.Lookup
    store = getattr(font["GDEF"].table, "VarStore", None)
    routes = {tuple(sorted(set(feature.LookupListIndex))) for feature in features}
    lookup_ids = {index for route in routes for index in route}
    for index, location in enumerate(locations):
        glyphs = font.getGlyphSet(location=location)
        variations = (VarStoreInstancer(store, font["fvar"].axes, font.normalizeLocation(location))
                      if store else None)
        lookups = {number: lookup_rows(layout[number], variations, by_left) for number in lookup_ids}

        @lru_cache(None)
        def outline(name):
            try:
                return shape_from_glyphs(glyphs, name)
            except pathops.PathOpsError:
                return raw_outline(glyphs, name)

        @lru_cache(None)
        def extents(name):
            return ink_extents(outline(name), step=.5, tolerance=.045)

        for route in sorted(routes):
            for left, right in pairs:
                origin = otRound(glyphs[left].width) + sum(
                    adjustment(lookups[number].get(left, ()), right) for number in route
                )
                if origin + outline(right).bounds[0] - outline(left).bounds[2] >= limit:
                    continue
                first, second = extents(left), extents(right)
                gap = min((origin + second[row][0] - first[row][1]
                           for row in first.keys() & second.keys()), default=float("inf"))
                if gap < limit:
                    yield index, route, (left, right), gap


def repair_near_contacts(font, pairs, *, locations=None, trigger=1, target=4):
    """Open reviewed sub-unit gaps after the collision repair has been installed."""
    if not 0 < trigger <= target:
        raise ValueError("Expected a positive trigger at or below the target")
    pairs = sorted(set(pairs))
    if locations is None:
        locations = axis_locations(font, weight_step=12.5)
    features = kern_features(font)
    fixes = defaultdict(dict)
    for index, route, pair, gap in pair_clearances(font, features, locations, pairs, trigger):
        if gap >= 0:
            values = fixes[route].setdefault(pair, [0] * len(locations))
            values[index] = ceil(target - gap)
    if fixes:
        install(font, features, fixes, locations)
    return {
        "trigger": trigger,
        "target": target,
        "locations_checked": len(locations),
        "candidate_pairs": [" ".join(pair) for pair in pairs],
        "corrected_pairs": max_pair_adjustments(fixes),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--involving", action="append", metavar="GLYPH",
                        help="review pairs involving this glyph, on either side")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("choose a separate output font")
    with TTFont(args.source, recalcTimestamp=False) as font:
        report = repair_kerning(font, involving=set(args.involving) if args.involving else None)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        font.save(args.output)
    args.output.with_suffix(".kerning.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f'{report["comparisons"]:,} pair checks, {len(report["corrected_pairs"])} pairs adjusted')


if __name__ == "__main__":
    main()
