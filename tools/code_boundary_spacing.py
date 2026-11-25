"""Fit the exposed edges of Code identifiers with position-only adjustments."""

from argparse import ArgumentParser
from collections import defaultdict
from itertools import product
import json
from pathlib import Path
from statistics import median

from fontTools.ttLib import TTFont

from code_crossbar_alignment import profile
from font_feature_tools import add_features, feature_subtables


def identifier_glyphs(font):
    names = {name for cp, name in font.getBestCmap().items() if ('a' + chr(cp)).isidentifier()}
    names |= {name for name in font.getGlyphOrder() if name.partition('.')[0] in names}
    ligatures = [table.ligatures for _, table in feature_subtables(font)
                 if hasattr(table, "ligatures")]
    for lookup in ligatures:
        for first, rows in lookup.items():
            if first in names:
                names.update(row.LigGlyph for row in rows if names.issuperset(row.Component))
    return names | {'.notdef'}


def split_boundary_shift(start, end):
    return (start // 2, end // 2) if start and end else (start, end)


def boundary_rules(font, settings):
    cmap = font.getBestCmap()
    rows = [(cmap[ord(left)], cmap[ord(right)], start, end)
            for left, right, start, end in settings]
    if not rows:
        return ""
    continued = ' '.join(sorted(identifier_glyphs(font)))
    edges = ' '.join(sorted({name for row in rows for name in row[:2]}))
    fits = {
        "Start": [(a, b, start, 0) for a, b, start, _ in rows if start],
        "End": [(a, b, 0, end) for a, b, _, end in rows if end],
        "Short": [(a, b, *split_boundary_shift(start, end)) for a, b, start, end in rows],
    }
    # The checks mark one input slot so an interior miss never skips the
    # next candidate pair. The nested PairPos can still position both glyphs.
    contexts = {
        "Start": ("@CodeContinue @CodeEdge' @CodeEdge @CodeContinue",
                  "@CodeEdge' lookup StartBoundaryFit @CodeEdge @CodeContinue"),
        "End": ("@CodeContinue @CodeEdge' @CodeEdge @CodeContinue",
                "@CodeContinue @CodeEdge' lookup EndBoundaryFit @CodeEdge"),
        "Short": ("@CodeContinue @CodeEdge' @CodeEdge, @CodeEdge' @CodeEdge @CodeContinue",
                  "@CodeEdge' lookup ShortBoundaryFit @CodeEdge"),
    }
    fea = ["languagesystem DFLT dflt;", "languagesystem latn dflt;",
           f"@CodeContinue = [{continued}];", f"@CodeEdge = [{edges}];"]
    for label, values in fits.items():
        if values:
            fea.append(f"lookup {label}BoundaryFit {{")
            fea.extend(f"pos {a} <{left} 0 0 0> {b} <{right} 0 0 0>;"
                       for a, b, left, right in values)
            fea.append(f"}} {label}BoundaryFit;")
    fea.append("feature calt {")
    for label, (interior, edge) in contexts.items():
        if fits[label]:
            fea.extend([f"lookup {label}Boundary {{", f"ignore pos {interior};",
                        f"pos {edge};", f"}} {label}Boundary;"])
    fea.append("} calt;")
    return "\n".join(fea)


def add_boundary_spacing(font, settings):
    if settings:
        add_features(font, boundary_rules(font, settings))


def facing_gap(left, right, advance, height):
    """Measure near-facing ink without letting a single tip set the gap."""
    clearances = sorted(advance + right[y][0] - left[y][1]
                        for y in left.keys() & right.keys() if 0 <= y <= height)
    return clearances[len(clearances) // 10]


def measure(font, spacing, axes):
    cmap = font.getBestCmap()
    groups = spacing["classes"]
    letters = sorted({char for chars in groups.values() for char in chars})
    movable = set(groups["WidthMovable"])
    reference = groups["WidthRound"] + groups["WidthStandard"]
    samples = defaultdict(list)
    margins = defaultdict(list)
    height = font["OS/2"].sxHeight
    for weight, width in product(axes["wght"], axes["wdth"]):
        glyphs = font.getGlyphSet(location={"wght": weight, "wdth": width})
        names = {char: cmap[ord(char)] for char in letters}
        edges = {char: profile(glyphs, name) for char, name in names.items()}
        advances = {char: glyphs[name].width for char, name in names.items()}
        for char, rows in edges.items():
            margins[char].append((min(x[0] for x in rows.values()),
                                  advances[char] - max(x[1] for x in rows.values())))
        gaps = {(a, b): facing_gap(edges[a], edges[b], advances[a], height)
                for a, b in product(letters, repeat=2)}
        typical = median(gaps[a, b] for a, b in product(reference, repeat=2))
        for pair, gap in gaps.items():
            samples[pair].append(gap - typical)
    rules = []
    for (left, right), errors in samples.items():
        # Leave ordinary variation in the letterfit. Treat ambiguous pairs
        # the same across the family and keep outward ink in its cell.
        low, high = min(errors), max(errors)
        change = 0
        for size in (8, 4):
            threshold = 12 + size
            if low >= threshold or high <= -threshold:
                change = size if low >= threshold else -size
                break
        start = change if left in movable else 0
        end = -change if right in movable else 0
        if change < 0:
            start = 0 if min(x for x, _ in margins[left]) <= -start + 2 else start
            end = 0 if min(x for _, x in margins[right]) <= end + 2 else end
        if start or end:
            rules.append([left, right, start, end])
    return rules


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Spacing trial with its recipe and variable fonts")
    parser.add_argument("output", type=Path, help="Output recipe")
    args = parser.parse_args()
    recipe = json.loads((args.source / "recipe.json").read_text())
    review = json.loads((args.source / "review.json").read_text())
    stem = review["family"].replace(" ", "")
    spacing = recipe["layout_review"]["edge_spacing"]
    for style, suffix in (("upright", ""), ("italic", "-Italic")):
        with TTFont(args.source / "VF" / f"{stem}{suffix}-VF.ttf") as font:
            spacing[style]["boundaries"] = measure(font, spacing[style], recipe["sample_coordinates"])
        print(style, len(spacing[style]["boundaries"]))
    args.output.write_text(json.dumps(recipe, indent=2) + "\n")


if __name__ == "__main__":
    main()
