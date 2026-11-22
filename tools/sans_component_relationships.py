"""Share the outlines of mirrored pairs and horizontal math bars in Sans."""

from math import dist

import pathops
from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables._g_l_y_f import UNSCALED_COMPONENT_OFFSET
from fontTools.ttLib.tables.TupleVariation import TupleVariation

from audit import shape_from_glyphs
from font_feature_tools import expanded_variations
from sans_baseline_trial import DOT, components, install

DELIMITER_PAIRS = (
    ("less", "greater"),
    ("parenleft", "parenright"),
    ("bracketleft", "bracketright"),
    ("braceleft", "braceright"),
)
LETTER_PAIRS = (("q", "p"), ("d", "b"))
ROUNDING_PAIRS = {DELIMITER_PAIRS[-1], *LETTER_PAIRS}


def default_mirror_matches(font, source, target):
    glyphs = font.getGlyphSet()
    original = shape_from_glyphs(glyphs, source)
    reflected = original.transform(-1, 0, 0, 1, glyphs[source].width, 0)
    partner = shape_from_glyphs(glyphs, target)
    return pathops.op(reflected, partner, pathops.PathOp.XOR).area == 0


def contours(glyph):
    start = 0
    for end in glyph.endPtsOfContours:
        yield [
            (x, y, bool(flag & 1))
            for (x, y), flag in zip(glyph.coordinates[start:end + 1], glyph.flags[start:end + 1])
        ]
        start = end + 1


def rounding_only_mirror(font, source, target):
    """Require exact reflected anchors and at most one unit of handle drift."""
    glyf = font["glyf"]
    advance = font["hmtx"][source][0]
    original = [[(advance - x, y, on) for x, y, on in reversed(contour)]
                for contour in contours(glyf[source])]
    remaining = list(contours(glyf[target]))
    if len(original) != len(remaining):
        return False
    for contour in original:
        for i, candidate in enumerate(remaining):
            if len(contour) != len(candidate):
                continue
            for start in range(len(candidate)):
                rotated = candidate[start:] + candidate[:start]
                if all(
                    a[2] == b[2] and dist(a[:2], b[:2]) <= (0 if a[2] else 1)
                    for a, b in zip(contour, rotated)
                ):
                    remaining.pop(i)
                    break
            else:
                continue
            break
        else:
            return False
    return True


def mirror(font, source, target):
    advance, _ = font["hmtx"][source]
    if font["hmtx"][target][0] != advance:
        raise ValueError(f"Unequal default advances in mirror pair {source}, {target}")
    glyph = components([(source, (advance, 0))])
    glyph.components[0].transform = [[-1, 0], [0, 1]]
    glyph.components[0].flags |= UNSCALED_COMPONENT_OFFSET
    source_deltas = expanded_variations(font, source)
    target_deltas = expanded_variations(font, target)
    zero = (0, 0)
    variations = []
    for support in sorted(source_deltas.keys() | target_deltas.keys()):
        src = source_deltas.get(support, [zero] * 4)
        dst = target_deltas.get(support, [zero] * 4)
        advance_shift = src[-3][0] - src[-4][0]
        if advance_shift != dst[-3][0] - dst[-4][0]:
            raise ValueError(f"Unequal varying advances in mirror pair {source}, {target}")
        variations.append(TupleVariation(dict(support), [(advance_shift, 0), *dst[-4:]]))
    install(font, target, glyph, variations)


def share_bar(font):
    minus = font["glyf"]["minus"]
    equal = font["glyf"]["equal"]
    if len(minus.coordinates) != 4 or len(equal.coordinates) != 8:
        raise ValueError("Expected rectangular minus and equals bars")
    top_lift = equal.coordinates[0][1] - minus.coordinates[0][1]
    bottom_drop = equal.coordinates[4][1] - minus.coordinates[0][1]
    center = (minus.coordinates[0][0] + minus.coordinates[2][0]) / 2
    division = font["glyf"]["divide"]
    _, lower, upper = division.components
    if lower.glyphName != DOT or upper.glyphName != DOT or lower.x != upper.x:
        raise ValueError("Expected aligned shared diamonds in division")

    minus_deltas = expanded_variations(font, "minus")
    equal_deltas = expanded_variations(font, "equal")
    divide_deltas = expanded_variations(font, "divide")
    minus_variations, equal_variations, divide_variations = [], [], []
    zero = (0, 0)
    for support in sorted(equal_deltas.keys() | minus_deltas.keys() | divide_deltas.keys()):
        minus_values = minus_deltas.get(support, [zero] * 8)
        equal_values = equal_deltas.get(support, [zero] * 12)
        divide_values = divide_deltas.get(support, [zero] * 7)
        thickness = equal_values[1][1] - equal_values[0][1]
        upper_bar = otRound(thickness / 2)
        lower_bar = upper_bar - thickness
        minus_outline = [
            (equal_values[i][0], upper_bar if i in (1, 2) else lower_bar) for i in range(4)
        ]
        minus_variations.append(TupleVariation(
            dict(support), [*minus_outline, *minus_values[-4:]]
        ))
        equal_variations.append(TupleVariation(dict(support), [
            (0, equal_values[1][1] - upper_bar),
            (0, equal_values[4][1] - lower_bar),
            *equal_values[-4:],
        ]))
        bar_center_shift = (minus_outline[0][0] + minus_outline[2][0]) / 2
        divide_variations.append(TupleVariation(dict(support), [
            (otRound(divide_values[1][0] - bar_center_shift), 0), *divide_values[1:]
        ]))
    font["gvar"].variations["minus"] = minus_variations
    install(font, "equal", components([("minus", (0, top_lift)), ("minus", (0, bottom_drop))]),
            equal_variations)
    install(font, "divide", components([
        ("minus", (otRound(lower.x - center), 0)),
        (DOT, (lower.x, lower.y)), (DOT, (upper.x, upper.y)),
    ]), divide_variations)


def apply_relationships(font):
    mirrored, normalized = [], []
    for source, target in (*DELIMITER_PAIRS, *LETTER_PAIRS):
        if not default_mirror_matches(font, source, target):
            if (source, target) not in ROUNDING_PAIRS or not rounding_only_mirror(font, source, target):
                raise ValueError(f"Unapproved Regular outline difference in {source}, {target}")
            normalized.append((source, target))
        mirror(font, source, target)
        mirrored.append((source, target))
    share_bar(font)
    return mirrored, normalized
