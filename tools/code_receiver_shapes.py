"""Fit Sans's m and w constructions to Code's three receiver widths."""

from functools import lru_cache

import pathops
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

from audit import shape_from_glyphs, spans
from font_feature_tools import compose, from_paths, master_locations
from specimens import ROOT, specimen_families

ADVANCE = 600
RECEIVERS = "mw"
EXTRA_WIDTH = {"m": 28, "w": 22}
FORM_SHIFT = {"m": 14, "w": 11}


def remap(value, old, new):
    """Map stem edges exactly and interpolate between them."""
    for index in range(1, len(old) - 1):
        if value <= old[index]:
            break
    else:
        index = len(old) - 1
    fraction = (value - old[index - 1]) / (old[index] - old[index - 1])
    return new[index - 1] + fraction * (new[index] - new[index - 1])


class HorizontalMapPen(TransformPen):
    def __init__(self, pen, x_map, y_map):
        super().__init__(pen, (1, 0, 0, 1, 0, 0))
        self.x_map = x_map
        self.y_map = y_map
        self._transformPoint = self._transform

    def _transform(self, point):
        return self.x_map(point[0]), self.y_map(point[1])


def fit_m(sans, original, width):
    _, y0, _, y1 = original.bounds
    stem = spans(original, y0 + 24, 1)[0]
    thickness = stem[1] - stem[0]
    left = (ADVANCE - width) / 2
    centers = (left + thickness / 2, ADVANCE / 2, left + width - thickness / 2)
    old_edges = [x for pair in spans(sans, sans.bounds[1] + 24, 1) for x in pair]
    new_edges = [
        center + delta
        for center in centers
        for delta in (-thickness / 2, thickness / 2)
    ]
    outline = pathops.Path()
    sans.draw(
        HorizontalMapPen(
            outline.getPen(),
            lambda x: remap(x, old_edges, new_edges),
            lambda y: remap(y, [sans.bounds[1], sans.bounds[3]], [y0, y1]),
        )
    )
    return outline


def top_stroke(outline):
    runs = spans(outline, outline.bounds[3] - 18, 1)
    return sum(right - left for left, right in runs) / len(runs)


def fit_w(sans_at, original, width):
    _, bottom, _, top = original.bounds
    desired = top_stroke(original)
    lower, upper = 300, 600
    for _ in range(12):
        weight = (lower + upper) / 2
        reference = sans_at("w", weight)
        x0, y0, x1, y1 = reference.bounds
        sx = width / (x1 - x0)
        if top_stroke(reference) * sx < desired:
            lower = weight
        else:
            upper = weight
    sy = (top - bottom) / (y1 - y0)
    left = (ADVANCE - width) / 2
    return reference.transform(sx, 0, 0, sy, left - sx * x0, bottom - sy * y0)


def build_receivers(font, *, alternates):
    """Rebuild m/w with normal ink widths and add opt-in widths if needed."""
    sans = TTFont(ROOT / specimen_families()["sans"]["font"])

    @lru_cache(maxsize=128)
    def sans_at(letter, weight):
        return shape_from_glyphs(sans.getGlyphSet(location={"wght": weight}), letter)

    _, locations = master_locations(font)
    for letter in RECEIVERS:
        original = [
            shape_from_glyphs(font.getGlyphSet(location=location), letter)
            for location in locations
        ]
        steps = [("", 0, 0)]
        if alternates:
            steps += [
                (".heal.left", EXTRA_WIDTH[letter], -FORM_SHIFT[letter]),
                (".heal.both", EXTRA_WIDTH[letter] * 2, 0),
            ]
        for suffix, extra, translation in steps:
            paths = []
            for location, outline in zip(locations, original):
                left, _, right, _ = outline.bounds
                width = right - left + extra
                if letter == "m":
                    path = fit_m(sans_at("m", location["wght"]), outline, width)
                else:
                    path = fit_w(sans_at, outline, width)
                # The same centered intermediate outline is translated once
                # for each neighbor, with no independent width calculation.
                paths.append(path.transform(1, 0, 0, 1, translation, 0))
            from_paths(font, letter + suffix, locations, paths, ADVANCE)
        if alternates:
            compose(
                font,
                letter + ".heal.right",
                [(letter + ".heal.left", 1, 1, FORM_SHIFT[letter] * 2, 0)],
                ADVANCE,
            )
