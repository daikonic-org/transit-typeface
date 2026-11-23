"""Rebuild System lowercase accents from Sans component relationships."""

from copy import deepcopy
from functools import lru_cache
from itertools import combinations
from unicodedata import combining, normalize

from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
import pathops

from audit import shape_from_glyphs
from font_feature_tools import expanded_variations
from italic_returns import raw_outline
from kern_clearance import overlaps
from sans_baseline_trial import build_variations, clear_hints, install
from sans_complete_rebuild import (
    box_center, component_offsets, joins, separation, signed_gap,
)


def recipes(source, donor, bases):
    output = {}
    codepoints = []
    donor_cmap = donor.getBestCmap()
    for codepoint, target in source.getBestCmap().items():
        decomposition = normalize("NFD", chr(codepoint))
        if len(decomposition) < 2 or not all(map(combining, decomposition[1:])):
            continue
        donor_name = donor_cmap.get(codepoint)
        if donor_name is None:
            continue
        glyph = donor["glyf"][donor_name]
        if glyph.isComposite() and glyph.components[0].glyphName in bases:
            output[target] = donor_name
            codepoints.append(codepoint)
    return output, codepoints


def drawing(glyphs, name):
    # Component coordinates are read at their stored origin.
    with glyphs.pushDepth():
        try:
            return shape_from_glyphs(glyphs, name)
        except pathops.PathOpsError:
            return raw_outline(glyphs, name)


def touching(first, second):
    try:
        return joins(first, second, contact=True)
    except pathops.PathOpsError:
        return overlaps(first, second)


def bounds(glyphs, name):
    pen = BoundsPen(glyphs)
    with glyphs.pushDepth():
        glyphs[name].draw(pen)
    return pen.bounds


def install_masters(font, source, name, glyph, points, model, default):
    if glyph.isComposite():
        for part, (x, y) in zip(glyph.components, points[default]):
            part.x, part.y = x, y
    else:
        glyph.coordinates = points[default]
    clear_hints(glyph)
    install(font, name, glyph, build_variations(model, points, expanded_variations(source, name)))


def movements(parts, glyphs, dot):
    if not parts.isComposite():
        return deepcopy(parts.coordinates)
    # The spacing dot already includes the single-dot offset. Both diaeresis
    # components use that same dot and retain the spacing from the Sans master.
    single, = glyphs["uni0307"].components
    points = GlyphCoordinates([(part.x - single.x, part.y - single.y) for part in parts.components])
    for part in parts.components:
        assert part.glyphName == single.glyphName
        part.glyphName = dot
    return points


def measure_components(source, targets, donor_masters, locations, model, default, dot):
    """Give the shared marks their clean curves at the established mark origins."""
    marks = sorted({part.glyphName for name in targets
                    for part in donor_masters[default]["glyf"][name].components[1:]})
    for name in marks:
        points = []
        template = None
        for index, (master, location) in enumerate(zip(donor_masters, locations)):
            glyph = deepcopy(master["glyf"][name])
            master_glyf = master["glyf"]
            coordinates = movements(glyph, master_glyf, dot)
            old = bounds(source.getGlyphSet(location=location), name)
            new = bounds(master.getGlyphSet(), name)
            coordinates.translate(tuple(otRound(box_center(old, axis) - box_center(new, axis))
                                        for axis in (0, 1)))
            if index == default:
                template = glyph
            points.append(coordinates)
        yield name, template, points


def mark_offset(mark, body, target, released, above, below, side):
    """Follow the reference alignment through the lowered or enlarged body."""
    old, new = body.bounds, target.bounds
    x = box_center(new, 0) - box_center(old, 0)
    y = 0
    if above:
        y = max(released[3] - mark[3], new[3] - old[3])
    elif below:
        y = min(released[1] - mark[1], new[1] - old[1])
    elif side:
        x = new[2] - old[2]
    elif mark[3] < (old[1] + old[3]) / 2:
        # Keep an attached mark at the same distance from the baseline.
        x = new[2] - old[2] if box_center(mark, 0) > box_center(old, 0) else x
    return box_center(mark, 0) + x, box_center(mark, 1) + y


def rebuild_accents(font, source, donors, locations, model, default, bases, dot):
    reference = donors[default["wght"]]
    layout, codepoints = recipes(source, reference, bases)
    static = [donors[loc["wght"]] for loc in locations]
    default_index = locations.index(default)

    for name, glyph, points in measure_components(source, layout.values(), static,
                                                   locations, model, default_index, dot):
        install_masters(font, source, name, glyph, points, model, default_index)

    positions = {name: [] for name in layout}
    for master, location in zip(static, locations):
        prior = source.getGlyphSet(location=location)
        target = font.getGlyphSet(location=location)
        donor = master.getGlyphSet()

        @lru_cache(None)
        def outline(name):
            return drawing(target, name)

        @lru_cache(None)
        def reference_outline(name):
            return drawing(donor, name)

        for name, donor_name in layout.items():
            parts = [part.getComponentInfo() for part in master["glyf"][donor_name].components]
            body, body_matrix = parts[0]
            assert body_matrix[:4] == (1, 0, 0, 1), (name, body_matrix)
            reference_body = reference_outline(body).transform(*body_matrix)
            finished_body = outline(body).transform(*body_matrix)
            released = bounds(prior, name)
            old = [reference_body]
            revised = [finished_body]
            offsets = [body_matrix[4:]]
            for mark, matrix in parts[1:]:
                assert matrix[:4] == (1, 0, 0, 1), (name, matrix)
                shape = reference_outline(mark).transform(*matrix)
                original = shape.bounds
                mark_shape = outline(mark)
                finished = mark_shape.bounds
                above = original[1] >= reference_body.bounds[3]
                below = original[3] <= reference_body.bounds[1]
                side = original[0] >= reference_body.bounds[2]
                x, y = mark_offset(original, reference_body, finished_body, released, above, below, side)
                offset = tuple(otRound(value - box_center(finished, axis))
                               for axis, value in enumerate((x, y)))
                offsets.append(offset)
                old.append(shape)
                revised.append(mark_shape.transform(translateX=offset[0], translateY=offset[1]))

            relationships = {}
            for i, j in combinations(range(len(parts)), 2):
                gap = separation(old[i].bounds, old[j].bounds)
                if gap:
                    axis, side, minimum = gap
                    gap = axis, side, min(minimum, old[j].bounds[3] - old[j].bounds[1])
                relationships[i, j] = gap, gap is None and touching(old[i], old[j])
            fixes = component_offsets(revised, relationships, 28)
            for (i, j), (gap, joined) in relationships.items():
                if gap:
                    axis, side, minimum = gap
                    assert signed_gap(revised[i].bounds, revised[j].bounds, axis, side) >= minimum - .01, (name, location)
                else:
                    assert overlaps(revised[i], revised[j]) == joined, (name, location, i, j, joined)
            positions[name].append(GlyphCoordinates((x + dx, y + dy)
                                                     for (x, y), (dx, dy) in zip(offsets, fixes)))

    for name, donor_name in layout.items():
        glyph = deepcopy(reference["glyf"][donor_name])
        install_masters(font, source, name, glyph, positions[name], model, default_index)
    return codepoints
