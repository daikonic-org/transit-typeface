"""Build Transit Code and System width presets from their variable fonts."""

import argparse
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from fontTools.otlLib.builder import buildStatTable
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont, TTCollection
from fontTools.varLib.instancer import instantiateVariableFont
import ots
import uharfbuzz as hb

from code_hairline_study import shape
from transit_width_trial import SOURCES, add_width, verify as verify_width, verify_code_grid

FAMILY = "Daikonic Transit Code Weight Width Trial"
STEM = FAMILY.replace(" ", "")
WEIGHTS = {350: "Book", 400: "Regular", 500: "Medium"}
CODE_SOURCE_WEIGHTS = {350: 300, 375: 325, 400: 350, 450: 375, 500: 400}
WIDTH_PRESETS = {94: "Narrow", 100: "", 108: "Wide"}
SYSTEM_WEIGHTS = {300: "Light", 350: "Book", 400: "Regular", 500: "Medium", 600: "SemiBold"}


def name_trial(font, family, weight_style="Regular", width=100, *, variable=False):
    italic = bool(font["head"].macStyle & 2)
    width_style = WIDTH_PRESETS[width]
    parts = [weight_style, width_style, "Italic" if italic else ""]
    if weight_style == "Regular" and not width_style and italic:
        parts[0] = ""
    style = " ".join(filter(None, parts))
    stem = family.replace(" ", "")
    legacy_styles = [entry for entry in (weight_style if weight_style != "Regular" else "",
                                          width_style) if entry]
    legacy_family = " ".join([family, *legacy_styles])
    legacy_style = "Italic" if italic else "Regular"
    full_name = family + ("" if style == "Regular" else " " + style)
    suffix = ("Italic-VF" if italic else "VF") if variable else style.replace(" ", "")
    ps_name = f"{stem}-{suffix}"
    version = font["name"].getDebugName(5)
    for name_id, value in {
        1: legacy_family, 2: legacy_style, 3: f"{ps_name}; {version}",
        4: full_name, 6: ps_name, 16: family, 17: style,
        25: stem + ("Italic" if italic else ""),
    }.items():
        font["name"].removeNames(nameID=name_id)
        font["name"].setName(value, name_id, 3, 1, 0x409)
        font["name"].setName(value, name_id, 1, 0, 0)
    return ps_name


def recalibrate(font):
    italic = bool(font["head"].macStyle & 2)
    axis, = font["fvar"].axes
    axis.minValue, axis.defaultValue, axis.maxValue = 350, 400, 500
    for instance in font["fvar"].instances:
        weight = {300: 350, 350: 400, 400: 500}[instance.coordinates["wght"]]
        instance.coordinates["wght"] = weight
        style = WEIGHTS[weight]
        if italic:
            style = "Italic" if weight == 400 else style + " Italic"
        instance.subfamilyNameID = font["name"].addName(style)
        instance.postscriptNameID = font["name"].addName(STEM + "-" + style.replace(" ", ""))
    font["OS/2"].usWeightClass = 400
    if not italic:
        font["OS/2"].fsSelection |= 1 << 6

    axes = [{
        "tag": "wght", "name": "Weight",
        "values": [{"value": weight, "name": style, "flags": 2 if weight == 400 else 0}
                   for weight, style in WEIGHTS.items()],
    }]
    if italic:
        axes.append({"tag": "ital", "name": "Italic", "values": [{"value": 1, "name": "Italic"}]})
    buildStatTable(font, axes)
    add_width(font, scale_carets=True)
    return name_trial(font, FAMILY, variable=True)


