"""System tabular 1: unscaled Sans drawing centered in the existing tabular cell."""

from pathlib import Path
import json
from copy import deepcopy
import pathops
from fontTools.ttLib import TTFont
from font_feature_tools import from_paths, master_locations
from audit import shape_from_glyphs
from specimens import ROOT, DATA, Panel
from check_syntax_numerals import run

SOURCE = ROOT / "fonts/system/VF/DaikonicTransitSystem-VF.ttf"
SANS = ROOT / "fonts/sans/VF/DaikonicTransitSans-VF.ttf"
OUT = ROOT / "releases/2026.11.18.2/system"
PROOF = ROOT / "specimens/features/System-Tabular-One.svg"


def build():
    font = TTFont(SOURCE, recalcTimestamp=False)
    sans = TTFont(SANS)
    assert font["head"].unitsPerEm == sans["head"].unitsPerEm
    name = "one.tnum"
    _, locations = master_locations(font)
    paths = []
    hvar = font["HVAR"].table
    maps = {
        key: deepcopy(getattr(hvar, key).mapping[name])
        for key in ["AdvWidthMap", "LsbMap", "RsbMap"]
        if getattr(hvar, key, None) is not None
    }
    advance = font["hmtx"][name][0]
    for loc in locations:
        p = shape_from_glyphs(sans.getGlyphSet(location={"wght": loc["wght"]}), "one")
        width = font.getGlyphSet(location=loc)[name].width
        x0, _, x1, _ = p.bounds
        paths.append(p.transform(1, 0, 0, 1, (width - x0 - x1) / 2, 0))
    from_paths(font, name, locations, paths, advance)
    for key, index in maps.items():
        getattr(hvar, key).mapping[name] = index
    for record in font["name"].names:
        if record.nameID in [3, 5]:
            record.string = (
                record.toUnicode()
                .replace("0.117", "0.118")
                .encode(record.getEncoding())
            )
    font["head"].fontRevision = 0.118
    (OUT / "VF").mkdir(parents=True, exist_ok=True)
    target = OUT / "VF/DaikonicTransitSystem-VF.ttf"
    font.save(target)
    (OUT / "selection.json").write_text(
        json.dumps(
            {
                "family": "Daikonic Transit System",
                "version": "0.118",
                "status": "release",
                "weight_range": [300, 600],
            },
            indent=2,
        )
        + "\n"
    )
    return target


def check(path):
    f = TTFont(path)
    original = TTFont(SOURCE)
    sans = TTFont(SANS)
    for tag in ["GSUB", "GPOS", "GDEF", "cmap", "fvar"]:
        assert f.getTableData(tag) == original.getTableData(tag), tag
    for n in original.getGlyphOrder():
        if n == "one.tnum":
            continue
        assert f["glyf"][n].compile(f["glyf"]) == original["glyf"][n].compile(
            original["glyf"]
        ), n
        assert f["gvar"].variations.get(n) == original["gvar"].variations.get(n), n
        assert f["hmtx"][n] == original["hmtx"][n], n
    samples = []
    for weight in range(300, 601, 25):
        for opsz in [10, 12, 14, 18, 24, 30, 36]:
            loc = {"wght": weight, "opsz": opsz}
            gs = f.getGlyphSet(location=loc)
            old = original.getGlyphSet(location=loc)
            width = old["one.tnum"].width
            assert abs(gs["one.tnum"].width - width) < 0.01, (loc, "advance")
            p = shape_from_glyphs(gs, "one.tnum")
            x0, y0, x1, y1 = p.bounds
            assert abs((x0 + x1) / 2 - width / 2) < 1, (loc, p.bounds, width)
            expected = shape_from_glyphs(
                sans.getGlyphSet(location={"wght": weight}), "one"
            )
            a, b, c, d = expected.bounds
            assert (
                abs((x1 - x0) - (c - a)) < 1.1
                and abs(y0 - b) < 1.1
                and abs(y1 - d) < 1.1
            ), (loc, p.bounds, expected.bounds)
            centered = expected.transform(1, 0, 0, 1, (width - a - c) / 2, 0)
            error = abs(pathops.op(p, centered, pathops.PathOp.XOR).area)
            assert error / max(centered.area, 1) < 0.015, (loc, "shape fidelity", error)
            shaped = run(path, "0123456789", loc, {"tnum": True})
            assert all(abs(adv - width) <= 0.51 for _, adv, *_ in shaped), (loc, shaped)
            assert run(path, "1", loc, {"tnum": False}) == run(
                SOURCE, "1", loc, {"tnum": False}
            )
            samples.append(
                {"location": loc, "cell": width, "one_bounds": list(p.bounds)}
            )
    (OUT / "tabular-one-checks.json").write_text(
        json.dumps(
            {
                "samples": samples,
                "drawing": "Sans one, unscaled; centered ink bounds",
                "other_glyphs": "unchanged",
            },
            indent=2,
        )
        + "\n"
    )
    print(
        "System tabular one:91 locations, Sans shape fidelity, original tabular advances and all other glyphs verified"
    )


def proof(path):
    p = Panel(
        "system-one",
        {**DATA["families"]["system"], "font": str(path.relative_to(ROOT))},
    )
    elements = [
        '<rect width="1100" height="700" fill="#eeeddb"/>',
        "<style>text{font-family:Arial,sans-serif;fill:#172331}</style>",
        '<text x="35" y="40" font-size="25">System · Sans-style tabular 1</text>',
        '<text x="35" y="74" font-size="15">Original proportions · centered within the existing tabular width</text>',
    ]
    for row, w in enumerate([300, 350, 400, 600]):
        y = 140 + row * 125
        elements.append(f'<text x="35" y="{y}" font-size="14">Weight {w}</text>')
        p.text("0123456789  11:11", 200, y, 36, w, "#172331", tabular=True)
        p.text("111 248 000", 200, y + 45, 24, w, "#172331", tabular=True)
        p.text("Default 1", 760, y, 22, w, "#172331")
        p.text("Tabular 1", 760, y + 45, 22, w, "#172331", tabular=True)
    PROOF.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="700"><defs>'
        + "".join(p.defs.values())
        + "</defs>"
        + "".join(elements)
        + "".join(p.elements)
        + "</svg>"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = OUT / "VF/DaikonicTransitSystem-VF.ttf" if args.check else build()
    check(path)
    if not args.check:
        proof(path)
