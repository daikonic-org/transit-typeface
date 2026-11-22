"""Construct upright Sans ligatures from the current letter outlines."""

from copy import deepcopy

import pathops

from fontTools.misc.bezierTools import solveQuadratic, splitCubicAtT
from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates, OVERLAP_COMPOUND
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.varLib.models import VariationModel, normalizeLocation

from audit import shape, shape_from_glyphs, spans
from compatibility import compatible_masters, curves_from_path
from derive_weights import topology
from font_feature_tools import expanded_variations
from hook_ligature_study import extend_hook, op, rect, run, trim_old_a_foot
from repeated_stems import pair_positions
from sans_baseline_trial import build_variations, components, install

HOOKS = ("a_i", "l_i")
JOINED = {"fi": ("f", "dotlessi"), "fl": ("f", "l")}
REPEATED = {"f_f": "f", "t_t": "t"}
LIGATURES = (*HOOKS, *JOINED, *REPEATED, "Q_U")


def span_width(span):
    return span[1] - span[0]


def hook_cut_mask(outline, clearance):
    """Sweep the exact hook curves downward to cut the adjacent letter."""
    bottom = outline.bounds[1] - 1
    mask = pathops.Path()
    for contour in outline.contours:
        for curve in curves_from_path(contour):
            a, b, c, d = (point.real for point in curve)
            # Split where the curve reverses in x, so each sweep encloses one
            # interval without doubling back or generating a thin sliver.
            extrema = sorted(set(
                t for t in solveQuadratic(-a + 3*b - 3*c + d, 2*(a - 2*b + c), b - a)
                if 0 < t < 1
            ))
            points = [(point.real, point.imag + clearance) for point in curve]
            for start, first, second, end in splitCubicAtT(*points, *extrema):
                if abs(start[0] - end[0]) < 1e-7:
                    continue
                strip = pathops.Path()
                strip.moveTo(*start)
                strip.cubicTo(*first, *second, *end)
                strip.lineTo(end[0], bottom)
                strip.lineTo(start[0], bottom)
                strip.close()
                mask = op(mask, strip)
    return mask


def hooked_paths(instance, regular_stem):
    a, l, i = (shape(instance, name) for name in ("a", "l", "i"))
    xheight = instance["OS/2"].sxHeight
    stem_probe = xheight * 0.58
    i_stem = spans(i, stem_probe, 1)[0]
    l_right = spans(l, stem_probe, 1)[0][1]
    ai_origin = run(instance, "ai", False)[0][1]
    li_origin = ai_origin + l_right - a.bounds[2]
    stem = span_width(i_stem)
    clearance = max(stem / 4, regular_stem * 0.625 - (stem - regular_stem) * 0.9)
    paths = []
    for origin, shift, first in ((ai_origin, a.bounds[2] - l_right, a), (li_origin, 0, None)):
        origin = otRound(origin)
        i_right = origin + i_stem[1]
        # Overshoot the terminal for the cutting mask so quantization cannot
        # leave a sliver along the i's right edge. Trim the visible hook back.
        overshoot = 2
        extension = i_right + overshoot - (l.bounds[2] + shift)
        hook = extend_hook(l, extension).transform(1, 0, 0, 1, shift, 0)
        if first is not None:
            hook = op(hook, rect(-1000, -1000, 3000, xheight * 0.38), pathops.PathOp.INTERSECTION)
        mask = hook_cut_mask(hook, clearance)
        stem_and_dot = i.transform(1, 0, 0, 1, origin, 0)
        trimmed = op(stem_and_dot, mask, pathops.PathOp.DIFFERENCE)
        visible = op(hook, rect(-1000, -1000, i_right, 2000), pathops.PathOp.INTERSECTION)
        if first is not None:
            visible = op(trim_old_a_foot(first, visible), visible)
        if op(visible, trimmed, pathops.PathOp.INTERSECTION).area > 0.01:
            raise ValueError("The hooked ligature touches its i stroke")
        paths.append(op(visible, trimmed))
    return paths


def placements(outlines, name, width, xheight):
    if name in JOINED:
        first, second = JOINED[name]
        y = xheight * 0.9
        bar_end = spans(shape_from_glyphs(outlines, first), y, 1)[-1][1]
        second_stem = spans(shape_from_glyphs(outlines, second), y, 1)[0]
        overlap = max(3, span_width(second_stem) / 20)
        return GlyphCoordinates([(0, 0), (otRound(bar_end - second_stem[0] - overlap), 0)])
    part = REPEATED[name]
    return GlyphCoordinates((otRound(x), 0) for x in
                            pair_positions(shape_from_glyphs(outlines, part), width / 2))


