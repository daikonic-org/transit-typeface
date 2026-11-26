"""Construct the upright Code alphabet from compatible Sans outlines."""

from copy import deepcopy
from unicodedata import category

from fontTools.misc.roundTools import otRound
from fontTools.misc.transform import Transform
from fontTools.subset import Options, Subsetter
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.varLib.instancer import instantiateVariableFont

from audit import shape_from_glyphs
from sans_baseline_trial import clear_hints
from scaling_study import vertical_stem
from system_width import stem_compensation


def glyph_categories(font):
    groups = {name: set() for name in font.getGlyphOrder()}
    for cp, name in font.getBestCmap().items():
        groups[name].add(category(chr(cp)))
    for name in groups:
        if not groups[name]:
            groups[name].update(groups.get(name.split(".")[0], ()))
    return groups


def outline_bounds(glyph, glyf):
    coordinates = glyph.getCoordinates(glyf)[0]
    return coordinates.calcBounds() if coordinates else (0, 0, 0, 0)


def horizontal_mirror(glyph):
    if glyph.isComposite() and len(glyph.components) == 1:
        donor, transform = glyph.components[0].getComponentInfo()
        if transform[:4] == (-1, 0, 0, 1) and transform[5] == 0:
            return donor, transform[4]
    return None


def center(bounds):
    left, bottom, right, top = bounds
    return (left + right) / 2, (bottom + top) / 2


def letter_projection(name, bounds, groups, source_cap, source_x, config):
    lower = "Ll" in groups[name]
    cap_scale = config["cap_height"] / source_cap
    low_scale = config["x_height"] / source_x
    upper_scale = (config["cap_height"] - config["x_height"]) / (source_cap - source_x)
    nominal_x = config["lowercase_x_scale"] if lower else 1

    def project(x, y):
        if not lower:
            height = y * cap_scale
        elif bounds[3] > source_x * 1.12 and y > source_x:
            height = config["x_height"] + (y - source_x) * upper_scale
        else:
            height = y * low_scale
        return x * nominal_x, height + config["baseline"]

    return project


def narrow_for_cell(glyph, limit, stem):
    """Apply the shared width-axis correction at the ratio the cell can hold."""
    left, _, right, _ = glyph.coordinates.calcBounds()
    if right - left <= limit:
        return 1
    corrections = stem_compensation(glyph, stem)
    coordinates = list(zip(glyph.coordinates, corrections, strict=True))

    def columns(factor):
        return [x * factor + dx * (factor - 1) for (x, _), (dx, _) in coordinates]

    narrow, normal = 0, 1
    for _ in range(20):
        factor = (narrow + normal) / 2
        xs = columns(factor)
        if otRound(max(xs)) - otRound(min(xs)) <= limit:
            narrow = factor
        else:
            normal = factor

    glyph.coordinates = GlyphCoordinates((otRound(x), y) for x, ((_, y), _) in
                                          zip(columns(narrow), coordinates, strict=True))
    return narrow


def map_attachment_anchors(font, projections):
    def move(anchor, name):
        if anchor is not None:
            anchor.XCoordinate, anchor.YCoordinate = map(
                otRound, projections[name](anchor.XCoordinate, anchor.YCoordinate)
            )

    for lookup in font["GPOS"].table.LookupList.Lookup:
        for wrapped in lookup.SubTable:
            table = getattr(wrapped, "ExtSubTable", wrapped)
            if hasattr(table, "MarkArray"):
                for name, record in zip(table.MarkCoverage.glyphs, table.MarkArray.MarkRecord, strict=True):
                    move(record.MarkAnchor, name)
            if hasattr(table, "BaseArray"):
                for name, record in zip(table.BaseCoverage.glyphs, table.BaseArray.BaseRecord, strict=True):
                    for anchor in record.BaseAnchor:
                        move(anchor, name)
            if hasattr(table, "LigatureArray"):
                for name, record in zip(table.LigatureCoverage.glyphs,
                                        table.LigatureArray.LigatureAttach, strict=True):
                    for component in record.ComponentRecord:
                        for anchor in component.LigatureAnchor:
                            move(anchor, name)
            if hasattr(table, "Mark1Array"):
                for name, record in zip(table.Mark1Coverage.glyphs, table.Mark1Array.MarkRecord, strict=True):
                    move(record.MarkAnchor, name)
                for name, record in zip(table.Mark2Coverage.glyphs, table.Mark2Array.Mark2Record, strict=True):
                    for anchor in record.Mark2Anchor:
                        move(anchor, name)


def ink_columns(glyph, factor, stem_scale, stem, translate=0):
    """Scale horizontal positions while compensating the stroke weight."""
    correction = stem_compensation(glyph, stem)
    return [x * factor + translate + dx * (factor - stem_scale)
            for (x, _), (dx, _) in zip(glyph.coordinates, correction, strict=True)]


