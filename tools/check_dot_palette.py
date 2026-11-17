"""Verify shared-dot variation, retained bodies, metrics and bullet separation."""

import json
import subprocess
import tempfile
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.varLib.models import supportScalar
import ots
from dot_palette import OUT, indices, expanded_variations
from dot_inventory import dots
from specimens import ROOT


def main():
    paths = json.loads((OUT / "fonts.json").read_text())
    reports = json.loads((OUT / "report.json").read_text())
    recipe = json.loads((ROOT / "recipes/syntax-numeral-trial.json").read_text())
    checks = {}
    for key, rel in paths.items():
        f = TTFont(ROOT / rel)
        old = TTFont(ROOT / recipe["inputs"][key]["font"])
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run(
                [ots.OTS_SANITIZE, str(ROOT / rel), str(Path(tmp) / "font.ttf")],
                capture_output=True,
            )
            assert p.returncode == 0, p.stderr.decode()
        changed = reports[key]["glyphs"]
        assert f["hmtx"].metrics.keys() == old["hmtx"].metrics.keys()
        for name in f.getGlyphOrder():
            assert f["hmtx"][name][0] == old["hmtx"][name][0], (key, name, "advance")
            if name not in changed:
                assert f["glyf"][name].compile(f["glyf"]) == old["glyf"][name].compile(
                    old["glyf"]
                ), (key, name, "unchanged")
                continue
            # The generator puts preserved body contours before shared dots.
            dotpoints = {i for ix in indices(old, name) for i in ix}
            body = [
                i
                for i in range(len(old["glyf"][name].coordinates))
                if i not in dotpoints
            ]
            count = len(body)
            assert list(f["glyf"][name].coordinates)[:count] == [
                old["glyf"][name].coordinates[i] for i in body
            ], (key, name, "body")
            a = expanded_variations(f, name)
            b = expanded_variations(old, name)
            for support in set(a) | set(b):
                av = a.get(support, [(0, 0)] * (len(f["glyf"][name].coordinates) + 4))
                bv = b.get(support, [(0, 0)] * (len(old["glyf"][name].coordinates) + 4))
                assert av[:count] == [bv[i] for i in body], (
                    key,
                    name,
                    "body variation",
                )
                assert av[-4:] == bv[-4:], (key, name, "phantoms")
        for table in ["GSUB", "GPOS", "GDEF", "HVAR"]:
            assert f[table].compile(f) == old[table].compile(old), (
                key,
                table,
                "retained",
            )
        weights = (
            [300, 312.5, 325, 350, 375, 387.5, 400]
            if key == "code"
            else [300, 325, 350, 375, 400, 450, 500, 550, 600]
        )
        samples = []
        for w in weights:
            for o in [10, 12, 14, 24, 36] if key == "system" else [None]:
                loc = {"wght": w, **({"opsz": o} if o else {})}
                gs = f.getGlyphSet(location=loc)
                master_name = recipe["dots"]["master_glyphs"][key]
                master = dots(gs, master_name)[0][1]
                reference = dots(old.getGlyphSet(location=loc), master_name)[0][1]
                assert abs(master["width"] - reference["width"]) < 2.1
                assert abs(master["height"] - reference["height"]) < 2.1
                for name, entry in changed.items():
                    found = dots(gs, name)
                    assert len(found) == entry["dots"], (
                        key,
                        loc,
                        name,
                        len(found),
                        entry,
                    )
                    for _, m in found:
                        assert (
                            abs(m["width"] - master["width"]) < 2.1
                            and abs(m["height"] - master["height"]) < 2.1
                        ), (key, loc, name, m, master)
                    # Clearance must survive interpolation between named weights.
                    for i, (_, a) in enumerate(found):
                        for _, b in found[i + 1 :]:
                            if abs(sum(a["bounds"][1::2]) - sum(b["bounds"][1::2])) < 6:
                                gap = max(a["bounds"][0], b["bounds"][0]) - min(
                                    a["bounds"][2], b["bounds"][2]
                                )
                                assert gap >= 9, (key, loc, name, "dot clearance", gap)
                samples.append(loc)
        checks[key] = {
            "sanitizer": "passed",
            "normal_dot_usages": len(changed),
            "sampled_locations": len(samples),
            "body_and_metrics": "preserved",
            "bullet": "unchanged",
            "layout_tables": "byte-identical",
        }
        print(key, checks[key], flush=True)
    (OUT / "validation.json").write_text(json.dumps(checks, indent=2) + "\n")


if __name__ == "__main__":
    main()
