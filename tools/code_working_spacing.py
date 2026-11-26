"""Build the current Code spacing previews from the reviewed source recipe."""

from argparse import ArgumentParser
import json
from pathlib import Path

from bundle_release import sanitize
from check_code_rebuild import RECIPE_PATH, ROOT
from code_gpos_compaction import FAMILY as LAYOUT_FAMILY, build
from code_width import verify_width
from font_feature_tools import add_features
from release_code import release_font


FAMILY = "Daikonic Transit Code Spacing Review"
SPACING_PATH = ROOT / "recipes/code-working-spacing.json"


def apply_compact_classes(recipe, refinement):
    compact = set(refinement["compact"])
    spacing = recipe["layout_review"]["edge_spacing"]
    spacing["fixed"] = "".join(sorted(set(spacing["fixed"]) - compact))
    for style, overrides in refinement["boundaries"].items():
        face = spacing[style]
        classes = face["classes"]
        classes["WidthWide"] = "".join(sorted(set(classes["WidthWide"]) - compact))
        for name in ("WidthCompact", "WidthMovable"):
            classes[name] = "".join(sorted(set(classes[name]) | compact))
        kept = [row for row in face["boundaries"] if compact.isdisjoint(row[:2])]
        face["boundaries"] = sorted(kept + overrides)


def add_wide_spacing(font, face, amount):
    cmap = font.getBestCmap()
    classes = {}
    for label, characters in face["classes"].items():
        bases = {cmap[ord(char)] for char in characters}
        classes[label] = " ".join(name for name in font.getGlyphOrder()
                                  if name.partition(".texture.")[0] in bases)
    shared = amount // 2
    add_features(font, "\n".join([
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        *(f"@{label} = [{names}];" for label, names in classes.items()),
        "feature calt {",
        "lookup WideNeighborSpacing {",
        # When both letters move into one gap, they share the allowance.
        f"pos @WidthWide @WidthMovable' <{shared} 0 0 0> @WidthMovable @WidthWide;",
        f"pos @WidthWide @WidthMovable @WidthMovable' <-{shared} 0 0 0> @WidthWide;",
        f"pos @WidthWide @WidthMovable' <{amount} 0 0 0> @WidthMovable;",
        f"pos @WidthMovable @WidthMovable' <-{amount} 0 0 0> @WidthWide;",
        "} WideNeighborSpacing;",
        "lookup WidePlacement {",
        *(f"pos @{left} @WidthWide' <{offset} 0 0 0> @{right};"
          for left, _, right, offset in face["rules"]),
        "} WidePlacement;",
        "} calt;",
    ]))


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    recipe = json.loads(RECIPE_PATH.read_text())
    refinement = json.loads(SPACING_PATH.read_text())
    apply_compact_classes(recipe, refinement)
    source = args.output / "source"
    source.mkdir(parents=True, exist_ok=True)
    build(recipe, None, source)
    for style, suffix in (("upright", ""), ("italic", "-Italic")):
        raw = source / f"{LAYOUT_FAMILY.replace(' ', '')}{suffix}-VF.ttf"
        target = args.output / f"{FAMILY.replace(' ', '')}{suffix}-VF.ttf"
        face = recipe["layout_review"]["edge_spacing"][style]
        with release_font(raw, "1.1.0", italic=bool(suffix), family=FAMILY) as font:
            add_wide_spacing(font, face, refinement["wide_neighbor_shift"])
            sanitize(font)
            verify_width(font, recipe["alphabet_review"]["cell"])
            font.save(target)
        print(target, flush=True)


if __name__ == "__main__":
    main()
