"""Build the selected upright and italic variable fonts for the release."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fontTools.ttLib import TTFont

from adopt_weighting import stamp
from bundle_release import OUT, RECIPE
from code_texture_healing import build as build_texture_healing, verify as verify_texture
from italic_companions import build as build_italic
from repeated_stems import add_repeated_stems
from specimens import DATA, ROOT


def stage(key, settings, scratch):
    config = {**DATA["families"][key], **settings, "version": settings["previous"]}
    stem = config["stem"]
    destination = OUT / key / "VF"
    destination.mkdir(parents=True, exist_ok=True)
    upright = ROOT / config["font"]
    if key == "code":
        textured = scratch / "textured.ttf"
        build_texture_healing(upright, textured, trial=False)
        verify_texture(upright, textured)
        upright = textured

    italic = build_italic(key, config, scratch, "cursive", descending_f=True)
    for source, suffix in ((upright, "-VF.ttf"), (scratch / italic["font"], "-Italic-VF.ttf")):
        font = TTFont(source, recalcTimestamp=False)
        add_repeated_stems(font)
        stamp(font, settings["previous"], settings["version"])
        font.save(destination / (stem + suffix))

    selection = destination.parent / "selection.json"
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
