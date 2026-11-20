"""Show the current specimen Code cut's refinements across named weights."""

from export_otf import STYLES
from specimens import ROOT, Panel, specimen_families
from fontTools.ttLib import TTFont


def main():
    cfg = specimen_families()["code"]
    parts = []
    heading = Panel("code", cfg)
    heading.text(
        "DAIKONIC TRANSIT CODE / "
        + cfg["version"]
        + " "
        + cfg.get("status", "").upper(),
        25,
        32,
        20,
        350,
        "#194454",
    )
    heading.text(
        "Current character, delimiter, spacing and coding-ligature refinements",
        25,
        62,
        14,
        350,
        "#194454",
    )
    parts.append(heading.body())
    font = TTFont(ROOT / cfg["font"])
    weights = sorted({item.coordinates["wght"] for item in font["fvar"].instances})
    for row, weight in enumerate(weights):
        name = STYLES[weight]
        p = Panel("code", cfg)
        y = 110 + row * 235
        p.text(f"{name} / {weight:g}", 25, y, 16, weight, "#194454")
        p.text("o@o  i l 1", 25, y + 76, 54, weight, "#101712")
        p.text("snake_case  value-key", 25, y + 122, 27, weight, "#101712")
        p.text("user@example.com  @name  @@  @@@", 25, y + 160, 16, weight, "#101712")
        p.text(
            "const snake_case = get_items([input]);", 620, y + 52, 18, weight, "#101712"
        )
        p.text(
            "if (key != null) { return value-key; }", 620, y + 88, 18, weight, "#101712"
        )
        p.text("() [] {} |   ke Ke KE ki ik", 620, y + 124, 19, weight, "#101712")
        p.text(
            "-> ->> => <- <<- == === != !== <= >= ::",
            620,
            y + 160,
            18,
            weight,
            "#101712",
        )
        p.elements.append(
            f'<rect y="{y+176}" width="1200" height="40" fill="#101712"/>'
        )
        p.text(
            "__init__  foo({snake_case: [some_value]})  email@host.io  ke Ke KE",
            25,
            y + 202,
            16,
            weight,
            "#EEECD9",
        )
        parts.append(p.body())
    (ROOT / "specimens/TransitCode-Details.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="820"><rect width="1200" height="820" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


if __name__ == "__main__":
    main()
