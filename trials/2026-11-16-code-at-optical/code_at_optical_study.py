"""Isotropically enlarge @; match o loop weight with a lighter inner a."""

from copy import deepcopy
import hashlib
import json
import math

import pathops
from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from adopt_weighting import ROOT, instance
from audit import shape, spans
from derive_weights import topology
from specimens import DATA, Panel
from code_at_study import BASE, build_at_variant
import code_balance_study as review

OUT = ROOT / "trials/2026-11-16-code-at-optical"
PREVIOUS = ROOT / "trials/2026-11-16-code-at-height/DaikonicTransitCodeAtStudy-VF.ttf"
SCALE = 1.09
INNER_RATIO = 0.55


def metrics(font):
    o = shape(font, "o")
    left, bottom, right, top = o.bounds
    cy = (bottom + top) / 2
    cx = (left + right) / 2
    vertical = spans(o, cy, 1)
    horizontal = spans(o, cx, 0)
    vx = sum(b - a for a, b in (vertical[0], vertical[-1])) / 2
    hy = sum(b - a for a, b in (horizontal[0], horizontal[-1])) / 2
    return o.bounds, vx, hy


def revise(font):
    g = font["glyf"]["at"]
    src = list(g.coordinates)
    assert len(src) == 791 and list(g.endPtsOfContours) == [716, 790]
    ob, vx, hy = metrics(font)
    cy = (ob[1] + ob[3]) / 2
    ax = (min(x for x, y in src) + max(x for x, y in src)) / 2
    ay = (min(y for x, y in src) + max(y for x, y in src)) / 2
    # The silhouette is scaled equally on both axes, centered against o.
    scaled = [(300 + (x - ax) * SCALE, cy + (y - ay) * SCALE) for x, y in src]
    outer_left = min(x for x, y in scaled)
    outer_right = max(x for x, y in scaled)
    outer_bottom = min(y for x, y in scaled)
    outer_top = max(y for x, y in scaled)
    inner = src[387:572]
    il, ir = min(x for x, y in inner), max(x for x, y in inner)
    ib, it = min(y for x, y in inner), max(y for x, y in inner)
    counter = src[717:]
    cl, cr = min(x for x, y in counter), max(x for x, y in counter)
    cb, ct = min(y for x, y in counter), max(y for x, y in counter)
    ccx, ccy = (cl + cr) / 2, (cb + ct) / 2
    aleft = min(x for x, y in src[93:188])
    abottom = min(y for x, y in src[93:188])
    atop = max(y for x, y in src[250:349])
    notch = max(y for x, y in src[188:250])
    dx = max(0, cl - aleft - INNER_RATIO * vx / SCALE)
    dy = max(0, cb - abottom - INNER_RATIO * hy / SCALE)
    lift = max(0, atop - notch - INNER_RATIO * hy / SCALE)
    start, end = src[387], src[571]
    for j, ((x, y), (xx, yy)) in enumerate(zip(src, scaled)):
        if 387 <= j <= 571:
            # Move the inner edge inward; taper into the thinner a/tail junction.
            rx = (
                outer_left
                + vx
                + (x - il) / (ir - il) * (outer_right - outer_left - 2 * vx)
            )
            ry = (
                outer_bottom
                + hy
                + (y - ib) / (it - ib) * (outer_top - outer_bottom - 2 * hy)
            )
            distance = min(
                math.hypot(x - start[0], y - start[1]),
                math.hypot(x - end[0], y - end[1]),
            )
            t = min(1, distance / 50)
            blend = t * t * (3 - 2 * t)
            xx += (rx - xx) * blend
            yy += (ry - yy) * blend
        elif j >= 717:
            xx = 300 + (ccx + (x - ccx) * (1 + 2 * dx / (cr - cl)) - ax) * SCALE
            yy = cy + (ccy + (y - ccy) * (1 + 2 * dy / (ct - cb)) - ay) * SCALE
        elif 188 <= j <= 249:
            taper = (
                max(0, min(1, (y - 270) / 20))
                * max(0, min(1, (x - 200) / 20))
                * max(0, min(1, (334 - x) / 20))
            )
            yy += lift * taper * SCALE
        g.coordinates[j] = (otRound(xx), otRound(yy))
    g.recalcBounds(font["glyf"])
    font["hmtx"]["at"] = (600, g.xMin)
    return {
        "scale": SCALE,
        "o_vertical": vx,
        "o_horizontal": hy,
        "target_inner_vertical": vx * INNER_RATIO,
        "target_inner_horizontal": hy * INNER_RATIO,
    }


