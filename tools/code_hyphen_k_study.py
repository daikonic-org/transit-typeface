"""Review a slightly wider hyphen and optical placement for k/K pairs."""

from copy import deepcopy
from io import BytesIO
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile

from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.misc.roundTools import otRound
import uharfbuzz as hb
import ots
from adopt_weighting import ROOT, instance
from audit import shape
from specimens import DATA, Panel
import code_balance_study as review

BASE = (
    ROOT
    / "trials/2026-11-16-code-underscore-weight/DaikonicTransitCodeUnderscoreStudy-VF.ttf"
)
OUT = ROOT / "trials/2026-11-16-code-hyphen-k"
RULES = ROOT / "trials/2026-11-16-code-delimiters/Positioning.fea"
SCALE = 344 / 304
SAMPLES = [
    "ke",
    "Ke",
    "KE",
    "ki",
    "ik",
    "Ki",
    "iK",
    "snake_case",
    "snake_key",
    "KeyValue",
    "KERNEL_KEY",
    "ke_ke",
    "keke",
    "AVATAR",
    "To",
    "value-key",
    "a-b",
    "--",
    "->",
    "->>",
    "<-",
    "<<-",
    ">=",
    "<=",
    "===",
    "!==",
]


def shaped(font, text):
    if not hasattr(font, "_review_hb_font"):
        stream = BytesIO()
        font.save(stream)
        font._review_hb_font = hb.Font(hb.Face(stream.getvalue()))
        font._review_hb_font.scale = (1000, 1000)
    h = font._review_hb_font
    b = hb.Buffer()
    b.add_str(text)
    b.guess_segment_properties()
    hb.shape(h, b, {"calt": True, "liga": True})
    return [
        (font.getGlyphOrder()[g.codepoint], g.cluster, p.x_advance, p.x_offset)
        for g, p in zip(b.glyph_infos, b.glyph_positions)
    ]


