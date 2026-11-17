"""Matched outline and browser proofs for positioning and optical-size trials."""

from pathlib import Path
import json
from fontTools.ttLib import TTFont
from adopt_weighting import ROOT, instance
from specimens import Panel, DATA, specimen_families
from code_balance_study import bind
import code_balance_study as browser

OUT = ROOT / "trials/2026-11-17-layout-optical"


def write(name, parts, width, height):
    (OUT / (name + ".svg")).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="{width}" height="{height}" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


def main():
    cfg = specimen_families()
    parts = []
    pinned = json.loads((ROOT / "recipes/layout-sources.json").read_text())
    cfg["code"]["font"] = pinned["code"]["font"]
    positioned = OUT / "code/CodePositioned-VF.ttf"
    for col, (label, path) in enumerate(
        [
            ("Current Code / no mark attachment", ROOT / cfg["code"]["font"]),
            ("Code / variable mark attachment", positioned),
        ]
    ):
        p = Panel("position" + str(col), DATA["families"]["code"])
        bind(p, instance(path, 350, None))
        x = 25 + 650 * col
        p.text(label, x, 30, 17, 400, "#194454")
        p.text("q\u0301 x\u0308 i\u0301 j\u0301", x, 140, 68, 400, "#101712")
        p.text("q\u0301\u0308 q\u0326 á a\u0301", x, 255, 68, 400, "#101712")
        p.text("café naïve résumé  ->>  ke  @@", x, 320, 23, 400, "#101712")
        p.text(
            "q\u0301 x\u0308 q\u0301\u0308 q\u0326 i\u0301 j\u0301 ç ą ę ș",
            x,
            370,
            17,
            400,
            "#101712",
        )
        parts.append(p.body())
    write("Positioning", parts, 1300, 405)
    (OUT / "code/Book.svg").write_text((OUT / "Positioning.svg").read_text())
    optical = json.loads((OUT / "optical-fonts.json").read_text())
    for key, relative in optical.items():
        parts = []
        for col, size in enumerate([10, 14, 36]):
            p = Panel(key + str(size), DATA["families"][key])
            bind(p, instance(ROOT / relative, 350, size))
            x = 25 + 430 * col
            p.text(f"{key.title()} Book / opsz {size}", x, 30, 18, 400, "#194454")
            p.text("a e c s o n", x, 110, 56, 400, "#101712")
            p.text("i j l 1 0 @", x, 190, 50, 400, "#101712")
            p.text("Context Menu  coffee", x, 245, 25, 400, "#101712")
            p.text("const snake_case = get_items();", x, 290, 17, 400, "#101712")
            p.text("q\u0301 x\u0308 café naïve résumé", x, 330, 17, 400, "#101712")
            p.text("() [] {} -> != <= >= ::", x, 370, 17, 400, "#101712")
            p.elements.append(
                '<rect x="'
                + str(430 * col)
                + '" y="400" width="430" height="110" fill="#101712"/>'
            )
            p.text("small text / counters / punctuation", x, 435, 14, 400, "#EEECD9")
            p.text("const snake_case = get_items();", x, 470, 13, 400, "#EEECD9")
            parts.append(p.body())
        write("Optical-" + key.title(), parts, 1290, 510)
    browser.OUT = OUT
    browser.browser_proof(
        {
            "Current Code": instance(ROOT / cfg["code"]["font"], 350, None),
            "Code with mark attachment": instance(positioned, 350, None),
            "Optical Code / 10": instance(ROOT / optical["code"], 350, 10),
            "Optical Code / 36": instance(ROOT / optical["code"], 350, 36),
        },
        samples=[
            (14, "q\u0301 x\u0308 q\u0301\u0308 i\u0301 j\u0301 café naïve résumé"),
            (14, "const snake_case = get_items([input]); ->> != <= @@"),
        ],
        title="Transit positioning and optical review — actual browser fonts",
    )
    print("Generated positioning, optical and browser proofs")


if __name__ == "__main__":
    main()
