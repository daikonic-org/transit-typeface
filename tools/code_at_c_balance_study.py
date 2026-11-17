"""Optical weight and tangent comparison for the open c/a at symbol."""

from functools import partial
import json
from adopt_weighting import ROOT, instance
from derive_weights import install
from specimens import DATA, Panel
import code_balance_study as review
from code_at_c_shell_study import construction
from code_at_uniform_study import main as build
from code_at_weight_proof import main as weight_proof

OUT = ROOT / "trials/2026-11-17-code-at-c-balance"
PREVIOUS = (
    ROOT / "trials/2026-11-17-code-at-c-shell/DaikonicTransitCodeCShellAtStudy-VF.ttf"
)
FAMILY = "Daikonic Transit Code Balanced C At Study"
STEM = "DaikonicTransitCodeBalancedCAtStudy"
DRAW = partial(construction, balance="lighter-c")


def proof(vf=None, variants=None):
    OUT.mkdir(exist_ok=True)
    parts = []
    for col, (label, balance) in enumerate(
        variants
        or [
            ("Previous c/a", "original"),
            ("Lighter c / smoother join", "lighter-c"),
            ("Heavier a / smoother join", "heavier-a"),
        ]
    ):
        font = instance(PREVIOUS, 350, None)
        if col == 1 and vf is not None:
            font = instance(vf, 350, None)
        else:
            install(font, "at", construction(font, balance=balance))
            install(font, "at.compact", construction(font, scale=1, balance=balance))
        panel = Panel(str(col), DATA["families"]["code"])
        review.bind(panel, font)
        x = 25 + 430 * col
        panel.text(label, x, 30, 13, 400, "#194454")
        panel.text("o@o", x, 190, 145, 400, "#101712")
        panel.text("user@example.com", x, 250, 23, 400, "#101712")
        panel.text("@name  @property", x, 294, 19, 400, "#101712")
        parts.append(panel.body())
    (OUT / "Book.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1290" height="330"><rect width="1290" height="330" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


def main():
    vf = build(
        out=OUT,
        family=FAMILY,
        draw=DRAW,
        previous=PREVIOUS,
        labels=("previous c/a", "lighter c / smooth join"),
    )
    weight_proof(out=OUT, stem=STEM)
    proof(vf)
    p = OUT / "validation.json"
    d = json.loads(p.read_text())
    d.pop("inner_and_outer_weight_ratio", None)
    d.pop("scale_centerline_both_axes", None)
    d.update(
        construction="Lighter c inner curve; smooth tangent into unchanged a",
        a_uniform_scale=0.85,
    )
    p.write_text(json.dumps(d, indent=2) + "\n")


if __name__ == "__main__":
    import sys

    proof() if "--draft" in sys.argv else main()
