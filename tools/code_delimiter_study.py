"""Review stronger Code delimiters, inward placement and a distinct brace waist."""

from copy import deepcopy
from pathlib import Path
import json
import subprocess
import tempfile
import pathops

from fontTools.ttLib import TTFont
from fontTools.designspaceLib import (
    DesignSpaceDocument,
    AxisDescriptor,
    SourceDescriptor,
)
from fontTools.varLib import build
import ots

from adopt_weighting import ROOT, instance
from audit import shape, spans
from compatibility import compatible_masters
from derive_weights import grow, install, coverage_difference, topology
import code_balance_study as review
from specimens import DATA, Panel

OUT = ROOT / ".build/code-delimiters"
BASE = (
    ROOT
    / "trials/2026-11-16-code-i-right-base-shaft/DaikonicTransitCodeRightBaseShaftStudy-VF.ttf"
)
PAIRS = (
    ("parenleft", "parenright"),
    ("bracketleft", "bracketright"),
    ("braceleft", "braceright"),
)
CHANGED = {name for pair in PAIRS for name in pair} | {"bar", "underscore"}
INWARD = 14
ARM = 28


def extended_brace(p, addition):
    # Retain the source curves; lengthen just the middle into a flat-ended nose.
    p = grow(p, addition, 0.72, 3)
    lo, hi = p.bounds[1], p.bounds[3]
    center = (lo + hi) / 2
    stem = spans(p, lo + (hi - lo) * 0.25, 1)[0]
    thickness = (stem[1] - stem[0]) * 0.72
    left = p.bounds[0] - 72
    nose = review.rect(
        left, center - thickness / 2, sum(stem) / 2, center + thickness / 2
    )
    return (
        pathops.op(p, nose, pathops.PathOp.UNION, fix_winding=True, clockwise=True),
        thickness,
    )


def move_underscore(font, position="bottom", full_width=True):
    glyph = font["glyf"]["underscore"]
    coords = glyph.coordinates
    low = min(y for x, y in coords)
    high = max(y for x, y in coords)
    dy = -low if position == "bottom" else -(low + high) / 2
    left, right = min(x for x, y in coords), max(x for x, y in coords)
    for j, (x, y) in enumerate(coords):
        coords[j] = ((x - left) * 600 / (right - left) if full_width else x, y + dy)
    glyph.recalcBounds(font["glyf"])
    font["hmtx"]["underscore"] = (600, glyph.xMin)
    return {
        "shift": dy,
        "stroke_height": high - low,
        "alignment": position + " at baseline",
        "full_cell_width": full_width,
    }


def construct(font, weight, distinct=True, raise_low_line=True):
    growth = 12 + (weight - 300) * 0.04
    records = {}
    for opening, closing in PAIRS:
        p = shape(font, opening)
        addition = growth
        full_width = None
        if distinct and opening == "braceleft":
            p, full_width = extended_brace(p, addition)
        elif distinct and opening == "bracketleft":
            glyph = font["glyf"][opening]
            right = max(x for x, y in glyph.coordinates)
            for j, (x, y) in enumerate(glyph.coordinates):
                if x == right:
                    glyph.coordinates[j] = (x + ARM, y)
            glyph.recalcBounds(font["glyf"])
            p = shape(font, opening)
        if full_width is None:
            p = grow(p, addition, 0.72, 3)
        p = p.transform(1, 0, 0, 1, INWARD, 0)
        install(font, opening, p)
        install(font, closing, p.transform(-1, 0, 0, 1, 600, 0))
        records[opening] = {
            "stroke_addition": addition,
            "inward_translation": INWARD,
            "bounds": p.bounds,
            "waist_extension": 72 if distinct and opening == "braceleft" else 0,
            "horizontal_nose_thickness": full_width,
        }
    bar = shape(font, "bar")
    addition = growth - 4
    install(font, "bar", grow(bar, addition, 0.72, 3))
    records["bar"] = {"stroke_addition": addition}
    if raise_low_line:
        records["underscore"] = move_underscore(font)
    return records


