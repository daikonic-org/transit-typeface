"""Build the current Code spacing previews from the reviewed source recipe."""

from argparse import ArgumentParser
import json
from pathlib import Path

from bundle_release import sanitize
from check_code_rebuild import RECIPE_PATH, ROOT
from code_boundary_spacing import identifier_glyphs
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


def glyph_class(font, characters):
    cmap = font.getBestCmap()
    bases = {cmap[ord(char)] for char in characters}
    return " ".join(name for name in font.getGlyphOrder()
                    if name.partition(".texture.")[0] in bases)


def add_wide_spacing(font, face, amount):
    classes = {label: glyph_class(font, chars) for label, chars in face["classes"].items()}
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


def add_directional_boundaries(font, settings):
    convex_left = settings["convex_left"]
    convex_right = settings["convex_right"]
    concave_left = settings["concave_left"]
    concave_right = settings["concave_right"]
    amount = settings["shift"]
    shared = amount // 2
    continued = " ".join(sorted(identifier_glyphs(font)))
    add_features(font, f"""
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        @Identifier = [{continued}];
        @ConvexLeft = [{glyph_class(font, convex_left)}];
        @ConvexRight = [{glyph_class(font, convex_right)}];
        @ConcaveLeft = [{glyph_class(font, concave_left)}];
        @ConcaveRight = [{glyph_class(font, concave_right)}];
        @TouchLeft = [{glyph_class(font, convex_right + concave_right)}];
        @TouchRight = [{glyph_class(font, convex_left + concave_left)}];
        feature calt {{
            lookup DirectionalStart {{
                ignore pos @Identifier @TouchLeft' @TouchRight;
                pos @ConvexRight' <{amount} 0 0 0> @ConcaveLeft @Identifier;
                pos @ConcaveRight' <{amount} 0 0 0> @ConvexLeft @Identifier;
                pos @ConvexRight' <{shared} 0 0 0> @ConcaveLeft;
                pos @ConcaveRight' <{shared} 0 0 0> @ConvexLeft;
            }} DirectionalStart;
            lookup DirectionalEnd {{
                ignore pos @TouchLeft @TouchRight' @Identifier;
                pos @Identifier @ConvexRight @ConcaveLeft' <-{amount} 0 0 0>;
                pos @Identifier @ConcaveRight @ConvexLeft' <-{amount} 0 0 0>;
                pos @ConvexRight @ConcaveLeft' <-{shared} 0 0 0>;
                pos @ConcaveRight @ConvexLeft' <-{shared} 0 0 0>;
            }} DirectionalEnd;
        }} calt;
    """)


def build_fonts(output, version, family=FAMILY, *, source=None, capital_spacing=False,
                delimiter_revision=False, even_spread=False):
    recipe = json.loads(RECIPE_PATH.read_text())
    refinement = json.loads(SPACING_PATH.read_text())
    apply_compact_classes(recipe, refinement)
    if delimiter_revision:
        recipe["layout_review"]["delimiter_revision"] = True
    if even_spread:
        recipe["layout_review"]["even_spread"] = True
    output.mkdir(parents=True, exist_ok=True)
    if source is None:
        source = output / "source"
        source.mkdir(exist_ok=True)
        build(recipe, None, source)
    for style, suffix in (("upright", ""), ("italic", "-Italic")):
        raw = source / f"{LAYOUT_FAMILY.replace(' ', '')}{suffix}-VF.ttf"
        target = output / f"{family.replace(' ', '')}{suffix}-VF.ttf"
        face = recipe["layout_review"]["edge_spacing"][style]
        with release_font(raw, version, italic=bool(suffix), family=family) as font:
            add_wide_spacing(font, face, refinement["wide_neighbor_shift"])
            add_directional_boundaries(font, refinement["directional_boundaries"])
            if capital_spacing:
                from code_capital_spacing import apply_capital_spacing

                apply_capital_spacing(font, wider=True, smart=True)
            if delimiter_revision:
                from code_delimiter_revision import apply_delimiter_revision

                apply_delimiter_revision(font)
            sanitize(font)
            verify_width(font, recipe["alphabet_review"]["cell"])
            font.save(target)
        print(target, flush=True)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", default="1.1.1")
    parser.add_argument("--capital-spacing", action="store_true")
    args = parser.parse_args()
    build_fonts(args.output, args.version, capital_spacing=args.capital_spacing)


if __name__ == "__main__":
    main()
