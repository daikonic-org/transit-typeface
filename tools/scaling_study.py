"""Controlled scaling/weight-order probes from the original Regular drawing."""

from pathlib import Path
import json
import pathops
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from audit import shape, spans
from derive_weights import weighted, coverage_difference

ROOT = Path(__file__).resolve().parents[1]


def vertical_stem(p, level=0.25):
    runs = spans(p, p.bounds[1] + (p.bounds[3] - p.bounds[1]) * level, 1)
    return runs[0][1] - runs[0][0]


def enlarge_lowercase(p, factor, stem, ratio=1):
    scaled = p.transform(factor, 0, 0, factor, 0, 0)
    result, actual = weighted(scaled, -(factor - 1) * stem, ratio, 3)
    return result.transform(1, 0, 0, 1, p.bounds[0] - result.bounds[0], 0), actual


def fit_width(p, width, stem):
    old_width = p.bounds[2] - p.bounds[0]
    if old_width <= width:
        return p, True
    scale = (width - stem) / (old_width - stem)
    radius = (1 - scale) * stem / 2
    center = (p.bounds[0] + p.bounds[2]) / 2
    for tallness in [64, 16, 4, 1]:
        q = p.transform(scale, 0, 0, tallness, center * (1 - scale), 0)
        edge = pathops.Path(q)
        edge.stroke(
            2 * radius, pathops.LineCap.BUTT_CAP, pathops.LineJoin.MITER_JOIN, 3
        )
        edge.convertConicsToQuads(0.05)
        try:
            r = pathops.op(
                q, edge, pathops.PathOp.UNION, fix_winding=True, clockwise=True
            )
        except pathops.PathOpsError:
            continue
        from derive_weights import topology

        if topology(r) == topology(p):
            sy = (p.bounds[3] - p.bounds[1]) / (r.bounds[3] - r.bounds[1])
            return r.transform(1, 0, 0, sy, 0, p.bounds[1] - sy * r.bounds[1]), True
    return (
        p.transform(width / old_width, 0, 0, 1, center * (1 - width / old_width), 0),
        False,
    )


def main():
    original = TTFont(ROOT / "upstream/MetropolitanLine-Regular.ttf")
    factor = 1.12
    n = shape(original, "n")
    n_stem = vertical_stem(n, 0.4)
    order = []
    for name in ["n", "o", "a", "e", "s"]:
        p = shape(original, name)
        for amount in [-25, -12.5, 40]:
            weighted_p, actual = weighted(p, amount, 1, 3)
            weighted_n, _ = weighted(n, amount, 1, 3)
            old_order, _ = enlarge_lowercase(
                weighted_p, factor, vertical_stem(weighted_n, 0.4)
            )
            sized, _ = enlarge_lowercase(p, factor, n_stem)
            new_order, new_actual = weighted(sized, amount, 1, 3)
            new_order = new_order.transform(
                1, 0, 0, 1, old_order.bounds[0] - new_order.bounds[0], 0
            )
            order.append(
                {
                    "glyph": name,
                    "nominal_weight_delta": amount,
                    "actual_weight_before_size": actual,
                    "actual_weight_after_size": new_actual,
                    "coverage_difference": coverage_difference(new_order, old_order),
                    "bounds_weight_then_size": old_order.bounds,
                    "bounds_size_then_weight": new_order.bounds,
                }
            )
    h = shape(original, "H")
    target = 528
    naive = h.transform(target / (h.bounds[2] - h.bounds[0]), 0, 0, 1, 0, 0)
    fitted, safe = fit_width(h, target, vertical_stem(h))
    profiles = {}
    families = json.loads((ROOT / "family.json").read_text())["families"]
    for key, cfg in families.items():
        f = instantiateVariableFont(
            TTFont(ROOT / cfg["font"]),
            {"wght": 400, **({"opsz": 14} if key == "system" else {})},
            inplace=False,
        )
        profiles[key] = {
            "declared_x_height": f["OS/2"].sxHeight,
            "declared_cap_height": f["OS/2"].sCapHeight,
            "glyphs": {
                name: {"bounds": shape(f, name).bounds, "advance": f["hmtx"][name][0]}
                for name in ["H", "x", "n", "o", "w", "M", "W"]
            },
        }
    data = {
        "scope": "controlled Regular-based glyph probes, not reconstruction of all manual choices",
        "uniform_size_factor": factor,
        "source_n_stem": n_stem,
        "order_probes": order,
        "width_probe": {
            "glyph": "H",
            "source_ink_width": h.bounds[2] - h.bounds[0],
            "target_ink_width": target,
            "source_vertical_stem": vertical_stem(h),
            "naively_scaled_vertical_stem": vertical_stem(naive),
            "compensated_vertical_stem": vertical_stem(fitted),
            "topology_preserved": safe,
        },
        "current_regular_profiles": profiles,
    }
    (ROOT / "docs/scaling-study.json").write_text(json.dumps(data, indent=2) + "\n")
    print(
        json.dumps(
            {
                "width_probe": data["width_probe"],
                "largest_order_difference": max(
                    v["coverage_difference"] for v in order
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
