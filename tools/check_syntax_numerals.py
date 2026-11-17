"""Check requested syntax groups, fixed cells, optional numerals and interpolation."""

from pathlib import Path
import json
import subprocess
import tempfile
import unicodedata
from fontTools.ttLib import TTFont
import uharfbuzz as hb
import ots
from syntax_numeral_study import OUT, TOKENS, RECIPE, DIGITS
from audit import shape_from_glyphs
from derive_weights import topology
from specimens import ROOT
from validate import TOKENS as EXISTING


def run(path, text, loc, features=None):
    font = TTFont(path)
    h = hb.Font(hb.Face(path.read_bytes()))
    h.scale = (1000, 1000)
    h.set_variations(loc)
    b = hb.Buffer()
    b.add_str(text)
    b.guess_segment_properties()
    hb.shape(h, b, features or {})
    return [
        (font.getGlyphName(i.codepoint), p.x_advance, p.x_offset, p.y_offset)
        for i, p in zip(b.glyph_infos, b.glyph_positions)
    ]


def main():
    paths = json.loads((OUT / "fonts.json").read_text())
    recipe = json.loads((OUT / "recipe-report.json").read_text())
    report = {}
    for key, rel in paths.items():
        path = ROOT / rel
        f = TTFont(path)
        baseline = TTFont(
            ROOT
            / json.loads(
                (ROOT / "trials/2026-11-17-dot-palette/fonts.json").read_text()
            )[key]
        )
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run(
                [ots.OTS_SANITIZE, str(path), str(Path(tmp) / "checked.ttf")],
                capture_output=True,
            )
            assert p.returncode == 0, (key, p.stderr.decode())
        weights = (
            [300, 312.5, 325, 350, 375, 387.5, 400]
            if key == "code"
            else [300, 325, 350, 375, 400, 450, 500, 550, 600]
        )
        samples = []
        for weight in weights:
            for optical in [10, 12, 14, 24, 36] if key == "system" else [None]:
                loc = {"wght": weight, **({"opsz": optical} if optical else {})}
                if key == "code":
                    gs = f.getGlyphSet(location=loc)
                    old = baseline.getGlyphSet(location=loc)
                    a = shape_from_glyphs(gs, "equal").bounds
                    b = shape_from_glyphs(old, "equal").bounds
                    assert abs((a[2] - a[0]) / (b[2] - b[0]) - 1.08) < 0.005
                    assert abs(a[1] - b[1]) < 0.01 and abs(a[3] - b[3]) < 0.01
                    for text in TOKENS:
                        result = run(path, text, loc)
                        assert (
                            len(result) == 1
                            and result[0][0] == recipe["code"]["tokens"][text]
                        ), (weight, text, result)
                        assert result[0][1] == 600 * len(text), (weight, text, result)
                    from dot_inventory import dots

                    for text in ("?.", "!."):
                        pairdots = dots(gs, recipe["code"]["tokens"][text])
                        assert len(pairdots) == 2, (weight, text, "separate dots")
                        boxes = sorted((m["bounds"] for _, m in pairdots))
                        gap = boxes[1][0] - boxes[0][2]
                        assert 300 <= gap <= 400, (
                            weight,
                            text,
                            "optical pair gap",
                            gap,
                        )
                    for text in EXISTING:
                        got = run(path, text, loc)
                        assert len(got) == 1 and got[0][1] == 600 * len(text), (
                            weight,
                            text,
                            got,
                        )
                    for text, count in [
                        ("Vec<T>", 2),
                        ("Vec<Vec<T>>", 4),
                        ("a<b", 0),
                        ("12<34", 0),
                        ("x<2", 0),
                        ("2<x", 0),
                        ("Vec<u8>", 2),
                        ("HashMap<key, value>", 2),
                        ("Option<someType>", 2),
                        ("lower<someType>", 2),
                        ("someType<lower>", 2),
                        ("variable_1<other_2", 0),
                        ("a< b", 1),
                        ("a <b", 1),
                        (" < ", 0),
                        ("<", 1),
                        ("foo::<u8>", 2),
                        ("a < b", 0),
                        ("a <= b", 0),
                        ("a >= b", 0),
                    ]:
                        got = run(path, text, loc)
                        assert (
                            sum(
                                n in ("less.generic", "greater.generic")
                                for n, a, x, y in got
                            )
                            == count
                        ), (weight, text, got)
                        assert sum(a for n, a, x, y in got) == len(text) * 600
                    for name in ["less.generic", "greater.generic"]:
                        bounds = shape_from_glyphs(gs, name).bounds
                        assert bounds[1] >= 0 and bounds[3] <= f["OS/2"].sCapHeight
                    for text in ["q\u0301", "j\u0301", "á"]:
                        got = run(path, text, loc)
                        assert sum(a for n, a, x, y in got) == 600
                    for name in recipe["code"]["tokens"].values():
                        coverage = f["GDEF"].table.LigCaretList.Coverage.glyphs
                        assert name in coverage
                    unchanged = set(baseline.getGlyphOrder()) - {
                        "equal",
                        "code.equal",
                        "code.strictEqual",
                        "code.notEqual",
                        "code.notStrict",
                        "ellipsis",
                    }
                    for name in unchanged:
                        assert f["glyf"][name].compile(f["glyf"]) == baseline["glyf"][
                            name
                        ].compile(baseline["glyf"]), (key, name, "unrelated glyph")
                else:
                    for text in ["1/2", "12/345", "123/456", "1 1/2"]:
                        got = run(path, text, loc, {"frac": True})
                        assert all(
                            n.endswith(".numr")
                            or n.endswith(".dnom")
                            or n in ("fraction", "space", "one")
                            for n, a, x, y in got
                        ), (key, loc, text, got)
                        assert "fraction" in [n for n, a, x, y in got]
                    plain = run(path, "0123456789", loc)
                    assert [n for n, a, x, y in plain] == DIGITS
                    for fraction, text in [("½", "1/2"), ("¼", "1/4"), ("⅒", "1/10")]:
                        a = run(path, fraction, loc)
                        b = run(path, text, loc, {"frac": True})
                        assert abs(sum(v[1] for v in a) - sum(v[1] for v in b)) <= 2, (
                            key,
                            loc,
                            fraction,
                            a,
                            b,
                        )
                        gs = f.getGlyphSet(location=loc)
                        assert (
                            abs(
                                sum(gs[n].width for n, _, _, _ in a)
                                - sum(gs[n].width for n, _, _, _ in b)
                            )
                            < 0.01
                        ), (key, loc, fraction, "real metrics")
                    if key == "sans":
                        got = run(path, "0123456789", loc, {"onum": True})
                        assert [n for n, a, x, y in got] == [
                            d + ".onum" for d in DIGITS
                        ]
                        frac = run(path, "12/345", loc, {"frac": True, "onum": True})
                        assert all(
                            n.endswith((".numr", ".dnom")) or n == "fraction"
                            for n, a, x, y in frac
                        ), (loc, frac)
                    else:
                        got = run(path, "0123456789", loc, {"tnum": True})
                        assert len({v[1] for v in got}) == 1
                        got = run(path, "12/345", loc, {"frac": True, "tnum": True})
                        assert "fraction" in [n for n, a, x, y in got]
                    for name in baseline.getGlyphOrder():
                        assert f["glyf"][name].compile(f["glyf"]) == baseline["glyf"][
                            name
                        ].compile(baseline["glyf"]), (key, name, "default drawing")
                samples.append(loc)
        report[key] = {
            "sanitizer": "passed",
            "samples": samples,
            "shaping": "passed",
            "default_drawings": "unchanged except explicit Code operator/ellipsis studies",
        }
        print(key, len(samples), "locations checked", flush=True)
    (OUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        "Syntax, numeral features, Unicode fractions, spacing and retained features verified"
    )


if __name__ == "__main__":
    main()
