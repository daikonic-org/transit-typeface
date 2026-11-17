"""Raise Code @ to x-height and open only its interior a."""

from copy import deepcopy
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.misc.roundTools import otRound
import pathops
import ots
from adopt_weighting import ROOT, instance
from audit import shape
from derive_weights import topology
from specimens import DATA, Panel
import code_balance_study as review

BASE = ROOT / "trials/2026-11-16-code-hyphen-k/DaikonicTransitCodeHyphenKStudy-VF.ttf"
OUT = ROOT / "trials/2026-11-16-code-at-height"
SHIFT = 24
OUTSET = 12
ARCH_LIFT = 10


def revise(font, lighten=True):
    g = font["glyf"]["at"]
    assert len(g.coordinates) == 791 and list(g.endPtsOfContours) == [716, 790]
    before = list(g.coordinates)
    counter = before[717:]
    left, right = min(x for x, y in counter), max(x for x, y in counter)
    bottom, top = min(y for x, y in counter), max(y for x, y in counter)
    cx, cy = (left + right) / 2, (bottom + top) / 2
    for j, (x, y) in enumerate(before):
        xx, yy = x, y
        if lighten and j >= 717:
            xx = cx + (x - cx) * (1 + 2 * OUTSET / (right - left))
            yy = cy + (y - cy) * (1 + 2 * OUTSET / (top - bottom))
        elif lighten and 188 <= j <= 249:
            # Smoothly ease the inside of the a arch, leaving its endpoints fixed.
            taper = (
                max(0, min(1, (y - 270) / 20))
                * max(0, min(1, (x - 200) / 20))
                * max(0, min(1, (334 - x) / 20))
            )
            yy += ARCH_LIFT * taper
        g.coordinates[j] = (otRound(xx), otRound(yy + SHIFT))
    g.recalcBounds(font["glyf"])
    return g


def build_at_variant(reviser, out, family, detail):
    out.mkdir(exist_ok=True)
    original = TTFont(BASE)
    f = deepcopy(original)
    masters = {w: instance(BASE, w, None) for w in [300, 350, 400]}
    for w, font in masters.items():
        reviser(font)
    f["glyf"]["at"] = deepcopy(masters[350]["glyf"]["at"])
    f["hmtx"]["at"] = masters[350]["hmtx"]["at"]
    default = f["glyf"]["at"].coordinates
    variations = []
    old_variations = original["gvar"].variations["at"]
    for w, axis in [(300, (-1.0, -1.0, 0.0)), (400, (0.0, 1.0, 1.0))]:
        old = next(v for v in old_variations if v.axes == {"wght": axis})
        deltas = [
            (x - bx, y - by)
            for (x, y), (bx, by) in zip(masters[w]["glyf"]["at"].coordinates, default)
        ]
        deltas += old.coordinates[-4:]
        variations.append(TupleVariation({"wght": axis}, deltas))
    assert len(old_variations) == 2
    f["gvar"].variations["at"] = variations
    stem = family.replace(" ", "")
    for r in f["name"].names:
        text = (
            r.toUnicode()
            .replace("Daikonic Transit Code Hyphen K Study", family)
            .replace("DaikonicTransitCodeHyphenKStudy", stem)
        )
        if r.nameID == 3:
            text = stem + "-VF 0.001"
        if r.nameID == 5:
            text = "Version 0.001; " + detail
        r.string = text.encode(r.getEncoding())
    f["head"].fontRevision = 0.001
    vf = out / (stem + "-VF.ttf")
    f.save(vf)
    paths = [vf]
    for w, style in [(300, "Light"), (350, "Book"), (400, "Regular")]:
        snap = instance(vf, w, None)
        names = {
            1: family if w == 400 else family + " " + style,
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
        path = out / (stem + "-" + style + ".ttf")
        snap.save(path)
        paths.append(path)
    for p in paths:
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [ots.OTS_SANITIZE, str(p), str(Path(tmp) / "checked.ttf")],
                capture_output=True,
            )
            assert r.returncode == 0, r.stderr.decode()
    reloaded = TTFont(vf)
    for tag in ["GSUB", "GPOS", "GDEF", "HVAR", "cmap", "fvar", "STAT"]:
        assert original.getTableData(tag) == reloaded.getTableData(tag), tag
    for name in original.getGlyphOrder():
        if name == "at":
            assert reloaded["hmtx"][name][0] == 600
            continue
        assert original["hmtx"][name] == reloaded["hmtx"][name], name
        assert original["glyf"][name].compile(original["glyf"]) == reloaded["glyf"][
            name
        ].compile(reloaded["glyf"]), name
        assert [
            (v.axes, v.coordinates) for v in original["gvar"].variations.get(name, [])
        ] == [
            (v.axes, v.coordinates) for v in reloaded["gvar"].variations.get(name, [])
        ], name
    return vf


