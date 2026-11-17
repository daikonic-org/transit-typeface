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
    "'\\n'": 0,
    "'\\''": 0,
    "'\\u{1F600}'": 0,
    "don't": 0,
    "foo'a": 0,
    "'123": 0,
    "'word'": 0,
    "'abcdefghijklmnopqrstuvwxyzabcdef'": 0,
}


def check(path):
    f = TTFont(path)
    h = hb.Font(hb.Face(path.read_bytes()))
    h.scale = (1000, 1000)
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
                got = sum(
                    n in ("quotesingle.lifetime", "code.lifetimeOpen") for n in names
                )
                assert got == (count if enabled else 0), (weight, text, enabled, names)
                assert sum(p.x_advance for p in b.glyph_positions) == 600 * len(text), (
                    weight,
                    text,
                    "advance",
                )
        gs = f.getGlyphSet(location={"wght": weight})
        p = shape_from_glyphs(gs, "quotesingle.lifetime")
        box = p.bounds
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
        "geometry": "rightward fit; horizontal terminal18units above x-height;22.5degree tapered prime from recipe",
        "context_limit": "quoted identifiers up to32 glyphs; does not parse source strings/comments",
    }
    print(
        "Rust lifetime checks passed:",
        len(CASES),
        "contexts,11weights,feature on/off,600unit cells and flat terminals",
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    path = (args.font or ROOT / specimen_families()["code"]["font"]).resolve()
    result = check(path)
    out = ROOT / "qa/rust-lifetimes.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