def scale_ink_width(font, scales, stem):
    """Widen outlines using the shared stroke correction, keeping components reusable."""
    glyf = font["glyf"]
    metrics = font["hmtx"].metrics
    centers = {name: center(outline_bounds(glyf[name], glyf)) for name in font.getGlyphOrder()}
    transforms = {}

    def draw(name):
        if name in transforms:
            return
        glyph = glyf[name]
        advance, _ = metrics[name]
        factor, stem_width_scale = scales.get(name, (1, 1))
        transform = Transform(factor, 0, 0, 1, (1 - factor) * advance / 2, 0)
        if glyph.isComposite():
            mirror = horizontal_mirror(glyph)
            for part in glyph.components:
                donor, matrix = part.getComponentInfo()
                draw(donor)
                if (mirror and advance == metrics[donor][0] == mirror[1]
                        and (factor, stem_width_scale) == scales.get(donor, (1, 1))):
                    continue
                component = Transform(*matrix)
                desired_x, _ = transform.transformPoint(component.transformPoint(centers[donor]))
                current_x, _ = component.transformPoint(center(outline_bounds(glyf[donor], glyf)))
                part.x += otRound(desired_x - current_x)
        elif glyph.numberOfContours and (factor != 1 or stem_width_scale != 1):
            xs = ink_columns(glyph, factor, stem_width_scale, stem, transform.dx)
            shift = centers[name][0] - (min(xs) + max(xs)) / 2
            glyph.coordinates = GlyphCoordinates((otRound(x + shift), y)
                                                  for x, (_, y) in zip(xs, glyph.coordinates, strict=True))
            transform = Transform(factor, 0, 0, 1, transform.dx + shift, 0)

        glyph.recalcBounds(glyf)
        metrics[name] = advance, getattr(glyph, "xMin", 0)
        transforms[name] = transform

    for name in font.getGlyphOrder():
        draw(name)

    def project(transform):
        return lambda x, y: transform.transformPoint((x, y))

    map_attachment_anchors(font, {name: project(transform) for name, transform in transforms.items()})


def width_class_scales(masters, recipe):
    """Group Regular lowercase outlines and share their factors across weights."""
    config = recipe["alphabet_review"]
    regular = masters[400]
    glyph_sets = {weight: font.getGlyphSet() for weight, font in masters.items()}
    classes = config["width_classes"]
    categories = glyph_categories(regular)
    cmap = regular.getBestCmap()
    reserved = {cmap[ord(char)] for char in recipe["code_specific_characters"] if ord(char) in cmap}
    reserved.update(recipe["constructed_forms"])
    reserved.difference_update(cmap[ord(char)] for char in config["width_class_preview"])
    glyf = regular["glyf"]
    assignments = {}

    def assign(name):
        if name not in assignments:
            glyph = glyf[name]
            primary = glyph.components[0].glyphName if glyph.isComposite() else None
            group = None
            if name not in reserved and regular["hmtx"][name][0] and "Ll" in categories[name]:
                if primary is not None and (primary in reserved or "Ll" in categories[primary]):
                    group = assign(primary)
                else:
                    left, _, right, _ = outline_bounds(glyph, glyf)
                    width = right - left
                    curved = glyph.numberOfContours > 0 and any(not flags & 1 for flags in glyph.flags)
                    group = next(row["name"] for row in classes
                                 if row.get("at_least", 0) <= width
                                 and (row["below"] is None or width < row["below"])
                                 and (not row.get("curved") or curved))
            assignments[name] = group
        return assignments[name]

    for name in regular.getGlyphOrder():
        assign(name)

    cohort = {chr(code): name for code, name in cmap.items()
              if code < 128 and chr(code).islower()}
    default_target = config["cell"] - 2 * config["ink_side_margin"]
    stems = {weight: vertical_stem(shape_from_glyphs(glyphs, "n"), .4)
             for weight, glyphs in glyph_sets.items()}
    report = {}
    for row in classes:
        group = row["name"]
        target = row.get("ink_target", default_target)
        stem_width_scale = row.get("stem_width_scale", config["stem_width_scale"])
        stem_growth = stem_width_scale - 1
        members = {char: name for char, name in cohort.items() if assignments[name] == group}
        widths = []
        for weight, font in masters.items():
            for name in members.values():
                left, _, right, _ = outline_bounds(font["glyf"][name], font["glyf"])
                widths.append((right - left, stems[weight]))
        room = min(
            ((target - width - stem * stem_growth) / max(1, width - stem) for width, stem in widths),
            default=0,
        )
        report[group] = {"factor": 1 + room * row["gap_share"], "stem_width_scale": stem_width_scale,
                         "sample": "".join(sorted(members))}
    scales = {name: (report[group]["factor"], report[group]["stem_width_scale"])
              for name, group in assignments.items() if group is not None and report[group]["sample"]}
    deferred = "".join(sorted(char for char, name in cohort.items() if assignments[name] is None))
    return scales, stems, {"classes": report, "deferred": deferred}


def review_layout(font):
    """Carry over composition and mark attachment for the alphabet proof."""
    options = Options(layout_features=["ccmp", "mark", "mkmk"], notdef_outline=True,
                      glyph_names=True, retain_gids=True, name_IDs=["*"])
    subsetter = Subsetter(options=options)
    subsetter.populate(glyphs=font.getGlyphOrder())
    subsetter.subset(font)


