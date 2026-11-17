"""Continuous thickness transition from c into the original a arch."""

from functools import partial
import json
from adopt_weighting import ROOT
from code_at_c_shell_study import construction
from code_at_uniform_study import main as build
from code_at_weight_proof import main as weight_proof
import code_at_c_balance_study as review
import code_at_source_a_study as pair_proof

OUT = ROOT / "trials/2026-11-17-code-at-c-taper"
PREVIOUS = (
    ROOT
    / "trials/2026-11-17-code-at-c-balance/DaikonicTransitCodeBalancedCAtStudy-VF.ttf"
)
FAMILY = "Daikonic Transit Code Tapered C At Study"
STEM = "DaikonicTransitCodeTaperedCAtStudy"
DRAW = partial(construction, balance="tapered")
UPTURN = False


def proof(vf=None):
    if UPTURN:
        pair_proof.OUT = OUT
        pair_proof.PREVIOUS = PREVIOUS
        pair_proof.construction = DRAW
        pair_proof.draft(
            vf, labels=("Approved taper / flat end", "Taper / gentle upward turn")
        )
        return
    review.OUT = OUT
    review.PREVIOUS = PREVIOUS
    review.proof(
        vf,
        variants=[
            ("Previous join", "lighter-c"),
            ("Gradual 95 to 82 taper", "tapered"),
            ("Uniform 82 stroke", "uniform"),
        ],
    )


def main():
    vf = build(
        out=OUT,
        family=FAMILY,
        draw=DRAW,
        previous=PREVIOUS,
        labels=(
            ("flat lower terminal", "gentle upward turn")
            if UPTURN
            else ("previous join", "gradual stroke taper")
        ),
    )
    weight_proof(out=OUT, stem=STEM)
    proof(vf)
    p = OUT / "validation.json"
    d = json.loads(p.read_text())
    d.pop("inner_and_outer_weight_ratio", None)
    d.pop("scale_centerline_both_axes", None)
    d.update(
        construction="Continuous c inner arc joins a arch; nominal95 to82 taper",
        a_uniform_scale=0.85,
        lower_terminal_rise=40 if UPTURN else 0,
    )
    p.write_text(json.dumps(d, indent=2) + "\n")


if __name__ == "__main__":
    import sys

    if "--upturn" in sys.argv:
        UPTURN = True
        PREVIOUS = OUT / f"{STEM}-VF.ttf"
        OUT = ROOT / "trials/2026-11-17-code-at-c-upturn"
        FAMILY = "Daikonic Transit Code Upturned C At Study"
        STEM = "DaikonicTransitCodeUpturnedCAtStudy"
        DRAW = partial(construction, balance="tapered", lower_turn=40)
    proof() if "--draft" in sys.argv else main()
