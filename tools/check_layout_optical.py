"""Check real shaping, CFF exports and default-preserving optical interpolation."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.varLib.instancer import instantiateVariableFont
import uharfbuzz as hb
import ots
from specimens import ROOT, specimen_families
from audit import shape_from_glyphs
from derive_weights import topology
from validate import TOKENS

OUT = ROOT / "trials/2026-11-17-layout-optical"


def shape(font, path, text, location, features=None):
    h = hb.Font(hb.Face(path.read_bytes()))
    h.scale = (1000, 1000)
    h.set_variations(location)
    b = hb.Buffer()
    b.add_str(text)
    b.guess_segment_properties()
    hb.shape(h, b, features or {})
    return [
        (font.getGlyphName(i.codepoint), p.x_advance, p.x_offset, p.y_offset)
        for i, p in zip(b.glyph_infos, b.glyph_positions)
    ]


def sanitized(path):
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(
            [ots.OTS_SANITIZE, str(path), str(Path(tmp) / "checked.ttf")],
            capture_output=True,
        )
        assert r.returncode == 0, (path, r.stderr.decode())


def mark_checks(path, sizes):
    font = TTFont(path)
    samples = []
    for w in [300, 312.5, 325, 350, 375, 387.5, 400]:
        for size in sizes:
            loc = {"wght": w, **({"opsz": size} if size is not None else {})}
            gs = font.getGlyphSet(location=loc)
            for text in [
                "q\u0301",
                "x\u0308",
                "q\u0326",
                "q\u0301\u0308",
                "i\u0301",
                "j\u0301",
                "A\u0301",
                "á",
                "a\u0301",
            ]:
                glyphs = shape(font, path, text, loc)
                assert sum(a for n, a, x, y in glyphs) == 600, (loc, text, glyphs)
                if len(glyphs) > 1:
                    base, n, a = glyphs[0][0], glyphs[1][0], glyphs[1]
                    base_pen = BoundsPen(gs)
                    gs[base].draw(base_pen)
                    pen = BoundsPen(gs)
                    gs[n].draw(pen)
                    mark_cx = 600 + a[2] + (pen.bounds[0] + pen.bounds[2]) / 2
                    base_cx = (base_pen.bounds[0] + base_pen.bounds[2]) / 2
                    assert abs(mark_cx - base_cx) < 2, (loc, text, mark_cx, base_cx)
                if len(glyphs) == 3:
                    assert glyphs[2][3] > glyphs[1][3] + 50, (loc, text, glyphs)
            assert shape(font, path, "á", loc) == shape(font, path, "a\u0301", loc)
            for token in TOKENS:
                got = shape(font, path, token, loc, {"calt": True, "liga": True})
                assert len(got) == 1 and got[0][1] == 600 * len(token), (
                    loc,
                    token,
                    got,
                )
            assert [v[2] for v in shape(font, path, "ke", loc)] == [18, -18]
            assert all(
                n == "at.compact" and a == 600
                for n, a, x, y in shape(font, path, "@@@", loc)
            )
            samples.append(loc)
    return samples


def main():
    cfg = specimen_families()
    report = {}
    positioned = OUT / "code/CodePositioned-VF.ttf"
    sanitized(positioned)
    report["code_positioning"] = {
        "locations": mark_checks(positioned, [None]),
        "checks": "top/bottom anchors, stacked marks, dotless contexts, canonical equivalence, zero mark advances, retained operators/spacing/compact fitting",
    }
    optical = json.loads((OUT / "optical-fonts.json").read_text())
    controls = [
        "H",
        "n",
        "o",
        "a",
        "e",
        "c",
        "s",
        "i",
        "j",
        "zero",
        "braceleft",
        "braceright",
        "parenleft",
        "percent",
        "at",
        "at.compact",
    ]
    for key, rel in optical.items():
        path = ROOT / rel
        sanitized(path)
        f = TTFont(path)
        baseline = TTFont(positioned if key == "code" else ROOT / cfg[key]["font"])
        for name in baseline.getGlyphOrder():
            assert f["glyf"][name].compile(f["glyf"]) == baseline["glyf"][name].compile(
                baseline["glyf"]
            ), (key, name, "default outline")
        rows = []
        weights = (
            [300, 325, 350, 375, 400]
            if key == "code"
            else [300, 325, 350, 375, 400, 450, 500, 550, 600]
        )
        for weight in weights:
            old = baseline.getGlyphSet(location={"wght": weight})
            default = f.getGlyphSet(location={"wght": weight, "opsz": 14})
            for name in baseline.getGlyphOrder():
                assert abs(old[name].width - default[name].width) < 0.01, (
                    key,
                    weight,
                    name,
                    "default advance",
                )
            for size in [10, 12, 14, 24, 36]:
                gs = f.getGlyphSet(location={"wght": weight, "opsz": size})
                for name in controls:
                    if name not in gs:
                        continue
                    expected = topology(shape_from_glyphs(old, name))
                    actual = topology(shape_from_glyphs(gs, name))
                    assert expected == actual, (
                        key,
                        weight,
                        size,
                        name,
                        expected,
                        actual,
                    )
                if key == "code":
                    for cp, name in f.getBestCmap().items():
                        import unicodedata

                        target = (
                            0 if unicodedata.category(chr(cp)).startswith("M") else 600
                        )
                        assert abs(gs[name].width - target) < 0.01, (
                            weight,
                            size,
                            name,
                            gs[name].width,
                        )
                rows.append({"wght": weight, "opsz": size})
        report[key] = {
            "default_outlines": "exact",
            "default_advances": "exact at all sampled weights",
            "interpolation_locations": rows,
            "control_counter_topology": "passed",
            "axes": [
                (a.axisTag, a.minValue, a.defaultValue, a.maxValue)
                for a in f["fvar"].axes
            ],
        }
        if key == "code":
            report[key]["mark_checks"] = mark_checks(path, [10, 12, 14, 24, 36])
        print(key, "optical interpolation/default checks passed", flush=True)
    # Audit retained proportional GPOS, including existing variable mark anchors.
    for key in ["sans", "system"]:
        f = TTFont(ROOT / cfg[key]["font"])
        features = {r.FeatureTag for r in f["GPOS"].table.FeatureList.FeatureRecord}
        assert {"kern", "mark", "mkmk"} <= features
        assert getattr(f["GDEF"].table, "VarStore", None)
        report[key + "_existing_gpos"] = {
            "features": sorted(features),
            "variable_anchors": True,
        }
    (OUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Positioning, optical trials and retained proportional GPOS verified")


if __name__ == "__main__":
    main()
