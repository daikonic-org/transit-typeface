"""Check contextual Rust lifetime marks, protected literals and prime geometry."""

import argparse
import json
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
import uharfbuzz as hb
from specimens import ROOT, specimen_families
from audit import shape_from_glyphs

CASES = {
    "'a": 1,
    "&'a": 1,
    "&'static str": 1,
    "Vec<'a>": 1,
    "for<'a>": 1,
    "<'a, 'b>": 2,
    "&'_": 1,
    "'outer: loop { break 'outer; }": 2,
    "T: 'static": 1,
    "'é": 1,
    "&'a mut T": 1,
    "<'a, 'b, 'static, '_>": 4,
    "'a'": 0,
    "'_'": 0,
    "'é'": 0,
    "'x' + &'a": 1,
    "<'a'>": 0,
    "&'a'": 0,
    "'\\n'": 0,
    "'\\''": 0,
    "'\\u{1F600}'": 0,
    "don't": 0,
    "foo'a": 0,
    "'123": 0,
    "'word'": 0,
    "'abcdefghijklmnopqrstuvwxyzabcdef'": 0,
}


def check_legacy(path):
    f = TTFont(path)
    h = hb.Font(hb.Face(path.read_bytes()))
    results = []
    for weight in range(300, 401, 10):
        h.set_variations({"wght": weight})
        for text, count in CASES.items():
            for enabled in [True, False]:
                b = hb.Buffer()
                b.add_str(text)
                b.guess_segment_properties()
                hb.shape(h, b, {"calt": enabled, "liga": True, "clig": True})
                names = [f.getGlyphName(g.codepoint) for g in b.glyph_infos]
                got = sum(n in ("quotesingle.lifetime",) for n in names)
                if f["hmtx"]["code.lifetimeOpen"][0] == 1200:
                    got += sum(
                        n in ("code.lifetimeOpen", "code.lifetimeBorrow") for n in names
                    )
                assert got == (count if enabled else 0), (weight, text, enabled, names)
                if enabled and text in ("&'a", "<'a, 'b>"):
                    expected_pair = (
                        "code.lifetimeBorrow"
                        if text.startswith("&")
                        else "code.lifetimeOpen"
                    )
                    assert names[0] == expected_pair, (weight, text, names)
                assert sum(p.x_advance for p in b.glyph_positions) == 600 * len(text), (
                    weight,
                    text,
                    "advance",
                )
        gs = f.getGlyphSet(location={"wght": weight})
        p = shape_from_glyphs(gs, "quotesingle.lifetime")
        box = p.bounds
        quote_style = (
            "code.lifetimeOpen" in f["hmtx"].metrics
            and f["hmtx"]["code.lifetimeOpen"][0] == 600
        )
        if quote_style:
            assert abs((box[0] + box[2]) / 2 - 600) < 1, (weight, box)
            quote = shape_from_glyphs(gs, "quoteleft").bounds
            assert (
                max(
                    abs(x - y)
                    for x, y in zip(
                        box, (quote[0] + 300, quote[1], quote[2] + 300, quote[3])
                    )
                )
                < 1
            )
            results.append({"wght": weight, "bounds": list(box)})
            continue
        assert 0 < box[0] < box[2] < 600, (weight, box)
        expected = shape_from_glyphs(gs, "x").bounds[3] + 18
        assert abs(box[1] - expected) < 1.5, (
            weight,
            "x-height clearance",
            box,
            expected,
        )
        pen = RecordingPen()
        gs["quotesingle.lifetime"].draw(pen)
        previous = None
        flat = False
        for verb, pts in pen.value:
            if verb in ("lineTo", "qCurveTo", "curveTo") and previous:
                end = pts[-1]
                if (
                    abs(previous[1] - box[1]) < 0.01
                    and all(abs(point[1] - box[1]) < 0.01 for point in pts)
                    and abs(end[0] - previous[0]) > 15
                ):
                    flat = True
            if pts:
                previous = pts[-1]
        assert flat, (weight, "horizontal bottom terminal")
        results.append({"wght": weight, "bounds": list(box)})
    report = {
        "font": str(path.relative_to(ROOT)),
        "cases": CASES,
        "weights": results,
        "feature_off": "no lifetime alternates",
        "advance": "600 per input character",
        "geometry": (
            "existing opening quote centered on boundary before following letter cell; contextual vertical clearance"
            if quote_style
            else "rightward fit; horizontal terminal18units above x-height;22.5degree tapered prime from recipe"
        ),
        "context_limit": "quoted identifiers up to32 glyphs; does not parse source strings/comments",
    }
    print(
        "Rust lifetime checks passed:",
        len(CASES),
        "contexts,11weights,feature on/off,600unit advances and marker geometry",
    )
    return report


