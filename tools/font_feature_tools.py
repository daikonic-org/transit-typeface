"""Shared compatible glyph composition and additive OpenType feature construction."""

from copy import deepcopy
import itertools
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.varLib.models import VariationModel, normalizeLocation
from fontTools.misc.roundTools import otRound
from fontTools.varLib.iup import iup_delta


def feature_subtables(font):
    table = font["GSUB"].table
    for record in table.FeatureList.FeatureRecord:
        for index in record.Feature.LookupListIndex:
            for subtable in table.LookupList.Lookup[index].SubTable:
                yield record.FeatureTag, getattr(subtable, "ExtSubTable", subtable)


def expanded_variations(font, name):
    old = font["glyf"][name]
    result = {}
    for v in font["gvar"].variations.get(name, []):
        key = tuple(sorted(v.axes.items()))
        values = (
            iup_delta(
                v.coordinates,
                list(old.coordinates) + [(0, 0)] * 4,
                old.endPtsOfContours,
            )
            if any(d is None for d in v.coordinates)
            else v.coordinates
        )
        if key not in result:
            result[key] = [(0, 0)] * len(values)
        result[key] = [(a + c, b + d) for (a, b), (c, d) in zip(result[key], values)]
    return result


def append_glyph(font, name, glyph, variations, advance, metric_source=None):
    # Decode gvar against the original glyph count before extending the order.
    gvar = font["gvar"]
    order = font.getGlyphOrder()
    if name not in order:
        font.setGlyphOrder(order + [name])
    font["glyf"][name] = glyph
    if glyph.numberOfContours:
        glyph.recalcBounds(font["glyf"])
    font["hmtx"][name] = (round(advance), glyph.xMin if glyph.numberOfContours else 0)
    gvar.variations[name] = variations
    if "HVAR" in font:
        table = font["HVAR"].table
        if table.AdvWidthMap is None:
            table.AdvWidthMap = otTables.VarIdxMap()
            table.AdvWidthMap.mapping = {n: i for i, n in enumerate(order)}
        if metric_source:
            table.AdvWidthMap.mapping[name] = table.AdvWidthMap.mapping[metric_source]
        else:
            if not hasattr(font, "_constant_advance_index"):
                from fontTools.varLib.builder import buildVarData

                store = table.VarStore
                font._constant_advance_index = len(store.VarData) << 16
                store.VarData.append(buildVarData([], [[]], optimize=False))
                store.VarDataCount = len(store.VarData)
            table.AdvWidthMap.mapping[name] = font._constant_advance_index
        for attr in ["LsbMap", "RsbMap"]:
            mapping = getattr(table, attr, None)
            if mapping is not None:
                mapping.mapping[name] = mapping.mapping.get(metric_source or "space", 0)
    if "GDEF" in font and font["GDEF"].table.GlyphClassDef:
        font["GDEF"].table.GlyphClassDef.classDefs[name] = 1
    font["maxp"].numGlyphs = len(font.getGlyphOrder())


