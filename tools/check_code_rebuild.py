"""Inventory the released Code design and record its shaping reference."""

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
import csv
import gzip
from hashlib import sha256
from io import BytesIO
from itertools import product
import json
from pathlib import Path
import unicodedata

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.otBase import ValueRecord
from fontTools.ttLib.tables.otTables import Coverage
import uharfbuzz as hb

from font_feature_tools import layout_lookup_records

ROOT = Path(__file__).resolve().parents[1]
RECIPE_PATH = ROOT / "recipes/code-rebuild.json"
STYLES = {"upright": "-VF.ttf", "italic": "-Italic-VF.ttf"}


def descendants(value, cls):
    if isinstance(value, cls):
        yield value
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from descendants(item, cls)
    elif hasattr(value, "__dict__"):
        for item in vars(value).values():
            yield from descendants(item, cls)


def codepoints(font):
    result = defaultdict(list)
    for cp, name in sorted(font.getBestCmap().items()):
        result[name].append(cp)
    return result


def axis_inventory(font):
    names = font["name"]
    stat = font["STAT"].table
    stat_axes = [axis.AxisTag for axis in stat.DesignAxisRecord.Axis]

    def stat_value(value):
        coordinates = (
            {stat_axes[record.AxisIndex]: record.Value for record in value.AxisValueRecord}
            if value.Format == 4 else
            {stat_axes[value.AxisIndex]: {
                field: getattr(value, field) for field in
                ("Value", "NominalValue", "RangeMinValue", "RangeMaxValue", "LinkedValue")
                if hasattr(value, field)
            }}
        )
        return {"name": names.getDebugName(value.ValueNameID), "format": value.Format,
                "flags": value.Flags, "coordinates": coordinates}

    return {
        "axes": {
            axis.axisTag: {"name": names.getDebugName(axis.axisNameID), "flags": axis.flags,
                           "min": axis.minValue, "default": axis.defaultValue, "max": axis.maxValue}
            for axis in font["fvar"].axes
        },
        "instances": [
            {"name": names.getDebugName(item.subfamilyNameID), "coordinates": item.coordinates}
            for item in font["fvar"].instances
        ],
        "avar": font["avar"].segments if "avar" in font else None,
        "stat_axes": stat_axes,
        "stat_values": [stat_value(value) for value in stat.AxisValueArray.AxisValue],
    }


def layout_inventory(font, tag):
    table = font[tag].table
    names = font["name"]
    lookups = []
    for lookup in table.LookupList.Lookup:
        values = Counter(key for record in descendants(lookup.SubTable, ValueRecord)
                         for key, value in vars(record).items() if value)
        lookups.append({
            "type": lookup.LookupType, "flags": lookup.LookupFlag,
            "calls": sorted({record.LookupListIndex for record in layout_lookup_records(lookup.SubTable)}),
            "coverage": sorted({name for coverage in descendants(lookup.SubTable, Coverage)
                                for name in coverage.glyphs}),
            "nonzero_positioning_fields": dict(values),
        })

    features = []
    for record in table.FeatureList.FeatureRecord:
        roots = list(record.Feature.LookupListIndex)
        pending, closure = roots.copy(), set()
        while pending:
            index = pending.pop()
            if index not in closure:
                closure.add(index)
                pending.extend(lookups[index]["calls"])
        params = record.Feature.FeatureParams
        label = names.getDebugName(params.UINameID) if params and hasattr(params, "UINameID") else None
        features.append({"tag": record.FeatureTag, "label": label,
                         "lookups": roots, "reachable": sorted(closure)})

    def language(system):
        return {"features": system.FeatureIndex, "required": None if system.ReqFeatureIndex == 65535
                else system.ReqFeatureIndex}

    scripts = {}
    for record in table.ScriptList.ScriptRecord:
        script = record.Script
        languages = {item.LangSysTag: language(item.LangSys) for item in script.LangSysRecord}
        if script.DefaultLangSys:
            languages["default"] = language(script.DefaultLangSys)
        scripts[record.ScriptTag] = languages
    return {"features": features, "scripts": scripts, "lookups": lookups}


