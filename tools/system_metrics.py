"""Coordinate System advances and vertical metrics."""

from math import ceil, floor

from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.varStore import OnlineVarStoreBuilder

from font_feature_tools import append_variation_rows, master_locations


def set_vertical_metrics(*fonts, minimum_ascent=0, maximum_descent=0):
    """Give upright and italic the same bounds using the System ink margin."""
    bottom, top = 0, 0
    sampled_locations = 0
    for font in fonts:
        _, locations = master_locations(font)
        sampled_locations += len(locations)
        for location in locations:
            glyphs = font.getGlyphSet(location=location)
            for name in font.getGlyphOrder():
                pen = BoundsPen(glyphs)
                glyphs[name].draw(pen)
                if pen.bounds is not None:
                    bottom = min(bottom, pen.bounds[1])
                    top = max(top, pen.bounds[3])
    margin = 12
    ascent = max(minimum_ascent, ceil(top) + margin)
    descent = min(maximum_descent, floor(bottom) - margin)
    for font in fonts:
        # The typographic metrics retain System's established line rhythm.
        font["hhea"].ascent = font["OS/2"].usWinAscent = ascent
        font["hhea"].descent = descent
        font["OS/2"].usWinDescent = -descent
    return {
        "sampled_locations": sampled_locations,
        "ink_bottom": bottom,
        "ink_top": top,
        "ascent": ascent,
        "descent": descent,
        "margin": margin,
    }


def set_advances(font, advances, model, *, multiples=None):
    """Install the same width model in HVAR and the gvar phantom points."""
    table = font["HVAR"].table
    store = table.VarStore
    start = len(store.VarData) << 16
    builder = OnlineVarStoreBuilder([axis.axisTag for axis in font["fvar"].axes])
    builder.setModel(model)
    multiples = multiples or {}
    for name, widths in advances.items():
        multiple = multiples.get(name, 1)
        delta = [value * multiple for value in model.getDeltas(
            [width / multiple for width in widths], round=otRound
        )]
        base, index = delta[0], builder.storeDeltas(delta[1:], round=otRound)
        _, lsb = font["hmtx"][name]
        font["hmtx"][name] = base, lsb
        table.AdvWidthMap.mapping[name] = start + index
        variations = font["gvar"].variations.setdefault(name, [])
        for item in variations:
            for i in (-4, -3):
                _, y = item.coordinates[i] or (0, 0)
                item.coordinates[i] = 0, y
        coordinates, _ = font["glyf"]._getCoordinatesAndControls(name, font["hmtx"].metrics)
        for support, value in zip(model.supports[1:], delta[1:]):
            if value:
                points = [(0, 0)] * len(coordinates)
                points[-3] = otRound(value), 0
                variations.append(TupleVariation(support, points))
    append_variation_rows(store, builder.finish())