def qu_master(glyphs):
    """Extend the current Q's tail to its bowl floor and place the current U."""
    q, q_offset = glyphs["Q"]._getGlyphAndOffset()
    u, u_offset = glyphs["U"]._getGlyphAndOffset()
    glyph = deepcopy(q)
    points = glyph.coordinates
    tail = [
        index for index in range(glyph.endPtsOfContours[0] - 2)
        if all(flag & 1 for flag in glyph.flags[index:index + 4])
        and points[index][1] > points[index + 1][1] > points[index + 2][1]
        and points[index + 3][1] > points[index + 2][1]
    ]
    if len(tail) != 1:
        raise ValueError(f"Expected one Q tail, found {len(tail)}")
    start = tail[0]
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = points[start:start + 4]
    floor = points[0][1]
    points[start + 1] = (ax + (floor - ay) * (bx - ax) / (by - ay), floor)
    points[start + 2] = (dx + (floor - dy) * (cx - dx) / (cy - dy), floor)
    count = len(points)
    advance = glyphs["Q"].width
    glyph.coordinates = GlyphCoordinates([
        *((otRound(x + q_offset), otRound(y)) for x, y in points),
        *((otRound(x + advance + u_offset), otRound(y)) for x, y in u.coordinates),
    ])
    glyph.endPtsOfContours = [*glyph.endPtsOfContours, *(i + count for i in u.endPtsOfContours)]
    glyph.flags = bytearray([*glyph.flags, *u.flags])
    glyph.numberOfContours = len(glyph.endPtsOfContours)
    return glyph


def rebuild_ligatures(font, *, proof_only=False):
    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
    default_weight = axes["wght"][1]
    weights = [default_weight, *(i.coordinates["wght"] for i in font["fvar"].instances
                                 if i.coordinates["wght"] != default_weight)]
    locations = [{"wght": weight} for weight in weights]
    model = VariationModel([normalizeLocation(location, axes) for location in locations])
    # Work on a frozen view of the new letters and the existing layout metrics.
    snapshot = deepcopy(font)
    default = snapshot.getGlyphSet()
    xheight = font["OS/2"].sxHeight
    regular_stem = span_width(spans(shape_from_glyphs(default, "i"), xheight * 0.58, 1)[0])
    masters = [hooked_paths(instantiateVariableFont(snapshot, loc), regular_stem) for loc in locations]
    report = {}
    for i, name in enumerate(HOOKS):
        paths = [master[i] for master in masters]
        target_topologies = [topology(path) for path in paths]
        glyphs, missing = compatible_masters(paths)
        metrics = expanded_variations(font, name)
        install(font, name, glyphs[0],
                build_variations(model, [glyph.coordinates for glyph in glyphs], metrics))
        master_changes = [
            weight for weight, value in zip(weights, target_topologies)
            if value != target_topologies[0]
        ]
        if not proof_only and (master_changes or missing):
            raise ValueError(f"Hook topology changes at the masters of {name}: {master_changes}")
        report[name] = {"source_letters": ["a", "l", "i"] if name == "a_i" else ["l", "i"],
                        "points": len(glyphs[0].coordinates),
                        "master_topology_changes": master_changes,
                        "missing_master_contours": missing}

    for name in (*JOINED, *REPEATED):
        parts = JOINED[name] if name in JOINED else (REPEATED[name],) * 2
        positions = []
        for loc in locations:
            glyphs = snapshot.getGlyphSet(location=loc)
            positions.append(placements(glyphs, name, glyphs[name].width, xheight))
        glyph = components(list(zip(parts, positions[0])))
        glyph.components[0].flags |= OVERLAP_COMPOUND
        install(font, name, glyph, build_variations(model, positions, expanded_variations(font, name)))
        report[name] = {"live_components": list(parts)}

    qu = [qu_master(snapshot.getGlyphSet(location=location)) for location in locations]
    install(font, "Q_U", qu[0], build_variations(
        model, [glyph.coordinates for glyph in qu], expanded_variations(font, "Q_U")
    ))
    report["Q_U"] = {"source_letters": ["Q", "U"], "points": len(qu[0].coordinates)}

    default_topologies = {name: topology(shape_from_glyphs(font.getGlyphSet(), name)) for name in LIGATURES}
    for weight in range(300, 601, 25):
        before = snapshot.getGlyphSet(location={"wght": weight})
        after = font.getGlyphSet(location={"wght": weight})
        for name in LIGATURES:
            if before[name].width != after[name].width:
                raise ValueError(f"Ligature width changed at {weight}: {name}")
            if topology(shape_from_glyphs(after, name)) != default_topologies[name]:
                if not proof_only:
                    raise ValueError(f"Rebuilt ligature changes its contour structure at {weight}: {name}")
                report[name].setdefault("topology_changes", []).append(weight)
    return report