def substitution_inputs(font, layout):
    """Read compiled substitutions as an input dependency graph."""
    labels = defaultdict(set)
    for feature in layout["features"]:
        for i in feature["reachable"]:
            labels[i].add(feature["tag"])

    parents = defaultdict(set)
    for i, lookup in enumerate(font["GSUB"].table.LookupList.Lookup):
        for wrapper in lookup.SubTable:
            table = getattr(wrapper, "ExtSubTable", wrapper)
            edges = [(out, (source,)) for source, target in getattr(table, "mapping", {}).items()
                     for out in ((target,) if isinstance(target, str) else target)]
            edges.extend((out, (source,)) for source, targets in getattr(table, "alternates", {}).items()
                         for out in targets)
            edges.extend((record.LigGlyph, (first, *record.Component))
                         for first, records in getattr(table, "ligatures", {}).items()
                         for record in records)
            for out, inputs in edges:
                parents[out].add((i, tuple(sorted(labels[i])), inputs))
    return parents


def donor(font, name, cps):
    cmap = font.getBestCmap()
    matches = sorted({cmap[cp] for cp in cps if cp in cmap})
    if not matches and name in font.getReverseGlyphMap():
        matches = [name]
    return matches


def canonical_parts(cmap, cps):
    for cp in cps:
        text = unicodedata.normalize("NFD", chr(cp))
        if len(text) > 1 and all(ord(char) in cmap for char in text):
            return [cmap[ord(char)] for char in text]
    return []


def glyph_inventory(font, sans, system, layout, recipe):
    chars = codepoints(font)
    cmap = font.getBestCmap()
    parents = substitution_inputs(font, layout)
    roles = defaultdict(list)
    dependents = defaultdict(set)
    for name in font.getGlyphOrder():
        cps = chars[name]
        glyph = font["glyf"][name]
        advance, lsb = font["hmtx"][name]
        counterpart = donor(sans, name, cps)
        sans_candidates = counterpart
        arrow = recipe["arrow_sequences"].get(name)
        forms = recipe["constructed_forms"].get(name)
        parts = canonical_parts(cmap, cps)
        inputs = [
            {"lookup": lookup, "feature_tags": tags, "glyphs": inputs}
            for lookup, tags, inputs in sorted(parents[name])
        ]
        components = [component.getComponentInfo() for component in glyph.components] if glyph.isComposite() else []
        sources = None

        if forms:
            group = "Drawings assembled from parts"
            parts, operation, sources = forms["parts"], forms["operation"], forms["source"]
            sans_candidates = sorted({name for part in parts for name in donor(sans, part, chars[part])})
        elif arrow or any(0x2190 <= cp <= 0x21FF for cp in cps) or name.startswith(("arrowleft.", "arrowright.")):
            group = "Shared Sans or System arrows"
            if arrow:
                sans_candidates = donor(sans, "", [ord(arrow)])
                system_candidates = donor(system, "", [ord(arrow)])
            else:
                system_candidates = donor(system, name, cps)
            operation = "Adapt shared arrow geometry to the Code operator axis and its cell or token advance."
        elif name.startswith("anglePair"):
            group = "Generated generic states"
            parts = [recipe["generic_state_parts"][name.rsplit(".", 1)[1]]]
            sources = "tools/code_angle_pairs.py"
            operation = "Generate each angle-pair alias from its rebuilt angle or lifetime opening form."
        elif name.startswith("code.genericClose"):
            group = "Generated generic states"
            parts = ["greater.generic.hairline" if name.endswith(".hairline") else "greater.generic"]
            sources = "tools/code_structural_fit.py"
            operation = "Assemble the closing run from the corresponding tall closing angle."
        elif ".heal." in name:
            group = "Texture Healing forms"
            parts = [name.split(".heal.", 1)[0]]
            sans_candidates = donor(sans, parts[0], chars[parts[0]])
            operation = "Generate contextual donor and receiver forms from the rebuilt letters."
            sources = "tools/code_texture_healing.py"
        elif ".hairline" in name:
            group = "Hairline forms"
            parts = [name.split(".hairline", 1)[0]]
            operation = "Add the delimiter echo or lifetime leader to the rebuilt source form."
            sources = "tools/code_hairline_study.py"
        elif parts:
            group, operation = "Canonical composites", "Build from the resolved base and combining marks and verify placement in shaping."
            sans_candidates = sorted({name for part in parts for name in donor(sans, part, chars[part])})
        elif any(chr(cp) in recipe["code_specific_characters"] for cp in cps):
            group, operation = "Code-specific base drawings", "Rebuild the approved Code details using the named Sans glyph as a donor where applicable."
            sources = recipe["construction_sources"].get(name)
        elif any(len(item["glyphs"]) > 1 for item in inputs) or name.endswith((".liga", ".liga.loose")):
            group, operation = "Derived ligatures and symbol shortcuts", "Assemble the silhouette from reviewed parts and preserve the shaped span and carets."
        elif cps and all(unicodedata.category(chr(cp)).startswith("M") for cp in cps):
            group, operation = "Combining marks", "Reuse or adapt the mark drawing and construct a zero-advance mark with variable anchors."
        elif sans_candidates and (cps or not inputs):
            group = "Sans base donors"
            if not glyph.numberOfContours:
                group, operation = "Spacing and empty glyphs", "Build spacing and combining controls with their recorded advances."
            elif any(unicodedata.category(chr(cp)) == "Ll" for cp in cps):
                operation = "Build lowercase from the Sans donor with the Code x-height and cell geometry."
            else:
                operation = "Build from the Sans donor with Code weight, proportions, and grid calibration."
        else:
            group = "Contextual forms and supporting glyphs"
            operation = "Rebuild the visible alternate or internal state from its Code inputs and the named donor when present."

        row = {"glyph": name, "codepoints": [f"U+{cp:04X}" for cp in cps], "sans": sans_candidates,
               "sans_counterpart": counterpart, "operation": operation,
               "construction_reference": sources, "parts": parts,
               "components_in_release": components, "gsub_inputs": inputs,
               "advance_at_default": advance, "left_sidebearing_at_default": lsb,
               "gdef_class": font["GDEF"].table.GlyphClassDef.classDefs.get(name, 0)}
        if group == "Shared Sans or System arrows":
            row["system"] = system_candidates
        roles[group].append(row)
        for parent in set(parts) | {part for part, _ in components} | {
            glyph_name for item in inputs for glyph_name in item["glyphs"]
        }:
            if parent != name:
                dependents[parent].add(name)

    for rows in roles.values():
        for row in rows:
            assert all(part in font.getReverseGlyphMap() for part in row["parts"]), row
            row["dependents"] = sorted(dependents[row["glyph"]])
    return dict(sorted(roles.items()))


