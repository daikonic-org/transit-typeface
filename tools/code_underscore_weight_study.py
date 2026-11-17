"""Thicken only the baseline-resting, full-cell Code underscore."""

from copy import deepcopy
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile

from fontTools.ttLib import TTFont
from fontTools.misc.roundTools import otRound
import ots
from adopt_weighting import ROOT, instance
from audit import shape
from specimens import DATA, Panel
import code_balance_study as review

BASE = (
    ROOT / "trials/2026-11-16-code-delimiters/DaikonicTransitCodePositionStudy-VF.ttf"
)
OUT = ROOT / "trials/2026-11-16-code-underscore-weight"
FACTOR = 1.20


def main():
    OUT.mkdir(exist_ok=True)
    old = TTFont(BASE)
    f = deepcopy(old)
    glyph = f["glyf"]["underscore"]
    for j, (x, y) in enumerate(glyph.coordinates):
        glyph.coordinates[j] = (x, otRound(y * FACTOR))
    for variation in f["gvar"].variations["underscore"]:
        variation.coordinates = [
            None if p is None else (p[0], otRound(p[1] * FACTOR))
            for p in variation.coordinates
        ]
    glyph.recalcBounds(f["glyf"])
    for record in f["name"].names:
        record.string = (
            record.toUnicode()
            .replace("Position Study", "Underscore Study")
            .replace("PositionStudy", "UnderscoreStudy")
            .encode(record.getEncoding())
        )
    stem = "DaikonicTransitCodeUnderscoreStudy"
    vf = OUT / (stem + "-VF.ttf")
    f.save(vf)
    paths = [vf]
    for weight, style in [(300, "Light"), (350, "Book"), (400, "Regular")]:
        snap = instance(vf, weight, None)
        family = "Daikonic Transit Code Underscore Study"
        names = {
            1: family if weight == 400 else family + " " + style,
            2: "Regular",
            3: "0.001;" + stem + "-" + style,
            4: family + " " + style,
            6: stem + "-" + style,
            16: family,
            17: style,
        }
        for r in snap["name"].names:
            if r.nameID in names:
                r.string = names[r.nameID].encode(r.getEncoding())
        path = OUT / (stem + "-" + style + ".ttf")
        snap.save(path)
        paths.append(path)
    for path in paths:
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [ots.OTS_SANITIZE, str(path), str(Path(tmp) / "checked.ttf")],
                capture_output=True,
            )
            assert r.returncode == 0, r.stderr.decode()
    reloaded = TTFont(vf)
    for tag in ["hmtx", "GSUB", "GPOS", "GDEF", "HVAR", "cmap", "fvar", "STAT"]:
        assert old.getTableData(tag) == reloaded.getTableData(tag), tag
    for name in old.getGlyphOrder():
        if name == "underscore":
            continue
        assert old["glyf"][name].compile(old["glyf"]) == reloaded["glyf"][name].compile(
            reloaded["glyf"]
        ), name
        assert [
            (v.axes, v.coordinates) for v in old["gvar"].variations.get(name, [])
        ] == [
            (v.axes, v.coordinates) for v in reloaded["gvar"].variations.get(name, [])
        ], name
    checks = []
    for weight in range(300, 401, 10):
        a, b = instance(BASE, weight, None), instance(vf, weight, None)
        before, after = shape(a, "underscore").bounds, shape(b, "underscore").bounds
        assert after[0] == 0 and after[2] == 600 and after[1] == 0, (weight, after)
        assert abs(after[3] - before[3] * FACTOR) < 1, (weight, before, after)
        assert b["hmtx"]["underscore"] == (600, 0)
        checks.append({"weight": weight, "before": before, "after": after})
    report = {
        "factor": FACTOR,
        "base": str(BASE.relative_to(ROOT)),
        "base_sha256": hashlib.sha256(BASE.read_bytes()).hexdigest(),
        "sanitized_fonts": 4,
        "other_glyphs_variations_layout_metrics": "exactly retained",
        "checks": checks,
    }
    (OUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    parts = []
    for row, weight in enumerate([300, 350, 400]):
        for col, path in enumerate([BASE, vf]):
            p = Panel(f"{row}-{col}", DATA["families"]["code"])
            review.bind(p, instance(path, weight, None))
            x = 25 + 600 * col
            y = 45 + row * 220
            p.text(
                f"{weight} / " + ("current" if col == 0 else "+20% underscore"),
                x,
                y,
                15,
                400,
                "#194454",
            )
            p.text("snake_case __", x, y + 70, 47, 400, "#101712")
            p.text("get_user_id()  __init__  _cache", x, y + 110, 14, 400, "#101712")
            p.elements.append(
                f'<rect x="{600*col}" y="{y+130}" width="600" height="65" fill="#101712"/>'
            )
            p.text("py_project  long_snake_case  ____", x, y + 170, 14, 400, "#EEECD9")
            parts.append(p.body())
    (OUT / "Comparison.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720"><rect width="1200" height="720" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    review.OUT = OUT
    review.browser_proof(
        {
            "Book / current underscore": instance(BASE, 350, None),
            "Book / underscore +20%": instance(vf, 350, None),
        },
        samples=[
            (13, "get_user_id() __init__ snake_case _cache py_project ____"),
            (14, "long_snake_case  glyph_metrics  _private_value  snake__case"),
            (16, "__init__  foo({snake_case: [some_value]})  ____"),
        ],
        title="Code underscore weight / Book 350",
    )
    print(
        "Built and sanitized 4 fonts; checked 11 weights; unrelated glyphs/layout exact."
    )


if __name__ == "__main__":
    main()
