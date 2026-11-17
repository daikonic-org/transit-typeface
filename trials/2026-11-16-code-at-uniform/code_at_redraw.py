"""Fresh, smooth spiral @ with a lighter double-storey interior a."""

from pathlib import Path
import cmath
import json
import math
import pathops
from adopt_weighting import ROOT, instance
from audit import shape
from derive_weights import install, topology, coverage_difference
from code_at_optical_study import metrics
from code_at_study import BASE, build_at_variant
from specimens import DATA, Panel
import code_balance_study as review

OUT = ROOT / "trials/2026-11-16-code-at-redraw"
PREVIOUS = (
    ROOT / "trials/2026-11-16-code-at-optical/DaikonicTransitCodeOpticalAtStudy-VF.ttf"
)
WIDTH, HEIGHT = 590, 597
OUTER, INNER = 0.80, 0.45
ERROR = 0.025


def smooth(t):
    return t * t * (3 - 2 * t)


def line(a, b, weight):
    return (lambda t: a + (b - a) * t, lambda t: b - a, lambda t: weight)


def bezier(a, b, c, d, w0, w1=None):
    if w1 is None:
        w1 = w0
    return (
        lambda t: (1 - t) ** 3 * a
        + 3 * (1 - t) ** 2 * t * b
        + 3 * (1 - t) * t * t * c
        + t**3 * d,
        lambda t: 3 * (1 - t) ** 2 * (b - a)
        + 6 * (1 - t) * t * (c - b)
        + 3 * t * t * (d - c),
        lambda t: w0 + (w1 - w0) * smooth(t),
    )


def stroke(segments, vx, hy):
    # Smooth cubic approximation of a varying-width elliptical-pen stroke.
    # The same cubic centerline and weight recipe is used at every master.
    def edge(seg, t, side):
        pos, vel, weight = seg
        d = vel(t)
        n = complex(-d.imag, d.real) / abs(d)
        a, b = vx * weight(t) / 2, hy * weight(t) / 2
        support = math.hypot(a * n.real, b * n.imag)
        offset = complex(a * a * n.real, b * b * n.imag) / support
        return pos(t) + side * offset

    def derivative(seg, t, side):
        h = 1e-5
        lo = max(0, t - h)
        hi = min(1, t + h)
        return (edge(seg, hi, side) - edge(seg, lo, side)) / (hi - lo)

    def fit(seg, lo, hi, side, depth=0):
        a, d = edge(seg, lo, side), edge(seg, hi, side)
        dt = hi - lo
        b = a + derivative(seg, lo, side) * dt / 3
        c = d - derivative(seg, hi, side) * dt / 3
        error = max(
            abs(
                (1 - u) ** 3 * a
                + 3 * (1 - u) ** 2 * u * b
                + 3 * (1 - u) * u * u * c
                + u**3 * d
                - edge(seg, lo + dt * u, side)
            )
            for u in [0.25, 0.5, 0.75]
        )
        if error > ERROR and depth < 14:
            mid = (lo + hi) / 2
            return fit(seg, lo, mid, side, depth + 1) + fit(
                seg, mid, hi, side, depth + 1
            )
        return [(a, b, c, d)]

    left = [c for seg in segments for c in fit(seg, 0, 1, 1)]
    right = [c for seg in segments for c in fit(seg, 0, 1, -1)]
    p = pathops.Path()
    p.moveTo(left[0][0].real, left[0][0].imag)
    for a, b, c, d in left:
        p.cubicTo(b.real, b.imag, c.real, c.imag, d.real, d.imag)
    p.lineTo(right[-1][-1].real, right[-1][-1].imag)
    for a, b, c, d in reversed(right):
        p.cubicTo(c.real, c.imag, b.real, b.imag, a.real, a.imag)
    p.close()
    return pathops.simplify(p, fix_winding=True, clockwise=True)