def export_trial():
    fonts = []
    recipes = []
    masters = OUT / "masters"
    masters.mkdir(exist_ok=True)
    for weight in (300, 350, 400):
        f = instance(BASE, weight, None)
        recipes.append(construct(f, weight))
        fonts.append(f)
    fidelity = {}
    for name in sorted(CHANGED):
        paths = [shape(f, name) for f in fonts]
        glyphs, missing = compatible_masters(paths)
        assert not missing
        errors = []
        for f, g, expected in zip(fonts, glyphs, paths):
            f["glyf"][name] = g
            g.recalcBounds(f["glyf"])
            f["hmtx"][name] = (600, g.xMin)
            errors.append(coverage_difference(shape(f, name), expected))
        assert max(errors) < 0.015, (name, errors)
        fidelity[name] = errors
    ds = DesignSpaceDocument()
    axis = AxisDescriptor()
    axis.name = "Weight"
    axis.tag = "wght"
    axis.minimum = 300
    axis.default = 350
    axis.maximum = 400
    ds.addAxis(axis)
    for weight, font in zip((300, 350, 400), fonts):
        path = masters / f"Master-{weight}.ttf"
        font.save(path)
        s = SourceDescriptor()
        s.path = str(path)
        s.name = str(weight)
        s.location = {"Weight": weight}
        ds.addSource(s)
    path = masters / "CodeDelimiters.designspace"
    ds.write(path)
    candidate, _, _ = build(path, optimize=False)
    result = TTFont(BASE)
    for name in CHANGED:
        result["glyf"][name] = deepcopy(candidate["glyf"][name])
        result["gvar"].variations[name] = deepcopy(candidate["gvar"].variations[name])
        result["hmtx"][name] = candidate["hmtx"][name]
    family = "Daikonic Transit Code Delimiter Study"
    stem = "DaikonicTransitCodeDelimiterStudy"
    oldfamily = result["name"].getDebugName(16)
    oldstem = oldfamily.replace(" ", "")
    for n in result["name"].names:
        n.string = (
            n.toUnicode()
            .replace(oldfamily, family)
            .replace(oldstem, stem)
            .encode(n.getEncoding())
        )
    result["head"].fontRevision = 0.001
    for n in result["name"].names:
        if n.nameID == 5:
            n.string = "Version 0.001; delimiter study".encode(n.getEncoding())
    paths = [OUT / (stem + "-VF.ttf")]
    result.save(paths[0])
    for weight, style in ((300, "Light"), (350, "Book"), (400, "Regular")):
        f = instance(paths[0], weight, None)
        names = {
            1: family if weight == 400 else family + " " + style,
            2: "Regular",
            3: "0.001;" + stem + "-" + style,
            4: family + " " + style,
            6: stem + "-" + style,
            16: family,
            17: style,
        }
        for n in f["name"].names:
            if n.nameID in names:
                n.string = names[n.nameID].encode(n.getEncoding())
        path = OUT / (stem + "-" + style + ".ttf")
        f.save(path)
        paths.append(path)
    for path in paths:
        with tempfile.TemporaryDirectory() as temporary:
            r = subprocess.run(
                [ots.OTS_SANITIZE, str(path), str(Path(temporary) / "checked.ttf")],
                capture_output=True,
            )
            assert r.returncode == 0, r.stderr.decode()
    baseline = TTFont(BASE)
    for name in result.getGlyphOrder():
        if name not in CHANGED:
            assert baseline["glyf"][name].compile(baseline["glyf"]) == result["glyf"][
                name
            ].compile(result["glyf"]), name
            assert [
                (v.axes, v.coordinates)
                for v in baseline["gvar"].variations.get(name, [])
            ] == [
                (v.axes, v.coordinates) for v in result["gvar"].variations.get(name, [])
            ], name
    for tag in ("GSUB", "GDEF", "HVAR", "MVAR", "cmap"):
        if tag in baseline:
            assert baseline.getTableData(tag) == result.getTableData(tag), tag
    weights = []
    samples = []
    for weight in range(300, 401, 10):
        f = instance(paths[0], weight, None)
        expected = instance(BASE, weight, None)
        construct(expected, weight)
        differences = {
            name: coverage_difference(shape(f, name), shape(expected, name))
            for name in CHANGED
        }
        assert max(differences.values()) < 0.025, (weight, differences)
        for name in CHANGED:
            p = shape(f, name)
            assert topology(p) == (1, 0), (weight, name, "topology")
            assert f["hmtx"][name][0] == 600
            if name == "underscore":
                assert (
                    0 <= p.bounds[0] < p.bounds[2] <= 600 and abs(p.bounds[1]) <= 1
                ), (weight, name, p.bounds)
                continue
            assert 25 < p.bounds[0] < p.bounds[2] < 575, (weight, name, p.bounds)
            assert abs(p.bounds[1] + 139) <= 1 and abs(p.bounds[3] - 740) <= 1, (
                weight,
                name,
                p.bounds,
            )
        weights.append(weight)
        gaps = {
            a: 600 + shape(f, b).bounds[0] - shape(f, a).bounds[2] for a, b in PAIRS
        }
        assert min(gaps.values()) > 250, (weight, gaps)
        samples.append(
            {
                "weight": weight,
                "outline_fidelity": differences,
                "empty_pair_ink_gaps": gaps,
            }
        )
    report = {
        "recipes": recipes,
        "named_master_fidelity": fidelity,
        "sanitized_fonts": 4,
        "weights_checked": weights,
        "changed_glyphs": sorted(CHANGED),
        "other_drawings_variations": "exact",
        "layout_and_advances": "retained",
        "samples": samples,
    }
    (OUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    return paths[0]


def draw_proof(fonts, filename="Comparison.svg"):
    cfg = DATA["families"]["code"]
    parts = []
    p = Panel("labels", cfg)
    p.text("CODE / DELIMITERS: WEIGHT, SPACING AND SHAPE", 25, 35, 21, 400, "#194454")
    p.text(
        "600-unit cells; opening +14 / closing -14 toward enclosed text. Reference JetBrains at Regular400.",
        25,
        65,
        12,
        400,
        "#194454",
    )
    parts.append(p.body())
    for row, (label, font) in enumerate(fonts.items()):
        y = 100 + row * 220
        p = Panel(label, cfg)
        review.bind(p, font)
        p.text(label, 25, y + 12, 14, 400, "#194454")
        p.text("( ) [ ] { } |", 25, y + 110, 72, 400, "#101712")
        p.text("(item) [item] {item}", 25, y + 155, 24, 400, "#101712")
        for text, dy in [
            ("const { items } = select([input]);", 75),
            ("fn({ key: [call(arg)] })", 115),
            ("{} () [] (() => { return []; })", 155),
        ]:
            p.text(text, 650, y + dy, 18, 400, "#101712")
        p.text(
            "if (isCurrent) { collect(items[index]); }   foo({a:[(1)]});",
            25,
            y + 192,
            13,
            400,
            "#101712",
        )
        parts.append(p.body())
    height = 110 + 220 * len(fonts)
    (OUT / filename).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}"><rect width="1200" height="{height}" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


