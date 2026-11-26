"""Stage the coordinated release's selected variable fonts."""

from argparse import ArgumentParser
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from fontTools.ttLib import TTFont

from adopt_weighting import stamp
import code_compact_operators as operators
from bundle_release import OUT, RECIPE
import code_hairline_study as hairlines
from code_hairline_toggle import build, default_hairlining, position_lifetime_ampersand, remove_lifetime_toggle, verify, verify_default
from release_metadata import stamp_release
from specimens import DATA, ROOT


def stage(key, settings, scratch, code_build=None):
    config = DATA["families"][key]
    stem = config["stem"]
    folder = OUT / key
    destination = folder / "VF"
    source = ROOT / settings["font"]
    if settings.get("rebuild_code"):
        from code_gpos_compaction import FAMILY
        from release_code import release_font

        destination.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-Italic"):
            input_path = code_build / f"{FAMILY.replace(' ', '')}{suffix}-VF.ttf"
            with release_font(input_path, settings["version"], italic=bool(suffix)) as font:
                font.save(destination / f"{stem}{suffix}-VF.ttf")
    elif settings.get("metadata_source"):
        destination.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-Italic"):
            input_path = ROOT / settings["metadata_source"] / f"{stem}{suffix}-VF.ttf"
            with TTFont(input_path, recalcTimestamp=False) as font:
                stamp_release(font, key, settings["version"])
                font.save(destination / f"{stem}{suffix}-VF.ttf")
    elif settings.get("approved_binary"):
        for label, suffix in (("font", "-VF.ttf"), ("italic_font", "-Italic-VF.ttf")):
            path = destination / (stem + suffix)
            assert path == ROOT / settings[label]
            with TTFont(path) as font:
                assert font["name"].getDebugName(16) == config["name"]
                assert font["name"].getDebugName(5) == "Version " + settings["version"]
    elif settings.get("reuse"):
        assert settings["previous"] == settings["version"]
        shutil.copytree(source.parent.parent, folder, dirs_exist_ok=True)
    elif settings.get("sans_rebuild"):
        from build_sans_italic import build_fonts

        assert key == "sans"
        build_fonts(destination, version=settings["version"])
    elif settings.get("punctuation"):
        from code_punctuation_size import release_font

        destination.mkdir(parents=True, exist_ok=True)
        for variant, suffix in (("font", "-VF.ttf"), ("italic_font", "-Italic-VF.ttf")):
            font = release_font(ROOT / settings[variant], config["name"], settings["version"])
            font.save(destination / (stem + suffix))
    elif settings.get("self_aligning"):
        assert key == "code"
        destination.mkdir(parents=True, exist_ok=True)
        operator_source = ROOT / settings.get("operator_source", settings["font"])
        upright = operators.build(operator_source)
        plain = scratch / "Plain-Operators.ttf"
        upright.save(plain)
        operators.verify(operator_source, plain)
        if settings.get("default_hairlining"):
            default_hairlining(upright)
        italic = TTFont(ROOT / settings["italic_font"], recalcTimestamp=False)
        for font, suffix in ((upright, "-VF.ttf"), (italic, "-Italic-VF.ttf")):
            original_version = font["name"].getDebugName(5).removeprefix("Version ")
            stamp(font, original_version, settings["version"])
            font.save(destination / (stem + suffix))
        if settings.get("default_hairlining"):
            verify_default(plain, destination / (stem + "-VF.ttf"))
    else:
        assert key == "code"
        destination.mkdir(parents=True, exist_ok=True)
        candidate, targets = hairlines.build(source, scratch, shifted=True)
        hairlines.verify(source, candidate, targets, shifted=True)
        upright, aliases = build(source, candidate, scratch, release=True)
        italic = TTFont(ROOT / settings["italic_font"], recalcTimestamp=False)
        remove_lifetime_toggle(italic)
        position_lifetime_ampersand(italic)
        for font, suffix in ((upright, "-VF.ttf"), (italic, "-Italic-VF.ttf")):
            previous = settings["previous"]
            assert font["name"].getDebugName(5) == "Version " + previous
            stamp(font, previous, settings["version"])
            font.save(destination / (stem + suffix))
        verify(source, candidate, destination / (stem + "-VF.ttf"), aliases, release=True)

    selection = folder / "selection.json"
    with TTFont(destination / f"{stem}-VF.ttf") as font:
        weight_axis = next(axis for axis in font["fvar"].axes if axis.axisTag == "wght")
        weight_range = [int(weight_axis.minValue), int(weight_axis.maxValue)]
    selection.write_text(json.dumps({
        "family": config["name"],
        "version": settings["version"],
        "status": "release",
        "weight_range": weight_range,
    }, indent=2) + "\n")
    return str(selection.relative_to(ROOT))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--code-build", type=Path, help="Use an already verified Code rebuild")
    args = parser.parse_args()
    with TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        code_build = args.code_build
        if not code_build and RECIPE["typography"].get("code", {}).get("rebuild_code"):
            from code_gpos_compaction import build as build_code

            code_build = scratch / "code"
            code_build.mkdir()
            build_code(json.loads((ROOT / "recipes/code-rebuild.json").read_text()), None, code_build)
        selections = {
            key: stage(key, RECIPE["typography"][key], scratch, code_build)
            for key in RECIPE["families"]
        }
    selection_path = ROOT / "specimens/font-selections.json"
    existing = json.loads(selection_path.read_text()) if selection_path.exists() else {}
    selection_path.write_text(json.dumps(existing | selections, indent=2) + "\n")
