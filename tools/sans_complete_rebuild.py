"""Rebuild every upright Sans variation from its current Regular geometry."""

from collections import defaultdict
from functools import lru_cache
from itertools import combinations, pairwise
from math import ceil
from typing import NamedTuple
from unicodedata import decomposition

import pathops
from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

from audit import shape_from_glyphs, spans
from derive_weights import topology
from font_feature_tools import expanded_variations, feature_subtables
from sans_aperture import apertures_for
from sans_baseline_trial import build_variations
from sans_component_relationships import DELIMITER_PAIRS, LETTER_PAIRS
from sans_ligature_construction import LIGATURES
from sans_direct_weight import direct_points, separation, signed_gap
from sans_weight_refinement import fitting_context, samples

DERIVED = set(LIGATURES) | {target for _, target in (*DELIMITER_PAIRS, *LETTER_PAIRS)}


def geometry_exclusions(font, settings):
    """Union the axis and transformation exclusions of each named class."""
    transforms = {"aperture_clearance", "contour_clearance", "component_placement"}
    cmap = font.getBestCmap()
    exclusions = defaultdict(set)
    for label, rules in settings["geometry_classes"].items():
        excluded_axes = set(rules.get("exclude_axes", ()))
        excluded_transforms = set(rules.get("exclude_transforms", ()))
        if excluded_axes - {"wght"} or excluded_transforms - transforms:
            raise ValueError(f"Unsupported geometry exclusions in {label}")
        names = set(rules.get("glyphs", ()))
        names.update(cmap[int(codepoint, 16)] for codepoint in rules.get("codepoints", ()))
        for name in names:
            glyph = font["glyf"][name]
            if "wght" in excluded_axes and (glyph.numberOfContours <= 0 or name in DERIVED):
                raise ValueError(f"Weight axis exclusions require standalone outlines: {name}")
            exclusions[name].update(excluded_axes | excluded_transforms)
    return exclusions


def miniature_scales(font, regular):
    """Measure miniature growth against its encoded or substituted parent."""
    cmap = font.getBestCmap()
    sources = {}
    for scalar, name in cmap.items():
        mapping = decomposition(chr(scalar)).split()
        if len(mapping) == 2 and mapping[0] in {"<sub>", "<super>"}:
            source = cmap.get(int(mapping[1], 16))
            if source is not None:
                sources[name] = source
    for tag, table in feature_subtables(font):
        if tag in {"subs", "sups", "sinf", "numr", "dnom"}:
            for source, target in getattr(table, "mapping", {}).items():
                if isinstance(target, str):
                    sources.setdefault(target, source)

    @lru_cache
    def height(name):
        _, bottom, _, top = shape_from_glyphs(regular, name).bounds
        return top - bottom

    scales = {}
    for name, full_size in sources.items():
        glyph = font["glyf"][name]
        # A scaled component already scales the variation of the full-size part.
        if glyph.numberOfContours > 0:
            full_height, scaled_height = height(full_size), height(name)
            if 0 < scaled_height < full_height:
                scales[name] = (scaled_height / full_height, full_size)
    return scales


def rebuild_drawn_outlines(font):
    settings, anchor, stems, weights, model, named, regular = fitting_context(font)
    variations = font["gvar"].variations
    scales = miniature_scales(font, regular)
    exclusions = geometry_exclusions(font, settings)
    weight_changes = [stems[str(weight)] - stems[str(anchor)] for weight in weights]
    maximum_change = max(map(abs, weight_changes))
    report = {}
    for name in font.getGlyphOrder():
        glyph = font["glyf"][name]
        if glyph.numberOfContours <= 0:
            continue
        if name in DERIVED:
            report[name] = {"method": "derived from regenerated glyphs"}
            continue
        advance = named[0][name].width
        scale, full_size = scales.get(name, (1, None))
        excluded = exclusions[name]
        if "wght" in excluded:
            scale = 0
        apertures = ()
        if scale and "aperture_clearance" not in excluded:
            apertures = apertures_for(glyph, 2 * maximum_change * scale)
        masters = [
            direct_points(glyph, scale * change,
                          settings["horizontal_growth_ratio"], settings["miter_limit"],
                          (instance[name].width - advance) / 2, apertures=apertures,
                          contour_gaps="contour_clearance" not in excluded)
            for change, instance in zip(weight_changes, named)
        ]
        variations[name] = build_variations(model, masters, expanded_variations(font, name))
        report[name] = {"method": "direct point movement"}
        if excluded:
            report[name]["geometry_exclusions"] = sorted(excluded)
        if full_size is not None:
            report[name].update(growth_scale=scale, full_size=full_size)
    return report