def main():
    vf = build_at_variant(
        revise,
        OUT,
        "Daikonic Transit Code Optical At Study",
        "isotropic at enlargement; o-matched loop and lighter inner a",
    )
    checks = []
    for w in range(300, 401, 10):
        f = instance(vf, w, None)
        p = shape(f, "at")
        ob, vx, hy = metrics(f)
        left, bottom, right, top = p.bounds
        cy = (ob[1] + ob[3]) / 2
        assert left >= 0 and right <= 600, (w, p.bounds)
        assert bottom < ob[1] and top > ob[3], (w, p.bounds, ob)
        assert abs((top + bottom) / 2 - cy) < 1
        assert (
            abs(
                (right - left) / (top - bottom)
                - (
                    (
                        shape(instance(BASE, w, None), "at").bounds[2]
                        - shape(instance(BASE, w, None), "at").bounds[0]
                    )
                    / 506
                )
            )
            < 0.005
        )
        assert topology(pathops.simplify(p, fix_winding=True, clockwise=True)) == (
            1,
            1,
        ), (w, topology(p))
        v = spans(p, cy, 1)
        h = spans(p, 300, 0)
        measured_v = [b - a for a, b in [v[0], v[-1]]]
        measured_h = [b - a for a, b in [h[0], h[-1]]]
        assert max(abs(x - vx) for x in measured_v) < 3, (w, measured_v, vx)
        assert max(abs(x - hy) for x in measured_h) < 3, (w, measured_h, hy)
        assert f["hmtx"]["at"][0] == 600
        checks.append(
            {
                "weight": w,
                "at_bounds": p.bounds,
                "o_bounds": ob,
                "o_vertical": vx,
                "o_horizontal": hy,
                "at_outer_vertical": measured_v,
                "at_outer_horizontal": measured_h,
            }
        )
    (OUT / "validation.json").write_text(
        json.dumps(
            {
                "uniform_scale": SCALE,
                "inner_weight_ratio": INNER_RATIO,
                "sanitized_fonts": 4,
                "unrelated_outlines_variations_layout": "retained exactly; at sidebearing follows new bounds",
                "checks": checks,
            },
            indent=2,
        )
        + "\n"
    )
    parts = []
    for row, w in enumerate([300, 350, 400]):
        for col, (label, path) in enumerate(
            [
                ("previous / raised", PREVIOUS),
                ("larger / o-weight loop / lighter a", vf),
            ]
        ):
            p = Panel(f"{row}-{col}", DATA["families"]["code"])
            review.bind(p, instance(path, w, None))
            x = 25 + 600 * col
            y = 35 + row * 235
            p.text(f"{w} / {label}", x, y, 12, 400, "#194454")
            p.text("no@no", x, y + 85, 90, 400, "#101712")
            p.text("o @ o  user@example.com", x, y + 135, 22, 400, "#101712")
            p.text("@name  @property  @decorator", x, y + 169, 15, 400, "#101712")
            p.elements.append(
                f'<rect x="{600*col}" y="{y+185}" width="600" height="34" fill="#101712"/>'
            )
            p.text("email@host.io  @name  @@@", x, y + 208, 14, 400, "#EEECD9")
            parts.append(p.body())
    (OUT / "Comparison.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="750"><rect width="1200" height="750" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    review.OUT = OUT
    review.browser_proof(
        {
            "Book / previous": instance(PREVIOUS, 350, None),
            "Book / larger and optically weighted": instance(vf, 350, None),
        },
        samples=[
            (13, "o@o no@no user@example.com @name @decorator"),
            (14, "o @ o  email@host.io  @property  @staticmethod"),
            (16, "no@no  user@example.com  @name  @@@"),
        ],
        title="Code / larger at with o-weight loop / Book 350",
    )
    print(
        "Built four sanitized fonts; checked 11 weights, isotropic bounds, overshoot and o-matched outer stroke."
    )


if __name__ == "__main__":
    main()