def main():
    OUT.mkdir(exist_ok=True)
    old = TTFont(BASE)
    f = deepcopy(old)
    g = f["glyf"]["hyphen"]
    for j, (x, y) in enumerate(g.coordinates):
        g.coordinates[j] = (otRound(300 + (x - 300) * SCALE), y)
    for v in f["gvar"].variations["hyphen"]:
        v.coordinates = [
            None if p is None else (otRound(p[0] * SCALE), p[1]) for p in v.coordinates
        ]
    g.recalcBounds(f["glyf"])
    f["hmtx"]["hyphen"] = (600, g.xMin)
    # Rebuild the existing trial rules, adding k/K to the same fitting class.
    rules = RULES.read_text().replace("[v y slash]", "[v y slash k K]")
    rules += """\nfeature calt {
      lookup KRound {
        pos k <18 0 0 0> e <-18 0 0 0>;
        pos K <18 0 0 0> e <-18 0 0 0>;
        pos K <18 0 0 0> E <-18 0 0 0>;
      } KRound;
    } calt;\n"""
    scratch = TTFont()
    scratch.setGlyphOrder(f.getGlyphOrder())
    addOpenTypeFeaturesFromString(scratch, rules)
    f["GPOS"] = scratch["GPOS"]
    (OUT / "Positioning.fea").write_text(rules)
    family = "Daikonic Transit Code Hyphen K Study"
    stem = family.replace(" ", "")
    for r in f["name"].names:
        text = (
            r.toUnicode()
            .replace("Daikonic Transit Code Underscore Study", family)
            .replace("DaikonicTransitCodeUnderscoreStudy", stem)
        )
        if r.nameID == 5:
            text = "Version 0.001; hyphen and k spacing study"
        if r.nameID == 3:
            text = stem + "-VF 0.001"
        r.string = text.encode(r.getEncoding())
    vf = OUT / (stem + "-VF.ttf")
    f.save(vf)
    paths = [vf]
    for weight, style in [(300, "Light"), (350, "Book"), (400, "Regular")]:
        snap = instance(vf, weight, None)
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
    for p in paths:
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [ots.OTS_SANITIZE, str(p), str(Path(tmp) / "checked.ttf")],
                capture_output=True,
            )
            assert r.returncode == 0, r.stderr.decode()
    reloaded = TTFont(vf)
    for tag in ["GSUB", "GDEF", "HVAR", "cmap", "fvar", "STAT"]:
        assert old.getTableData(tag) == reloaded.getTableData(tag), tag
    for name in old.getGlyphOrder():
        if name == "hyphen":
            continue
        assert old["glyf"][name].compile(old["glyf"]) == reloaded["glyf"][name].compile(
            reloaded["glyf"]
        ), name
        assert old["hmtx"][name] == reloaded["hmtx"][name], name
        assert [
            (v.axes, v.coordinates) for v in old["gvar"].variations.get(name, [])
        ] == [
            (v.axes, v.coordinates) for v in reloaded["gvar"].variations.get(name, [])
        ], name
    checks = []
    for weight in range(300, 401, 10):
        a, b = instance(BASE, weight, None), instance(vf, weight, None)
        before, after = shape(a, "hyphen").bounds, shape(b, "hyphen").bounds
        assert before[1::2] == after[1::2]
        assert abs((after[0] + after[2] - before[0] - before[2]) / 2) < 1
        assert abs((after[2] - after[0]) - (before[2] - before[0]) * SCALE) < 1.5
        assert all(
            advance == 600
            for name, (advance, lsb) in b["hmtx"].metrics.items()
            if name in b.getBestCmap().values() and name != ".notdef"
        )
        runs = []
        for text in SAMPLES:
            aa, bb = shaped(a, text), shaped(b, text)
            assert [(p[0], p[1], p[2]) for p in aa] == [
                (p[0], p[1], p[2]) for p in bb
            ], (weight, text)
            if text in ["ke", "Ke", "KE"]:
                assert [p[3] for p in bb] == [18, -18]
            if text in [
                "AVATAR",
                "To",
                "a-b",
                "--",
                "->",
                "->>",
                "<-",
                "<<-",
                ">=",
                "<=",
                "===",
                "!==",
            ]:
                assert aa == bb, (weight, text)
            runs.append({"text": text, "before": aa, "after": bb})
        checks.append(
            {
                "weight": weight,
                "hyphen_before": before,
                "hyphen_after": after,
                "runs": runs,
            }
        )
    report = {
        "base": str(BASE.relative_to(ROOT)),
        "base_sha256": hashlib.sha256(BASE.read_bytes()).hexdigest(),
        "hyphen_scale": SCALE,
        "sanitized_fonts": 4,
        "checks": checks,
        "unrelated_drawings_and_variations": "exact; uppercase drawings unchanged",
        "operator_ligatures": "GSUB exact; tested shaping unchanged",
    }
    (OUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    parts = []
    for row, weight in enumerate([300, 350, 400]):
        for col, path in enumerate([BASE, vf]):
            p = Panel(f"{row}-{col}", DATA["families"]["code"])
            review.bind(p, instance(path, weight, None))
            x = 25 + 600 * col
            y = 35 + row * 235
            p.text(
                f"{weight} / "
                + ("installed design" if col == 0 else "wider hyphen + k/K placement"),
                x,
                y,
                12,
                400,
                "#194454",
            )
            p.text("snake_case", x, y + 70, 65, 400, "#101712")
            p.text("ke Ke KE ki ik Ki iK", x, y + 112, 25, 400, "#101712")
            p.text("value-key  - --  a-b  -> ->>", x, y + 150, 19, 400, "#101712")
            p.elements.append(
                f'<rect x="{600*col}" y="{y+170}" width="600" height="48" fill="#101712"/>'
            )
            p.text("snake_case  KeyValue  KERNEL_KEY", x, y + 201, 15, 400, "#EEECD9")
            parts.append(p.body())
    (OUT / "Comparison.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="745"><rect width="1200" height="745" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    review.OUT = OUT
    review.browser_proof(
        {
            "Book / installed design": instance(BASE, 350, None),
            "Book / wider hyphen and k/K placement": instance(vf, 350, None),
        },
        samples=[
            (13, "snake_case snake_key KeyValue KERNEL_KEY ke_ke keke"),
            (14, "value-key a-b - -- -> ->> <- <<- snake_case"),
            (16, "snake_case  ke Ke KE ki ik Ki iK"),
        ],
        title="Code / hyphen and k spacing / Book 350",
    )
    print(
        "Built VF + 3 snapshots; sanitized four fonts; checked 11 weights, fixed cells, k pairs and operator retention."
    )


if __name__ == "__main__":
    main()