def shape(engine, text, flags):
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(engine, buffer, flags)
    return [[engine.glyph_to_string(info.codepoint), info.cluster, pos.x_advance,
             pos.y_advance, pos.x_offset, pos.y_offset]
            for info, pos in zip(buffer.glyph_infos, buffer.glyph_positions)]


def fixtures(feature_tags, recipe):
    for tag, spec in recipe["features"].items():
        if tag in feature_tags:
            for text in spec["texts"]:
                yield {"feature": tag, "text": text,
                       "states": {"default": {}, "off": {tag: False}, "on": {tag: True}}}
    for spec in recipe["interactions"]:
        if all(set(flags) <= feature_tags for flags in spec["flags"]):
            yield {"text": spec["text"], "states": {str(i): flags for i, flags in enumerate(spec["flags"])}}
    for text in (
        "Vec<" * 16 + "T" + ">" * 16, "Vec<" * 17 + "T" + ">" * 17,
        "Vec<" + "x" * 60 + ">", "Vec<" + "x" * 61 + ">",
        "ke\nvi", "x::tail", "1 ± 2", "é é",
    ):
        yield {"text": text, "states": {"default": {}, "literal": {"calt": False, "liga": False}}}


def shaping_inventory(path, feature_tags, recipe):
    engine = hb.Font(hb.Face(path.read_bytes()))
    definitions = list(fixtures(feature_tags, recipe))
    results = []
    for weight, width in product(recipe["sample_coordinates"]["wght"], recipe["sample_coordinates"]["wdth"]):
        coordinates = {"wght": weight, "wdth": width}
        engine.set_variations(coordinates)
        runs = [[shape(engine, fixture["text"], flags) for flags in fixture["states"].values()]
                for fixture in definitions]
        results.append({"coordinates": coordinates, "space_advance": shape(engine, " ", {})[0][2],
                        "runs": runs})
    return {"position_fields": ["glyph", "cluster", "x_advance", "y_advance", "x_offset", "y_offset"],
            "fixtures": definitions, "results": results}


def spacing_witnesses(path, spec, coordinates):
    engine = hb.Font(hb.Face(path.read_bytes()))
    cases = []
    for weight, width in product(coordinates["wght"], coordinates["wdth"]):
        location = {"wght": weight, "wdth": width}
        engine.set_variations(location)
        for text in spec["texts"]:
            before = shape(engine, text, {spec["feature"]: False})
            after = shape(engine, text, {spec["feature"]: True})
            cases.append({"text": text, "coordinates": location, "off": before, "on": after,
                          "advance_delta": sum(g[2] for g in after) - sum(g[2] for g in before)})
    return {"feature": spec["feature"], "cases": cases}


