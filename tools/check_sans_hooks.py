"""Verify selected hook fidelity, interpolation, spacing and unchanged Sans glyphs."""

import json
from pathlib import Path
import string
import argparse
import uharfbuzz as hb
from fontTools.ttLib import TTFont

from adopt_weighting import ROOT, instance
from audit import shape
from derive_weights import coverage_difference, topology
from hook_ligature_study import construct, whitespace_band
from validate import run as static_run


def shaper(path, weight):
    font = TTFont(path)
    h = hb.Font(hb.Face(Path(path).read_bytes()))
    h.set_variations({"wght": weight})

    def run(text, liga=True):
        b = hb.Buffer()
        b.add_str(text)
        b.guess_segment_properties()
        hb.shape(h, b, {"liga": liga})
        return [
            (font.getGlyphName(g.codepoint), p.x_advance, p.x_offset, p.y_offset)
            for g, p in zip(b.glyph_infos, b.glyph_positions)
        ]

    return run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", type=Path)
    args = parser.parse_args()
    cfg = json.loads((ROOT / "family.json").read_text())["families"]["sans"]
    if not cfg.get("ligature_baseline"):
        return
    current, prior = ROOT / cfg["font"], ROOT / cfg["ligature_baseline"]
    font, old = TTFont(current), TTFont(prior)
    changed = {"a_i", "l_i"}
    for name in font.getGlyphOrder():
        if name not in changed:
            assert font["glyf"][name].compile(font["glyf"]) == old["glyf"][
                name
            ].compile(old["glyf"]), (name, "outline")
            assert [
                (v.axes, v.coordinates) for v in font["gvar"].variations.get(name, [])
            ] == [
                (v.axes, v.coordinates) for v in old["gvar"].variations.get(name, [])
            ], (
                name,
                "variation",
            )
    rows = []
    chars = string.ascii_letters + string.digits + string.punctuation + " "
    for weight in range(300, 601, 25):
        f, expected = instance(current, weight, None), instance(prior, weight, None)
        band = whitespace_band(expected)
        details = {pair: construct(expected, pair, band) for pair in ("ai", "li")}
        differences = {
            n: coverage_difference(shape(f, n), shape(expected, n)) for n in changed
        }
        assert max(differences.values()) < 0.025, (weight, differences)
        assert all(
            topology(shape(f, n)) == topology(shape(expected, n)) for n in changed
        ), (weight, "topology")
        run, previous = shaper(current, weight), shaper(prior, weight)
        for a in chars:
            for b in chars:
                if a + b not in ("ai", "li"):
                    assert run(a + b) == previous(a + b), (
                        weight,
                        a + b,
                        "unrelated positioning",
                    )
        for word in (
            "ai",
            "li",
            "Daikonic",
            "daily",
            "liquid",
            "mailing",
            "aili",
            "liai",
        ):
            plain = sum(p[1] for p in run(word, False))
            actual = sum(p[1] for p in run(word))
            # Between named masters, rounding a combined advance can differ
            # by one unit from rounding each ordinary letter separately.
            tolerance = (
                0
                if weight in (300, 350, 400, 500, 600)
                else word.count("ai") + word.count("li")
            )
            assert abs(actual - (plain - 135 * word.count("li"))) <= tolerance, (
                weight,
                word,
                plain,
                actual,
            )
        for n in changed:
            assert abs(f["hmtx"][n][0] - expected["hmtx"][n][0]) <= 1, (
                weight,
                n,
                "advance",
            )
        rows.append(
            {
                "wght": weight,
                "coverage_difference": differences,
                "word_spacing": "passed",
                "unrelated_ASCII_pair_positions": len(chars) ** 2 - 2,
            }
        )
    (ROOT / "qa/sans/hook-validation.json").write_text(
        json.dumps(
            {"unchanged_other_outlines_and_variations": "exact", "samples": rows},
            indent=2,
        )
        + "\n"
    )
    print(
        "Sans hooks validated at",
        len(rows),
        "weights; unrelated outlines/variations and pair positioning retained",
    )
    if args.native:
        native_rows = []
        for weight in (300, 350, 400, 500, 600):
            f, e = instance(args.native, weight, None), instance(current, weight, None)
            differences = {
                n: coverage_difference(shape(f, n), shape(e, n))
                for n in ("a_i", "l_i", "a", "i", "l")
            }
            assert max(differences.values()) < 0.025, (weight, differences)
            widths = {
                word: sum(p[1] for p in static_run(f, word))
                - sum(p[1] for p in static_run(e, word))
                for word in ("ai", "li", "Daikonic", "daily", "liquid", "mailing")
            }
            assert max(map(abs, widths.values())) <= 1, (weight, widths)
            native_rows.append(
                {
                    "wght": weight,
                    "outline_coverage_difference": differences,
                    "word_advance_differences": widths,
                }
            )
        (ROOT / "qa/sans/hook-native-validation.json").write_text(
            json.dumps(native_rows, indent=2) + "\n"
        )
        print(
            "Independent editable-source hooks and word spacing verified at five weights"
        )


if __name__ == "__main__":
    main()