def compose(font, name, parts, advance, metric_source=None, sum_metrics=False):
    """Compose affine copies, retaining the sources' complete variation functions."""
    glyph = Glyph()
    glyph.numberOfContours = 0
    glyph.coordinates = GlyphCoordinates()
    glyph.flags = bytearray()
    glyph.endPtsOfContours = []
    sources = []
    supports = {}
    for source, sx, sy, tx, ty in parts:
        old = font["glyf"][source]
        offset = len(glyph.coordinates)
        glyph.coordinates.extend(
            [(otRound(x * sx + tx), otRound(y * sy + ty)) for x, y in old.coordinates]
        )
        glyph.flags.extend(old.flags)
        glyph.endPtsOfContours.extend(end + offset for end in old.endPtsOfContours)
        glyph.numberOfContours += old.numberOfContours
        variations = {
            key: TupleVariation(dict(key), values)
            for key, values in expanded_variations(font, source).items()
        }
        supports.update({key: dict(key) for key in variations})
        sources.append((old, sx, sy, variations))
    # OVERLAP_SIMPLE is legal only on the first point of a simple glyph.
    # A later composed component can carry it on its own first point.
    overlap = any(flag & 0x40 for flag in glyph.flags)
    glyph.flags = bytearray(flag & ~0x40 for flag in glyph.flags)
    if overlap and glyph.flags:
        glyph.flags[0] |= 0x40
    from fontTools.ttLib.tables.ttProgram import Program

    glyph.program = Program()
    glyph.program.fromBytecode(b"")
    output = []
    for key, axes in supports.items():
        coordinates = []
        prefix = 0
        for old, sx, sy, variations in sources:
            values = (
                variations[key].coordinates[:-4]
                if key in variations
                else [(0, 0)] * len(old.coordinates)
            )
            coordinates.extend(
                None if v is None else (otRound(v[0] * sx + prefix), otRound(v[1] * sy))
                for v in values
            )
            if sum_metrics and key in variations:
                phantom = variations[key].coordinates[-4:]
                prefix += phantom[1][0] - phantom[0][0]
        coordinates += [(0, 0), (otRound(prefix), 0), (0, 0), (0, 0)]
        if metric_source and key in sources[0][3]:
            coordinates[-4:] = deepcopy(sources[0][3][key].coordinates[-4:])
        output.append(TupleVariation(axes, coordinates))
    append_glyph(font, name, glyph, output, advance, metric_source)
    if sum_metrics:
        from fontTools.varLib.builder import buildVarRegion, buildVarData

        store = font["HVAR"].table.VarStore
        indices = []
        values = []
        for variation in output:
            delta = variation.coordinates[-3][0]
            if delta:
                indices.append(len(store.VarRegionList.Region))
                store.VarRegionList.Region.append(
                    buildVarRegion(
                        variation.axes, [a.axisTag for a in font["fvar"].axes]
                    )
                )
                values.append(delta)
        if indices:
            outer = len(store.VarData)
            store.VarData.append(buildVarData(indices, [values], optimize=False))
            store.VarRegionList.RegionCount = len(store.VarRegionList.Region)
            store.VarDataCount = len(store.VarData)
            font["HVAR"].table.AdvWidthMap.mapping[name] = outer << 16


def master_locations(font):
    triples = {
        a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes
    }
    values = []
    for a in font["fvar"].axes:
        values.append(
            sorted(
                {a.minValue, a.defaultValue, a.maxValue}
                | {i.coordinates[a.axisTag] for i in font["fvar"].instances}
            )
        )
    locations = [dict(zip(triples, v)) for v in itertools.product(*values)]
    return triples, locations


def from_paths(font, name, locations, paths, advance):
    from compatibility import compatible_masters

    glyphs, missing = compatible_masters(paths)
    assert not missing, (name, missing)
    triples = {
        a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes
    }
    normalized = [
        {k: v for k, v in normalizeLocation(loc, triples).items() if v}
        for loc in locations
    ]
    model = VariationModel(normalized, axisOrder=list(triples))
    default = normalized.index({})
    coords = [GlyphCoordinates(list(g.coordinates) + [(0, 0)] * 4) for g in glyphs]
    deltas = model.getDeltas(coords)
    variations = [
        TupleVariation(support, [(otRound(x), otRound(y)) for x, y in delta])
        for delta, support in zip(deltas, model.supports)
        if support
    ]
    append_glyph(font, name, glyphs[default], variations, advance)


def remap_lookup_records(value, offset, start=0):
    """Shift nested lookup references when a layout lookup is moved or inserted."""
    if isinstance(value, (otTables.SubstLookupRecord, otTables.PosLookupRecord)):
        if value.LookupListIndex >= start:
            value.LookupListIndex += offset
    elif isinstance(value, list):
        for item in value:
            remap_lookup_records(item, offset, start)
    elif hasattr(value, "__dict__"):
        for item in vars(value).values():
            remap_lookup_records(item, offset, start)


