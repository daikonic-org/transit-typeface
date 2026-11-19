"""Stage the coordinated release's selected variable fonts."""

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
from specimens import DATA, ROOT


def stage(key, settings, scratch):
    config = DATA["families"][key]
    stem = config["stem"]
    folder = OUT / key
    destination = folder / "VF"
    source = ROOT / settings["font"]
    if settings.get("reuse"):
        assert settings["previous"] == settings["version"]
        shutil.copytree(source.parent.parent, folder, dirs_exist_ok=True)
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
    selection.write_text(json.dumps({
        "family": config["name"],
        "version": settings["version"],
        "status": "release",
        "weight_range": [config["light"], config["heavy"]],
    }, indent=2) + "\n")
    return str(selection.relative_to(ROOT))


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        selections = {
            key: stage(key, settings, Path(tmp))
            for key, settings in RECIPE["typography"].items()
        }
    (ROOT / "specimens/font-selections.json").write_text(json.dumps(selections, indent=2) + "\n")
