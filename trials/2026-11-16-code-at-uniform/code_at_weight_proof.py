"""Show the selected equal-stroke @ at all named Code weights."""

from adopt_weighting import instance
from code_at_uniform_study import OUT
from specimens import DATA, Panel
import code_balance_study as review


def main():
    vf = OUT / "DaikonicTransitCodeUniformAtStudy-VF.ttf"
    parts = []
    for col, (weight, name) in enumerate(
        [(300, "Light"), (350, "Book"), (400, "Regular")]
    ):
        p = Panel("at-weight-" + name, DATA["families"]["code"])
        review.bind(p, instance(vf, weight, None))
        x = 25 + 360 * col
        p.text(f"{name} / {weight}", x, 38, 19, 400, "#194454")
        for y in [200 - 528 * 0.14, 200 - 2 * 0.14]:
            p.elements.append(
                f'<path d="M{x} {y}h300" stroke="#ADB8B5" stroke-width=".55"/>'
            )
        p.text("o@o", x, 200, 140, 400, "#101712")
        p.text("user@example.com", x, 260, 22, 400, "#101712")
        p.text("@property  @name", x, 298, 16, 400, "#101712")
        p.text("@@  @@@", x, 329, 16, 400, "#101712")
        p.elements.append(
            f'<rect x="{360*col}" y="355" width="360" height="120" fill="#101712"/>'
        )
        p.text("o@o  @name", x, 405, 34, 400, "#EEECD9")
        p.text("email@host.io  @@", x, 446, 14, 400, "#EEECD9")
        parts.append(p.body())
    (OUT / "NamedWeights.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="475"><rect width="1080" height="475" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


if __name__ == "__main__":
    main()