def drawing(font, outer=OUTER, inner=INNER, scale=1.0):
    ob, vx, hy = metrics(font)
    cy = (ob[1] + ob[3]) / 2
    rx = (WIDTH - vx * outer) / 2
    ry = (HEIGHT - hy * outer) / 2
    center = complex(300, cy)

    def arc(start, end, w0, w1):
        a, b = math.radians(start), math.radians(end)
        delta = b - a
        return (
            lambda t: center
            + complex(rx * math.cos(a + delta * t), ry * math.sin(a + delta * t)),
            lambda t: complex(
                -rx * math.sin(a + delta * t) * delta,
                ry * math.cos(a + delta * t) * delta,
            ),
            lambda t: w0 + (w1 - w0) * smooth(t),
        )

    spiral = [
        arc(a, b, outer, outer)
        for a, b in [(-57, -90), (-90, -180), (-180, -270), (-270, -360)]
    ]
    middle_weight = 0.64 if (outer, inner) == (OUTER, INNER) else (outer + inner) / 2
    spiral.append(arc(-360, -390, outer, middle_weight))
    end = spiral[-1][0](1)
    tangent = spiral[-1][1](1)
    tangent /= abs(tangent)
    spiral.append(
        bezier(
            end,
            end + tangent * 38,
            complex(375, 112),
            complex(375, 195),
            middle_weight,
            inner,
        )
    )
    spiral.append(line(complex(375, 195), complex(375, 335), inner))
    spiral.append(
        bezier(
            complex(375, 335),
            complex(375, 368),
            complex(344, 383),
            complex(307, 383),
            inner,
        )
    )
    spiral.append(
        bezier(
            complex(307, 383),
            complex(272, 383),
            complex(239, 370),
            complex(219, 345),
            inner,
        )
    )
    bowl = [
        bezier(
            complex(375, 277),
            complex(322, 285),
            complex(245, 276),
            complex(228, 235),
            inner,
        ),
        bezier(
            complex(228, 235),
            complex(207, 184),
            complex(238, 145),
            complex(282, 145),
            inner,
        ),
        bezier(
            complex(282, 145),
            complex(324, 145),
            complex(354, 166),
            complex(375, 193),
            inner,
        ),
    ]
    if scale != 1:

        def resize(seg):
            pos, vel, weight = seg
            return (
                lambda t: center + (pos(t) - center) * scale,
                lambda t: vel(t) * scale,
                weight,
            )

        spiral = [resize(seg) for seg in spiral]
        bowl = [resize(seg) for seg in bowl]
    return pathops.op(
        stroke(spiral, vx, hy),
        stroke(bowl, vx, hy),
        pathops.PathOp.UNION,
        fix_winding=True,
        clockwise=True,
    )


def revise(font):
    install(font, "at", drawing(font))


def proof(vf):
    parts = []
    for row, w in enumerate([300, 350, 400]):
        for col, (label, path) in enumerate(
            [
                ("previous edited outline", PREVIOUS),
                ("fresh spiral / lighter strokes", vf),
            ]
        ):
            p = Panel(f"{row}-{col}", DATA["families"]["code"])
            review.bind(p, instance(path, w, None))
            x = 25 + 600 * col
            y = 35 + row * 235
            p.text(f"{w} / {label}", x, y, 12, 400, "#194454")
            p.text("o@o", x, y + 90, 110, 400, "#101712")
            p.text("user@example.com", x, y + 143, 27, 400, "#101712")
            p.text("@name  @property  @decorator", x, y + 177, 15, 400, "#101712")
            p.elements.append(
                f'<rect x="{600*col}" y="{y+188}" width="600" height="32" fill="#101712"/>'
            )
            p.text("no@no  email@host.io  @@@", x, y + 210, 14, 400, "#EEECD9")
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
            "Book / fresh spiral": instance(vf, 350, None),
        },
        samples=[
            (13, "o@o no@no user@example.com @name @decorator"),
            (14, "email@host.io  @property  @staticmethod  @@@"),
            (16, "o @ o  user@example.com  @name"),
        ],
        title="Code / freshly drawn at / Book 350",
    )


def main():
    vf = build_at_variant(
        revise,
        OUT,
        "Daikonic Transit Code Redrawn At Study",
        "fresh smooth spiral at",
        compatible_paths=True,
    )
    checks = []
    for w in range(300, 401, 10):
        font = instance(vf, w, None)
        p = shape(font, "at")
        expected = drawing(instance(BASE, w, None))
        bounds = p.bounds
        assert topology(pathops.simplify(p, fix_winding=True, clockwise=True)) == (
            1,
            1,
        ), (w, topology(p))
        assert bounds[0] >= 0 and bounds[2] <= 600, (w, bounds)
        assert abs(bounds[1] + 33.5) < 1 and abs(bounds[3] - 563.5) < 1, (w, bounds)
        assert font["hmtx"]["at"][0] == 600
        error = coverage_difference(p, expected)
        assert error < 0.015, (w, error)
        checks.append(
            {
                "weight": w,
                "bounds": bounds,
                "coverage_error": error,
                "points": len(font["glyf"]["at"].coordinates),
            }
        )
    (OUT / "validation.json").write_text(
        json.dumps(
            {
                "outer_width": WIDTH,
                "outer_height": HEIGHT,
                "outer_stroke_ratio": OUTER,
                "inner_stroke_ratio": INNER,
                "curve_approximation_tolerance": ERROR,
                "sanitized_fonts": 4,
                "checks": checks,
            },
            indent=2,
        )
        + "\n"
    )
    proof(vf)
    print(
        "Built and sanitized four fonts; checked compatible smooth outline at 11 weights; other glyphs/layout retained."
    )


if __name__ == "__main__":
    main()
