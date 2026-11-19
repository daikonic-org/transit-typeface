"""Left-hook lifetime markers; ss01 extends the straight bar into the next cell."""

from pathlib import Path
import json
import math
import unicodedata
import pathops
from fontTools.ttLib import TTFont
from audit import shape_from_glyphs, spans
from font_feature_tools import (
    from_paths,
    master_locations,
    compose,
    add_features,
    label_stylistic_set,
)
from specimens import ROOT, DATA, Panel
from check_syntax_numerals import run

SOURCE = ROOT / "sources/code-rust-generics/VF/DaikonicTransitCode-VF.ttf"
OUT = ROOT / "sources/code-lifetime-hook/VF/DaikonicTransitCode-VF.ttf"
OPT_IN_SHIFT = (40, 45)
PROOF = ROOT / "trials/2026-11-18-lifetime-designs/Lifetime-Extension.svg"


def marker(gs):
    # Retain the study's small footprint, with full-size l stem thickness.
    stem = spans(shape_from_glyphs(gs, "l"), 400, 1)[0]
    thickness = stem[1] - stem[0]
    right = 435
    cx, cy, radius = 315, 550, 150
    inner = radius - thickness
    k = 0.5522847498307936
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo((right, 700))
    pen.lineTo((cx, 700))
    pen.curveTo((cx - k * radius, 700), (165, cy + k * radius), (165, cy))
    pen.lineTo((165, 490))
    pen.lineTo((165 + thickness, 490))
    pen.lineTo((165 + thickness, cy))
    pen.curveTo(
        (165 + thickness, cy + k * inner),
        (cx - k * inner, cy + inner),
        (cx, cy + inner),
    )
    pen.lineTo((right, 700 - thickness))
    pen.closePath()
    return path


def build():
    font = TTFont(SOURCE, recalcTimestamp=False)
    _, locations = master_locations(font)
    from_paths(
        font,
        "quotesingle.lifetime",
        locations,
        [marker(font.getGlyphSet(location=loc)) for loc in locations],
        600,
    )
    compose(
        font,
        "quotesingle.lifetime.compact",
        [("quotesingle.lifetime", 1, 1, 0, 0)],
        600,
    )
    # Extend the already-converted outline, preserving the hook point for point.
    glyph = font["glyf"]["quotesingle.lifetime.compact"]
    indices = [i for i, (x, y) in enumerate(glyph.coordinates) if x == 435]
    assert len(indices) == 4
    for i in indices:
        x, y = glyph.coordinates[i]
        glyph.coordinates[i] = (x + 245, y)
    for variation in font["gvar"].variations["quotesingle.lifetime.compact"]:
        assert all(variation.coordinates[i][0] == 0 for i in indices)
    glyph.recalcBounds(font["glyf"])
    # ss01 no longer moves the preceding & or < into the marker's cell.
    for name, source in [
        ("code.lifetimeOpen", "less.generic"),
        ("code.lifetimeBorrow", "ampersand"),
    ]:
        compose(font, name, [(source, 1, 1, 0, 0)], 600, metric_source=source)
    # Replace the old boundary-centered quote positioning with geometry-based clearance.
    for record in font["GPOS"].table.FeatureList.FeatureRecord:
        if record.FeatureTag == "ss01":
            record.Feature.LookupListIndex = []
            record.Feature.LookupCount = 0
    samples = [font.getGlyphSet(location={"wght": w}) for w in range(300, 401, 10)]
    starts = sorted(
        {
            name
            for cp, name in font.getBestCmap().items()
            if unicodedata.category(chr(cp)).startswith("L")
        }
        | {"underscore", "dotlessi", "dotlessj"}
    )
    heights = {}
    for name in starts:
        overlap = any(
            pathops.op(
                shape_from_glyphs(gs, "quotesingle.lifetime.compact").transform(
                    1, 0, 0, 1, *OPT_IN_SHIFT
                ),
                shape_from_glyphs(gs, name).transform(1, 0, 0, 1, 600, 0),
                pathops.PathOp.INTERSECTION,
            ).area
            > 0.01
            for gs in samples
        )
        # Only the straight bar reaches the following cell; its lower edge sets clearance.
        bottom = min(
            700
            - (
                spans(shape_from_glyphs(gs, "l"), 400, 1)[0][1]
                - spans(shape_from_glyphs(gs, "l"), 400, 1)[0][0]
            )
            for gs in samples
        )
        top = max(shape_from_glyphs(gs, name).bounds[3] for gs in samples)
        rise = max(0, math.ceil(top + 14 - bottom - OPT_IN_SHIFT[1])) if overlap else 0
        heights.setdefault(rise, []).append(name)
    lines = ["languagesystem DFLT dflt;", "languagesystem latn dflt;"]
    for rise, names in sorted(heights.items()):
        lines.append(f"@HookHeight{rise}=[" + " ".join(names) + "];")
    lines += [
        "feature ss01 {",
        f"lookup LifetimeHookInset {{ pos [quotesingle.lifetime.compact code.lifetimeOpen code.lifetimeBorrow] <{OPT_IN_SHIFT[0]} {OPT_IN_SHIFT[1]} 0 0>; }} LifetimeHookInset;",
        "lookup LifetimeHookClearance { lookupflag IgnoreMarks;",
    ]
    for rise in sorted(heights):
        lines.append(
            f"pos quotesingle.lifetime.compact' <0 {rise} 0 0> @HookHeight{rise};"
        )
    lines += ["} LifetimeHookClearance; } ss01;"]
    add_features(font, "\n".join(lines))
    label_stylistic_set(font, "ss01", "Extended Rust lifetime hooks")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    font.save(OUT)
    return OUT


