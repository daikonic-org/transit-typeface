"""Add System width presets with horizontal stroke compensation and matching layout."""

from copy import deepcopy
from math import isclose
from string import digits

from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.varLib.builder import buildVarDevTable
from fontTools.varLib.models import VariationModel

from audit import shape_from_glyphs
from sans_direct_weight import near_square_symmetry, offset_corner
from scaling_study import vertical_stem
from system_figures import tabular_substitutions
from transit_width_trial import WIDTHS, add_width, scaled_row, width_ratio, width_regions


def stem_compensation(glyph, thickness):
    """Measure the horizontal correction on existing points before a width change."""
    if len(glyph.coordinates) == 4 and near_square_symmetry(glyph):
        center = (min(x for x, _ in glyph.coordinates) + max(x for x, _ in glyph.coordinates)) / 2
        return GlyphCoordinates((center - x, 0) for x, _ in glyph.coordinates)
    results = []
    start = 0
    for end in glyph.endPtsOfContours:
        ring = [complex(x, y) for x, y in glyph.coordinates[start:end + 1]]
        start = end + 1
        for i, point in enumerate(ring):
            before = next((ring[i - j] for j in range(1, len(ring)) if ring[i - j] != point), point)
            after = next((ring[(i + j) % len(ring)] for j in range(1, len(ring))
                          if ring[(i + j) % len(ring)] != point), point)
            outward = (offset_corner(before, point, after, 1, 2) - point).real
            results.append((-thickness * outward / 2, 0))
    return GlyphCoordinates(results)


def width_corrections(font):
    """Measure at the same weight masters as the upright; keep all y coordinates."""
    weights = sorted({instance.coordinates["wght"] for instance in font["fvar"].instances})
    samples = [{"wght": weight} for weight in weights]
    model = VariationModel([{tag: val for tag, val in font.normalizeLocation(sample).items() if val}
                            for sample in samples], axisOrder=["wght"])
    outlines = [font.getGlyphSet(location=sample) for sample in samples]
    stems = [vertical_stem(shape_from_glyphs(master, "n"), .4) for master in outlines]
    corrections = {}
    for name, glyph in font["glyf"].glyphs.items():
        if glyph.numberOfContours <= 0:
            continue
        masters = [stem_compensation(master[name]._getGlyphAndOffset()[0], stem)
                   for master, stem in zip(outlines, stems)]
        deltas = model.getDeltas(masters)
        for width, support in WIDTHS:
            factor = width_ratio(width)
            for delta, axes in zip(deltas, model.supports):
                points = [(otRound(x * factor), 0) for x, _ in delta]
                if any(x for x, _ in points):
                    corrections.setdefault(name, []).append(
                        TupleVariation(dict(axes) | {"wdth": support}, points + [(0, 0)] * 4)
                    )
    return corrections


def scale_layout(font):
    """Move horizontal kerning, mark anchors and carets with the width axis."""
    gdef = font["GDEF"].table
    store = gdef.VarStore
    regions = width_regions(store, [axis.axisTag for axis in font["fvar"].axes])
    cache = {}

    def device(value, old):
        if old is not None:
            if old.DeltaFormat != 0x8000:
                raise ValueError("System width expects design-unit layout adjustments")
            index = old.StartSize << 16 | old.EndSize
        else:
            index = 0xFFFFFFFF
        return buildVarDevTable(scaled_row(store, regions, index, value, cache))

    def visit(value):
        if isinstance(value, otTables.Anchor):
            assert value.Format in (1, 3)
            value.XDeviceTable = device(value.XCoordinate, getattr(value, "XDeviceTable", None))
            value.YDeviceTable = getattr(value, "YDeviceTable", None)
            value.Format = 3
        elif isinstance(value, otTables.CaretValue):
            assert value.Format in (1, 3)
            value.DeviceTable = device(value.Coordinate, getattr(value, "DeviceTable", None))
            value.Format = 3
        elif isinstance(value, list):
            for entry in value:
                visit(entry)
        elif hasattr(value, "__dict__"):
            for entry in vars(value).values():
                visit(entry)

    def values(table, key, records):
        format = getattr(table, key)
        for prop, value_bit, dev, device_bit in (
            ("XPlacement", 1, "XPlaDevice", 0x10), ("XAdvance", 4, "XAdvDevice", 0x40)
        ):
            if format & value_bit:
                format |= device_bit
                for record in records:
                    if record is not None:
                        setattr(record, dev, device(getattr(record, prop, 0), getattr(record, dev, None)))
        setattr(table, key, format)

    for lookup in font["GPOS"].table.LookupList.Lookup:
        for wrapper in lookup.SubTable:
            table = getattr(wrapper, "ExtSubTable", wrapper)
            if isinstance(table, otTables.PairPos):
                if table.Format == 1:
                    rows = [row for group in table.PairSet for row in group.PairValueRecord]
                else:
                    rows = [row for group in table.Class1Record for row in group.Class2Record]
                for i in (1, 2):
                    values(table, f"ValueFormat{i}", [getattr(row, f"Value{i}", None) for row in rows])
            elif isinstance(table, otTables.SinglePos):
                values(table, "ValueFormat", table.Value if table.Format == 2 else [table.Value])
            else:
                visit(table)
    visit(gdef.LigCaretList)


def width_names(font):
    stat = font["STAT"].table
    names = font["name"]
    axis_id = next(i for i, axis in enumerate(stat.DesignAxisRecord.Axis) if axis.AxisTag == "wdth")
    opsz = next(axis.defaultValue for axis in font["fvar"].axes if axis.axisTag == "opsz")
    text_instances = [item for item in font["fvar"].instances if isclose(item.coordinates["opsz"], opsz)]
    for width, label in ((94, "Narrow"), (100, "Normal"), (108, "Wide")):
        value = otTables.AxisValue()
        value.Format, value.AxisIndex, value.Flags = 1, axis_id, 2 if width == 100 else 0
        value.Value, value.ValueNameID = width, names.addName(label)
        stat.AxisValueArray.AxisValue.append(value)
        if width == 100:
            continue
        for text in text_instances:
            instance = deepcopy(text)
            instance.coordinates["wdth"] = width
            style = names.getDebugName(text.subfamilyNameID).replace(" Text", "")
            instance.subfamilyNameID = names.addName(f"{style} {label}")
            prefix = names.getBestFamilyName().replace(" ", "")
            instance.postscriptNameID = names.addName(prefix + "-" + style.replace(" ", "") + label)
            font["fvar"].instances.append(instance)
    stat.AxisValueCount = len(stat.AxisValueArray.AxisValue)


def add_system_width(font):
    font["glyf"].ensureDecompiled()
    deferred = width_corrections(font)
    pairs = tabular_substitutions(font)
    cmap = font.getBestCmap()
    grids = {pairs[cmap[ord(char)]]: 2 for char in digits}
    grids.update({pairs[cmap[ord(char)]]: 1 for char in ".,:"})
    add_width(font, scale_layout=scale_layout, grids=grids)
    for name, tuples in deferred.items():
        font["gvar"].variations[name].extend(tuples)
    width_names(font)