def carets(font):
    table = font["GDEF"].table.LigCaretList

    def caret_value(caret):
        value = {field: getattr(caret, field) for field in ("Format", "Coordinate", "CaretValuePoint")
                 if hasattr(caret, field)}
        device = getattr(caret, "DeviceTable", None)
        if device is not None:
            value["device"] = vars(device)
        return value
    return {name: [caret_value(caret) for caret in glyph.CaretValue]
            for name, glyph in zip(table.Coverage.glyphs, table.LigGlyph, strict=True)}


def build_inventory(recipe, output=None):
    data = {"inputs": {}, "styles": {}, "anchor": recipe["anchor"],
            "generator_sources": recipe["generator_sources"],
            "recipe_sha256": sha256(RECIPE_PATH.read_bytes()).hexdigest()}
    for style, suffix in STYLES.items():
        paths = {key: ROOT / (stem + suffix) for key, stem in recipe["fonts"].items()}
        data["inputs"][style] = {key: {"path": str(path.relative_to(ROOT)),
                                      "sha256": sha256(path.read_bytes()).hexdigest()}
                                 for key, path in paths.items()}
        with ExitStack() as stack:
            fonts = {key: stack.enter_context(TTFont(path)) for key, path in paths.items()}
            code = fonts["code"]
            layout = {tag: layout_inventory(code, tag) for tag in ("GSUB", "GPOS")}
            tags = {record["tag"] for table in layout.values() for record in table["features"]}
            assert tags <= set(recipe["features"]), sorted(tags - set(recipe["features"]))
            metrics = code["OS/2"]
            xml = BytesIO()
            code.saveXML(xml, tables=["GSUB", "GPOS", "GDEF"])
            compiled_layout = xml.getvalue()
            data["styles"][style] = {
                "version": code["name"].getDebugName(5),
                "upm": code["head"].unitsPerEm, "italic_angle": code["post"].italicAngle,
                "vertical_metrics": {"cap_height": metrics.sCapHeight, "x_height": metrics.sxHeight,
                                     "ascent": code["hhea"].ascent, "descent": code["hhea"].descent},
                "coverage": len(code.getBestCmap()), "glyph_count": len(code.getGlyphOrder()),
                "axis_inventory": axis_inventory(code),
                "glyph_groups": glyph_inventory(code, fonts["sans"], fonts["system"], layout["GSUB"], recipe),
                "features": {tag: recipe["features"][tag]["activation"] for tag in sorted(tags)},
                "layout": layout,
                "layout_xml_sha256": sha256(compiled_layout).hexdigest(),
                "carets_at_default": carets(code),
                "spacing": spacing_witnesses(paths["code"], recipe["spacing_witnesses"][style],
                                             recipe["sample_coordinates"]),
                "shaping": shaping_inventory(paths["code"], tags, recipe),
            }
            if output is not None:
                (output / f"layout-{style}.ttx.gz").write_bytes(gzip.compress(compiled_layout, mtime=0))
    return data


def encode(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def write_glyph_index(path, data):
    fields = ("glyph", "codepoints", "sans", "system", "sans_counterpart", "parts",
              "operation", "construction_reference", "dependents")
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=("style", "group", *fields))
        writer.writeheader()
        for style, inventory in data["styles"].items():
            for group, glyphs in inventory["glyph_groups"].items():
                for glyph in glyphs:
                    row = {"style": style, "group": group}
                    for field in fields:
                        value = glyph.get(field)
                        row[field] = " ".join(value) if isinstance(value, list) else value
                    writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--record", type=Path)
    command.add_argument("--check", type=Path)
    args = parser.parse_args()
    recipe = json.loads(RECIPE_PATH.read_text())
    output = args.record.parent if args.record else None
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
    data = build_inventory(recipe, output)
    captured = encode(data)
    if args.record:
        args.record.write_text(captured)
        write_glyph_index(output / "glyphs.csv", data)
        print(f"Recorded {args.record}")
    elif captured != encode(json.loads(args.check.read_text())):
        parser.exit(1, f"Code reference differs from {args.check}\n")
    else:
        print(f"Code reference matches {args.check}")


if __name__ == "__main__":
    main()
