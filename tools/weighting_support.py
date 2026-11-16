"""Retain approved layout and metric variations while changing outline weights."""

from copy import deepcopy
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables import otTables


def preserve_layout(
    font, baseline, protected, metric_overrides=(), append_kerning_lookup=False
):
    # Adding rounded named-weight masters can otherwise change advances by one
    # unit between masters. Keep the original phantom-point variation functions.
    candidate_hvar = deepcopy(font["HVAR"]) if metric_overrides else None
    kerning = (
        deepcopy(font["GPOS"].table.LookupList.Lookup[-1])
        if append_kerning_lookup
        else None
    )
    for name in font.getGlyphOrder():
        if name in metric_overrides:
            continue
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
    if metric_overrides:
        retain_advance_overrides(font, candidate_hvar, metric_overrides)
    if kerning:
        # This correction is constant across masters. Retain all original
        # positioning/mark variation functions and append only this new lookup.
        assert kerning.LookupType == 2
        assert all(
            s.Format == 1 and s.ValueFormat1 == 4 and s.ValueFormat2 == 0
            for s in kerning.SubTable
        )
        table = font["GPOS"].table
        index = len(table.LookupList.Lookup)
        table.LookupList.Lookup.append(kerning)
        table.LookupList.LookupCount += 1
        for record in table.FeatureList.FeatureRecord:
            if record.FeatureTag == "kern":
                record.Feature.LookupListIndex.append(index)
                record.Feature.LookupCount += 1


def retain_advance_overrides(font, candidate, names):
    """Append only explicitly revised glyph-width functions to retained HVAR."""
    target, source = font["HVAR"].table, candidate.table
    if target.AdvWidthMap is None:
        target.AdvWidthMap = otTables.VarIdxMap()
        target.AdvWidthMap.mapping = {
            n: font.getGlyphID(n) for n in font.getGlyphOrder()
        }
    for name in names:
        index = (
            source.AdvWidthMap.mapping[name]
            if source.AdvWidthMap
            else font.getGlyphID(name)
        )
        data = deepcopy(source.VarStore.VarData[index >> 16])
        data.Item = [data.Item[index & 0xFFFF]]
        data.ItemCount = 1
        indices = []
        for region_index in data.VarRegionIndex:
            indices.append(len(target.VarStore.VarRegionList.Region))
            target.VarStore.VarRegionList.Region.append(
                deepcopy(source.VarStore.VarRegionList.Region[region_index])
            )
        data.VarRegionIndex = indices
        outer = len(target.VarStore.VarData)
        target.VarStore.VarData.append(data)
        target.AdvWidthMap.mapping[name] = outer << 16
    target.VarStore.VarDataCount = len(target.VarStore.VarData)
    target.VarStore.VarRegionList.RegionCount = len(
        target.VarStore.VarRegionList.Region
    )
