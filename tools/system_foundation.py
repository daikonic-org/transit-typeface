"""Start the System design space from one rebuilt Sans variable font."""

import argparse
from copy import deepcopy
from hashlib import file_digest
import json
from pathlib import Path

from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib.instancer import instantiateVariableFont

from bundle_release import sanitize
from code_weight_width_trial import name_trial
from font_feature_tools import feature_subtables
from font_size_calibration import ensure_system_calibration
from optical_study import append_axis_to_store


FAMILY = "Daikonic Transit System Curve Review"
WEIGHT = (300, 350, 600)
PROFILES = (("Caption", 10, 8, 1.10), ("Text", 14, 5, 1.06), ("Display", 36, 2, 1.0))
OMITTED_LIGATURES = {"a_i", "l_i"}


def remove_hooked_ligatures(font):
    for _, table in feature_subtables(font):
        if not hasattr(table, "ligatures"):
            continue
        for first, forms in list(table.ligatures.items()):
            retained = [form for form in forms if form.LigGlyph not in OMITTED_LIGATURES]
            if retained:
                table.ligatures[first] = retained
            else:
                del table.ligatures[first]


def from_sans(sans):
    if sans["head"].unitsPerEm != 1000 or [a.axisTag for a in sans["fvar"].axes] != ["wght"]:
        raise ValueError("System requires the rebuilt, 1000-unit Sans with its weight axis")
    font = instantiateVariableFont(sans, {"wght": WEIGHT}, inplace=False)
    font.recalcTimestamp = False
    remove_hooked_ligatures(font)

    fvar, names = font["fvar"], font["name"]
    weights = [(names.getDebugName(instance.subfamilyNameID), instance.coordinates["wght"])
               for instance in fvar.instances]
    weight_axis, = fvar.axes
    optical = Axis()
    optical.axisTag, optical.axisNameID, optical.flags = "opsz", names.addName("Optical Size"), 0
    optical.minValue, optical.defaultValue, optical.maxValue = [profile[1] for profile in PROFILES]
    fvar.axes.append(optical)
    if "avar" in font:
        font["avar"].segments["opsz"] = {-1: -1, 0: 0, 1: 1}
    append_axis_to_store(font["HVAR"].table.VarStore)
    append_axis_to_store(font["GDEF"].table.VarStore)

    stem = FAMILY.replace(" ", "")
    instances = []
    for label, size, _, _ in PROFILES:
        for item, (style, _) in zip(fvar.instances, weights):
            instance = deepcopy(item)
            instance.coordinates["opsz"] = size
            instance.subfamilyNameID = names.addName(f"{style} {label}")
            instance.postscriptNameID = names.addName(f"{stem}-{style.replace(' ', '')}{label}")
            instances.append(instance)
    fvar.instances = instances
    buildStatTable(font, [
        {"tag": "wght", "name": "Weight", "values": [
            {"name": style, "value": weight, "flags": 2 if weight == weight_axis.defaultValue else 0}
            for style, weight in weights
        ]},
        {"tag": "opsz", "name": "Optical Size", "values": [
            {"name": label, "value": size, "flags": 2 if size == optical.defaultValue else 0}
            for label, size, _, _ in PROFILES
        ]},
    ])
    font["OS/2"].usWeightClass = int(weight_axis.defaultValue)
    name_trial(font, FAMILY, weight_style="Book", variable=True)
    ensure_system_calibration(font)
    return font


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sans", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "DaikonicTransitSystemFoundation-VF.ttf"
    with TTFont(args.sans, recalcTimestamp=False) as sans:
        font = from_sans(sans)
        font.save(target)
    with TTFont(target) as built:
        sanitize(built)
        with args.sans.open("rb") as stream:
            digest = file_digest(stream, "sha256").hexdigest()
        report = {
            "input": str(args.sans), "source_sha256": digest, "units_per_em": built["head"].unitsPerEm,
            "axes": {axis.axisTag: [axis.minValue, axis.defaultValue, axis.maxValue]
                     for axis in built["fvar"].axes},
            "named_instances": len(built["fvar"].instances),
        }
        (args.output / "foundation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(target)


if __name__ == "__main__":
    main()
