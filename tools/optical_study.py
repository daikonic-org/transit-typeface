"""Default-preserving compatible optical deltas for Sans and Code review fonts."""

from copy import deepcopy
from pathlib import Path
import json
import math
import unicodedata
from fontTools.ttLib import TTFont
from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables._f_v_a_r import Axis, NamedInstance
from fontTools.ttLib.tables import otTables
from fontTools.varLib.models import VariationModel, normalizeValue
from fontTools.varLib.builder import buildVarData, buildVarRegion
from fontTools.otlLib.builder import buildStatTable
from specimens import ROOT, specimen_families
from layout_extensions import add_code_marks

OUT = ROOT / "trials/2026-11-17-layout-optical"
RECIPE = json.loads((ROOT / "recipes/optical-trial.json").read_text())


def identify(font):
    roots = {}
    for cp, name in font.getBestCmap().items():
        char = chr(cp)
        roots.setdefault(
            name, (unicodedata.normalize("NFD", char)[0], unicodedata.category(char))
        )
    return roots


def deformation(glyph, profile, root, protected=False):
    coords = getattr(glyph, "coordinates", GlyphCoordinates())
    if protected or not len(coords):
        return GlyphCoordinates([(0, 0)] * len(coords))
    result = []
    start = 0
    char, category = root
    for end in glyph.endPtsOfContours:
        points = list(coords[start : end + 1])
        count = len(points)
        area = sum(
            points[i][0] * points[(i + 1) % count][1]
            - points[(i + 1) % count][0] * points[i][1]
            for i in range(count)
        )
        radius = profile["outer"] if area < 0 else profile["counter"]
        if category[0] in ("P", "S", "M"):
            radius = profile["punctuation"]
        for i, (x, y) in enumerate(points):
            before = points[(i - 1) % count]
            after = points[(i + 1) % count]
            dx = after[0] - before[0]
            dy = after[1] - before[1]
            length = math.hypot(dx, dy)
            ox = -dy / length * radius if length else 0
            oy = dx / length * radius if length else 0
            result.append((x + ox, y + oy))
        start = end + 1
    # Preserve baseline, descender and cap-height extents while adjusting stroke.
    low = min(y for x, y in coords)
    high = max(y for x, y in coords)
    b = min(y for x, y in result)
    t = max(y for x, y in result)
    sy = (high - low) / (t - b) if t > b else 1
    result = [(x, low + (y - b) * sy) for x, y in result]
    l = min(x for x, y in coords)
    r = max(x for x, y in coords)
    cy = (low + high) / 2
    aperture = profile["aperture"]
    if char.lower() in ("c", "e", "s") and aperture:
        adjusted = []
        for (x, y), (oldx, oldy) in zip(result, coords):
            right = max(
                0, min(1, (oldx - (l + 0.65 * (r - l))) / max(1, 0.35 * (r - l)))
            )
            left = (
                max(0, min(1, ((l + 0.35 * (r - l)) - oldx) / max(1, 0.35 * (r - l))))
                if char.lower() == "s"
                else 0
            )
            shift = aperture * (
                right if oldy > cy else -left if char.lower() == "s" else -right
            )
            # Limit movement away from vertical extremes.
            fade = max(0, min(1, (oldy - low) / 25, (high - oldy) / 25))
            adjusted.append((x, y + shift * fade))
        result = adjusted
    tracking = profile["tracking"]
    return GlyphCoordinates(
        [(x - bx + tracking / 2, y - by) for (x, y), (bx, by) in zip(result, coords)]
    )


def append_axis_to_store(store):
    for region in store.VarRegionList.Region:
        axis = otTables.VarRegionAxis()
        axis.StartCoord = axis.PeakCoord = axis.EndCoord = 0
        region.VarRegionAxis.append(axis)
    store.VarRegionList.RegionAxisCount += 1


def tracking_hvar(font, advances):
    table = font["HVAR"].table
    store = table.VarStore
    new_regions = []
    for support in [(-1, -1, 0), (0, 1, 1)]:
        new_regions.append(len(store.VarRegionList.Region))
        store.VarRegionList.Region.append(
            buildVarRegion({"opsz": support}, ["wght", "opsz"])
        )
    store.VarRegionList.RegionCount = len(store.VarRegionList.Region)
    oldmap = (
        table.AdvWidthMap.mapping
        if table.AdvWidthMap
        else {n: i for i, n in enumerate(font.getGlyphOrder())}
    )
    mapping = {}
    cache = {}
    for name in font.getGlyphOrder():
        old = oldmap[name]
        factor = advances.get(name, 0)
        key = (old, factor)
        if key not in cache:
            data = store.VarData[old >> 16]
            row = list(data.Item[old & 65535]) + [8 * factor, -6 * factor]
            new = buildVarData(
                list(data.VarRegionIndex) + new_regions, [row], optimize=False
            )
            cache[key] = len(store.VarData) << 16
            store.VarData.append(new)
        mapping[name] = cache[key]
    store.VarDataCount = len(store.VarData)
    table.AdvWidthMap = otTables.VarIdxMap()
    table.AdvWidthMap.mapping = mapping


