"""Prepare a Code positioning recipe using the original lowercase width classes."""

from argparse import ArgumentParser
import json
from itertools import permutations
from pathlib import Path
from string import ascii_lowercase

from fontTools.ttLib import TTFont

from code_foundation import build_master, width_class_scales
from specimens import ROOT


def width_membership(recipe):
    # Classify the custom glyphs from their donor outlines. The fitted glyphs
    # retain their current outlines and advances in the resulting spacing trial.
    letters = set(ascii_lowercase)
    calibration = recipe | {
        "code_specific_characters": "".join(char for char in recipe["code_specific_characters"]
                                            if char not in letters),
        "constructed_forms": {name: shape for name, shape in recipe["constructed_forms"].items()
                              if name not in letters},
    }
    config = recipe["alphabet_review"]
    with TTFont(ROOT / (recipe["fonts"]["sans"] + "-VF.ttf")) as source:
        masters = {int(weight): build_master(source, donor, int(weight), config)
                   for weight, donor in config["weights"].items()}
        _, _, report = width_class_scales(masters, calibration)
    groups = {name: record["sample"] for name, record in report["classes"].items()}
    assert sorted("".join(groups.values())) == list(ascii_lowercase)
    return groups


def width_spacing(recipe, steps):
    groups = width_membership(recipe)
    classes = {f"Width{name}": members for name, members in groups.items() if members}
    fixed = groups["Wide"]
    classes["WidthMovable"] = "".join(char for char in ascii_lowercase if char not in fixed)
    width_rules = []
    for (i, left), (j, right) in permutations(enumerate(groups), 2):
        if groups[left] and groups[right]:
            change = steps[min(abs(i-j), len(steps)) - 1] * (1 if i > j else -1)
            width_rules.append([f"Width{left}", "WidthMovable", f"Width{right}", change])

    settings = recipe["layout_review"]
    previous = settings.get("edge_spacing", {})
    new = {"fixed": fixed}
    for style in ("upright", "italic"):
        prior = previous.get(style, {})
        prior_classes = prior.get("classes", {})

        def letter_class(name):
            chars = prior_classes[name]
            return isinstance(chars, str) and set(chars).issubset(ascii_lowercase)

        boundaries = [rule for rule in prior.get("rules", ())
                      if not (letter_class(rule[0]) and letter_class(rule[2]))]
        used = {name for rule in boundaries for name in rule[:3]}
        boundary_classes = {name: members for name, members in prior_classes.items() if name in used}
        new[style] = {"classes": boundary_classes | classes, "rules": boundaries + width_rules}
    settings["edge_spacing"] = new
    return groups, len(width_rules)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output-recipe", type=Path, required=True)
    parser.add_argument("--steps", type=int, nargs="+", required=True)
    args = parser.parse_args()
    if any(step <= 0 for step in args.steps) or sorted(args.steps) != args.steps:
        parser.error("Steps must be positive, in increasing order")
    recipe = json.loads(args.recipe.read_text())
    groups, count = width_spacing(recipe, args.steps)
    args.output_recipe.write_text(json.dumps(recipe, indent=2) + "\n")
    print(f"{count} class patterns; fixed Wide glyphs: {groups['Wide']}")
    print(json.dumps(groups, indent=2))


if __name__ == "__main__":
    main()