def verify(source, variable_path):
    original, trial = TTFont(source), TTFont(variable_path)
    verify_code_grid(source, variable_path, original, trial,
                     weight_pairs=tuple((old, new) for new, old in CODE_SOURCE_WEIGHTS.items()))
    original_engine, trial_engine = [
        hb.Font(hb.Face(path.read_bytes())) for path in (source, variable_path)
    ]
    for weight, source_weight in CODE_SOURCE_WEIGHTS.items():
        before_location = {"wght": source_weight}
        after_location = {"wght": weight, "wdth": 100}
        original_engine.set_variations(before_location)
        trial_engine.set_variations(after_location)
        for sample in ("minimum_width", "parse::<Vec<T>>()", "a === b || c !== d",
                       "fn load<'a>(arg: &'a str)", "x ->> y => z"):
            assert shape(original, original_engine, sample, {}) == shape(
                trial, trial_engine, sample, {}
            ), (weight, sample)
        old = original.getGlyphSet(location=before_location)
        new = trial.getGlyphSet(location=after_location)
        for name in original.getGlyphOrder():
            a, b = RecordingPen(), RecordingPen()
            old[name].draw(a)
            new[name].draw(b)
            assert a.value == b.value, (weight, name)


def sanitize(path):
    with TemporaryDirectory() as tmp:
        subprocess.run([ots.OTS_SANITIZE, str(path), str(Path(tmp) / "checked.ttf")],
                       check=True, capture_output=True)


def build_static(variable_paths, output, family, weights):
    paths = []
    for variable_path in variable_paths:
        variable = TTFont(variable_path)
        defaults = {axis.axisTag: axis.defaultValue for axis in variable["fvar"].axes}
        for weight, style in weights.items():
            for width in WIDTH_PRESETS:
                static = instantiateVariableFont(variable, defaults | {"wght": weight, "wdth": width})
                ps_name = name_trial(static, family, style, width)
                if weights is WEIGHTS:
                    assert static["hmtx"]["space"][0] == 6 * width
                path = output / "TTF" / (ps_name + ".ttf")
                static.save(path)
                sanitize(path)
                paths.append(path)
    collection = TTCollection()
    collection.fonts = [TTFont(path) for path in paths]
    assert len({font["name"].getDebugName(6) for font in collection.fonts}) == len(paths)
    collection_path = output / "TTC" / (family.replace(" ", "") + ".ttc")
    collection.save(collection_path)
    with TTCollection(collection_path) as result:
        assert len(result.fonts) == 2 * len(weights) * len(WIDTH_PRESETS)
        assert {font["name"].getDebugName(16) for font in result.fonts} == {family}
    print(collection_path, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--family", choices=SOURCES, default="code")
    args = parser.parse_args()
    folder, stem = SOURCES[args.family]
    code = args.family == "code"
    family = FAMILY if code else "Daikonic Transit System Width Trial"
    for directory in ("VF", "TTF", "WOFF2", "TTC"):
        (args.output / directory).mkdir(parents=True, exist_ok=True)

    variable_paths = []
    for suffix in ("-VF.ttf", "-Italic-VF.ttf"):
        source = folder / (stem + suffix)
        font = TTFont(source, recalcTimestamp=False)
        if code:
            ps_name = recalibrate(font)
        else:
            add_width(font)
            italic = bool(font["head"].macStyle & 2)
            for name in font["name"].names:
                original = "Daikonic Transit System Caption Spacing"
                new_name = name.toUnicode().replace(original, family).replace(
                    original.replace(" ", ""), family.replace(" ", "")
                )
                name.string = new_name.encode(name.getEncoding())
            ps_name = family.replace(" ", "") + ("-Italic-VF" if italic else "-VF")
        variable_path = args.output / "VF" / (ps_name + ".ttf")
        font.save(variable_path)
        if code:
            sanitize(variable_path)
            verify(source, variable_path)
        else:
            verify_width(source, variable_path, args.family)
        font.flavor = "woff2"
        web_path = args.output / "WOFF2" / (ps_name + ".woff2")
        font.save(web_path)
        sanitize(web_path)
        variable_paths.append(variable_path)
    preset_family = family.replace(" Trial", " Presets")
    build_static(variable_paths, args.output, preset_family, WEIGHTS if code else SYSTEM_WEIGHTS)


if __name__ == "__main__":
    main()
