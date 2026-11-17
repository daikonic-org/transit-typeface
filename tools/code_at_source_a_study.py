"""Original two-storey a whose upper hook extends around the bowl, left open."""

from functools import lru_cache
import json
import hashlib
import pathops
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from adopt_weighting import ROOT, instance
from audit import shape
from derive_weights import grow, install, topology, coverage_difference
from code_at_uniform_study import main as build
from code_at_weight_proof import main as weight_proof
from specimens import DATA, Panel
import code_balance_study as review

OUT = ROOT / "trials/2026-11-17-code-at-source-a"
PREVIOUS = ROOT / "previews/code-1.021/VF/DaikonicTransitCode-VF.ttf"
SOURCE = ROOT / "upstream/MetropolitanLine-Regular.ttf"
BODY_SCALE = 0.80
SHORT_HOOK = False
FAMILY = "Daikonic Transit Code Source Hook At Study"
STEM = "DaikonicTransitCodeSourceHookAtStudy"


@lru_cache(None)
def original_and_hook():
    font = TTFont(SOURCE)
    pen = RecordingPen()
    font.getGlyphSet()["a"].draw(pen)
    output = RecordingPen()
    replaced = False
    for operation, points in pen.value:
        if operation == "lineTo" and points == ((48, 320),):
            # Continue from the upper hook's inner edge (58,320), not the stem foot.
            output.curveTo((15, 281), (-35, 240), (-35, 190))
            output.curveTo((-35, 35), (40, -80), (210, -80))
            if SHORT_HOOK:
                # Stop below the original right stem's outer edge, x=417.
                output.curveTo((285, -80), (360, -80), (417, -80))
                output.lineTo((417, -176))
                output.curveTo((360, -176), (285, -176), (210, -176))
            else:
                output.curveTo((450, -80), (500, -80), (500, 185))
                output.lineTo((500, 350))
                output.curveTo((500, 485), (493, 580), (470, 640))
                output.lineTo((563, 676))
                output.curveTo((590, 600), (600, 470), (600, 350))
                output.lineTo((600, 185))
                output.curveTo((600, -20), (445, -176), (210, -176))
            output.curveTo((-25, -176), (-135, -15), (-135, 190))
            output.curveTo((-135, 310), (23, 404), (85, 444))
            replaced = True
        elif replaced and operation == "lineTo" and points == ((85, 444),):
            continue
        else:
            getattr(output, operation)(*points)
    assert replaced
    p = pathops.Path()
    output.replay(p.getPen())
    return shape(font, "a"), pathops.simplify(p, fix_winding=True, clockwise=True)


def construction(font, outer=0.8, inner=0.8, scale=1.06):
    original, raw = original_and_hook()
    weight = font["OS/2"].usWeightClass
    delta = (weight - 350) * 0.5
    p = grow(raw, delta, 0.72, 3) if delta else raw
    s = BODY_SCALE * scale / 1.06
    l, b, r, t = p.bounds
    return p.transform(s, 0, 0, s, 300 - (l + r) / 2 * s, 265 - (b + t) / 2 * s)


def draft(vf=None, labels=None):
    OUT.mkdir(exist_ok=True)
    p = construction(instance(PREVIOUS, 350, None))
    print("Book bounds", p.bounds, "topology", topology(p))
    parts = []
    for col, (label, font) in enumerate(
        [
            (
                (
                    labels[0]
                    if labels
                    else (
                        "Previous tall wrap"
                        if SHORT_HOOK
                        else "Installed single-storey at"
                    )
                ),
                instance(PREVIOUS, 350, None),
            ),
            (
                (
                    labels[1]
                    if labels
                    else (
                        "Wrap stops at right stem"
                        if SHORT_HOOK
                        else "Original a / upper hook extended"
                    )
                ),
                instance(PREVIOUS, 350, None),
            ),
        ]
    ):
        if col and vf is not None:
            font = instance(vf, 350, None)
        elif col:
            install(font, "at", p)
            install(
                font, "at.compact", construction(instance(PREVIOUS, 350, None), scale=1)
            )
        panel = Panel(str(col), DATA["families"]["code"])
        review.bind(panel, font)
        x = 25 + 600 * col
        panel.text(label, x, 30, 14, 400, "#194454")
        panel.text("o@o", x, 195, 150, 400, "#101712")
        panel.text("user@example.com", x, 255, 28, 400, "#101712")
        panel.text("@name  @property", x, 300, 20, 400, "#101712")
        parts.append(panel.body())
    (OUT / "Book.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="335"><rect width="1200" height="335" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


def main():
    vf = build(
        out=OUT,
        family=FAMILY,
        draw=construction,
        previous=PREVIOUS,
        labels=(
            ("previous tall wrap", "wrap stops at right stem")
            if SHORT_HOOK
            else ("installed single-storey a", "original a / extended upper hook")
        ),
    )
    weight_proof(out=OUT, stem=STEM)
    draft(vf)
    report = json.loads((OUT / "validation.json").read_text())
    report.pop("inner_and_outer_weight_ratio", None)
    report.pop("scale_centerline_both_axes", None)
    report.update(
        construction=(
            "Upper hook wraps below bowl and stops at right stem"
            if SHORT_HOOK
            else "Original upper hook extended; right stem and bowl retained"
        ),
        whole_shape_uniform_scale_book=BODY_SCALE,
        weight_offsets={"300": -25, "350": 0, "400": 25},
    )
    (OUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    original, raw = original_and_hook()
    a_hole = [c for c in original.contours if not c.clockwise][0]
    hook_hole = [c for c in raw.contours if not c.clockwise][0]
    error = coverage_difference(pathops.Path(a_hole), pathops.Path(hook_hole))
    assert error < 0.0001, error
    (OUT / "source-a-provenance.json").write_text(
        json.dumps(
            {
                "source": str(SOURCE.relative_to(ROOT)),
                "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                "source_a_bounds": original.bounds,
                "original_counter_fidelity": error,
                "bowl_horizontal_stretch": 1,
                "whole_shape_uniform_scale_book": BODY_SCALE,
                "extension": (
                    "upper hook terminal at(58,320); wrap stops below right stem at x417"
                    if SHORT_HOOK
                    else "upper hook terminal at(58,320), preserving right stem; partial open return"
                ),
                "weight_delta": {"300": -25, "350": 0, "400": 25},
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--short-hook", action="store_true")
    args = parser.parse_args()
    if args.short_hook:
        SHORT_HOOK = True
        PREVIOUS = OUT / f"{STEM}-VF.ttf"
        OUT = ROOT / "trials/2026-11-17-code-at-short-hook"
        FAMILY = "Daikonic Transit Code Short Hook At Study"
        STEM = "DaikonicTransitCodeShortHookAtStudy"
    draft() if args.draft else main()
