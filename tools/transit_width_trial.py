"""Build modest affine width prototypes for the Transit System and Code families."""

import argparse
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib.builder import buildVarData, buildVarDevTable, buildVarRegion
from fontTools.varLib.iup import iup_delta
from fontTools.varLib.varStore import VarStoreInstancer
import uharfbuzz as hb
import ots

from code_hairline_study import shape
from optical_study import append_axis_to_store
from specimens import ROOT

SOURCES = {
    "system": (ROOT / "trials/2026-11-19-system-caption-spacing",
               "DaikonicTransitSystemCaptionSpacing"),
    "code": (ROOT / "releases/2026.11.19.3/code/VF", "DaikonicTransitCode"),
}
WIDTHS = ((94, (-1, -1, 0)), (108, (0, 1, 1)))


def width_ratio(width):
    return (width - 100) / 100


def rounded_width_delta(value, factor, multiple=1):
    return multiple * otRound(value * factor / multiple)


def extend_outlines(font, grids):
    glyf = font["glyf"]
    variations = font["gvar"].variations
    for name in font.getGlyphOrder():
        if glyf[name].isComposite():
            assert all(part.getComponentInfo()[1][1:3] == (0, 0)
                       for part in glyf[name].components), name
        base, controls = glyf._getCoordinatesAndControls(name, font["hmtx"].metrics)
        tuples = variations.setdefault(name, [])
        coordinates_by_support = {}
        for variation in tuples:
            key = tuple(sorted(variation.axes.items()))
            coordinates = variation.coordinates
            if None in coordinates:
                coordinates = iup_delta(coordinates, base, controls.endPts)
            accumulator = coordinates_by_support.setdefault(key, [0] * len(base))
            for index, (x, _) in enumerate(coordinates):
                accumulator[index] += x
        coordinates_by_support[()] = [x for x, _ in base]
        for width, support in WIDTHS:
            factor = width_ratio(width)
            for axes, points in coordinates_by_support.items():
                delta = [(otRound(x * factor), 0) for x in points]
                if name in grids:
                    advance = rounded_width_delta(points[-3] - points[-4], factor, grids[name])
                    delta[-3] = (delta[-4][0] + advance, 0)
                if any(x for x, _ in delta):
                    tuples.append(TupleVariation(dict(axes) | {"wdth": support}, delta))


def advance_row(store, index):
    outer, inner = divmod(index, 65536)
    if outer < len(store.VarData):
        data = store.VarData[outer]
        if inner < len(data.Item):
            return dict(zip(data.VarRegionIndex, data.Item[inner]))
    return {}


def width_regions(store, tags):
    append_axis_to_store(store)
    regions = store.VarRegionList.Region
    original_count = len(regions)
    output = []
    for width, support in WIDTHS:
        base_region = len(regions)
        regions.append(buildVarRegion({"wdth": support}, tags))
        crossed = {}
        by_coordinates = {}
        for index in range(original_count):
            source = regions[index]
            coordinates = {tag: (axis.StartCoord, axis.PeakCoord, axis.EndCoord)
                           for tag, axis in zip(tags, source.VarRegionAxis)
                           if axis.PeakCoord}
            if coordinates:
                key = tuple(coordinates.items())
                if key not in by_coordinates:
                    by_coordinates[key] = len(regions)
                    regions.append(buildVarRegion(coordinates | {"wdth": support}, tags))
                crossed[index] = by_coordinates[key]
            else:
                crossed[index] = base_region
        output.append((width_ratio(width), base_region, crossed))
    store.VarRegionList.RegionCount = len(regions)
    return output


def scaled_row(store, basis, index, value, cache, *, multiple=1):
    key = index, value, multiple
    if key not in cache:
        row = advance_row(store, index)
        values = row.copy()
        for factor, base, crossed in basis:
            combined = {base: value}
            for old_region, delta in row.items():
                region = crossed[old_region]
                combined[region] = combined.get(region, 0) + delta
            values.update({region: rounded_width_delta(delta, factor, multiple)
                           for region, delta in combined.items()})
        cache[key] = len(store.VarData) << 16
        store.VarData.append(buildVarData(list(values), [list(values.values())]))
        store.VarDataCount = len(store.VarData)
    return cache[key]


def extend_advances(font, grids):
    hvar = font["HVAR"].table
    assert hvar.AdvWidthMap and not hvar.LsbMap and not hvar.RsbMap
    store = hvar.VarStore
    basis = width_regions(store, [axis.axisTag for axis in font["fvar"].axes])
    mapping = hvar.AdvWidthMap.mapping
    cache = {}
    for name, index in mapping.items():
        mapping[name] = scaled_row(store, basis, index, font["hmtx"][name][0], cache,
                                   multiple=grids.get(name, 1))


def extend_carets(font):
    gdef = font["GDEF"].table
    store = gdef.VarStore
    if gdef.LigCaretList is None:
        return
    tags = [axis.axisTag for axis in font["fvar"].axes]
    regions = store.VarRegionList.Region
    indices = [len(regions) + i for i in range(len(WIDTHS))]
    regions.extend(buildVarRegion({"wdth": support}, tags) for _, support in WIDTHS)
    store.VarRegionList.RegionCount = len(regions)
    carets = [value for glyph in gdef.LigCaretList.LigGlyph for value in glyph.CaretValue]
    coordinates = sorted({caret.Coordinate for caret in carets})
    rows = [[otRound(x * width_ratio(width)) for width, _ in WIDTHS] for x in coordinates]
    outer = len(store.VarData)
    store.VarData.append(buildVarData(indices, rows))
    store.VarDataCount = len(store.VarData)
    indices_by_position = {value: outer << 16 | i for i, value in enumerate(coordinates)}
    for caret in carets:
        assert caret.Format == 1
        caret.Format = 3
        caret.DeviceTable = buildVarDevTable(indices_by_position[caret.Coordinate])


