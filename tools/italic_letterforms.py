"""Draw Transit italic alternates using the Metropolitan Line constructions."""

import unicodedata

import pathops

from audit import shape_from_glyphs, spans
from code_receiver_shapes import HorizontalMapPen, remap
from font_feature_tools import from_paths, master_locations
from italic_returns import raw_outline, splice_return


def polygon(points):
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()
    return path


def crop(path, left, bottom, right, top):
    clip = polygon([(left, bottom), (right, bottom), (right, top), (left, top)])
    return pathops.op(path, clip, pathops.PathOp.INTERSECTION)


def fit_bowl(outline, original, target="a", *, retain_segments=False):
    """Fit white space within the bowl while holding the stem thickness."""
    left, bottom, right, top = outline.bounds
    bound_left, _, bound_right, _ = original.bounds
    allowance = 24 if target == "a" else 12
    desired = min(right - left, bound_right - bound_left + allowance)
    origin = (bound_left + bound_right - desired) / 2
    runs = spans(outline, top * 0.54, 1)
    if len(runs) == 2:
        inner_left, inner_right = runs[0][1], runs[1][0]
        old = [left, inner_left, inner_right, right]
        new = [
            origin,
            origin + inner_left - left,
            origin + desired - (right - inner_right),
            origin + desired,
        ]
    else:
        old, new = [left, right], [origin, origin + desired]
    fitted = pathops.Path()
    outline.draw(
        HorizontalMapPen(fitted.getPen(), lambda x: remap(x, old, new), lambda y: y)
    )
    return fitted if retain_segments else pathops.simplify(fitted, fix_winding=True, clockwise=True)


def g_return(bowl, original, construction):
    """Draw a smooth return and join it to the source bowl or q stem."""
    q_based = construction == "q"
    start_y = -58 if q_based else 2
    overlap_y = start_y + 17
    probe_y = overlap_y if q_based else bowl.bounds[3] * 0.57
    left, right = spans(bowl, probe_y, 1)[-1]
    width = right - left
    depth = abs(original.bounds[1]) * (0.94 if q_based else 0.88)
    reach = (right - bowl.bounds[0]) * (0.66 if q_based else 0.84)
    tip_x = right - reach
    # The outer and inner curves meet their adjoining vertical strokes tangentially.
    outer_turn = -depth * (0.67 if q_based else 0.54)
    inner_bottom = -depth + width * 0.80
    middle = right - reach * 0.51
    terminal_y = -depth + 31
    return_path = pathops.Path()
    pen = return_path.getPen()
    pen.moveTo((right, overlap_y))
    pen.lineTo((right, outer_turn))
    pen.curveTo(
        (right, -depth * 0.88), (middle + reach * 0.30, -depth), (middle, -depth)
    )
    pen.curveTo(
        (middle - reach * 0.23, -depth),
        (tip_x + reach * 0.15, terminal_y - 26),
        (tip_x, terminal_y),
    )
    pen.lineTo((tip_x + 37, terminal_y + width * 0.74))
    pen.curveTo(
        (tip_x + reach * 0.24, inner_bottom - 8),
        (middle - reach * 0.13, inner_bottom),
        (middle, inner_bottom),
    )
    pen.curveTo(
        (middle + reach * 0.29, inner_bottom),
        (left, outer_turn - 8),
        (left, outer_turn + 28),
    )
    pen.lineTo((left, overlap_y))
    pen.closePath()
    body = crop(bowl, -2000, start_y, 2000, 2000) if q_based else bowl
    return pathops.op(body, return_path, pathops.PathOp.UNION)


def rotated_f_hook(source):
    """Rotate a copy of the original hook and fit it to the foot of f."""
    _, bottom, _, top = source.bounds
    join = bottom + 10
    left, right = spans(source, join, 1)[0]
    width = right - left
    for depth in range(208, 125, -4):
        cut = top - depth
        runs = spans(source, cut, 1)
        if len(runs) == 1 and width * 0.91 <= runs[0][1] - runs[0][0] <= width * 1.14:
            break
    else:
        raise ValueError("Could not isolate a straight f stem above its crossbar")
    source_left, source_right = runs[0]
    hook = crop(source, -2000, cut, 2000, 2000)
    sx = (width - 4) / (source_right - source_left)
    sy = 0.39
    turned = hook.transform(
        -sx, 0, 0, -sy, right - 2 + sx * source_left, join + sy * cut
    )
    return pathops.op(source, turned, pathops.PathOp.UNION)


