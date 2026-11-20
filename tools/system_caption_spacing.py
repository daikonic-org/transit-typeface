"""Build a review cut of System with more advance at small optical sizes."""

import argparse
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from fontTools.misc.fixedTools import floatToFixedToFloat
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.builder import buildVarData, buildVarRegion
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.varLib.models import normalizeValue, supportScalar
import ots

from specimens import ROOT

SOURCE = ROOT / "releases/2026.11.19.3/system/VF"
SMALL_TEXT = 12


def spacing_deltas(font):
    axis = next(axis for axis in font["fvar"].axes if axis.axisTag == "opsz")
    coordinates = axis.minValue, axis.defaultValue, axis.maxValue
    breakpoint = floatToFixedToFloat(normalizeValue(SMALL_TEXT, coordinates), 14)
    caption = round(font["head"].unitsPerEm * 0.01)
    return coordinates, [((-1.0, -1.0, 0.0), caption),
                         ((-1.0, breakpoint, 0.0), round(caption * (1 + breakpoint)))]


def spacing_glyphs(font):
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    return [
        name for name in font.getGlyphOrder()
        if name != ".notdef" and font["hmtx"][name][0] > 0 and classes.get(name) != 3
    ]


def append_advance_delta(font, name, support, delta):
    points, _ = font["glyf"]._getCoordinatesAndControls(name, font["hmtx"].metrics)
    phantom_deltas = [(0, 0)] * len(points)
    phantom_deltas[-3] = (delta, 0)
    font["gvar"].variations.setdefault(name, []).append(TupleVariation(support, phantom_deltas))


def sync_tabular_one(font):
    """Copy width deltas already shared with zero in HVAR into the glyf metrics."""
    variations = font["gvar"].variations
    for variation in variations["one.tnum"]:
        assert all(point in (None, (0, 0)) for point in variation.coordinates[-4:-2])
    for variation in variations["zero.tnum"]:
        left, right = variation.coordinates[-4:-2]
        delta = (right or (0, 0))[0] - (left or (0, 0))[0]
        if delta:
            append_advance_delta(font, "one.tnum", variation.axes, delta)


def add_spacing(font):
    sync_tabular_one(font)
    _, deltas = spacing_deltas(font)
    axes = [axis.axisTag for axis in font["fvar"].axes]
    hvar = font["HVAR"].table
    store = hvar.VarStore
    mapping = hvar.AdvWidthMap.mapping
    regions = store.VarRegionList.Region
    region_indices = []
    for support, _ in deltas:
        new = buildVarRegion({"opsz": support}, axes)
        index = next((i for i, region in enumerate(regions) if region == new), len(regions))
        if index == len(regions):
            regions.append(new)
        region_indices.append(index)
    store.VarRegionList.RegionCount = len(regions)
    remapped = {}
    for name in spacing_glyphs(font):
        original = mapping[name]
        if original not in remapped:
            row = store.VarData[original >> 16]
            values = dict(zip(row.VarRegionIndex, row.Item[original & 65535]))
            for index, (_, delta) in zip(region_indices, deltas):
                values[index] = values.get(index, 0) + delta
            remapped[original] = len(store.VarData) << 16
            store.VarData.append(buildVarData(list(values), [list(values.values())]))
        mapping[name] = remapped[original]

        # Static instancing and glyf-based renderers read the same advance from gvar.
        for support, delta in deltas:
            append_advance_delta(font, name, {"opsz": support}, delta)
    store.VarDataCount = len(store.VarData)


def verify(source, trial):
    original, revised = TTFont(source), TTFont(trial)
    for table in ("glyf", "hmtx", "fvar", "STAT", "GPOS", "GSUB", "GDEF", "cmap"):
        assert original.getTableData(table) == revised.getTableData(table), table
    coordinates, deltas = spacing_deltas(original)
    expanded = set(spacing_glyphs(original))
    for weight in (300, 350, 500, 600):
        for optical in (coordinates[0], 11, 12, 13, 14, coordinates[1], coordinates[2]):
            location = {"wght": weight, "opsz": optical}
            before, after = (font.getGlyphSet(location=location) for font in (original, revised))
            at = normalizeValue(optical, coordinates)
            offset = sum(delta * supportScalar({"opsz": at}, {"opsz": support})
                         for support, delta in deltas)
            for name in original.getGlyphOrder():
                expected = offset if name in expanded else 0
                assert abs(after[name].width - before[name].width - expected) < 0.01, (
                    weight, optical, name, before[name].width, after[name].width, expected,
                )
    for optical in (coordinates[0], 12, coordinates[1]):
        location = {"wght": 350, "opsz": optical}
        old_static, new_static = [instantiateVariableFont(font, location)
                                  for font in (original, revised)]
        before, after = (font.getGlyphSet(location=location) for font in (original, revised))
        for name in original.getGlyphOrder():
            var_delta = after[name].width - before[name].width
            static_delta = new_static["hmtx"][name][0] - old_static["hmtx"][name][0]
            if name != "one.tnum":
                assert abs(static_delta - var_delta) <= 1, (optical, name, static_delta, var_delta)
            assert old_static["hmtx"][name][1] == new_static["hmtx"][name][1]
        digits = [new_static["hmtx"][name][0] for name in revised.getGlyphOrder()
                  if name.endswith(".tnum") and name.split(".")[0] in
                  ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")]
        assert len(digits) == 10 and len(set(digits)) == 1
    with TemporaryDirectory() as directory:
        checked = Path(directory) / "verified.ttf"
        subprocess.run([ots.OTS_SANITIZE, str(trial), str(checked)], check=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    upright = SOURCE / "DaikonicTransitSystem-VF.ttf"
    for source in (upright, upright.with_name("DaikonicTransitSystem-Italic-VF.ttf")):
        font = TTFont(source, recalcTimestamp=False)
        add_spacing(font)
        family = "Daikonic Transit System"
        trial_family = family + " Caption Spacing"
        for entry in font["name"].names:
            value = entry.toUnicode().replace(family, trial_family).replace(
                family.replace(" ", ""), trial_family.replace(" ", "")
            )
            entry.string = value.encode(entry.getEncoding())
        output = args.directory / source.name.replace("TransitSystem", "TransitSystemCaptionSpacing")
        font.save(output)
        verify(source, output)
        font.flavor = "woff2"
        font.save(output.with_suffix(".woff2"))
        print(output, flush=True)


if __name__ == "__main__":
    main()