def direct_outline_findings(font, report):
    instances = samples(font)
    regular = font.getGlyphSet()
    for name, row in report.items():
        if row["method"] != "direct point movement":
            continue
        original = topology(shape_from_glyphs(regular, name))
        outlines = {weight: shape_from_glyphs(gs, name) for weight, gs in instances.items()}
        row["topology_changes"] = [w for w, path in outlines.items() if topology(path) != original]
        areas = [p.area for p in outlines.values()]
        row["ink_loss"] = any(b < a - 0.01 for a, b in zip(areas, areas[1:]))
    return report


def intersects(first, second):
    if separation(first.bounds, second.bounds):
        return False
    return pathops.op(first, second, pathops.PathOp.INTERSECTION).area > 0.01


def joins(first, second, *, contact=False):
    if intersects(first, second):
        return True
    if not contact:
        return False
    nearby = separation(first.bounds, second.bounds)
    if nearby and nearby[2] >= 0.25:
        return False
    border = pathops.Path(first)
    border.stroke(0.5, pathops.LineCap.BUTT_CAP, pathops.LineJoin.MITER_JOIN, 2.5)
    border.convertConicsToQuads()
    return intersects(border, second)


@lru_cache
def candidate_offsets(reach):
    return sorted(
        ((x, y) for x in range(-reach, reach + 1) for y in range(-reach, reach + 1)
         if 0 < x*x + y*y <= reach*reach),
        key=lambda point: (point[0]**2 + point[1]**2, abs(point[1]), point),
    )


def move_shape(shape, offset):
    return shape.transform(translateX=offset[0], translateY=offset[1])


def component_offsets(shapes, relationships, reach):
    offsets = [[0, 0] for _ in shapes]
    groups = list(range(len(shapes)))

    def move(index, shift):
        offsets[index][0] += shift[0]
        offsets[index][1] += shift[1]
        shapes[index] = move_shape(shapes[index], shift)

    for (i, j), (_, joined) in relationships.items():
        if not joined:
            continue
        if not intersects(shapes[i], shapes[j]):
            shift = next((offset for offset in candidate_offsets(reach)
                          if intersects(shapes[i], move_shape(shapes[j], offset))), None)
            if shift:
                move(j, shift)
        group = min(groups[i], groups[j])
        groups = [group if old in (groups[i], groups[j]) else old for old in groups]

    for (i, j), (gap, joined) in relationships.items():
        if joined or groups[i] == groups[j]:
            continue
        if groups[i] > groups[j]:
            i, j = j, i
            if gap:
                axis, sign, minimum = gap
                gap = axis, -sign, minimum
        if gap:
            axis, sign, minimum = gap
            missing = minimum - signed_gap(shapes[i].bounds, shapes[j].bounds, axis, sign)
            shift = [0, 0]
            shift[axis] = sign * max(0, ceil(missing - 1e-4))
        elif intersects(shapes[i], shapes[j]):
            shift = next((offset for offset in candidate_offsets(reach)
                          if not intersects(shapes[i], move_shape(shapes[j], offset))), (0, 0))
        else:
            continue
        if any(shift):
            for index, group in enumerate(groups):
                if group == groups[j]:
                    move(index, shift)
    return offsets


