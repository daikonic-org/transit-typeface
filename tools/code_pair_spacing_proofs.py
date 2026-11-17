"""Compare previous and right-shifted question-period optical placement."""

from copy import deepcopy
import json
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from font_feature_tools import compose
from syntax_numeral_study import OUT
from specimens import ROOT, DATA, Panel
from code_balance_study import bind


def main():
    font = TTFont(ROOT / json.loads((OUT / "fonts.json").read_text())["code"])
    previous = deepcopy(font)
    mapping = json.loads((OUT / "recipe-report.json").read_text())["code"]["tokens"]
    for text in ("?.", "!."):
        first = font.getBestCmap()[ord(text[0])]
        compose(
            previous,
            mapping[text],
            [
                (first, 1, 1, 35, 0),
                ("period", 1, 1, 520, 0),
            ],
            1200,
        )
    elements = []
    for col, (label, f) in enumerate(
        [("Original spacing", previous), ("Original spacing + right shift", font)]
    ):
        for row, w in enumerate((300, 350, 400)):
            p = Panel(f"pair{col}-{w}", DATA["families"]["code"])
            bind(p, instantiateVariableFont(deepcopy(f), {"wght": w}, inplace=True))
            x = 25 + 650 * col
            y = 40 + 220 * row
            p.text(
                label + " / " + {300: "Light", 350: "Book", 400: "Regular"}[w],
                x,
                y,
                21,
                400,
                "#194454",
            )
            p.text("?.    !.", x, y + 75, 58, 400, "#101712")
            p.text(
                "object?.field; value!.next;",
                x,
                y + 130,
                25,
                400,
                "#101712",
                max_width=600,
            )
            p.text(
                "a?.b   x!.y   value?.method()",
                x,
                y + 177,
                24,
                400,
                "#101712",
                max_width=600,
            )
            elements.append(p.body())
    (OUT / "Punctuation-Pairs.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="670"><rect width="1300" height="670" fill="#EEECD9"/>'
        + "".join(elements)
        + "</svg>"
    )
    print("Punctuation pair proof generated")


if __name__ == "__main__":
    main()
