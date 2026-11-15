"""Retain approved layout and metric variations while changing outline weights."""

from copy import deepcopy
from fontTools.ttLib.tables.TupleVariation import TupleVariation


def preserve_layout(font, baseline, protected):
    # Adding rounded named-weight masters can otherwise change advances by one
    # unit between masters. Keep the original phantom-point variation functions.
    for name in font.getGlyphOrder():
        if name in protected:
            font["glyf"][name] = deepcopy(baseline["glyf"][name])
            font["hmtx"][name] = baseline["hmtx"][name]
            font["gvar"].variations[name] = deepcopy(
                baseline["gvar"].variations.get(name, [])
            )
            continue
        glyph = font["glyf"][name]
        oldglyph = baseline["glyf"][name]
        if glyph.numberOfContours:
            glyph.recalcBounds(font["glyf"])
            left = oldglyph.xMin - baseline["hmtx"][name][1]
            font["hmtx"][name] = (baseline["hmtx"][name][0], glyph.xMin - left)
        else:
            font["hmtx"][name] = baseline["hmtx"][name]
        variations = font["gvar"].variations.setdefault(name, [])
        for variation in variations:
            variation.coordinates[-4:] = [None] * 4
        count = len(glyph.getCoordinates(font["glyf"])[0]) + 4
        for variation in baseline["gvar"].variations.get(name, []):
            phantom = variation.coordinates[-4:]
            if any(v is not None and v != (0, 0) for v in phantom):
                variations.append(
                    TupleVariation(
                        deepcopy(variation.axes),
                        [None] * (count - 4) + deepcopy(phantom),
                    )
                )
    for tag in ("GSUB", "GPOS", "GDEF", "HVAR", "MVAR"):
        if tag in baseline:
            font[tag] = deepcopy(baseline[tag])
