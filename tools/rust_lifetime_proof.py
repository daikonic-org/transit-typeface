"""Show lifetime on/off context and left-hook construction across Code named weights."""

from copy import deepcopy
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from specimens import ROOT, DATA, Panel, specimen_families
from code_balance_study import bind


def main():
    cfg = specimen_families()["code"]
    vf = TTFont(ROOT / cfg["font"])
    parts = []
    for row, (w, label) in enumerate([(300, "Light"), (350, "Book"), (400, "Regular")]):
        f = instantiateVariableFont(deepcopy(vf), {"wght": w}, inplace=True)
        for col, (title, enabled) in enumerate(
            [("Normal / ss01 off", False), ("Extended / ss01 on", True)]
        ):
            p = Panel(f"rust-{w}-{col}", DATA["families"]["code"])
            bind(p, f)
            x = 25 + 650 * col
            y = 40 + row * 250
            p.text(label + " / " + title, x, y, 20, 400, "#194454")
            p.text(
                "&'a  <'a, 'b>  'static",
                x,
                y + 70,
                36,
                400,
                "#101712",
                features={"calt": True, "ss01": enabled},
                max_width=610,
            )
            p.text(
                "let c = 'a'; let u = '_';",
                x,
                y + 125,
                25,
                400,
                "#101712",
                features={"calt": True, "ss01": enabled},
                max_width=610,
            )
            p.text(
                "fn get<'a>(x: &'a str) -> &'a str",
                x,
                y + 177,
                24,
                400,
                "#101712",
                features={"calt": True, "ss01": enabled},
                max_width=610,
            )
            parts.append(p.body())
    f = instantiateVariableFont(deepcopy(vf), {"wght": 350}, inplace=True)
    gs = f.getGlyphSet()
    for col, (name, title) in enumerate(
        [
            ("i", "Shared diamond / i"),
            ("quotesingle", "Literal apostrophe"),
            ("quotesingle.lifetime", "Lifetime left hook"),
        ]
    ):
        x = 100 + col * 400
        pen = SVGPathPen(gs)
        gs[name].draw(pen)
        scale = 0.25
        base = 1030
        parts.append(
            f'<path d="{pen.getCommands()}" transform="translate({x} {base}) scale({scale} {-scale})" fill="#101712"/>'
        )
        for yy in [
            base - f["OS/2"].sxHeight * scale,
            base - f["OS/2"].sCapHeight * scale,
        ]:
            parts.append(f'<path d="M{x-25},{yy} h260" stroke="#C06D3E"/>')
        p = Panel("rust-label-" + name, DATA["families"]["code"])
        bind(p, f)
        p.text(title, x - 50, 810, 17, 400, "#194454", max_width=360)
        parts.append(p.body())
    path = ROOT / "specimens/features/Rust-Lifetimes.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="1060"><rect width="1300" height="1060" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    print("Rust lifetime weight and construction proof generated")


if __name__ == "__main__":
    main()