def occupied_gap(bounds, i, j, axis):
    """A third component can anchor both pieces of a row of marks."""
    low, high = sorted((bounds[i], bounds[j]), key=lambda box: box[axis])
    return any(
        k not in (i, j) and box[axis] < low[axis + 2] and box[axis + 2] > high[axis]
        for k, box in enumerate(bounds)
    )


def assembly_center(shapes, axis):
    low = min(shape.bounds[axis] for shape in shapes)
    high = max(shape.bounds[axis + 2] for shape in shapes)
    return (low + high) / 2


def component_centers(shapes, axis):
    return [(shape.bounds[axis] + shape.bounds[axis + 2]) / 2 for shape in shapes]


def centering_axis(parts, shapes, relationships):
    """Find the arrangement axis for separate or regularly repeated parts."""
    if any(shape.area == 0 for shape in shapes):
        return None
    if any(joined for _, joined in relationships.values()):
        return None
    intervals = sorted((shape.bounds[0], shape.bounds[2]) for shape in shapes)
    if all(first[1] < second[0] for first, second in zip(intervals, intervals[1:])):
        return 0
    forms = {(name, transform[:4]) for name, transform in
             (part.getComponentInfo() for part in parts)}
    if len(forms) == 1:
        x, y = (component_centers(shapes, axis) for axis in (0, 1))
        if max(y) - min(y) <= 1 < max(x) - min(x):
            return 0
        if max(x) - min(x) <= 1 < max(y) - min(y):
            return 1
    return None


def recenter_assembly(shapes, offsets, axis, target):
    shift = otRound(target - assembly_center(shapes, axis))
    if not shift:
        return
    delta = [0, 0]
    delta[axis] = shift
    for i, offset in enumerate(offsets):
        offset[axis] += shift
        shapes[i] = move_shape(shapes[i], delta)


def terminal_centers(shape, axis, side, depth=4):
    centers = []
    for contour in shape.contours:
        if not contour.clockwise:
            continue
        low, high = contour.bounds[axis], contour.bounds[axis + 2]
        inset = min(depth, (high - low) / 2)
        probe = low + inset if side < 0 else high - inset
        centers.extend((a + b) / 2 for a, b in spans(contour, probe, axis))
    return sorted(centers)


class Attachment(NamedTuple):
    body: int
    axis: int
    side: int
    index: int
    terminal_count: int
    bias: float
    cross_from_body_center: float
    row_center: float


def box_center(bounds, axis):
    return (bounds[axis] + bounds[axis + 2]) / 2


def component_attachments(shapes):
    """Match a smaller separate shape to a facing terminal in Regular."""
    boxes = [shape.bounds for shape in shapes]
    areas = [shape.area for shape in shapes]
    result = {}
    for i, bounds in enumerate(boxes):
        if not areas[i]:
            continue
        options = []
        for j, body in enumerate(boxes):
            if areas[j] <= areas[i]:
                continue
            gap = separation(body, bounds)
            if gap is None:
                continue
            axis, side, clearance = gap
            cross = 1 - axis
            center = box_center(bounds, cross)
            extent = bounds[cross + 2] - bounds[cross]
            terminals = terminal_centers(shapes[j], axis, side)
            for index, terminal in enumerate(terminals):
                bias = center - terminal
                if abs(bias) <= extent / 4:
                    attachment = Attachment(
                        j, axis, side, index, len(terminals), bias,
                        center - box_center(body, cross), box_center(bounds, axis),
                    )
                    options.append((clearance, abs(bias), attachment))
        if options:
            _, _, result[i] = min(options)
    return dict(sorted(result.items(), key=lambda item: areas[item[0]], reverse=True))


def facing_terminal(shape, attachment):
    axis, side = attachment.axis, attachment.side
    for depth in (4, 8, 16, 32):
        centers = terminal_centers(shape, axis, side, depth)
        if len(centers) == attachment.terminal_count:
            return centers[attachment.index]
    guess = box_center(shape.bounds, 1 - axis) + attachment.cross_from_body_center - attachment.bias
    centers = terminal_centers(shape, axis, side)
    return min(centers, key=lambda x: abs(x - guess)) if centers else None


