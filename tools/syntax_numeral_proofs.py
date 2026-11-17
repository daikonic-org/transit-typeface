"""Review syntax groups and optional numeral features using real font shaping."""

import json
from pathlib import Path
from fontTools.ttLib import TTFont
from adopt_weighting import ROOT, instance
from specimens import DATA, Panel, specimen_families
from code_balance_study import bind
from syntax_numeral_study import OUT


def write(name, parts, w, h):
    (OUT / (name + ".svg")).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><rect width="{w}" height="{h}" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


def main():
    files = json.loads((OUT / "fonts.json").read_text())
    cfg = specimen_families()
    parts = []
    for col, (label, path) in enumerate(
        [
            ("Code1.023 / current", ROOT / cfg["code"]["font"]),
            ("Wider equals / syntax trial", ROOT / files["code"]),
        ]
    ):
        p = Panel("code" + str(col), DATA["families"]["code"])
        bind(p, instance(path, 350, None))
        x = 25 + 700 * col
        p.text(label, x, 32, 20, 400, "#194454")
        rows = [
            ("= == === != !== <= >= =>", 70, 33),
            ("a = b; a == b; a === b;", 130, 21),
            ("?.  !.  ${  $[  $(", 200, 29),
            ("..  .=  ..=  ...  …", 265, 29),
            (":=  |=  |-  ##  ###  ####", 330, 27),
            ("Vec<T>  Vec<Vec<T>>  Result<T, E>", 410, 22),
            ("fn parse<'a>(value: &'a str)", 470, 22),
            ("a < b; a > b; a<b; Vec<T>;", 530, 22),
            ("0..10  0..=10  object?.field", 595, 22),
        ]
        for text, y, size in rows:
            p.text(text, x, y, size, 400, "#101712", max_width=650)
        p.elements.append(
            '<rect x="'
            + str(700 * col)
            + '" y="630" width="700" height="125" fill="#101712"/>'
        )
        p.text("fn get<T>(x: T) -> Option<T> {", x, 665, 18, 400, "#EEECD9")
        p.text("  value?.field;  ${name};  1..=10", x, 710, 18, 400, "#EEECD9")
        parts.append(p.body())
    write("Code", parts, 1400, 755)
    parts = []
    for row, key in enumerate(["sans", "system"]):
        p = Panel(key, DATA["families"][key])
        bind(p, instance(ROOT / files[key], 350, 14 if key == "system" else None))
        y = 35 + row * 310
        p.text(
            key.title() + " / lining and optional fractions", 25, y, 21, 400, "#194454"
        )
        p.text(
            "1/2   3/4   12/345   123/456   1 1/2",
            25,
            y + 64,
            37,
            400,
            "#101712",
            features={"frac": False},
        )
        p.text(
            "1/2   3/4   12/345   123/456   1 1/2",
            25,
            y + 130,
            48,
            400,
            "#101712",
            features={"frac": True},
        )
        p.text(
            "Recipe: 1/2 cup, 3/4 teaspoon, 12/25 portion",
            25,
            y + 195,
            25,
            400,
            "#101712",
            features={"frac": True},
        )
        p.text(
            "¼ ½ ¾ ⅓ ⅔ ⅛   |   2026 / 11 / 17 (frac off)",
            25,
            y + 250,
            22,
            400,
            "#101712",
            features={"frac": False},
        )
        parts.append(p.body())
    write("Fractions", parts, 1200, 640)
    p = Panel("oldstyle", DATA["families"]["sans"])
    bind(p, instance(ROOT / files["sans"], 350, None))
    p.text("Sans / lining figures", 25, 35, 21, 400, "#194454")
    p.text("0123456789   2026   1,234.56", 25, 125, 58, 400, "#101712")
    p.text("Sans / old-style figures (onum)", 25, 200, 21, 400, "#194454")
    p.text(
        "0123456789   2026   1,234.56",
        25,
        290,
        58,
        400,
        "#101712",
        features={"onum": True},
    )
    p.text(
        "The story began in 1926, continued in 2026, and spans 100 years.",
        25,
        390,
        26,
        400,
        "#101712",
        features={"onum": True},
        max_width=1150,
    )
    p.text(
        "1/2   12/345   2026",
        25,
        465,
        35,
        400,
        "#101712",
        features={"frac": True, "onum": True},
    )
    write("Oldstyle", [p.body()], 1200, 505)
    print("Generated Code, fractions and old-style proofs")


if __name__ == "__main__":
    main()
