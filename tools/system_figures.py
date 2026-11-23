"""Rebuild proportional and tabular System figures from shared Sans outlines."""

from copy import deepcopy
from string import digits

from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

from font_feature_tools import append_glyph, expanded_variations, feature_subtables
from sans_baseline_trial import build_variations, components, install
from sans_complete_rebuild import box_center
from system_accents import bounds, install_masters


OPTICAL_DOT_SCALES = (1.10, 1.06, 1.0)


def tabular_substitutions(font):
    return {name: alternate for tag, table in feature_subtables(font) if tag == "tnum"
            for name, alternate in table.mapping.items()}


def rebuild_figures(font, source, donors, locations, model, default):
    """Install clean drawings, then give each tabular form a live base component."""
    pairs = tabular_substitutions(source)
    cmap = source.getBestCmap()
    numeral_names = {cmap[ord(char)] for char in digits}
    separator_names = {cmap[ord(char)] for char in ".,:"}
    assert pairs.keys() == numeral_names | separator_names
    optical = next(axis for axis in source["fvar"].axes if axis.axisTag == "opsz")
    dot_scale = dict(zip((optical.minValue, optical.defaultValue, optical.maxValue), OPTICAL_DOT_SCALES))
    donor = donors[locations[default]["wght"]]
    original = [source.getGlyphSet(location=loc) for loc in locations]
    masters = [donors[loc["wght"]] for loc in locations]
    dot_name = "diamond.dot"
    dot = deepcopy(donor["glyf"][dot_name])
    dot_masters = []
    for loc, face in zip(locations, masters):
        assert loc["opsz"] in dot_scale, loc
        scale = dot_scale[loc["opsz"]]
        dot_masters.append(GlyphCoordinates((otRound(x * scale), otRound(y * scale))
                                            for x, y in face["glyf"][dot_name].coordinates))
    dot.coordinates = dot_masters[default]
    append_glyph(font, dot_name, dot, build_variations(model, dot_masters), 0)
    font["GDEF"].table.GlyphClassDef.classDefs[dot_name] = 3

    for name in pairs:
        glyph = deepcopy(donor["glyf"][name])
        points = []
        for face, target in zip(masters, original):
            item = face["glyf"][name]
            shift = otRound(box_center(bounds(target, name), 0)
                            - box_center(bounds(face.getGlyphSet(), name), 0))
            if glyph.isComposite():
                assert all(part.glyphName == dot_name for part in item.components), name
                points.append(GlyphCoordinates((part.x + shift, part.y) for part in item.components))
            else:
                coords = item.coordinates.copy()
                coords.translate((shift, 0))
                points.append(coords)
        install_masters(font, source, name, glyph, points, model, default)

    shifted = [font.getGlyphSet(location=loc) for loc in locations]
    width_map = font["HVAR"].table.AdvWidthMap.mapping
    columns = (pairs[cmap[ord("0")]], pairs[cmap[ord(".")]])
    metrics = [expanded_variations(source, name) for name in columns]
    for name, tabular in pairs.items():
        column = 0 if name in numeral_names else 1
        axis_metrics = metrics[column]
        placements = []
        for glyphs in shifted:
            box = bounds(glyphs, name)
            x = otRound(glyphs[columns[column]].width / 2 - box_center(box, 0))
            y = otRound(font["OS/2"].sCapHeight / 2 - box_center(box, 1)) if name == cmap[ord(":")] else 0
            placements.append(GlyphCoordinates([(x, y)]))
        glyph = components([(name, placements[default][0])])
        install(font, tabular, glyph, build_variations(model, placements, axis_metrics))
        width_map[tabular] = width_map[columns[column]]
        assert font["hmtx"][tabular][0] == font["hmtx"][columns[column]][0], tabular

    return pairs