def align_attachments(shapes, offsets, alignments, *, advance_shift, reset_row=False):
    # A body is larger than its attached part, so attachments can form a chain.
    for i, attachment in alignments.items():
        body = shapes[attachment.body]
        axis = attachment.axis
        cross = 1 - axis
        terminal = facing_terminal(body, attachment)
        if terminal is not None:
            shift = otRound(terminal + attachment.bias - box_center(shapes[i].bounds, cross))
            change_offset(shapes, offsets, i, cross, shift)
        if reset_row:
            target = attachment.row_center + (advance_shift if axis == 0 else 0)
            shift = otRound(target - box_center(shapes[i].bounds, axis))
            change_offset(shapes, offsets, i, axis, shift)


def change_offset(shapes, offsets, index, axis, shift):
    if shift:
        offsets[index][axis] += shift
        delta = (shift, 0) if axis == 0 else (0, shift)
        shapes[index] = move_shape(shapes[index], delta)


def regular_repeat(parts, shapes, axis, relationships):
    """Read equal spacing from a complete row of the same component form."""
    forms = {(name, transform[:4]) for name, transform in
             (part.getComponentInfo() for part in parts)}
    if axis is None or len(parts) < 3 or len(forms) != 1:
        return None
    centers = component_centers(shapes, axis)
    order = sorted(range(len(parts)), key=centers.__getitem__)
    gaps = [relationships[tuple(sorted(pair))][0] for pair in pairwise(order)]
    sizes = [gap[2] for gap in gaps if gap and gap[0] == axis]
    if len(sizes) == len(gaps) and max(sizes) - min(sizes) <= 1:
        return order, max(sizes)
    return None


def space_repeat(shapes, offsets, axis, repeat):
    order, minimum = repeat
    centers = component_centers(shapes, axis)
    width = max(shapes[i].bounds[axis + 2] - shapes[i].bounds[axis] for i in order)
    pitch = max(width + minimum, (centers[order[-1]] - centers[order[0]]) / (len(order) - 1))
    for rank, index in enumerate(order):
        desired = centers[order[0]] + rank * pitch
        change_offset(shapes, offsets, index, axis, otRound(desired - centers[index]))