def add_features(font, fea, prepend=False):
    scratch = TTFont()
    scratch.setGlyphOrder(font.getGlyphOrder())
    addOpenTypeFeaturesFromString(scratch, fea)
    for tag in ("GSUB", "GPOS"):
        if tag not in scratch:
            continue
        source = scratch[tag].table
        target = font[tag].table
        offset = len(target.LookupList.Lookup)

        for lookup in source.LookupList.Lookup:
            remap_lookup_records(lookup, offset)
        target.LookupList.Lookup.extend(source.LookupList.Lookup)
        target.LookupList.LookupCount = len(target.LookupList.Lookup)
        added = []
        for record in source.FeatureList.FeatureRecord:
            indices = [i + offset for i in record.Feature.LookupListIndex]
            existing = [
                r
                for r in target.FeatureList.FeatureRecord
                if r.FeatureTag == record.FeatureTag
            ]
            if existing:
                for r in existing:
                    r.Feature.LookupListIndex = (
                        (indices + r.Feature.LookupListIndex)
                        if prepend
                        else (r.Feature.LookupListIndex + indices)
                    )
                    r.Feature.LookupCount = len(r.Feature.LookupListIndex)
            else:
                r = deepcopy(record)
                r.Feature.LookupListIndex = indices
                added.append(len(target.FeatureList.FeatureRecord))
                target.FeatureList.FeatureRecord.append(r)
        for script in target.ScriptList.ScriptRecord:
            for lang in [script.Script.DefaultLangSys] + [
                l.LangSys for l in script.Script.LangSysRecord
            ]:
                if lang is not None:
                    lang.FeatureIndex.extend(added)
                    lang.FeatureCount = len(lang.FeatureIndex)
        records = target.FeatureList.FeatureRecord
        order = sorted(range(len(records)), key=lambda i: records[i].FeatureTag)
        mapping = {old: new for new, old in enumerate(order)}
        target.FeatureList.FeatureRecord = [records[i] for i in order]
        target.FeatureList.FeatureCount = len(records)
        for script in target.ScriptList.ScriptRecord:
            for lang in [script.Script.DefaultLangSys] + [
                l.LangSys for l in script.Script.LangSysRecord
            ]:
                if lang is not None:
                    lang.FeatureIndex = sorted(mapping[i] for i in lang.FeatureIndex)
                    if lang.ReqFeatureIndex != 65535:
                        lang.ReqFeatureIndex = mapping[lang.ReqFeatureIndex]
    if "GDEF" in scratch:
        new = scratch["GDEF"].table
        old = font["GDEF"].table
        if new.GlyphClassDef:
            old.GlyphClassDef.classDefs.update(new.GlyphClassDef.classDefs)
        if new.LigCaretList:
            records = (
                {
                    n: deepcopy(v)
                    for n, v in zip(
                        old.LigCaretList.Coverage.glyphs, old.LigCaretList.LigGlyph
                    )
                }
                if old.LigCaretList
                else {}
            )
            records.update(
                zip(new.LigCaretList.Coverage.glyphs, new.LigCaretList.LigGlyph)
            )
            names = sorted(records, key=font.getGlyphID)
            old.LigCaretList = otTables.LigCaretList()
            old.LigCaretList.Coverage = otTables.Coverage()
            old.LigCaretList.Coverage.glyphs = names
            old.LigCaretList.LigGlyph = [records[n] for n in names]
            old.LigCaretList.LigGlyphCount = len(names)


def label_stylistic_set(font, tag, label):
    """Attach a readable UI label to an existing stylistic-set feature."""
    record = next(
        r for r in font["GSUB"].table.FeatureList.FeatureRecord if r.FeatureTag == tag
    )
    params = otTables.FeatureParamsStylisticSet()
    params.Version = 0
    params.UINameID = font["name"].addName(label)
    record.Feature.FeatureParams = params
