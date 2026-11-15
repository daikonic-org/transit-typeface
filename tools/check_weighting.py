"""Check accepted-weighting interpolation before replacing production files."""

from pathlib import Path
import argparse
import json
import subprocess
import tempfile

from fontTools.ttLib import TTFont
import ots

from adopt_weighting import OUT, ROOT, instance
from audit import shape
from derive_weights import locked, topology
from validate import TOKENS, run


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
        path = fontdir / "VF" / (cfg["stem"] + "-VF.ttf")
        baseline = ROOT / cfg.get("weighting_baseline", cfg["font"])
        sanitized = []
        for exported in fontdir.rglob("*"):
            if exported.suffix not in (".ttf", ".woff2"):
                continue
            with tempfile.TemporaryDirectory() as tmp:
                r = subprocess.run(
                    [ots.OTS_SANITIZE, str(exported), str(Path(tmp) / "check.ttf")],
                    capture_output=True,
                )
                assert r.returncode == 0, (exported, r.stderr.decode())
            sanitized.append(exported.name)
        protected = locked(TTFont(path), recipe["defaults"]["locks"])
        samples = []
        for w in (
            [300, 312.5, 325, 350, 375, 387.5, 400]
            if key == "code"
            else [300, 325, 350, 375, 400, 450, 500, 550, 600]
        ):
            for optical in [10, 12, 14, 24, 36] if key == "system" else [None]:
                f = instance(path, w, optical)
                old = instance(baseline, w, optical)
                assert f.getBestCmap() == old.getBestCmap()
                assert all(
                    f["hmtx"][n][0] == old["hmtx"][n][0] for n in old.getGlyphOrder()
                ), (key, w, optical, "advance")
                for table in ("GSUB", "GPOS", "GDEF"):
                    if table in old:
                        assert f[table].compile(f) == old[table].compile(old), (
                            key,
                            w,
                            optical,
                            table,
                        )
                for name in ["H", "n", "o", "a", "e", "s", "f", "t"]:
                    assert topology(shape(f, name)) == topology(shape(old, name)), (
                        key,
                        w,
                        optical,
                        name,
                        "counter topology",
                    )
                for char in "←↑→↓↔↕⇐⇑⇒⇓⇔⇕":
                    name = f.getBestCmap()[ord(char)]
                    assert topology(shape(f, name)) == topology(shape(old, name)), (
                        key,
                        w,
                        optical,
                        char,
                    )
                if key == "code":
                    assert all(f["hmtx"][n][0] == 600 for n in f.getBestCmap().values())
                    for token in TOKENS:
                        got = run(f, "a" + token + "n")
                        assert len(got) == 3 and sum(p[1] for p in got) == 600 * (
                            len(token) + 2
                        ), (w, token, got)
                if key == "system":
                    assert run(f, "1", {"tnum": True})[0][0] == "one.tnum"
                samples.append({"wght": w, **({"opsz": optical} if optical else {})})
        parity = []
        for optical in recipe["families"][key]["optical_sizes"]:
            for weight in recipe["families"][key]["target_H_stems"]:
                w = int(weight)
                f = instance(path, w, optical)
                old = instance(baseline, w, optical)
                for name in protected:
                    assert f["glyf"][name].compile(f["glyf"]) == old["glyf"][
                        name
                    ].compile(old["glyf"]), (key, w, optical, name, "locked drawing")
                parity.append({"wght": w, "opsz": optical, "selected_glyphs": "exact"})
        report = {
            "sanitized": sanitized,
            "sampled_locations": samples,
            "metrics_and_layout": "passed",
            "counter_topology_controls": "passed",
            "selected_glyphs": parity,
        }
        reportpath = (
            ROOT / "qa" / key / "weighting-validation.json"
            if args.production
            else target / "validation.json"
        )
        reportpath.write_text(json.dumps(report, indent=2) + "\n")
        print(key, "validated", len(samples), "interpolation locations", flush=True)


if __name__ == "__main__":
    main()