def rounded_return(
    source, *, cut, bottom, reach, rise, trim=False, turn_ceiling=None,
    bevel=0.18, broad_turn=False, matching_curves=False, tip_extension=0,
):
    """Continue the right stem into a curved leftward terminal."""
    join = cut + 12
    left, right = spans(source, join, 1)[-1 if trim else 0]
    stem = right - left
    stroke = stem * 0.94
    radius_x = max(stem + 10, reach * 0.64 if broad_turn else min(reach * 0.72, stem * 1.68))
    turn_fraction = 0.74 if matching_curves else 0.66
    rise_to_stem = max(stem * 1.50, -bottom * turn_fraction) if broad_turn else stem * 1.50
    radius_y = min(cut - bottom - 10, rise_to_stem)
    if turn_ceiling is not None:
        radius_y = min(radius_y, turn_ceiling - bottom)
    turn_x, turn_y = right - radius_x, bottom + radius_y
    tip_x = right - reach - tip_extension
    arc = 0.5523
    tail_length = turn_x - tip_x
    cap_offset = stroke * bevel
    outer_controls = (
        (turn_x - tail_length * 0.42, bottom),
        (tip_x + tail_length * 0.35, bottom + rise * 0.44),
    )
    if matching_curves:
        inner_controls = (
            (outer_controls[1][0] + cap_offset * 0.5, outer_controls[1][1] + stroke),
            (outer_controls[0][0], outer_controls[0][1] + stroke),
        )
    else:
        inner_controls = (
            (tip_x + tail_length * 0.42, bottom + stroke + rise * 0.36),
            (turn_x - tail_length * 0.49, bottom + stroke),
        )

    hook = pathops.Path()
    pen = hook.getPen()
    pen.moveTo((right, join))
    pen.lineTo((right, turn_y))
    pen.curveTo(
        (right, turn_y - arc * radius_y),
        (turn_x + arc * radius_x, bottom),
        (turn_x, bottom),
    )
    pen.curveTo(
        (turn_x - (turn_x - tip_x) * 0.42, bottom),
        (tip_x + (turn_x - tip_x) * 0.35, bottom + rise * 0.44),
        (tip_x, bottom + rise),
    )
    pen.lineTo((tip_x + stroke * bevel, bottom + rise + stroke))
    pen.curveTo(
        (tip_x + (turn_x - tip_x) * 0.42, bottom + stroke + rise * 0.36),
        (turn_x - (turn_x - tip_x) * 0.35, bottom + stroke),
        (turn_x, bottom + stroke),
    )
    pen.curveTo(
        (turn_x + arc * (radius_x - stem), bottom + stroke),
        (left, turn_y - arc * (radius_y - stroke)),
        (left, turn_y),
    )
    pen.lineTo((left, join))
    pen.closePath()
    upper = crop(source, -2000, cut, 2000, 2000) if trim else source
    return pathops.op(upper, hook, pathops.PathOp.UNION)


def cursive_g(bowl, original, *, smooth=False):
    """Finish a q-based bowl with an open, round return at the g depth."""
    left, _, right, _ = bowl.bounds
    bottom = original.bounds[1]
    return rounded_return(
        bowl,
        cut=-43,
        bottom=bottom,
        reach=(right - left) * 0.80,
        rise=-bottom * 0.25,
        trim=True,
        bevel=0.10,
        broad_turn=True,
        matching_curves=smooth,
    )


def f_return(source, xheight, *, extended=False, tip_extension=0):
    if extended:
        # Let the stem continue below the baseline before turning. Keep the
        # reach wide enough for a full-weight inside curve at heavier masters.
        left, right = spans(source, 74, 1)[0]
        reach = max(0.35 * xheight, 1.24 * (right - left))
        return rounded_return(
            source,
            cut=62,
            bottom=-0.34 * xheight,
            reach=reach,
            rise=12,
            turn_ceiling=-14,
            bevel=0.04,
            tip_extension=tip_extension,
        )
    return rounded_return(
        source, cut=62, bottom=-0.28 * xheight, reach=0.40 * xheight, rise=15
    )


def trim_i_left_foot(source):
    """Keep the stem and rightward foot, with the original diamond above."""
    left, _ = spans(source, 165, 1)[0]
    return pathops.op(
        crop(source, left, -2000, 2000, 146),
        crop(source, -2000, 146, 2000, 2000),
        pathops.PathOp.UNION,
    )


def related_glyphs(font):
    bases = {"a": "a", "g": "g", "f": "f"}
    for codepoint, name in font.getBestCmap().items():
        decomp = unicodedata.normalize("NFD", chr(codepoint))
        if len(decomp) > 1 and decomp[0] in ("a", "g"):
            bases[name] = decomp[0]
    # Selecting SS01 in Sans or System may substitute this glyph explicitly.
    bases["a.ss01"] = "a"
    return bases


def replace_layout_a_ligature(font):
    """Keep the new italic a visible where upright Sans joined a and i."""
    for lookup in font["GSUB"].table.LookupList.Lookup:
        for subtable in lookup.SubTable:
            subtable = getattr(subtable, "ExtSubTable", subtable)
            ligatures = getattr(subtable, "ligatures", {})
            for first in list(ligatures):
                ligatures[first] = [
                    lig for lig in ligatures[first] if lig.LigGlyph != "a_i"
                ]
                if not ligatures[first]:
                    del ligatures[first]