def check(path, *, extended=True):
    from check_rust_lifetimes import CASES

    font = TTFont(path)
    report = []
    source = TTFont(SOURCE)
    changed = {
        "quotesingle.lifetime",
        "quotesingle.lifetime.compact",
        "code.lifetimeOpen",
        "code.lifetimeBorrow",
    }
    from code_structural_fit import separate_enclosures, INTERPOLATION

    if separate_enclosures(font):
        changed.update(INTERPOLATION)
    if "m.heal.both" in font.getGlyphOrder():
        from code_receiver_shapes import RECEIVERS

        changed.update(RECEIVERS)
    if font["glyf"]["i"].yMin == font["glyf"]["n"].yMin:
        from code_i_baseline import align_i_baseline

        align_i_baseline(source)
    if "code.equal.loose" in font.getGlyphOrder():
        from code_compact_operators import CHANGED_BASE_GLYPHS

        changed.update(CHANGED_BASE_GLYPHS)
    for name in source.getGlyphOrder():
        if name not in changed:
            assert font["glyf"][name].compile(font["glyf"]) == source["glyf"][
                name
            ].compile(source["glyf"]), name
            assert font["gvar"].variations.get(name) == source["gvar"].variations.get(
                name
            ), name
            assert font["hmtx"][name] == source["hmtx"][name], name
    for w in range(300, 401, 10):
        gs = font.getGlyphSet(location={"wght": w})
        a = shape_from_glyphs(gs, "quotesingle.lifetime").bounds
        b = shape_from_glyphs(gs, "quotesingle.lifetime.compact").bounds
        clip = pathops.Path()
        pen = clip.getPen()
        pen.moveTo((-1000, -1000))
        for point in [(300, -1000), (300, 2000), (-1000, 2000)]:
            pen.lineTo(point)
        pen.closePath()
        hook_a = pathops.op(
            shape_from_glyphs(gs, "quotesingle.lifetime"),
            clip,
            pathops.PathOp.INTERSECTION,
        )
        hook_b = pathops.op(
            shape_from_glyphs(gs, "quotesingle.lifetime.compact"),
            clip,
            pathops.PathOp.INTERSECTION,
        )
        assert abs(pathops.op(hook_a, hook_b, pathops.PathOp.XOR).area) < 1, (
            w,
            "hook changed",
        )
        assert abs(a[0] - b[0]) < 1 and abs(a[1] - b[1]) < 1 and abs(a[3] - b[3]) < 1
        assert abs(b[2] - 680) < 1
        stem = spans(shape_from_glyphs(gs, "l"), 400, 1)[0]
        for glyph in ["quotesingle.lifetime", "quotesingle.lifetime.compact"]:
            bar = spans(shape_from_glyphs(gs, glyph), 400, 0)[0]
            assert abs((bar[1] - bar[0]) - (stem[1] - stem[0])) < 1.1, (
                w,
                glyph,
                bar,
                stem,
            )
        for calt in [False, True]:
            for enabled in ([False, True] if extended else [False]):
                for text, count in CASES.items():
                    shaped = run(
                        path, text, {"wght": w}, {"calt": calt, "ss01": enabled}
                    )
                    assert sum(v[1] for v in shaped) == len(text) * 600
                    for name, advance, x, y in shaped:
                        if name.startswith("quotesingle.lifetime"):
                            assert x == (OPT_IN_SHIFT[0] if enabled else 0), (
                                text,
                                enabled,
                                name,
                                x,
                            )
                            if enabled:
                                assert y >= OPT_IN_SHIFT[1]
                        if enabled and name in [
                            "code.lifetimeOpen",
                            "code.lifetimeBorrow",
                        ]:
                            assert (x, y) == OPT_IN_SHIFT, (text, name, x, y)
                    marks = [
                        n for n, *_ in shaped if n.startswith("quotesingle.lifetime")
                    ]
                    assert len(marks) == (count if calt or enabled else 0), (
                        text,
                        shaped,
                    )
        for letter in ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_é" if extended else ""):
            for prefix in ["'", "&'", "<'"]:
                shaped = run(
                    path, prefix + letter, {"wght": w}, {"calt": True, "ss01": True}
                )
                cursor = 0
                items = []
                for n, advance, x, y in shaped:
                    items.append(
                        (
                            n,
                            shape_from_glyphs(gs, n).transform(
                                1, 0, 0, 1, cursor + x, y
                            ),
                        )
                    )
                    cursor += advance
                ink = next(p for n, p in items if n == "quotesingle.lifetime.compact")
                for n, p in items:
                    if n != "quotesingle.lifetime.compact":
                        assert (
                            pathops.op(ink, p, pathops.PathOp.INTERSECTION).area < 1
                        ), (w, prefix + letter, n)
                assert ink.bounds[3] <= font["OS/2"].usWinAscent, (
                    w,
                    letter,
                    ink.bounds,
                )
        report.append({"weight": w, "normal": list(a), "extended": list(b)})
    if extended:
        (PROOF.parent / "extension-checks.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
    result = {
        "font": str(path.relative_to(ROOT)),
        "weights": report,
        "feature": "ss01" if extended else "calt",
        "label": "Extended Rust lifetime hooks" if extended else "Rust lifetime hooks",
        "default": "left downward hook in its own cell",
        "advance": "600 per input character",
    }
    if extended:
        result["toggle"] = "extend stroke to680; opt-in marker and leaders +40x/+45y; advances fixed"
    print("Lifetime hooks: 11 weights, contextual selection and fixed cells verified")
    return result


def proof(path):
    cfg = {**DATA["families"]["code"], "font": str(path.relative_to(ROOT))}
    p = Panel("lifetime-hook", cfg)
    header = [
        '<rect width="1100" height="730" fill="#eeeddb"/>',
        "<style>text{font-family:Arial,sans-serif;fill:#172331}</style>",
        '<text x="35" y="40" font-size="25">Left-hook lifetime marker · normal and opt-in</text>',
        '<text x="35" y="75" font-size="15">Normal</text>',
        '<text x="570" y="75" font-size="15">Extended + inset · ss01</text>',
    ]
    for row, w in enumerate([300, 350, 400]):
        y = 125 + row * 150
        header.append(f'<text x="35" y="{y}" font-size="13">Weight {w}</text>')
        for x, enabled in [(35, False), (570, True)]:
            p.text(
                "&'a <'a> 'static",
                x,
                y + 48,
                32,
                w,
                "#172331",
                features={"ss01": enabled},
            )
            p.text(
                "'T 'l '_ 'é 'a'",
                x,
                y + 98,
                24,
                w,
                "#172331",
                features={"ss01": enabled},
            )
    header.append('<rect x="25" y="580" width="1050" height="100" fill="#142130"/>')
    for x, enabled in [(35, False), (570, True)]:
        p.text(
            "&'a <'_> 'static", x, 620, 18, 350, "#eeeddb", features={"ss01": enabled}
        )
        p.text(
            "&'a <'_> 'static", x, 660, 14, 350, "#eeeddb", features={"ss01": enabled}
        )
    PROOF.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="730">'
        + "<defs>"
        + "".join(p.defs.values())
        + "</defs>"
        + "".join(header)
        + "".join(p.elements)
        + "</svg>"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    path = args.font or build()
    check(path)
    proof(path)
