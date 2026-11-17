"""Actual shaped before/after dot and bounded generic-angle review sheets."""

import json
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from dot_palette import OUT
from dot_inventory import dots
from specimens import ROOT, DATA, Panel
from adopt_weighting import instance
from code_balance_study import bind


def main():
    recipe = json.loads((ROOT / "recipes/syntax-numeral-trial.json").read_text())
    files = json.loads((OUT / "fonts.json").read_text())
    parts = []
    for row, key in enumerate(["sans", "system", "code"]):
        y = 40 + row * 315
        for col, (title, path) in enumerate(
            [
                ("Current", ROOT / recipe["inputs"][key]["font"]),
                ("Shared-dot trial", ROOT / files[key]),
            ]
        ):
            x = 25 + col * 650
            p = Panel(key + str(col), DATA["families"][key])
            f = instance(path, 350, 14 if key == "system" else None)
            bind(p, f)
            p.text(key.title() + " / " + title, x, y, 22, 400, "#194454")
            p.text(
                "i j . : ; ! ? · ÷ … •", x, y + 70, 43, 400, "#101712", max_width=600
            )
            p.text(
                "Wait... really?!  naïve  façade  q̇  Ä",
                x,
                y + 125,
                26,
                400,
                "#101712",
                max_width=600,
            )
            p.text(
                "items?.field  value!.next  Type::name",
                x,
                y + 177,
                23,
                400,
                "#101712",
                max_width=600,
            )
            p.text("Light   Book   Regular", x, y + 222, 15, 400, "#194454")
            for wi, w in enumerate([300, 350, 400]):
                label = Panel(key + str(col) + str(w), DATA["families"][key])
                bind(label, instance(path, w, 14 if key == "system" else None))
                label.text(
                    "i . ! ? …",
                    x + wi * 200,
                    y + 267,
                    29,
                    400,
                    "#101712",
                    max_width=185,
                )
                parts.append(label.body())
            parts.append(p.body())
    (OUT / "Comparison.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="960"><rect width="1300" height="960" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    syntax = ROOT / "trials/2026-11-17-syntax-numerals"
    fontpaths = json.loads((syntax / "fonts.json").read_text())
    f = instance(ROOT / fontpaths["code"], 350, None)
    p = Panel("angles", DATA["families"]["code"])
    bind(p, f)
    p.text("Code / comparison and generic angles", 30, 40, 25, 400, "#194454")
    for text, y in [
        ("a < b    a<b    Vec<T>    Vec<Vec<T>>", 115),
        ("fn parse<'a>(value: &'a str) -> Result<T, E>", 185),
        ("a > b    a>b    Result<T, E>    [T] {T} (T)", 255),
    ]:
        p.text(text, 30, y, 32, 400, "#101712", max_width=1230)
    elements = [p.body()]
    for col, (name, label) in enumerate(
        [
            ("less", "comparison <"),
            ("less.generic", "generic <"),
            ("greater.generic", "generic >"),
            ("bracketleft", "bracket"),
        ]
    ):
        x = 80 + col * 320
        scale = 0.24
        base = 505
        gs = f.getGlyphSet()
        pen = SVGPathPen(gs)
        gs[name].draw(pen)
        cap = f["OS/2"].sCapHeight
        elements.append(
            f'<path d="{pen.getCommands()}" transform="translate({x} {base}) scale({scale} {-scale})" fill="#101712"/>'
        )
        for yy in [base, base - cap * scale]:
            elements.append(
                f'<path d="M{x-20},{yy} h220" stroke="#C06D3E" stroke-width="1"/>'
            )
        p2 = Panel("label" + name, DATA["families"]["code"])
        bind(p2, f)
        p2.text(label, x - 10, 560, 19, 400, "#194454")
        elements.append(p2.body())
    annotation = Panel("annotation", DATA["families"]["code"])
    bind(annotation, f)
    annotation.text(
        "Orange guides: baseline and cap height. Generic angles stay within both.",
        30,
        620,
        18,
        400,
        "#194454",
    )
    elements.append(annotation.body())
    (OUT / "Angles.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="650"><rect width="1300" height="650" fill="#EEECD9"/>'
        + "".join(elements)
        + "</svg>"
    )
    print("Dot comparison and angle proofs generated")


if __name__ == "__main__":
    main()
