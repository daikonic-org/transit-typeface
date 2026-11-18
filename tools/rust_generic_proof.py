"""Current-font Rust inference placeholders and turbofish fitting."""

from copy import deepcopy
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from specimens import ROOT, DATA, Panel, specimen_families
from code_balance_study import bind


def main():
    vf = TTFont(ROOT / specimen_families()["code"]["font"])
    parts = []
    rows = [
        ("<'_>  <_>  <[_]>", 34),
        ("::<T>  ::<_>  ::<[_]>", 32),
        ("from_iter::<Vec<_>>()", 28),
        ("::<   Vec<T   a<b", 26),
        ("f::<'_>()  f::<_>()  f::<[_]>()", 14),
    ]
    for row, (weight, label) in enumerate(
        [(300, "Light"), (350, "Book"), (400, "Regular")]
    ):
        font = instantiateVariableFont(deepcopy(vf), {"wght": weight}, inplace=True)
        for col, enabled in enumerate([True, False]):
            p = Panel(
                "rust-generics-" + str(weight) + str(col), DATA["families"]["code"]
            )
            bind(p, font)
            x, y = 25 + col * 700, 40 + row * 350
            p.text(
                label + " / calt " + ("on" if enabled else "off"),
                x,
                y,
                22,
                400,
                "#194454",
            )
            for line, (text, size) in enumerate(rows):
                p.text(
                    text,
                    x,
                    y + 60 + 59 * line,
                    size,
                    400,
                    "#101712",
                    features={"calt": enabled, "ss01": False, "ss02": False},
                    max_width=660,
                )
            parts.append(p.body())
    (ROOT / "specimens/features/Rust-Generics.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1080" viewBox="0 0 1400 1080"><rect width="1400" height="1080" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    print("Rust generic proof generated at reading and display sizes")


if __name__ == "__main__":
    main()
