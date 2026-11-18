"""One-step heavier structural delimiters using exact compatible source outlines."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import ots
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.instancer import instantiateVariableFont
from audit import shape_from_glyphs, spans
from font_feature_tools import append_glyph, compose, expanded_variations, from_paths
from derive_weights import grow
from specimens import ROOT, DATA, Panel
from code_balance_study import bind

OUT = ROOT / "trials/2026-11-17-delimiter-weight-step"
SOURCE = ROOT / "previews/code-1.029/source/DaikonicTransitCodeSyntaxStudy-VF.ttf"
DELIMITERS = [
    "parenleft",
    "parenright",
    "bracketleft",
    "bracketright",
    "braceleft",
    "braceright",
    "bar.delimiterOpen",
    "bar.delimiterClose",
    "less.generic",
    "greater.generic",
    "code.lifetimeOpen",
]


def main():
    OUT.mkdir(exist_ok=True)
    original = TTFont(SOURCE)
    font = deepcopy(original)
    sample = {
        w: instantiateVariableFont(deepcopy(original), {"wght": w}, inplace=True)
        for w in (300, 350, 400)
    }
    for name in DELIMITERS:
        book, regular = sample[350]["glyf"][name], sample[400]["glyf"][name]
        assert (
            book.endPtsOfContours == regular.endPtsOfContours
            and book.flags == regular.flags
        ), name
        low = book.coordinates
        mid = regular.coordinates
        high = GlyphCoordinates(
            [(2 * x - a, 2 * y - b) for (x, y), (a, b) in zip(mid, low)]
        )
        glyph = deepcopy(regular)
        default = GlyphCoordinates(list(mid) + [(0, 0)] * 4)
        targets = [
            GlyphCoordinates(list(points) + [(0, 0)] * 4) for points in (low, high)
        ]
        variations = [
            TupleVariation(
                {"wght": support},
                [(a - x, b - y) for (a, b), (x, y) in zip(points, default)],
            )
            for support, points in zip([(-1, -1, 0), (0, 1, 1)], targets)
        ]
        append_glyph(font, name, glyph, variations, 600, metric_source=name)
    # The final brace endpoint needs optical continuation: raw point
    # extrapolation folds a terminal below the baseline. Use the established
    # 72% weight-growth method, with its vertical-span preservation.
    for name in ("braceleft", "braceright"):
        paths = [shape_from_glyphs(sample[w].getGlyphSet(), name) for w in (350, 400)]
        paths.append(grow(paths[-1], 20, 0.72, 3))
        from_paths(font, name, [{"wght": w} for w in (300, 350, 400)], paths, 600)
    font["HVAR"] = deepcopy(original["HVAR"])
    # Recompose only the structural components of existing ligatures. Quotes
    # and dollars retain their original outlines and weight.
    mapping = json.loads(
        (ROOT / "trials/2026-11-17-syntax-numerals/recipe-report.json").read_text()
    )["code"]["tokens"]
    changed = set(DELIMITERS)
    gdef = deepcopy(original["GDEF"])
    for text, delimiter in [
        ("${", "braceleft"),
        ("$[", "bracketleft"),
        ("$(", "parenleft"),
    ]:
        name = mapping[text]
        compose(
            font,
            name,
            [("dollar", 1, 1, 35, 0), (delimiter, 1, 1, 565, 0)],
            1200,
            metric_source=name,
        )
        changed.add(name)
    name = mapping["<'"]
    compose(
        font,
        name,
        [("less.generic", 1, 1, 0, 0), ("quotesingle", 1, 1, 680, 0)],
        1200,
        metric_source=name,
    )
    changed.add(name)
    font["GDEF"] = gdef
    family = font["name"].getDebugName(16)
    study = "Daikonic Transit Code Delimiter Weight Study"
    for record in font["name"].names:
        record.string = (
            record.toUnicode()
            .replace(family, study)
            .replace(family.replace(" ", ""), study.replace(" ", ""))
            .encode(record.getEncoding())
        )
    font.recalcTimestamp = False
    target = OUT / "DaikonicTransitCodeDelimiterWeightStudy-VF.ttf"
    font.save(target)
    actual = TTFont(target)
    for tag in ["GSUB", "GPOS", "GDEF", "cmap", "fvar", "STAT", "HVAR"]:
        assert original.getTableData(tag) == actual.getTableData(tag), tag
    for name in original.getGlyphOrder():
        if name not in changed:
            assert original["glyf"][name].compile(original["glyf"]) == actual["glyf"][
                name
            ].compile(actual["glyf"]), name
            assert expanded_variations(original, name) == expanded_variations(
                actual, name
            ), name
            assert original["hmtx"][name] == actual["hmtx"][name], name
        assert original["hmtx"][name][0] == actual["hmtx"][name][0], name
    measurements = []
    for weight in range(300, 401, 10):
        gs = actual.getGlyphSet(location={"wght": weight})
        oldgs = original.getGlyphSet(location={"wght": weight})
        parent = shape_from_glyphs(gs, "parenleft")
        width = spans(parent, (parent.bounds[1] + parent.bounds[3]) / 2, 1)[0]
        for name in DELIMITERS:
            p = shape_from_glyphs(gs, name)
            assert all(a < b for a, b in zip(p.bounds[:2], p.bounds[2:])), (
                weight,
                name,
                p.bounds,
            )
            assert abs(p.bounds[1] - shape_from_glyphs(oldgs, name).bounds[1]) < 1.1, (
                weight,
                name,
                "bottom",
            )
            assert abs(p.bounds[3] - shape_from_glyphs(oldgs, name).bounds[3]) < 1.1, (
                weight,
                name,
                "top",
            )
        for name in ["bar.delimiterOpen", "bar.delimiterClose"]:
            box = shape_from_glyphs(gs, name).bounds
            assert abs(box[2] - box[0] - (width[1] - width[0])) < 1.1
        if weight in (300, 350):
            expected = sample[weight + 50].getGlyphSet()
            for name in DELIMITERS:
                assert (
                    max(
                        abs(a - b)
                        for a, b in zip(
                            shape_from_glyphs(gs, name).bounds,
                            shape_from_glyphs(expected, name).bounds,
                        )
                    )
                    < 1.1
                ), (weight, name)
        measurements.append(
            {
                "weight": weight,
                "delimiter_weight": weight + 50,
                "paren_stem": width[1] - width[0],
            }
        )
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                ots.OTS_SANITIZE,
                str(target),
                str(Path(tmp) / "check.ttf"),
            ],
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr.decode()
    (OUT / "validation.json").write_text(
        json.dumps(
            {
                "source": str(SOURCE.relative_to(ROOT)),
                "changed_glyphs": sorted(changed),
                "mapping": {
                    "300": 350,
                    "350": 400,
                    "400": "450 continuation; compatible extrapolation with optically grown braces",
                },
                "weights": measurements,
                "preserved": "all other outlines/variations/metrics, all advances and layout tables",
                "sanitizer": "passed",
            },
            indent=2,
        )
        + "\n"
    )
    parts = []
    for row, (weight, label, target_label) in enumerate(
        [
            (300, "Light", "Book350 delimiters"),
            (350, "Book", "Regular400 delimiters"),
            (400, "Regular", "450 delimiters / derived continuation"),
        ]
    ):
        f = instantiateVariableFont(deepcopy(actual), {"wght": weight}, inplace=True)
        p = Panel("delim-weight-" + label, DATA["families"]["code"])
        bind(p, f)
        y = 40 + 250 * row
        p.text(label + " / " + target_label, 25, y, 23, 400, "#194454")
        for n, text in enumerate(
            [
                "(abc) [abc] {abc}  |x|  Vec<T>",
                "fn f(x: T) { map(|v| v + x); }",
                "let x = ${value};  get<'a>(x: &'a T)",
            ]
        ):
            p.text(
                text,
                25,
                y + 65 + 65 * n,
                32,
                400,
                "#101712",
                features={"calt": True},
                max_width=1230,
            )
        parts.append(p.body())
    (OUT / "Delimiter-Weight.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="800" viewBox="0 0 1300 800"><title>Structural delimiters one weight step heavier</title><rect width="1300" height="800" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    print(
        "One-step delimiter study passed: exact next-weight samples,11interpolation locations,preserved heights/advances/other glyphs/layout; OTS passed"
    )


if __name__ == "__main__":
    main()
