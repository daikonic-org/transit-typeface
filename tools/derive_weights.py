"""Configured Regular-anchored weight studies; never overwrite released fonts."""

from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json
import math
import subprocess
import tempfile
import unicodedata

from fontTools.misc.roundTools import otRound
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.freetypePen import FreeTypePen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import ImageChops
import pathops
import ots
from audit import shape, spans

ROOT = Path(__file__).resolve().parents[1]


def topology(p):
    return tuple(
        sum(c.clockwise == orientation and c.area > 50 for c in p.contours)
        for orientation in [True, False]
    )


def grow(p, amount, ratio, miter):
    if not amount:
        return p
    stretched = p.transform(1, 0, 0, 1 / ratio, 0, 0)
    edge = pathops.Path(stretched)
    edge.stroke(
        abs(amount), pathops.LineCap.BUTT_CAP, pathops.LineJoin.MITER_JOIN, miter
    )
    edge.convertConicsToQuads(0.05)
    result = pathops.op(
        stretched,
        edge,
        pathops.PathOp.UNION if amount > 0 else pathops.PathOp.DIFFERENCE,
        fix_winding=True,
        clockwise=True,
    )
    result = result.transform(1, 0, 0, ratio, 0, 0)
    low, high = p.bounds[1], p.bounds[3]
    bottom, top = result.bounds[1], result.bounds[3]
    if top <= bottom:
        raise ValueError("empty weighted path")
    scale = (high - low) / (top - bottom)
    return result.transform(1, 0, 0, scale, 0, low - scale * bottom)


def weighted(p, amount, ratio, miter):
    expected = topology(p)
    for factor in [1, 0.75, 0.5, 0.25, 0]:
        actual = amount * factor
        try:
            result = grow(p, actual, ratio, miter)
            if topology(result) == expected:
                return result, actual
        except (pathops.PathOpsError, ValueError):
            pass
    raise ValueError("no topology-preserving candidate")


def coverage_difference(a, b):
    left = math.floor(min(a.bounds[0], b.bounds[0])) - 3
    bottom = math.floor(min(a.bounds[1], b.bounds[1])) - 3
    right = math.ceil(max(a.bounds[2], b.bounds[2])) + 3
    top = math.ceil(max(a.bounds[3], b.bounds[3])) + 3
    images = []
    for p in [a, b]:
        pen = FreeTypePen(None)
        p.draw(pen)
        images.append(
            pen.image(
                width=2 * (right - left),
                height=2 * (top - bottom),
                transform=(2, 0, 0, 2, -2 * left, -2 * bottom),
            ).getchannel("A")
        )
    error = sum(i * n for i, n in enumerate(ImageChops.difference(*images).histogram()))
    area = sum(i * n for i, n in enumerate(images[1].histogram()))
    return error / area if area else 0


def install(font, name, p):
    pen = TTGlyphPen(None)
    p.draw(Cu2QuPen(pen, 0.15, reverse_direction=False))
    glyph = pen.glyph()
    font["glyf"][name] = glyph
    glyph.recalcBounds(font["glyf"])
    font["hmtx"][name] = (
        font["hmtx"][name][0],
        glyph.xMin if glyph.numberOfContours else 0,
    )


def stem(font):
    p = shape(font, "H")
    _, lo, _, hi = p.bounds
    values = spans(p, lo + (hi - lo) * 0.25, 1)
    return sum(b - a for a, b in values) / len(values)


def locked(font, config):
    roots = set(config["roots"])
    categories = set(config.get("unicode_categories", []))
    names = set()
    for cp, name in font.getBestCmap().items():
        if (
            unicodedata.normalize("NFD", chr(cp))[0] in roots
            or unicodedata.category(chr(cp))[0] in categories
        ):
            names.add(name)
    for name in font.getGlyphOrder():
        if name.split(".")[0] in roots or any(
            name.startswith(prefix) for prefix in config["prefixes"]
        ):
            names.add(name)
    return names