def sample_sans_weight(source, weight):
    axis, = source["fvar"].axes
    light = axis.minValue
    if weight >= light:
        return instantiateVariableFont(source, {axis.axisTag: weight}, static=True)

    next_weight = min(instance.coordinates[axis.axisTag] for instance in source["fvar"].instances
                      if instance.coordinates[axis.axisTag] > light)
    distance = light - weight
    if distance > next_weight - light:
        raise ValueError("The requested Sans weight extends beyond the first weight interval")
    ramp = instantiateVariableFont(source, {axis.axisTag: (light, light, next_weight)})

    # Rebase at Light and reverse the slope toward the next master. Instancing
    # the reflected ramp carries outline, component, metric and anchor deltas
    # together through the same extrapolation.
    linear_support = (0, 1, 1)
    for variations in ramp["gvar"].variations.values():
        for variation in variations:
            assert variation.axes == {axis.axisTag: linear_support}
            variation.scaleDeltas(-1)
    for tag in ("HVAR", "VVAR", "MVAR", "GDEF"):
        store = getattr(ramp[tag].table, "VarStore", None) if tag in ramp else None
        if store is None:
            continue
        for region in store.VarRegionList.Region:
            support, = region.VarRegionAxis
            assert (support.StartCoord, support.PeakCoord, support.EndCoord) == linear_support
        for data in store.VarData:
            data.Item = [[-delta for delta in row] for row in data.Item]
    return instantiateVariableFont(ramp, {axis.axisTag: light + distance}, static=True)


def build_master(source, sans_weight, code_weight, config):
    font = sample_sans_weight(source, sans_weight)
    review_layout(font)
    glyf = font["glyf"]
    original = deepcopy(glyf)
    stem = vertical_stem(shape_from_glyphs(font.getGlyphSet(), "n"), .4)
    old_metrics = font["hmtx"].metrics.copy()
    groups = glyph_categories(font)
    source_cap, source_x = font["OS/2"].sCapHeight, font["OS/2"].sxHeight
    placements = {}
    projections = {
        name: letter_projection(name, outline_bounds(original[name], original), groups,
                                source_cap, source_x, config)
        for name in font.getGlyphOrder()
    }
    cell = config["cell"]
    ink_limit = cell - 2 * config["side_margin"]

    def advance(name):
        return cell if old_metrics[name][0] else 0

    def draw(name):
        if name in placements:
            return
        glyph = glyf[name]
        old = original[name]
        project = projections[name]

        mirrored = horizontal_mirror(old)
        if mirrored and advance(name) == advance(mirrored[0]) == cell:
            base, old_axis = mirrored
            draw(base)
            part = glyph.components[0]
            part.x, part.y = cell, 0
            base_project = placements[base]

            def project(x, y):
                px, py = base_project(old_axis - x, y)
                return cell - px, py
        elif old.isComposite():
            for part in old.components:
                draw(part.glyphName)
            base, transform = old.components[0].getComponentInfo()
            if transform[:4] == (1, 0, 0, 1) and advance(base):
                # Attach the accent to the already-constructed base. This
                # preserves the spacing origin of the plain letter.
                base_x, base_y = transform[4:]
                base_project = placements[base]

                def project(x, y):
                    px, py = base_project(x - base_x, y - base_y)
                    return px + base_x, py + base_y

            for old_part, part in zip(old.components, glyph.components, strict=True):
                donor, matrix = old_part.getComponentInfo()
                original_center = Transform(*matrix).transformPoint(center(outline_bounds(original[donor], original)))
                desired = project(*original_center)
                linear = Transform(*matrix[:4], 0, 0)
                revised_center = linear.transformPoint(center(outline_bounds(glyf[donor], glyf)))
                part.x, part.y = map(otRound, (desired[0] - revised_center[0], desired[1] - revised_center[1]))
        elif glyph.numberOfContours:
            glyph.coordinates = GlyphCoordinates(tuple(map(otRound, project(x, y)))
                                                  for x, y in old.coordinates)
            if advance(name):
                ratio = narrow_for_cell(glyph, ink_limit, stem)
                dx = otRound(cell / 2 - center(outline_bounds(glyph, glyf))[0])
                glyph.coordinates.translate((dx, 0))
                nominal = project

                def project(x, y):
                    px, py = nominal(x, y)
                    return px * ratio + dx, py

        clear_hints(glyph)
        glyph.recalcBounds(glyf)
        font["hmtx"][name] = (advance(name), getattr(glyph, "xMin", 0))
        placements[name] = project

    for name in font.getGlyphOrder():
        draw(name)

    map_attachment_anchors(font, placements)
    metrics = font["OS/2"]
    metrics.usWeightClass = code_weight
    metrics.sCapHeight = config["baseline"] + config["cap_height"]
    metrics.sxHeight = config["baseline"] + config["x_height"]
    metrics.xAvgCharWidth = cell
    metrics.fsSelection &= ~(1 << 5 | 1 << 6)
    if code_weight == 400:
        metrics.fsSelection |= 1 << 6
    font["head"].unitsPerEm = config["units_per_em"]
    font["post"].isFixedPitch = 1
    font.recalcTimestamp = False
    return font