def add_width(font, *, scale_carets=False, scale_layout=None, grids=None):
    grids = grids or {}
    extend_outlines(font, grids)
    axis = Axis()
    axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue = "wdth", 94, 100, 108
    axis.flags = 0
    axis.axisNameID = font["name"].addName("Width")
    font["fvar"].axes.append(axis)
    for instance in font["fvar"].instances:
        instance.coordinates["wdth"] = 100
    if "avar" in font:
        font["avar"].segments["wdth"] = {-1: -1, 0: 0, 1: 1}
    stat = font["STAT"].table
    record = otTables.AxisRecord()
    record.AxisTag, record.AxisNameID = axis.axisTag, axis.axisNameID
    record.AxisOrdering = max(a.AxisOrdering for a in stat.DesignAxisRecord.Axis) + 1
    stat.DesignAxisRecord.Axis.append(record)
    stat.DesignAxisCount = len(stat.DesignAxisRecord.Axis)
    extend_advances(font, grids)
    if scale_layout is not None:
        scale_layout(font)
    else:
        append_axis_to_store(font["GDEF"].table.VarStore)
    if scale_carets:
        extend_carets(font)


def verify(source, output, family):
    original, trial = TTFont(source), TTFont(output)
    assert original.getTableData("glyf") == trial.getTableData("glyf")
    assert original.getTableData("GPOS") == trial.getTableData("GPOS")
    samples = (
        {"wght": weight} | optical
        for weight in (300, 350, 400, 600 if family == "system" else 375)
        for optical in (({"opsz": 10.91}, {"opsz": 12}, {"opsz": 15.27}, {"opsz": 39.27})
                        if family == "system" else ({},))
    )
    for location in samples:
        base = original.getGlyphSet(location=location)
        for width in (94, 97, 100, 104, 108):
            resized = trial.getGlyphSet(location=location | {"wdth": width})
            for name in original.getGlyphOrder():
                try:
                    base_advance = base[name].width
                except IndexError:
                    # The released Code font has two constant advances with missing HVAR rows.
                    base_advance = original["hmtx"][name][0]
                expected = base_advance * width / 100
                error = abs(resized[name].width - expected)
                assert error < (0.000001 if width == 100 else 3), (location, width, name, error)
    if family == "code":
        verify_code_grid(source, output, original, trial)
    with TemporaryDirectory() as tmp:
        subprocess.run([ots.OTS_SANITIZE, str(output), str(Path(tmp) / "checked.ttf")],
                       check=True, capture_output=True)


def verify_code_grid(source, output, original, trial,
                     weight_pairs=((300, 300), (350, 350), (375, 375), (400, 400))):
    samples = (
        ("0123456789", {}),
        ("obj?.value obj!.id", {}),
        ("parse::<Vec<T>>()", {}),
        ("a === b || c !== d", {}),
        ("a == b && c !== d", {"ss06": True}),
        ("x ->> y => z", {}),
        ("map(|| f(x))", {}),
        ("fn load<'a>(arg: &'a str)", {}),
    )
    original_engine, trial_engine = [hb.Font(hb.Face(path.read_bytes())) for path in (source, output)]
    for original_weight, weight in weight_pairs:
        original_engine.set_variations({"wght": original_weight})
        for width in range(94, 109):
            trial_engine.set_variations({"wght": weight, "wdth": width})
            for text, features in samples:
                before = shape(original, original_engine, text, features)
                after = shape(trial, trial_engine, text, features)
                assert [(n, c) for n, c, *_ in before] == [(n, c) for n, c, *_ in after]
                assert [advance * width // 100 for _, _, advance, *_ in before] == [
                    advance for _, _, advance, *_ in after
                ], (weight, width, text)
    old_carets = original["GDEF"].table.LigCaretList.LigGlyph
    new_carets = trial["GDEF"].table.LigCaretList.LigGlyph
    for width, support in WIDTHS:
        instancer = VarStoreInstancer(trial["GDEF"].table.VarStore, trial["fvar"].axes,
                                     {"wdth": support[1]})
        for old, new in zip(old_carets, new_carets):
            for a, b in zip(old.CaretValue, new.CaretValue):
                device = b.DeviceTable
                index = device.StartSize << 16 | device.EndSize
                assert b.Coordinate + instancer[index] == otRound(a.Coordinate * width / 100)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--family", choices=SOURCES, default="system")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    folder, stem = SOURCES[args.family]
    suffixes = ("-VF.ttf", "-Italic-VF.ttf")
    for source in (folder / (stem + suffix) for suffix in suffixes):
        font = TTFont(source, recalcTimestamp=False)
        add_width(font, scale_carets=args.family == "code")
        for record in font["name"].names:
            family = "Daikonic Transit " + args.family.title()
            old = family + (" Caption Spacing" if args.family == "system" else "")
            new = family + " Width Trial"
            value = record.toUnicode().replace(old, new).replace(
                old.replace(" ", ""), new.replace(" ", "")
            )
            record.string = value.encode(record.getEncoding())
        destination = "DaikonicTransit" + args.family.title() + "WidthTrial"
        output = args.output / source.name.replace(stem, destination)
        font.save(output)
        verify(source, output, args.family)
        font.flavor = "woff2"
        font.save(output.with_suffix(".woff2"))
        print(output, flush=True)


if __name__ == "__main__":
    main()
