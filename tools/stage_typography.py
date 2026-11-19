"""Build the selected upright and italic variable fonts for the release."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fontTools.ttLib import TTFont

from adopt_weighting import stamp
from bundle_release import OUT, RECIPE
from code_i_baseline import align_i_baseline
from code_texture_healing import build as build_texture_healing
from repeated_stems import add_monospace_l_pair, add_repeated_stems, fit_monospace_pairs
from specimens import DATA, ROOT
from font_size_calibration import recalibrate


def stage(key, settings, scratch):
    config = DATA["families"][key]
    stem = config["stem"]
    destination = OUT / key / "VF"
    destination.mkdir(parents=True, exist_ok=True)

    upright = ROOT / settings["font"]
    if key == "code":
        upright = scratch / "textured.ttf"
        build_texture_healing(
            ROOT / settings["unhealed_font"], upright, trial=False, default_on=True
        )

    for source, italic in ((upright, False), (ROOT / settings["italic_font"], True)):
        font = TTFont(source, recalcTimestamp=False)
        previous = settings["previous"]
        if key == "code":
            if not italic:
                add_repeated_stems(font)
                previous = settings["unhealed_version"]
            fit_monospace_pairs(font)
            add_monospace_l_pair(font)
            align_i_baseline(font)
        if "previous_point_size" in settings:
            recalibrate(font, settings["previous_point_size"])
        assert font["name"].getDebugName(5) == "Version " + previous, source
        stamp(font, previous, settings["version"])
        suffix = "-Italic-VF.ttf" if italic else "-VF.ttf"
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