def repair_components(font, *, ligatures=False):
    """Keep component contact and separation that are present in Regular."""
    settings, anchor, stems, weights, model, named, _ = fitting_context(font)
    glyf = font["glyf"]
    exclusions = geometry_exclusions(font, settings)
    glyphs = [name for name in font.getGlyphOrder()
              if "component_placement" not in exclusions[name] and glyf[name].isComposite() and len(glyf[name].components) > 1
              and (name in LIGATURES) == ligatures]
    glyphs.sort(key=lambda name: glyf[name].getCompositeMaxpValues(glyf).maxComponentDepth)
    result, unresolved, centered, attached = {}, {}, {}, {}
    for name in glyphs:
        glyph = glyf[name]
        if any(not hasattr(part, "x") for part in glyph.components):
            continue
        positions, weight_offsets, failures = [], {}, {}
        relationships = {}
        center_axis = None
        alignments = {}
        repeat = None
        for weight, instance in zip(weights, named):
            item = instance[name]
            outline, origin = item._getGlyphAndOffset()
            parts = outline.components
            shapes = []
            for part in parts:
                base, transform = part.getComponentInfo()
                # Component drawings use their stored origin, without top-level LSB normalization.
                with instance.pushDepth():
                    shapes.append(shape_from_glyphs(instance, base).transform(*transform))
            offsets = [[0, 0] for _ in parts]
            if weight == anchor:
                bounds = [shape.bounds for shape in shapes]
                alignments = component_attachments(shapes)
                if alignments:
                    attached[name] = {str(i): parts[attachment.body].glyphName
                                      for i, attachment in alignments.items()}
                attachment_pairs = {tuple(sorted((i, attachment.body))): i
                                    for i, attachment in alignments.items()}
                regular_advance = item.width
                for i, j in combinations(range(len(parts)), 2):
                    if shapes[i].area == 0 or shapes[j].area == 0:
                        continue
                    gap = separation(bounds[i], bounds[j])
                    joined = gap is None and joins(shapes[i], shapes[j], contact=True)
                    if gap and (i, j) in attachment_pairs:
                        axis, sign, clearance = gap
                        part = bounds[attachment_pairs[i, j]]
                        cross = 1 - axis
                        gap = axis, sign, min(clearance, part[cross + 2] - part[cross])
                    if gap and (i, j) not in attachment_pairs and (
                        i in alignments or j in alignments or occupied_gap(bounds, i, j, gap[0])
                    ):
                        # Keep visible clearance while respecting the shared body's anchors.
                        gap = gap[0], gap[1], min(gap[2], 1)
                    relationships[i, j] = gap, joined
                center_axis = centering_axis(parts, shapes, relationships)
                if center_axis == 1 and any(box[1] <= 0 <= box[3] for box in bounds):
                    # The bottom repeat is aligned to the baseline. Allow the
                    # weight change to use the available clearance in the stack.
                    center_axis = None
                    relationships = {pair: ((gap[0], gap[1], min(gap[2], 1)), joined)
                                     if gap and gap[0] == 1 else (gap, joined)
                                     for pair, (gap, joined) in relationships.items()}
                # Center self-contained assemblies with an internal body.
                # A reusable spacing glyph keeps its own placement and bearings.
                bodies = {part.body for part in alignments.values()}
                if len(bodies) == 1 and len(alignments) == len(parts) - 1:
                    body, = bodies
                    body_width = instance[parts[body].glyphName].width
                    if body_width != item.width:
                        center_axis = 0
                if center_axis is not None:
                    center = assembly_center(shapes, center_axis)
                    if center_axis == 0:
                        center += origin - item.width / 2
                    centered[name] = "x" if center_axis == 0 else "y"
                    repeat = regular_repeat(parts, shapes, center_axis, relationships)
            else:
                reach = ceil(abs(stems[str(weight)] - stems[str(anchor)]) * settings["miter_limit"])
                offsets = [[0, 0] for _ in parts]
                advance_shift = (item.width - regular_advance) / 2
                align_attachments(shapes, offsets, alignments, advance_shift=advance_shift, reset_row=True)
                for offset, correction in zip(offsets, component_offsets(shapes, relationships, reach)):
                    offset[0] += correction[0]
                    offset[1] += correction[1]
                # Track the final body before centering the whole assembly.
                align_attachments(shapes, offsets, alignments, advance_shift=advance_shift)
                if repeat:
                    space_repeat(shapes, offsets, center_axis, repeat)
                if center_axis is not None:
                    target = center + (item.width / 2 - origin if center_axis == 0 else 0)
                    recenter_assembly(shapes, offsets, center_axis, target)
                remaining = []
                for (i, j), (gap, joined) in relationships.items():
                    if gap:
                        axis, sign, minimum = gap
                        valid = signed_gap(shapes[i].bounds, shapes[j].bounds, axis, sign) >= minimum - 1e-4
                    else:
                        valid = intersects(shapes[i], shapes[j]) == joined
                    if not valid:
                        remaining.append([i, j])
                if remaining:
                    failures[weight] = remaining
            positions.append(GlyphCoordinates([(part.x + dx, part.y + dy)
                                               for part, (dx, dy) in zip(parts, offsets)]))
            if any(any(offset) for offset in offsets):
                weight_offsets[weight] = offsets
        if weight_offsets:
            old = expanded_variations(font, name)
            font["gvar"].variations[name] = build_variations(model, positions, old)
            result[name] = weight_offsets
        if failures:
            unresolved[name] = failures
    return {"offsets": result, "unresolved": unresolved, "centered_assemblies": centered,
            "component_attachments": attached}
