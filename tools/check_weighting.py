"""Check interpolation without instancing every unused outline at every location."""

from io import BytesIO
from pathlib import Path
import argparse
import json
import subprocess
import tempfile

from fontTools.ttLib import TTFont
import ots
import uharfbuzz as hb

from adopt_weighting import OUT, ROOT
from audit import shape_from_glyphs, spans
from derive_weights import locked, topology
from validate import TOKENS


def variation_data(font, name):
    return [(v.axes, v.coordinates) for v in font["gvar"].variations.get(name, [])]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "family", choices=["all", "sans", "system", "code"], nargs="?", default="all"
    )
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    data = json.loads((ROOT / "family.json").read_text())
    recipe = json.loads((ROOT / "recipes/weights.json").read_text())
    for key, cfg in data["families"].items():
        if args.family not in ("all", key):
            continue
        target = OUT / key
        fontdir = ROOT / "fonts" / key if args.production else target / "fonts"
        font = TTFont(fontdir / "VF" / (cfg["stem"] + "-VF.ttf"))
        baseline = TTFont(ROOT / cfg.get("weighting_baseline", cfg["font"]))
        assert font.getGlyphOrder() == baseline.getGlyphOrder()
        assert font.getBestCmap() == baseline.getBestCmap()
        revised = set(cfg.get("layout_revision", {}).get("metric_overrides", []))
        for tag in ("GSUB", "GPOS", "GDEF", "HVAR", "MVAR"):
            if revised and tag in ("GPOS", "HVAR"):
                continue  # Explicitly checked by check_sans_hooks.py.
            if tag in baseline:
                assert font.getTableData(tag) == baseline.getTableData(tag), (key, tag)
        assert all(
            font["hmtx"][n][0] == baseline["hmtx"][n][0]
            for n in baseline.getGlyphOrder()
            if n not in revised
        )
        assert [
            (a.axisTag, a.minValue, a.defaultValue, a.maxValue)
            for a in font["fvar"].axes
        ] == [
            (a.axisTag, a.minValue, a.defaultValue, a.maxValue)
            for a in baseline["fvar"].axes
        ]
        protected = locked(font, recipe["defaults"]["locks"])
        # Compare complete selected-glyph functions, not only sampled snapshots.
        for name in protected:
            assert font["glyf"][name].compile(font["glyf"]) == baseline["glyf"][
                name
            ].compile(baseline["glyf"]), (key, name, "selected outline")
            assert variation_data(font, name) == variation_data(baseline, name), (
                key,
                name,
                "selected variations",
            )
        sanitized = []
        for exported in fontdir.rglob("*"):
            if exported.suffix not in (".ttf", ".woff2"):
                continue
            with tempfile.TemporaryDirectory() as tmp:
                r = subprocess.run(
                    [ots.OTS_SANITIZE, str(exported), str(Path(tmp) / "checked.ttf")],
                    capture_output=True,
                )
                assert r.returncode == 0, (exported, r.stderr.decode())
            sanitized.append(exported.name)
        stream = BytesIO()
        font.save(stream)
        face = hb.Face(stream.getvalue())
        samples = []
        for weight in (
            [300, 312.5, 325, 350, 375, 387.5, 400]
            if key == "code"
            else [300, 325, 350, 375, 400, 450, 500, 550, 600]
        ):
            for optical in [10, 12, 14, 24, 36] if key == "system" else [None]:
                location = {"wght": weight, **({"opsz": optical} if optical else {})}
                glyphs = font.getGlyphSet(location=location)
                old = baseline.getGlyphSet(location=location)
                assert all(
                    glyphs[n].width == old[n].width
                    for n in font.getGlyphOrder()
                    if n not in revised
                ), (key, location, "advance")
                for name in ["H", "n", "o", "a", "e", "s", "f", "t"] + [
                    font.getBestCmap()[ord(c)] for c in "←↑→↓↔↕⇐⇑⇒⇓⇔⇕"
                ]:
                    assert topology(shape_from_glyphs(glyphs, name)) == topology(
                        shape_from_glyphs(old, name)
                    ), (key, location, name, "counter topology")
                hfont = hb.Font(face)
                hfont.scale = (font["head"].unitsPerEm,) * 2
                hfont.set_variations(location)

                def run(text, features=None):
                    buffer = hb.Buffer()
                    buffer.add_str(text)
                    buffer.guess_segment_properties()
                    hb.shape(hfont, buffer, features or {})
                    return [
                        (font.getGlyphName(g.codepoint), p.x_advance)
                        for g, p in zip(buffer.glyph_infos, buffer.glyph_positions)
                    ]

                if key == "code":
                    assert all(
                        glyphs[n].width == 600 for n in font.getBestCmap().values()
                    )
                    for token in TOKENS:
                        got = run("a" + token + "n")
                        assert len(got) == 3 and sum(g[1] for g in got) == 600 * (
                            len(token) + 2
                        ), (location, token, got)
                    assert font["GDEF"].table.LigCaretList.LigGlyphCount == 12
                    bars = []
                    for token in ("=", "==", "==="):
                        p = shape_from_glyphs(glyphs, run(token)[0][0])
                        x0, _, x1, _ = p.bounds
                        bars.extend(b - a for a, b in spans(p, (x0 + x1) / 2, 0))
                    assert max(bars) - min(bars) <= 1, (
                        location,
                        "equals-family thickness",
                        bars,
                    )
                if key == "system":
                    assert run("1", {"tnum": True})[0][0] == "one.tnum"
                samples.append(location)
        report = {
            "sanitized": sanitized,
            "sampled_locations": samples,
            "metrics_and_layout": "passed",
            "explicit_metric_revisions": sorted(revised),
            "counter_topology_controls": "passed",
            "selected_glyph_variation_functions": "exact",
            "selected_glyph_count": len(protected),
            "evaluation": "Actual variable glyph sets and HarfBuzz at every location; full static snapshots/rebuilds checked by validate.py",
        }
        output = (
            ROOT / "qa" / key / "weighting-validation.json"
            if args.production
            else target / "validation.json"
        )
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(key, "validated", len(samples), "interpolation locations", flush=True)


if __name__ == "__main__":
    main()
