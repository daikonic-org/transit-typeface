"""Actual-font comparison of approved faces with Regular-anchored studies."""

from io import BytesIO
from pathlib import Path
import json
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import uharfbuzz as hb
from specimens import Panel, DATA

ROOT = Path(__file__).resolve().parents[1]


def main():
    fragments = []
    reference = DATA["families"]["sans"]
    label = Panel("labels", reference)
    label.text("REGULAR-ANCHORED WEIGHT STUDY", 28, 34, 22, 400, "#194454")
    label.text(
        "Approved current fonts at left. Generated studies at right. No released fonts changed.",
        28,
        60,
        14,
        400,
        "#194454",
    )
    label.text("CURRENT", 28, 100, 12, 400, "#194454")
    label.text("REGULAR-ANCHORED STUDY", 620, 100, 12, 400, "#194454")
    fragments.append(label.body())
    y = 145
    for key, weight in [
        ("sans", 350),
        ("system", 350),
        ("code", 350),
        ("sans", 600),
        ("system", 600),
    ]:
        cfg = DATA["families"][key]
        l = Panel("label-" + key + str(weight), reference)
        l.text(cfg["title"] + " " + str(weight), 28, y, 13, 400, "#194454")
        fragments.append(l.body())
        y += 58
        for side, x in [("current", 28), ("study", 620)]:
            if side == "current":
                f = instantiateVariableFont(
                    TTFont(ROOT / cfg["font"]),
                    {"wght": weight, **({"opsz": 14} if key == "system" else {})},
                    inplace=False,
                )
            else:
                f = TTFont(
                    ROOT
                    / ".build/weight-studies/approved-regular-ratio-1"
                    / f'{key}-{weight}{"-opsz14"if key=="system"else""}.ttf'
                )
            stream = BytesIO()
            f.save(stream)
            h = hb.Font(hb.Face(stream.getvalue()))
            h.scale = (f["head"].unitsPerEm,) * 2
            p = Panel(f"{key}-{weight}-{side}", cfg)
            p.instances[weight] = (f, h)
            p.text("Hno aeo affix", x, y, 44, weight, "#101712", max_width=545)
            p.text(
                "minimum, banana, source -> result",
                x,
                y + 35,
                14,
                weight,
                "#101712",
                max_width=545,
            )
            fragments.append(p.body())
        y += 80
    label2 = Panel("footer", reference)
    label2.text(
        "Studies retain declared design locks and matched metrics. A generic filter is not a finished optical master.",
        28,
        y + 10,
        12,
        400,
        "#194454",
    )
    fragments.append(label2.body())
    height = y + 35
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}"><rect width="1200" height="{height}" fill="#EEECD9"/>'
        + "".join(fragments)
        + "</svg>"
    )
    (ROOT / "docs/Regular-Anchor-Study.svg").write_text(svg)
    print("Generated controlled study comparison SVG")


if __name__ == "__main__":
    main()