def build_family(key):
    cfg = specimen_families()[key]
    pinned = json.loads((ROOT / "recipes/layout-sources.json").read_text())[key]
    source = ROOT / pinned["font"]
    font = TTFont(source)
    font.recalcTimestamp = False
    weights = sorted(
        {a.coordinates["wght"] for a in font["fvar"].instances}
        | {
            font["fvar"].axes[0].minValue,
            font["fvar"].axes[0].defaultValue,
            font["fvar"].axes[0].maxValue,
        }
    )
    axis = font["fvar"].axes[0]
    triple = (axis.minValue, axis.defaultValue, axis.maxValue)
    model = VariationModel(
        [
            {"wght": normalizeValue(w, triple)} if w != axis.defaultValue else {}
            for w in weights
        ],
        axisOrder=["wght"],
    )
    glyphsets = {w: font.getGlyphSet(location={"wght": w}) for w in weights}
    # Materialize compatible instantiated points; all source glyphs are simple.
    from fontTools.varLib.instancer import instantiateVariableFont

    instances = {
        w: instantiateVariableFont(deepcopy(font), {"wght": w}, inplace=True)
        for w in weights
    }
    roots = identify(font)
    advance_factors = {}
    for name in font.getGlyphOrder():
        protected = name in RECIPE["protected"] or name.startswith(
            tuple(RECIPE["protected_prefixes"])
        )
        root = roots.get(name, ("", "Cn"))
        if font["hmtx"][name][0] and root[1][0] != "M":
            advance_factors[name] = 2 if name in ("fi", "fl", "a_i", "l_i") else 1
        for profile_name, support in [("small", (-1, -1, 0)), ("display", (0, 1, 1))]:
            profile = RECIPE["families"][key][profile_name]
            all_deltas = []
            for weight in weights:
                g = instances[weight]["glyf"][name]
                delta = deformation(g, profile, root, protected)
                tracking = profile["tracking"] * advance_factors.get(name, 0)
                if protected and tracking:
                    delta = GlyphCoordinates(
                        [(tracking / 2, 0)] * len(getattr(g, "coordinates", []))
                    )
                delta.extend([(0, 0), (tracking, 0), (0, 0), (0, 0)])
                all_deltas.append(delta)
            for delta, weight_support in zip(
                model.getDeltas(all_deltas), model.supports
            ):
                if any(abs(x) > 0.001 or abs(y) > 0.001 for x, y in delta):
                    font["gvar"].variations.setdefault(name, []).append(
                        TupleVariation(
                            {**weight_support, "opsz": support},
                            [(otRound(x), otRound(y)) for x, y in delta],
                        )
                    )
    optical = Axis()
    optical.axisTag = "opsz"
    optical.minValue = 10
    optical.defaultValue = 14
    optical.maxValue = 36
    optical.flags = 0
    optical.axisNameID = font["name"].addName("Optical size")
    font["fvar"].axes.append(optical)
    for i in font["fvar"].instances:
        i.coordinates["opsz"] = 14
    for optical_size, label in [(10, "Caption"), (36, "Display")]:
        i = NamedInstance()
        i.subfamilyNameID = font["name"].addName(
            ("Book" if key == "code" else "Regular") + " " + label
        )
        i.coordinates = {"wght": axis.defaultValue, "opsz": optical_size}
        font["fvar"].instances.append(i)
    if "avar" in font:
        font["avar"].segments["opsz"] = {-1.0: -1.0, 0.0: 0.0, 1.0: 1.0}
    for tag in ["HVAR", "MVAR", "GDEF"]:
        if tag in font:
            table = font[tag].table
            store = getattr(table, "VarStore", None)
            if store:
                append_axis_to_store(store)
    if key == "sans":
        tracking_hvar(font, advance_factors)
    if key == "code":
        add_code_marks(font, OUT / key / "optical-mark-attachment.json")
    buildStatTable(
        font,
        [
            {
                "tag": "wght",
                "name": "Weight",
                "values": [
                    {
                        "value": w,
                        "name": {
                            300: "Light",
                            350: "Book",
                            400: "Regular",
                            500: "Medium",
                            600: "SemiBold",
                        }[w],
                    }
                    for w in weights
                ],
            },
            {
                "tag": "opsz",
                "name": "Optical size",
                "values": [
                    {"value": 10, "name": "Caption"},
                    {"value": 14, "name": "Text", "flags": 2},
                    {"value": 36, "name": "Display"},
                ],
            },
        ],
    )
    family = cfg["name"] + " Optical Study"
    old = font["name"].getDebugName(16)
    for record in font["name"].names:
        text = (
            record.toUnicode()
            .replace(old, family)
            .replace(old.replace(" ", ""), family.replace(" ", ""))
        )
        record.string = text.encode(record.getEncoding())
    font["head"].fontRevision = 0.001
    for record in font["name"].names:
        if record.nameID == 5:
            record.string = "Version 0.001; optical-size review trial".encode(
                record.getEncoding()
            )
    path = OUT / key / (family.replace(" ", "") + "-VF.ttf")
    font.save(path)
    return path


def main():
    OUT.mkdir(exist_ok=True)
    result = {}
    for key in ("sans", "code"):
        (OUT / key).mkdir(exist_ok=True)
        result[key] = str(build_family(key).relative_to(ROOT))
        print(result[key], flush=True)
    (OUT / "optical-fonts.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
