"""Construct System’s italic from the rebuilt upright and its shared components."""

from copy import deepcopy

from fontTools.misc.roundTools import otRound
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates, OVERLAP_COMPOUND
from fontTools.varLib.models import VariationModel

from audit import shape_from_glyphs
from build_sans_italic import apply_slant, reuse_single_storey_a
from font_feature_tools import master_locations
from italic_companions import set_style
from italic_letterforms import fit_bowl
from italic_returns import raw_outline, splice_return
from sans_aperture import apertures_for
from sans_baseline_trial import components
from sans_complete_rebuild import box_center
from sans_direct_weight import direct_points
from sans_ligature_construction import JOINED, REPEATED, placements
from scaling_study import vertical_stem
from system_accents import bounds, install_masters
from system_figures import tabular_substitutions
from system_width import add_system_width


def designspace(font):
    _, locations = master_locations(font)
    normalized = [{tag: value for tag, value in font.normalizeLocation(loc).items() if value}
                  for loc in locations]
    tags = [axis.axisTag for axis in font["fvar"].axes]
    return locations, VariationModel(normalized, axisOrder=tags), normalized.index({})


def rebuild_ligatures(font, source, locations, model, default):
    glyphs = [font.getGlyphSet(location=loc) for loc in locations]
    height = font["OS/2"].sxHeight
    for name in (*JOINED, *REPEATED):
        parts = JOINED[name] if name in JOINED else (REPEATED[name],) * 2
        points = [placements(master, name, master[name].width, height) for master in glyphs]
        glyph = components(list(zip(parts, points[default])))
        glyph.components[0].flags |= OVERLAP_COMPOUND
        install_masters(font, source, name, glyph, points, model, default)


def cursive_drawings(font, regular):
    """Cut the established reflected l return into the current f and q curves."""
    donor_cut = 210
    height = font["OS/2"].sxHeight
    donor = raw_outline(regular, "l")
    floor = -.34 * height
    f = splice_return(
        raw_outline(regular, "f"), donor, cut=donor_cut + floor - donor.bounds[1],
        donor_cut=donor_cut, floor=floor, reflect=True, reach_factor=.8,
    )
    original_g = shape_from_glyphs(regular, "g")
    bowl = fit_bowl(raw_outline(regular, "q"), original_g, target="g", retain_segments=True)
    g = splice_return(
        bowl, donor, cut=-43, donor_cut=donor_cut, floor=original_g.bounds[1],
        reach=(bowl.bounds[2] - bowl.bounds[0]) * .84, reflect=True,
    )
    return {"f": f, "g": g}


def shape_italic_core(font, source, locations, model, default):
    anchor = {"wght": 400}
    regular = source.getGlyphSet(location=anchor)
    originals = [source.getGlyphSet(location=loc) for loc in locations]
    regular_stem = vertical_stem(shape_from_glyphs(regular, "n"), .4)
    stems = {loc["wght"]: vertical_stem(shape_from_glyphs(instance, "n"), .4)
             for loc, instance in zip(locations, originals)}
    height = font["OS/2"].sxHeight
    for name, path in cursive_drawings(source, regular).items():
        pen = TTGlyphPen(None)
        path.draw(pen)
        drawing = pen.glyph()
        origin = box_center(bounds(regular, name), 0)
        coordinates = []
        for loc, instance in zip(locations, originals):
            delta = stems[loc["wght"]] - regular_stem
            shift = box_center(bounds(instance, name), 0) - origin
            coordinates.append(direct_points(
                drawing, delta, .72, 3, shift,
                apertures=apertures_for(drawing, abs(delta) * 3), x_height=height,
            ))
        install_masters(font, source, name, drawing, coordinates, model, default)


def center_tabular_ink(font):
    locations, model, default = designspace(font)
    masters = [font.getGlyphSet(location=loc) for loc in locations]
    for tabular in tabular_substitutions(font).values():
        points = []
        for glyphs in masters:
            item = glyphs[tabular]
            part, = item._getGlyphAndOffset()[0].components
            shift = otRound(item.width / 2 - box_center(bounds(glyphs, tabular), 0))
            points.append(GlyphCoordinates([(part.x + shift, part.y)]))
        glyph = deepcopy(font["glyf"][tabular])
        install_masters(font, font, tabular, glyph, points, model, default)


def make_italic(upright):
    font = deepcopy(upright)
    locations, model, default = designspace(font)
    masters = [font.getGlyphSet(location=loc) for loc in locations]
    metrics = reuse_single_storey_a(font, designspace=(model, masters, default))
    shape_italic_core(font, upright, locations, model, default)
    rebuild_ligatures(font, upright, locations, model, default)
    add_system_width(font)
    apply_slant(font, metrics, dotted=("i", "j"), variable_anchors=True)
    center_tabular_ink(font)
    name = font["name"].getBestFamilyName()
    set_style(font, {"name": name, "stem": name.replace(" ", ""),
                     "version": font["name"].getDebugName(5).removeprefix("Version ")})
    return font