def main():
    vf = build_at_variant(
        revise,
        OUT,
        "Daikonic Transit Code At Study",
        "raised and lighter interior at study",
    )
    checks = []
    for w in range(300, 401, 10):
        a, b = instance(BASE, w, None), instance(vf, w, None)
        pa, pb = shape(a, "at"), shape(b, "at")
        assert topology(pathops.simplify(pb, fix_winding=True, clockwise=True)) == (
            1,
            1,
        ), (w, topology(pb))
        assert pb.bounds == (
            pa.bounds[0],
            pa.bounds[1] + SHIFT,
            pa.bounds[2],
            pa.bounds[3] + SHIFT,
        )
        assert abs(pb.bounds[3] - shape(b, "x").bounds[3]) < 0.01
        assert b["hmtx"]["at"][0] == 600
        ga, gb = a["glyf"]["at"], b["glyf"]["at"]
        for j, ((x, y), (xx, yy)) in enumerate(zip(ga.coordinates, gb.coordinates)):
            if j < 188 or 249 < j < 717:
                assert (xx, yy) == (x, y + SHIFT), (w, j)
        ca = list(pa.contours)[1].bounds
        cb = list(pb.contours)[1].bounds
        assert abs((cb[2] - cb[0]) - (ca[2] - ca[0]) - 24) < 1
        assert abs((cb[3] - cb[1]) - (ca[3] - ca[1]) - 24) < 1
        checks.append(
            {
                "weight": w,
                "before": pa.bounds,
                "after": pb.bounds,
                "counter_before": ca,
                "counter_after": cb,
            }
        )
    report = {
        "base": str(BASE.relative_to(ROOT)),
        "base_sha256": hashlib.sha256(BASE.read_bytes()).hexdigest(),
        "shift_y": SHIFT,
        "counter_outset": OUTSET,
        "arch_easing_max": ARCH_LIFT,
        "other_drawings_layout_metrics": "exactly retained",
        "sanitized_fonts": 4,
        "checks": checks,
    }
    (OUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    parts = []
    for row, w in enumerate([300, 350, 400]):
        old = instance(BASE, w, None)
        raised = deepcopy(old)
        revise(raised, False)
        final = instance(vf, w, None)
        for col, (label, font) in enumerate(
            [
                ("current", old),
                ("raised only", raised),
                ("raised + lighter inner a", final),
            ]
        ):
            p = Panel(f"{row}-{col}", DATA["families"]["code"])
            review.bind(p, font)
            x = 20 + 400 * col
            y = 35 + row * 235
            p.text(f"{w} / {label}", x, y, 12, 400, "#194454")
            p.text("no@no", x, y + 82, 88, 400, "#101712")
            p.text("user@example.com", x, y + 128, 18, 400, "#101712")
            p.text("@name @decorator", x, y + 163, 14, 400, "#101712")
            p.elements.append(
                f'<rect x="{400*col}" y="{y+180}" width="400" height="40" fill="#101712"/>'
            )
            p.text("email@host.io  @name", x, y + 206, 14, 400, "#EEECD9")
            parts.append(p.body())
    (OUT / "Comparison.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="750"><rect width="1200" height="750" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    old = instance(BASE, 350, None)
    raised = deepcopy(old)
    revise(raised, False)
    review.OUT = OUT
    review.browser_proof(
        {
            "Book / current": old,
            "Book / raised only": raised,
            "Book / raised + lighter inner a": instance(vf, 350, None),
        },
        samples=[
            (13, "user@example.com @name @decorator no@no x@x"),
            (14, "email@host.io  @property  @staticmethod  @@@"),
            (16, "no@no  user@example.com  @name"),
        ],
        title="Code / at sign alignment and interior weight / Book 350",
    )
    print(
        "Built and sanitized four fonts; checked 11 weights; outer stroke translated exactly; unrelated glyphs/layout retained."
    )


if __name__ == "__main__":
    main()
