"""Validate the curated exports and their portable binary-source rebuilds."""

from io import BytesIO
from pathlib import Path
import argparse
import json
import subprocess
import tempfile
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import uharfbuzz as hb
import ots

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ["->", "->>", "=>", "<-", "<<-", "==", "===", "!=", "!==", "<=", ">=", "::"]


def run(font, text, features=None):
    out = BytesIO()
    font.save(out)
    h = hb.Font(hb.Face(out.getvalue()))
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(h, buffer, features or {})
    return [
        (font.getGlyphName(g.codepoint), p.x_advance)
        for g, p in zip(buffer.glyph_infos, buffer.glyph_positions)
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuilt", action="store_true")
    args = parser.parse_args()
    families = json.loads((ROOT / "family.json").read_text())["families"]
    report = {}
    for key, cfg in families.items():
        path = ROOT / cfg["font"]
        variable = TTFont(path)
        if args.rebuilt:
            rebuilt = TTFont(ROOT / ".build" / key / (cfg["stem"] + "-VF.ttf"))
            for tag in [
                "glyf",
                "gvar",
                "hmtx",
                "cmap",
                "GSUB",
                "GPOS",
                "GDEF",
                "fvar",
                "STAT",
            ]:
                if tag in variable:
                    assert variable.getTableData(tag) == rebuilt.getTableData(tag), (
                        key,
                        "rebuilt",
                        tag,
                    )
        for path in (ROOT / "fonts" / key).rglob("*"):
            if path.suffix not in [".ttf", ".woff2"]:
                continue
            with tempfile.TemporaryDirectory() as tmp:
                r = subprocess.run(
                    [ots.OTS_SANITIZE, str(path), str(Path(tmp) / "sanitized.ttf")],
                    capture_output=True,
                )
                assert r.returncode == 0, (path, r.stderr.decode())
            if path.parent.name == "TTF":
                static = TTFont(path)
                loc = {"wght": static["OS/2"].usWeightClass}
                if key == "system":
                    loc["opsz"] = {"Caption": 10, "Text": 14, "Display": 36}[
                        static["name"].getDebugName(17).split()[-1]
                    ]
                expected = instantiateVariableFont(
                    TTFont(ROOT / cfg["font"]), loc, inplace=False
                )
                for tag in ["glyf", "hmtx", "cmap", "GSUB", "GPOS", "GDEF"]:
                    if tag in static:
                        assert static.getTableData(tag) == expected.getTableData(tag), (
                            key,
                            path.name,
                            tag,
                        )
        tested = []
        for weight in (
            [300, 325, 350, 375, 400] if key == "code" else [300, 350, 400, 500, 600]
        ):
            for opsz in [10, 14, 36] if key == "system" else [14]:
                f = instantiateVariableFont(
                    TTFont(ROOT / cfg["font"]),
                    {"wght": weight, **({"opsz": opsz} if key == "system" else {})},
                    inplace=False,
                )
                assert all(ord(c) in f.getBestCmap() for c in "←↑→↓↔↕⇐⇑⇒⇓⇔⇕")
                if key == "code":
                    assert f["post"].isFixedPitch == 1
                    # Instancing recalculates the summary average including
                    # unencoded multi-cell ligatures. Test actual cell advances.
                    assert all(
                        f["hmtx"][name][0] == 600 for name in f.getBestCmap().values()
                    )
                    for token in TOKENS:
                        shaped = run(f, "a" + token + "n")
                        assert len(shaped) == 3 and sum(g[1] for g in shaped) == 600 * (
                            len(token) + 2
                        ), (weight, token, shaped)
                    carets = f["GDEF"].table.LigCaretList
                    assert carets.LigGlyphCount == 12
                if key == "system":
                    assert run(f, "1", {"tnum": True})[0][0] == "one.tnum"
                tested.append(
                    {"wght": weight, **({"opsz": opsz} if key == "system" else {})}
                )
        report[key] = {
            "version": cfg["version"],
            "sanitizer": "passed",
            "static_snapshot_parity": "exact",
            "binary_source_rebuild": "exact" if args.rebuilt else "not requested",
            "locations": tested,
        }
        print(key, "passed", flush=True)
    (ROOT / "qa/repository-validation.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