def weights_proof(vf):
    cfg = DATA["families"]["code"]
    parts = []
    p = Panel("labels", cfg)
    p.text("CODE / STRUCTURAL DELIMITERS ACROSS WEIGHTS", 25, 35, 21, 400, "#194454")
    p.text("EXISTING DELIMITERS / SELECTED i", 25, 70, 12, 400, "#194454")
    p.text("STRONGER + INWARD + CLEAR BRACE WAIST", 625, 70, 12, 400, "#194454")
    parts.append(p.body())
    for row, weight in enumerate((300, 350, 400)):
        y = 100 + row * 220
        for col, path in enumerate((BASE, vf)):
            p = Panel(f"{weight}-{col}", cfg)
            review.bind(p, instance(path, weight, None))
            x = 25 + 600 * col
            p.text(str(weight), x, y + 12, 12, 400, "#194454")
            p.text("() [] {} | ({[]})", x, y + 70, 45, 400, "#101712")
            p.text("fn({ snake_case: [call(arg)] });", x, y + 105, 14, 400, "#101712")
            p.elements.append(
                f'<rect x="{600*col}" y="{y+120}" width="600" height="78" fill="#101712"/>'
            )
            p.text(
                "const {snake_case} = get_items([input]);",
                x,
                y + 147,
                14,
                400,
                "#EEECD9",
            )
            p.text("() [] {}  fn({x:[call(y)]})  ||", x, y + 177, 13, 400, "#EEECD9")
            parts.append(p.body())
    (OUT / "Weights.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760"><rect width="1200" height="760" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


def underscore_proof(selected):
    old = instance(BASE, 350, None)
    current = deepcopy(selected)
    current["glyf"]["underscore"] = deepcopy(old["glyf"]["underscore"])
    current["hmtx"]["underscore"] = old["hmtx"]["underscore"]
    centered = deepcopy(current)
    move_underscore(centered, full_width=False)
    variants = {
        "Current / below baseline": current,
        "Raised / original width": centered,
        "Raised / full cell width / proposed": selected,
    }
    cfg = DATA["families"]["code"]
    parts = []
    label = Panel("underscore-title", cfg)
    label.text("CODE / UNDERSCORE AND THE READING BASELINE", 25, 35, 22, 400, "#194454")
    label.text(
        "Same stroke thickness and 600-unit cells. Compare height and gapless width; Book 350.",
        25,
        65,
        12,
        400,
        "#194454",
    )
    parts.append(label.body())
    metrics = {}
    for row, (name, font) in enumerate(variants.items()):
        y = 100 + row * 210
        p = Panel(name, cfg)
        review.bind(p, font)
        metrics[name] = shape(font, "underscore").bounds
        p.text(name, 25, y + 12, 14, 400, "#194454")
        p.elements.append(
            f'<path d="M25 {y+105}H535" stroke="#8FA3A6" stroke-width=".55"/>'
        )
        p.text("snake_case", 25, y + 105, 72, 400, "#101712")
        p.text("baseline", 545, y + 108, 9, 400, "#194454")
        p.text("glyph_metrics __init__ _private_value", 650, y + 63, 20, 400, "#101712")
        p.text("py_project  get_user_id  trailing_", 650, y + 100, 20, 400, "#101712")
        p.elements.append(
            f'<rect y="{y+133}" width="1200" height="62" fill="#101712"/>'
        )
        p.text(
            "long_snake_case  get_user_id()  __init__  _cache  py_project",
            25,
            y + 171,
            14,
            400,
            "#EEECD9",
        )
        parts.append(p.body())
    (OUT / "Underscore.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="740" viewBox="0 0 1200 740"><rect width="1200" height="740" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    (OUT / "underscore-positions.json").write_text(json.dumps(metrics, indent=2) + "\n")
    review.OUT = OUT / "underscore-browser"
    review.OUT.mkdir(exist_ok=True)
    review.browser_proof(
        variants,
        samples=[
            (13, "long_snake_case  get_user_id()  __init__  _cache  py_project"),
            (14, "snake_case  glyph_metrics  _private_value  snake__case"),
            (16, "__init__   foo({ snake_case: [some_value] })"),
        ],
        title="Underscore height — actual text at13,14,16px",
    )


def fitting_study(vf):
    """Optical placement only: keep advances, glyph identity and outlines intact."""
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from io import BytesIO
    import uharfbuzz as hb

    base = TTFont(vf)
    scratch = TTFont()
    scratch.setGlyphOrder(base.getGlyphOrder())
    rules = """languagesystem DFLT dflt;
    languagesystem latn dflt;
    @Diagonal = [v y slash];
    @Foot = [i l];
    feature calt {
        lookup DiagonalFoot {
            pos @Diagonal <18 0 0 0> @Foot <-18 0 0 0>;
        } DiagonalFoot;
        lookup FootDiagonal {
            pos @Foot <18 0 0 0> @Diagonal <-18 0 0 0>;
        } FootDiagonal;
    } calt;
    """
    addOpenTypeFeaturesFromString(scratch, rules)
    base["GPOS"] = scratch["GPOS"]
    # Keep the positioning trial separate from the delimiter candidate.
    path = OUT / "DaikonicTransitCodePositionStudy-VF.ttf"
    for n in base["name"].names:
        n.string = (
            n.toUnicode()
            .replace("Delimiter Study", "Position Study")
            .replace("DelimiterStudy", "PositionStudy")
            .encode(n.getEncoding())
        )
    base.save(path)
    (OUT / "Positioning.fea").write_text(rules)
    report = []
    for weight in range(300, 401, 10):
        f = instance(path, weight, None)
        stream = BytesIO()
        f.save(stream)
        font = hb.Font(hb.Face(stream.getvalue()))
        font.scale = (1000, 1000)
        for text in [
            "vi",
            "yi",
            "iv",
            "iy",
            "/i",
            "i/",
            "vl",
            "ly",
            "ivivi",
            "civil",
            "lively",
            "visibility",
            "a/b",
            "__init__",
        ]:
            runs = []
            for enabled in (False, True):
                buf = hb.Buffer()
                buf.add_str(text)
                buf.guess_segment_properties()
                hb.shape(font, buf, {"calt": enabled})
                assert all(p.x_advance == 600 for p in buf.glyph_positions), (
                    weight,
                    text,
                )
                runs.append(
                    {
                        "glyphs": [g.codepoint for g in buf.glyph_infos],
                        "positions": [
                            (p.x_advance, p.x_offset) for p in buf.glyph_positions
                        ],
                    }
                )
            assert runs[0]["glyphs"] == runs[1]["glyphs"]
            if text == "vi":
                assert runs[1]["positions"] == [(600, 18), (600, -18)]
            report.append(
                {"weight": weight, "text": text, "off": runs[0], "on": runs[1]}
            )
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(
            [ots.OTS_SANITIZE, str(path), str(Path(tmp) / "checked.ttf")],
            capture_output=True,
        )
        assert r.returncode == 0, r.stderr.decode()
    original = TTFont(vf)
    for tag in ["glyf", "gvar", "hmtx", "GSUB", "GDEF", "HVAR"]:
        assert original.getTableData(tag) == base.getTableData(tag), tag
    (OUT / "positioning-validation.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    fonts = {
        "Fixed-cell spacing": instance(vf, 350, None),
        "Contextual placement / 18 units per letter": instance(path, 350, None),
    }
    draw_proof_fitting(fonts)
    review.OUT = OUT / "positioning-browser"
    review.OUT.mkdir(exist_ok=True)
    review.browser_proof(
        fonts,
        samples=[
            (13, "civil lively visibility ivy /items i/value  ivivi viyi"),
            (14, "living delivery civil  /i i/  vi iv yi iy vl ly"),
            (16, "visibility  civil  lively  ivy  ivivi"),
        ],
        title="Fixed advances / contextual optical placement",
    )
    return path


def draw_proof_fitting(fonts):
    parts = []
    for row, (label, font) in enumerate(fonts.items()):
        p = Panel(label, DATA["families"]["code"])
        review.bind(p, font)
        y = 50 + row * 260
        p.text(label, 25, y, 16, 400, "#194454")
        p.text("vi iv yi iy /i i/ vl ly", 25, y + 90, 50, 400, "#101712")
        p.text("civil  lively  visibility  ivy", 25, y + 145, 30, 400, "#101712")
        p.text(
            "living delivery  /items i/value  ivivi", 25, y + 195, 16, 400, "#101712"
        )
        parts.append(p.body())
    (OUT / "Positioning.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="570"><rect width="1200" height="570" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


def main():
    OUT.mkdir(exist_ok=True)
    current = instance(BASE, 350, None)
    weighted = deepcopy(current)
    construct(weighted, 350, distinct=False, raise_low_line=False)
    vf = export_trial()
    fitting_study(vf)
    selected = instance(vf, 350, None)
    fonts = {
        "Existing delimiters / selected i": current,
        "Heavier + inward only": weighted,
        "Full trial / extended brace nose + gapless underscore": selected,
        "JetBrains Mono Regular400": review.load(
            review.REFERENCES["JetBrains Mono 400"]
        ),
    }
    draw_proof(fonts)
    draw_proof(
        {
            "Existing delimiters / selected i": current,
            "Full trial / extended brace nose": selected,
        },
        "BeforeAfter.svg",
    )
    weights_proof(vf)
    underscore_proof(selected)
    review.OUT = OUT
    review.browser_proof(
        fonts,
        samples=[
            (
                13,
                "const {snake_case} = get_items([input]); if (ready) { collect(items[index]); }",
            ),
            (14, "() [] {} ||   ({[]})   fn({ long_snake_case: [call(arg)] })"),
            (16, "__init__ _private_value  foo({key: some_value})"),
        ],
        title="Code delimiters — actual browser text at13,14,16px",
    )
    print(
        "Built and sanitized delimiter VF +3snapshots; verified11weights; generated comparison/weight/browser proofs"
    )


if __name__ == "__main__":
    main()
