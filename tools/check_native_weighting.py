"""Compare independently compiled editable sources with the production VF."""

import argparse
import json

from adopt_weighting import ROOT, OUT, instance
from audit import shape
from derive_weights import coverage_difference
from validate import run, TOKENS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("family", choices=["sans", "system", "code"])
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    key = args.family
    cfg = json.loads((ROOT / "family.json").read_text())["families"][key]
    recipe = json.loads((ROOT / "recipes/weights.json").read_text())["families"][key]
    root = OUT / key
    rows = []
    for optical in recipe["optical_sizes"]:
        for weight in recipe["target_H_stems"]:
            f = instance(root / "Native-VF.ttf", int(weight), optical)
            expected = instance(
                (
                    ROOT / cfg["font"]
                    if args.production
                    else root / "fonts/VF" / (cfg["stem"] + "-VF.ttf")
                ),
                int(weight),
                optical,
            )
            assert set(f.getBestCmap()) == set(expected.getBestCmap())
            advance_error = max(
                abs(f["hmtx"][f.getBestCmap()[cp]][0] - expected["hmtx"][name][0])
                for cp, name in expected.getBestCmap().items()
            )
            # Independent UFO compilation rounds phantom points separately;
            # the production TTF route retains exact original metric variations.
            assert advance_error <= 1, (
                key,
                weight,
                optical,
                "native advances",
                advance_error,
            )
            differences = {}
            for char in "Hnoaesftilj01yéÅ←↑→↓↔↕⇐⇑⇒⇓⇔⇕":
                a, b = f.getBestCmap()[ord(char)], expected.getBestCmap()[ord(char)]
                difference = coverage_difference(shape(f, a), shape(expected, b))
                assert difference < 0.025, (key, weight, optical, char, difference)
                differences[char] = difference
            if key == "code":
                for token in TOKENS:
                    got = run(f, "a" + token + "n")
                    assert len(got) == 3 and sum(x[1] for x in got) == 600 * (
                        len(token) + 2
                    ), (key, token, got)
            if key == "system":
                assert run(f, "1", {"tnum": True})[0][0] == "one.tnum"
            rows.append(
                {
                    "wght": int(weight),
                    "opsz": optical,
                    "maximum_advance_difference_units": advance_error,
                    "maximum_control_coverage_difference": max(differences.values()),
                    "glyphs": differences,
                }
            )
    (root / "native-validation.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(key, "editable sources verified", len(rows), "locations", flush=True)


if __name__ == "__main__":
    main()