def check(path):
    f = TTFont(path)
    if "quotesingle.lifetime.compact" not in f.getGlyphOrder():
        return check_legacy(path)
    record = next(
        (r for r in f["GSUB"].table.FeatureList.FeatureRecord if r.FeatureTag == "ss01"), None
    )
    if record is None or (
        f["name"].getDebugName(record.Feature.FeatureParams.UINameID)
        == "Extended Rust lifetime hooks"
    ):
        from code_lifetime_hook import check as check_hooks

        return check_hooks(path, extended=record is not None)
    h = hb.Font(hb.Face(path.read_bytes()))

    def run(text, calt, compact):
        b = hb.Buffer()
        b.add_str(text)
        b.guess_segment_properties()
        hb.shape(h, b, {"calt": calt, "ss01": compact})
        return [
            (f.getGlyphName(g.codepoint), p.x_advance, p.x_offset, p.y_offset)
            for g, p in zip(b.glyph_infos, b.glyph_positions)
        ]

    results = []
    for weight in range(300, 401, 10):
        h.set_variations({"wght": weight})
        for calt in (False, True):
            for compact in (False, True):
                for text, count in CASES.items():
                    shaped = run(text, calt, compact)
                    marks = [
                        n
                        for n, a, x, y in shaped
                        if n.startswith("quotesingle.lifetime")
                    ]
                    assert len(marks) == (count if calt or compact else 0), (
                        weight,
                        text,
                        calt,
                        compact,
                        shaped,
                    )
                    expected = (
                        "quotesingle.lifetime.compact"
                        if compact
                        else "quotesingle.lifetime"
                    )
                    assert all(n == expected for n in marks), (
                        weight,
                        text,
                        calt,
                        compact,
                        shaped,
                    )
                    assert sum(a for n, a, x, y in shaped) == 600 * len(text)
                for text in (
                    "->",
                    "->>",
                    "=>",
                    "==",
                    "===",
                    "###",
                    "?.",
                    "!.",
                    "::",
                    "Vec<T>",
                ):
                    assert run(text, calt, False) == run(text, calt, True), (
                        weight,
                        text,
                        "independent switch",
                    )
        gs = f.getGlyphSet(location={"wght": weight})
        normal = shape_from_glyphs(gs, "quotesingle.lifetime").bounds
        quote = shape_from_glyphs(gs, "quoteleft").bounds
        compact = shape_from_glyphs(gs, "quotesingle.lifetime.compact").bounds
        assert max(abs(a - b) for a, b in zip(normal, quote)) < 1, (
            weight,
            "normal quote outline",
        )
        assert (
            max(
                abs(a - b)
                for a, b in zip(
                    compact, (quote[0] + 300, quote[1], quote[2] + 300, quote[3])
                )
            )
            < 1
        )
        assert abs((compact[0] + compact[2]) / 2 - 600) < 1
        results.append(
            {
                "wght": weight,
                "normal_bounds": list(normal),
                "compact_bounds": list(compact),
            }
        )
    record = next(
        r for r in f["GSUB"].table.FeatureList.FeatureRecord if r.FeatureTag == "ss01"
    )
    label = f["name"].getDebugName(record.Feature.FeatureParams.UINameID)
    assert label == "Boundary-centered Rust lifetimes", label
    print(
        "Rust lifetime toggle passed:26contexts,11weights,all4calt/ss01 combinations; other coding ligatures unchanged"
    )
    return {
        "font": str(path.relative_to(ROOT)),
        "cases": CASES,
        "weights": results,
        "feature": "ss01",
        "label": label,
        "default": "normal opening quote in its own cell under calt",
        "toggle": "ss01 shifts lifetime quote to boundary and < / & one cell right; works independently of calt",
        "advance": "600 per input character",
        "other_coding_features": "unchanged with ss01 toggle",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    path = (args.font or ROOT / specimen_families()["code"]["font"]).resolve()
    result = check(path)
    out = ROOT / "qa/rust-lifetimes.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
