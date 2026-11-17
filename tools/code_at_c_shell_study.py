"""Round c-shell at study, preserving the original proportional two-storey a."""

import json
import pathops
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from adopt_weighting import ROOT, instance
from audit import shape
from derive_weights import grow, topology, install
from code_at_uniform_study import main as build
from code_at_weight_proof import main as weight_proof
import code_at_source_a_study as proof

OUT = ROOT / "trials/2026-11-17-code-at-c-shell"
PREVIOUS = (
    ROOT
    / "trials/2026-11-17-code-at-short-hook/DaikonicTransitCodeShortHookAtStudy-VF.ttf"
)
FAMILY = "Daikonic Transit Code C Shell At Study"
STEM = "DaikonicTransitCodeCShellAtStudy"


def construction(
    font, outer=0.8, inner=0.8, scale=1.06, balance="original", lower_turn=0
):
    source = TTFont(ROOT / "upstream/MetropolitanLine-Regular.ttf")
    # Fix the outer c size first. Fit a by reducing it uniformly.
    original = RecordingPen()
    source.getGlyphSet()["a"].draw(original)
    joined = RecordingPen()
    a_pen = TransformPen(joined, (0.85, 0, 0, 0.85, 170.55, 156.5))
    skip = 0
    contour = 0
    for op, pts in original.value:
        if op == "moveTo":
            contour += 1
        if skip:
            skip -= 1
            continue
        if (
            balance in ("tapered", "uniform")
            and op == "qCurveTo"
            and pts[-1] == (58, 320)
        ):
            # Replace the descending a hook entirely: c inner arc joins its arch.
            thickness = 95 if balance == "tapered" else 82
            ix = 20 + thickness
            iy = -50 + thickness
            joined.curveTo((217, 487.15), (ix, 384), (ix, 258))
            joined.curveTo((ix, 140), (213, iy), (333, iy))
            if lower_turn:
                joined.curveTo(
                    (405, iy), (475, iy + lower_turn * 0.4), (525, iy + lower_turn)
                )
                joined.lineTo((525, -50 + lower_turn))
                joined.curveTo((475, -50 + lower_turn * 0.4), (405, -50), (333, -50))
            else:
                joined.lineTo((525, iy))
                joined.lineTo((525, -50))
                joined.lineTo((333, -50))
            joined.curveTo((160, -50), (20, 86), (20, 258))
            joined.curveTo((20, 430), (160, 568.75), (333, 568.75))
            joined.lineTo((366.9, 568.75))
            skip = 3
        elif op == "lineTo" and pts == ((48, 320),):
            # Rounded c arc, merging into the a arch instead of overlapping it.
            inner_left = 103 if balance == "lighter-c" else 115
            inner_bottom = 35 if balance == "lighter-c" else 45
            first_control = (155, 399) if balance == "original" else (186, 398)
            if balance == "heavier-a":
                first_control = (186, 386)
            joined.curveTo(first_control, (inner_left, 330), (inner_left, 258))
            joined.curveTo((inner_left, 140), (213, inner_bottom), (333, inner_bottom))
            joined.lineTo((525, inner_bottom))
            joined.lineTo((525, -50))
            joined.lineTo((333, -50))
            joined.curveTo((160, -50), (20, 86), (20, 258))
            joined.curveTo((20, 430), (160, 568.75), (333, 568.75))
            joined.lineTo((366.9, 568.75))
            skip = 2  # Original hook bevel and upper return, now replaced.
        else:
            if balance == "heavier-a":
                if contour == 2:
                    pts = tuple(
                        (240 + (x - 240) * 0.88, 142 + (y - 142) * 0.88) for x, y in pts
                    )
                elif op == "qCurveTo" and pts[-1] == (217, 389):
                    pts = tuple((x, y - 12) for x, y in pts)
                elif op == "qCurveTo" and pts[-1] == (58, 320):
                    pts = tuple((x, y - 12) for x, y in pts)
                elif op == "lineTo" and pts[0] in ((317, 0), (317, 25)):
                    pts = ((303, pts[0][1]),)
            getattr(a_pen, op)(*pts)
    p = pathops.Path()
    joined.replay(p.getPen())
    p = pathops.simplify(p, fix_winding=True, clockwise=True)
    delta = (font["OS/2"].usWeightClass - 350) * 0.4
    if delta:
        p = grow(p, delta, 0.72, 3)
    l, b, r, t = p.bounds
    s = scale / 1.06
    return p.transform(s, 0, 0, s, 300 - (l + r) / 2 * s, 265 - (b + t) / 2 * s)


def draft(vf=None):
    proof.OUT, proof.PREVIOUS, proof.SHORT_HOOK = OUT, PREVIOUS, True
    proof.construction = construction
    proof.draft(vf, labels=("Previous short wrap", "Round c shell / original a"))
    p = OUT / "Book.svg"
    p.write_text(
        p.read_text()
        .replace("Previous tall wrap", "Previous short wrap")
        .replace("Wrap stops at right stem", "Round c shell / original a")
    )


def main():
    vf = build(
        out=OUT,
        family=FAMILY,
        draw=construction,
        previous=PREVIOUS,
        labels=("previous short wrap", "round c shell / original a"),
    )
    weight_proof(out=OUT, stem=STEM)
    draft(vf)


if __name__ == "__main__":
    import sys

    draft() if "--draft" in sys.argv else main()
