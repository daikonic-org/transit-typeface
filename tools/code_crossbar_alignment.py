"""Generate position-only Code triplet adjustments from finished variable outlines."""

from argparse import ArgumentParser
from collections import defaultdict
from itertools import product
import json
from math import ceil
from pathlib import Path
from statistics import median
from string import ascii_lowercase

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont

from audit import Samples, shape_from_glyphs
from transit_width_trial import WIDTHS, rounded_width_delta, width_ratio


TARGETS = "ft"


def profile(glyphs, name):
    """Return the outermost ink edges at each integer height."""
    samples = Samples(tolerance=.125)
    shape_from_glyphs(glyphs, name).draw(samples)
    rows = defaultdict(list)
    for (x0, y0), (x1, y1) in samples.lines:
        if y0 == y1:
            continue
        low, high = sorted((y0, y1))
        slope = (x1 - x0) / (y1 - y0)
        for y in range(ceil(low), ceil(high)):
            rows[y].append(x0 + slope * (y - y0))
    return {y: (min(xs), max(xs)) for y, xs in rows.items()}


def crossbar_level(rows, x_height):
    band = {y: right - left for y, (left, right) in rows.items() if .55 * x_height <= y < 1.06 * x_height}
    widest = max(band.values())
    levels = sorted(y for y, width in band.items() if width > widest - .5)
    return levels[len(levels) // 2]


def clearances(left, right, advance, level):
    if level not in left or level not in right:
        return None, None
    gap = advance + right[level][0] - left[level][1]
    minimum = min(advance + right[y][0] - left[y][1] for y in left.keys() & right.keys())
    return gap, minimum


def location_clearances(font, weight, width, levels):
    glyphs = font.getGlyphSet(location={"wght": weight, "wdth": width})
    cmap = font.getBestCmap()
    names = {char: cmap[ord(char)] for char in ascii_lowercase}
    profiles = {char: profile(glyphs, name) for char, name in names.items()}
    advances = {char: glyphs[name].width for char, name in names.items()}
    return {
        center: (
            {char: clearances(profiles[char], profiles[center], advances[char], level)
             for char in ascii_lowercase},
            {char: clearances(profiles[center], profiles[char], advances[center], level)
             for char in ascii_lowercase},
        )
        for center, level in levels.items()
    }


def scaled_offset(units, width):
    """Match the rounded width-axis GPOS adjustments used by the Code builder."""
    if width == 100:
        return units
    side = WIDTHS[0 if width < 100 else 1][0]
    delta = rounded_width_delta(units, width_ratio(side))
    return units + otRound(delta * (width - 100) / (side - 100))


def acceptable(offset, samples):
    for width, left, right, left_minimum, right_minimum in samples:
        adjustment = scaled_offset(offset, width)
        if abs(left - right + 2 * adjustment) > abs(left - right) + 1e-6:
            return False
        if min(left_minimum + adjustment, right_minimum - adjustment) < min(left_minimum, right_minimum) - 1e-6:
            return False
    return True


def align_crossbars(fonts, weights, widths, minimum_shift, maximum_shift):
    nominal, samples = defaultdict(list), defaultdict(list)
    for font in fonts:
        cmap = font.getBestCmap()
        height = font["OS/2"].sxHeight
        for weight in weights:
            normal = font.getGlyphSet(location={"wght": weight, "wdth": 100})
            levels = {char: crossbar_level(profile(normal, cmap[ord(char)]), height) for char in TARGETS}
            for width in widths:
                for center, (left_side, right_side) in location_clearances(font, weight, width, levels).items():
                    for left, right in product(ascii_lowercase, repeat=2):
                        context = left + center + right
                        left_gap, left_minimum = left_side[left]
                        right_gap, right_minimum = right_side[right]
                        samples[context].append((width, left_gap, right_gap, left_minimum, right_minimum))
                        if weight == 400 and width == 100 and left_gap is not None and right_gap is not None:
                            nominal[context].append((right_gap - left_gap) / 2)

    offsets = {}
    for context, values in sorted(samples.items()):
        left, center, right = context
        if center in (left, right) or any(sample[1] is None or sample[2] is None for sample in values):
            continue
        target = otRound(median(nominal[context]))
        # Two neighboring movable letters can each open their shared gap.
        # Forbid moves into that gap so the adjustments remain safe together.
        if (target < 0 and left in TARGETS) or (target > 0 and right in TARGETS):
            continue
        sign = -1 if target < 0 else 1
        for size in range(min(abs(target), maximum_shift), minimum_shift - 1, -1):
            offset = sign * size
            if acceptable(offset, values):
                offsets[context] = offset
                break
    return offsets


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("upright", type=Path)
    parser.add_argument("italic", type=Path)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output-recipe", type=Path, required=True)
    parser.add_argument("--minimum-shift", required=True, type=int)
    parser.add_argument("--maximum-shift", required=True, type=int)
    args = parser.parse_args()
    if not 0 < args.minimum_shift <= args.maximum_shift:
        parser.error("Expected 0 < minimum shift <= maximum shift")
    recipe = json.loads(args.recipe.read_text())
    axes = recipe["sample_coordinates"]
    if 400 not in axes["wght"] or 100 not in axes["wdth"]:
        parser.error("The sample coordinates must include Regular 400 at Normal width")
    with TTFont(args.upright) as upright, TTFont(args.italic) as italic:
        offsets = align_crossbars((upright, italic), axes["wght"], axes["wdth"],
                                  args.minimum_shift, args.maximum_shift)
    recipe["layout_review"]["triplet_offsets"] = offsets
    args.output_recipe.write_text(json.dumps(recipe, indent=2) + "\n")
    print(f"Measured {len(offsets)} GPOS contexts for f and t")


if __name__ == "__main__":
    main()