def redraw_italic_letters(
    font, construction, *, family, descending_f=False, live_components=False,
    smooth_g=False, f_tip_extension=0, donor_returns=False,
):
    _, locations = master_locations(font)
    glyphsets = [font.getGlyphSet(location=location) for location in locations]
    xheight = font["OS/2"].sxHeight
    bases = related_glyphs(font)
    refined = construction == "refined"
    keep_johnston = construction == "johnston"
    cursive = construction == "cursive"
    restore_proportional_a = (
        (refined or keep_johnston or cursive) and family in ("sans", "system")
    )
    if keep_johnston:
        bases = {name: base for name, base in bases.items() if base == "a"}
    if cursive:
        del bases["f"]
    rounded_f = refined or descending_f
    f_forms = ("f",) if family == "code" else ("f", "fi", "fl")
    if rounded_f:
        bases.update((name, name) for name in f_forms)
    if family == "code":
        for cp, name in font.getBestCmap().items():
            if unicodedata.normalize("NFD", chr(cp))[0] == "i":
                bases[name] = "i"
        bases["dotlessi"] = "i"
    if live_components:
        # The Sans rebuild supplies a via its live alternate. Keep existing
        # accents live, and draw the descending return on the joined f forms.
        bases = {name: base for name, base in bases.items()
                 if base != "a" and (name in f_forms or not font["glyf"][name].isComposite())}
    by_location = []
    for glyphs in glyphsets:
        single = shape_from_glyphs(glyphs, "a.ss01")
        a = (
            single
            if restore_proportional_a
            else fit_bowl(single, shape_from_glyphs(glyphs, "a"))
        )
        designs = {"a": a}
        if rounded_f:
            if donor_returns:
                donor = raw_outline(glyphs, "l")
                floor, donor_cut = -0.34 * xheight, 210
                cut = donor_cut + floor - donor.bounds[1]
                for name in f_forms:
                    upper = (raw_outline if name == "f" else shape_from_glyphs)(glyphs, name)
                    designs[name] = splice_return(
                        upper, donor, cut=cut, donor_cut=donor_cut, floor=floor,
                        reflect=True, reach_factor=0.8,
                    )
            else:
                designs.update(
                    (name, f_return(shape_from_glyphs(glyphs, name), xheight, extended=descending_f,
                                    tip_extension=f_tip_extension))
                    for name in f_forms
                )
        if keep_johnston:
            by_location.append(designs)
            continue
        original_g = shape_from_glyphs(glyphs, "g")
        q_outline = raw_outline if donor_returns else shape_from_glyphs
        g_source = q_outline(glyphs, "q") if construction != "a" else single
        bowl = fit_bowl(g_source, original_g, target="g", retain_segments=donor_returns)
        if cursive and donor_returns:
            width = bowl.bounds[2] - bowl.bounds[0]
            g = splice_return(
                bowl, raw_outline(glyphs, "l"), cut=-43, donor_cut=210,
                floor=original_g.bounds[1], reach=width * 0.69, reflect=True, extension=width * 0.18,
            )
        elif cursive:
            g = cursive_g(bowl, original_g, smooth=smooth_g)
        elif refined:
            g = rounded_return(
                bowl,
                cut=-43,
                bottom=original_g.bounds[1] * 0.94,
                reach=(bowl.bounds[2] - bowl.bounds[0]) * 0.72,
                rise=40,
                trim=True,
            )
        else:
            g = g_return(bowl, original_g, construction)
        designs["g"] = g
        if not rounded_f and not cursive:
            designs["f"] = rotated_f_hook(shape_from_glyphs(glyphs, "f"))
        by_location.append(designs)

    replacements = {}
    for name, base in bases.items():
        curves = []
        for glyphs, designs in zip(glyphsets, by_location):
            if base == "i":
                curves.append(trim_i_left_foot(shape_from_glyphs(glyphs, name)))
                continue
            outline = pathops.Path(designs[base])
            if name not in (base, "a.ss01"):
                original = pathops.Path()
                glyphs[name].draw(original.getPen(glyphs))
                marks = [
                    contour
                    for contour in original.contours
                    if contour.bounds[1] > xheight + 18 or contour.bounds[3] < -26
                ]
                if not marks:
                    break
                accent_shift = 0
                if base == "a" and restore_proportional_a:
                    accent_shift = (glyphs["a.ss01"].width - glyphs["a"].width) / 2
                for mark in marks:
                    outline.addPath(mark.transform(1, 0, 0, 1, accent_shift, 0))
            curves.append(outline)
        if len(curves) == len(locations):
            replacements[name] = curves

    advance_map = font["HVAR"].table.AdvWidthMap.mapping
    metric_sources = {}
    for name, curves in replacements.items():
        source = "a.ss01" if restore_proportional_a and bases[name] == "a" else name
        advance_index = advance_map[source]
        from_paths(font, name, locations, curves, font["hmtx"][source][0])
        advance_map[name] = advance_index
        if source != name:
            metric_sources[name] = source
    if "a_i" in font.getGlyphOrder():
        replace_layout_a_ligature(font)
    return set(replacements), metric_sources