def names(font, key, weight, optical, source, ratio):
    model = (
        ("Upstream" if source == "upstream-regular" else "Approved")
        + "R"
        + str(ratio).replace(".", "p")
    )
    family = f"Daikonic Transit {key.title()} Study {model}"
    style = {300: "Light", 350: "Book", 400: "Regular", 500: "Medium", 600: "SemiBold"}[
        weight
    ]
    if optical is not None:
        style += " " + str(optical)
    ps = family.replace(" ", "") + "-" + style.replace(" ", "")
    values = {
        1: family,
        2: style,
        3: ps + " 0.001",
        4: family + " " + style,
        5: "Version 0.001; experimental Regular-anchored weight study",
        6: ps,
        16: family,
        17: style,
        18: family + " " + style,
        21: family,
        22: style,
        25: family.replace(" ", ""),
    }
    for record in font["name"].names:
        if record.nameID in values:
            record.string = values[record.nameID].encode(record.getEncoding())
    font["head"].fontRevision = 0.001
    font["OS/2"].usWeightClass = weight
    font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~(1 | 32)) | 64
    font["head"].macStyle = 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "family", choices=["all", "sans", "system", "code"], nargs="?", default="all"
    )
    parser.add_argument("--ratio-y", type=float)
    parser.add_argument(
        "--source",
        choices=["approved-regular", "upstream-regular"],
        default="approved-regular",
    )
    parser.add_argument("--no-locks", action="store_true")
    args = parser.parse_args()
    config = json.loads((ROOT / "recipes/weights.json").read_text())
    families = json.loads((ROOT / "family.json").read_text())["families"]
    defaults = config["defaults"]
    ratio = (
        args.ratio_y
        if args.ratio_y is not None
        else defaults["horizontal_growth_ratio"]
    )
    assert 0.2 <= ratio <= 1.5
    if args.source == "upstream-regular" and args.family != "sans":
        parser.error(
            "upstream-regular is a Sans baseline study; use family sans. Other families retain declared designed Regular sources."
        )
    output = ROOT / ".build" / "weight-studies" / f"{args.source}-ratio-{ratio:g}"
    output.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for key, cfg in families.items():
        if args.family not in ["all", key]:
            continue
        recipe = config["families"][key]
        records = []
        for optical in recipe["optical_sizes"]:
            source = (
                ROOT / cfg.get("weighting_baseline", cfg["font"])
                if args.source == "approved-regular"
                else ROOT / "upstream/MetropolitanLine-Regular.ttf"
            )
            location = {
                "wght": defaults["anchor_weight"],
                **({"opsz": optical} if optical is not None else {}),
            }
            anchor = (
                instantiateVariableFont(TTFont(source), location, inplace=False)
                if args.source == "approved-regular"
                else TTFont(source)
            )
            paths = {
                name: shape(anchor, name)
                for name in anchor.getGlyphOrder()
                if anchor["glyf"][name].numberOfContours
            }
            protected = (
                locked(anchor, defaults["locks"])
                if not args.no_locks and args.source == "approved-regular"
                else set()
            )
            baseline = stem(anchor)
            for weight_string, target in recipe["target_H_stems"].items():
                weight = int(weight_string)
                amount = target - baseline
                reference = (
                    instantiateVariableFont(
                        TTFont(ROOT / cfg.get("weighting_baseline", cfg["font"])),
                        {
                            "wght": weight,
                            **({"opsz": optical} if optical is not None else {}),
                        },
                        inplace=False,
                    )
                    if args.source == "approved-regular"
                    else deepcopy(anchor)
                )
                font = deepcopy(reference)
                backoffs = {}
                errors = {}
                applied = {}
                for name, p in paths.items():
                    if name in protected or amount == 0:
                        continue
                    transformed, actual = weighted(
                        p, amount, ratio, defaults["miter_limit"]
                    )
                    expected = shape(reference, name)
                    shift = (
                        expected.bounds[0]
                        + expected.bounds[2]
                        - transformed.bounds[0]
                        - transformed.bounds[2]
                    ) / 2
                    transformed = transformed.transform(1, 0, 0, 1, shift, 0)
                    install(font, name, transformed)
                    applied[name] = round(actual, 4)
                    if actual != amount:
                        backoffs[name] = {"requested": amount, "actual": actual}
                    if name in ["H", "n", "o", "a", "e", "s", "f", "t"]:
                        errors[name] = coverage_difference(shape(font, name), expected)
                roundtrips = {}
                for name in ["H", "n", "o", "a", "e", "s"]:
                    p = paths[name]
                    down, actual = weighted(p, -25, ratio, defaults["miter_limit"])
                    up, _ = weighted(down, -actual, ratio, defaults["miter_limit"])
                    shift = (
                        p.bounds[0] + p.bounds[2] - up.bounds[0] - up.bounds[2]
                    ) / 2
                    up = up.transform(1, 0, 0, 1, shift, 0)
                    roundtrips[name] = {
                        "lightening": actual,
                        "coverage_error_after_return": coverage_difference(up, p),
                        "counter_area_original": sum(
                            c.area for c in p.contours if not c.clockwise
                        ),
                        "counter_area_return": sum(
                            c.area for c in up.contours if not c.clockwise
                        ),
                    }
                if amount == 0:
                    assert all(
                        font["glyf"][name].compile(font["glyf"])
                        == anchor["glyf"][name].compile(anchor["glyf"])
                        for name in anchor.getGlyphOrder()
                    )
                names(font, key, weight, optical, args.source, ratio)
                if key == "code":
                    assert all(
                        font["hmtx"][n][0] == 600 for n in font.getBestCmap().values()
                    )
                filename = (
                    f"{key}-{weight}"
                    + (f"-opsz{optical}" if optical is not None else "")
                    + ".ttf"
                )
                dest = output / filename
                font.save(dest)
                with tempfile.TemporaryDirectory() as tmp:
                    check = subprocess.run(
                        [ots.OTS_SANITIZE, str(dest), str(Path(tmp) / "checked.ttf")],
                        capture_output=True,
                    )
                    assert check.returncode == 0, (key, weight, check.stderr.decode())
                records.append(
                    {
                        "file": str(dest.relative_to(ROOT)),
                        "anchor": str(source.relative_to(ROOT)),
                        "anchor_sha256": hashlib.sha256(
                            source.read_bytes()
                        ).hexdigest(),
                        "anchor_location": location,
                        "requested_weight": weight,
                        "requested_H_stem": target,
                        "measured_H_stem": stem(font),
                        "nominal_offset": amount,
                        "regular_outlines_retained_exactly": amount == 0,
                        "ratio_y": ratio,
                        "metrics": "matched approved weight/profile; upstream study retains upstream metrics",
                        "preserved_design_glyphs": sorted(protected),
                        "backoffs": backoffs,
                        "actual_offsets": applied,
                        "coverage_difference_from_approved": errors,
                        "roundtrip": roundtrips,
                        "sanitizer": "passed",
                    }
                )
                print(
                    key,
                    weight,
                    optical,
                    "H stem",
                    stem(font),
                    "backoffs",
                    len(backoffs),
                    flush=True,
                )
        summaries[key] = records
    (output / "report.json").write_text(json.dumps(summaries, indent=2) + "\n")
    (ROOT / "docs" / f"weight-study-{args.source}-ratio-{ratio:g}.json").write_text(
        json.dumps(summaries, indent=2) + "\n"
    )
    print("Experimental fonts and report:", output.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
