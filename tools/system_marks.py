"""Keep System marks on the rebuilt bodies through the weight and optical axes."""

from copy import deepcopy

from fontTools.misc.roundTools import otRound
from fontTools.otlLib.builder import buildAnchor, buildCoverage
from fontTools.varLib.builder import buildVarDevTable
from fontTools.varLib.varStore import OnlineVarStoreBuilder, VarStoreInstancer

from font_feature_tools import append_layout_variations
from sans_complete_rebuild import box_center
from system_accents import bounds


def reflected_mark_attachment(font, locations, model):
    """Fill the missing b anchors by reflecting the matching d placement."""
    cmap = font.getBestCmap()
    b, d = (cmap[ord(letter)] for letter in "bd")
    top_and_bottom = {cmap[mark] for mark in (0x0301, 0x0327)}
    store = font["GDEF"].table.VarStore
    axes = font["fvar"].axes
    base_index = len(store.VarData) << 16
    builder = OnlineVarStoreBuilder([axis.axisTag for axis in axes])
    builder.setModel(model)
    instances = [font.getGlyphSet(location=location) for location in locations]
    variations = [VarStoreInstancer(store, axes, font.normalizeLocation(loc)) for loc in locations]
    centers = [sum(box_center(bounds(instance, letter), 0) for letter in (b, d))
               for instance in instances]
    changed = 0
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for wrapped in lookup.SubTable:
            table = getattr(wrapped, "ExtSubTable", wrapped)
            if not hasattr(table, "BaseArray") or not top_and_bottom.intersection(table.MarkCoverage.glyphs):
                continue
            records = dict(zip(table.BaseCoverage.glyphs, table.BaseArray.BaseRecord))
            if b in records or d not in records:
                continue
            record = deepcopy(records[d])
            for index, anchor in enumerate(record.BaseAnchor):
                if anchor is None:
                    continue
                device = getattr(anchor, "XDeviceTable", None)
                original = anchor.XCoordinate
                if device:
                    assert device.DeltaFormat == 0x8000
                    var_index = device.StartSize << 16 | device.EndSize
                    values = [center - original - variation[var_index]
                              for center, variation in zip(centers, variations)]
                else:
                    values = [center - original for center in centers]
                x, var_index = builder.storeMasters(values, round=otRound)
                record.BaseAnchor[index] = buildAnchor(
                    x, anchor.YCoordinate, deviceX=buildVarDevTable(base_index + var_index),
                    deviceY=getattr(anchor, "YDeviceTable", None),
                )
            records[b] = record
            table.BaseCoverage = buildCoverage(records, font.getReverseGlyphMap())
            table.BaseArray.BaseRecord = [records[name] for name in table.BaseCoverage.glyphs]
            table.BaseArray.BaseCount = len(records)
            changed += 1
    append_layout_variations(font, builder.finish())
    return changed
