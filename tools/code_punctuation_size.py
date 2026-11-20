"""Proof larger Transit Code punctuation while retaining its variable layout."""

import argparse
from itertools import product
from pathlib import Path

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.models import VariationModel, supportScalar

from code_glyph_names import FAMILY as SOURCE_FAMILY, add_unicode_symbols, glyph_names
from code_hairline_study import COMPACT, LEADERS, MARKER
from code_weight_width_trial import WEIGHTS, build_static, name_trial, recalibrate, sanitize
from dot_palette import indices
from font_feature_tools import expanded_variations

FAMILY = "Daikonic Transit Code Punctuation Trial"
DOTS = {
    "period": (1.12, 1.12, 0),
    "ellipsis": (1.04, 1.14, 0),
    "period_period_period.liga": (1.12, 1.12, 0),
    "colon": (1.12, 1.12, None),
    "colon_colon.liga": (1.12, 1.12, None),
    "colon_colon.liga.hairline": (1.12, 1.12, None),
    "periodcentered": (1.12, 1.12, None),
    "periodcentered.loclCAT": (1.12, 1.12, None),
    "periodcentered.loclCAT.case": (1.12, 1.12, None),
    "period_period.liga": (1.12, 1.12, None),
    "period_equal.liga": (1.12, 1.12, None),
    "period_period_equal.liga": (1.12, 1.12, None),
    "colon_equal.liga": (1.12, 1.12, None),
}
COMMA_FORMS = ("comma", "semicolon")
TILDES = ("asciitilde", "equal_equal.liga.loose", "exclam_equal.liga.loose")
UPRIGHT_MARKS = ("exclam", "question", "exclamdbl", "uni2047", "uni2048", "uni2049")
QUOTES = ("quotesingle", "quotedbl", "quoteleft", "quoteright",
          "quotedblleft", "quotedblright", "quotesinglbase", "quotedblbase")


def get_transforms(font, name):
    glyph = font["glyf"][name]
    points = list(range(len(glyph.coordinates)))
    if name in (MARKER, COMPACT):
        hook = [i for i in points if glyph.coordinates[i][1] <= 564]
        return [(hook, 1, 1.55, 1)]
    if name in LEADERS:
        bottom = min(y for x, y in glyph.coordinates if x >= 600)
        rail = [i for i in points if glyph.coordinates[i][1] == bottom
                and glyph.coordinates[i][0] >= 600]
        diamond = [i for i in points if glyph.coordinates[i][1] < bottom]
        return [(diamond, 1, 1.35, rail)]
    if name in QUOTES:
        height = 1.42 if name in ("quotesingle", "quotedbl") else 1.37
        return [(points, 1.12, height, 1)]
    if name == "asciicircum":
        return [(points, 1, 1.50, 0)]
    if name == "asciitilde":
        return [(points, 1.30, 1.27, None)]
    if name in TILDES:
        start = 0
        contours = []
        for end in glyph.endPtsOfContours:
            contours.append(list(range(start, end + 1)))
            start = end + 1
        wave = max(contours, key=lambda contour: min(glyph.coordinates[i][1] for i in contour))
        return [(wave, 1.30, 1.27, 0)]
    groups = indices(font, name)
    if name in COMMA_FORMS:
        dot_points = {i for group in groups for i in group}
        tail = [i for i in points if i not in dot_points]
        return [(tail, 1, 1.18, 1)] + [(group, 1.12, 1.12, None) for group in groups]
    if name in ("exclam_period.liga", "question_period.liga"):
        terminal = max(groups, key=lambda group: min(glyph.coordinates[i][0] for i in group))
        return [(group, 1.12, 1.12, 0 if group == terminal else 1) for group in groups]
    factors = DOTS.get(name, (1.12, 1.12, 0 if name.endswith("down") else 1))
    return [(group, *factors) for group in groups]


def center_in_cell(coords, variations, advance):
    axes = ("wght", "wdth")
    locations = [{k: v for k, v in zip(axes, values) if v}
                 for values in product((-1, 0, 1), repeat=len(axes))]
    model = VariationModel(locations, axisOrder=axes)
    shifts = []
    for location in locations:
        xs = [x for x, _ in coords]
        width = advance
        for support, deltas in variations.items():
            scalar = supportScalar(location, dict(support))
            if scalar:
                xs = [x + dx * scalar for x, (dx, _) in zip(xs, deltas)]
                width += (deltas[-3][0] - deltas[-4][0]) * scalar
        shifts.append((width - min(xs) - max(xs)) / 2)

    for support, shift in zip(model.supports, model.getDeltas(shifts)):
        shift = otRound(shift)
        if not support:
            for i, (x, y) in enumerate(coords):
                coords[i] = (x + shift, y)
        elif shift:
            key = tuple(sorted(support.items()))
            deltas = variations.setdefault(key, [(0, 0)] * (len(coords) + 4))
            for i, (x, y) in enumerate(deltas[:-4]):
                deltas[i] = (x + shift, y)


def transform_glyph(font, name, transforms):
    glyph = font["glyf"][name]
    old_x_min = glyph.xMin
    base = list(glyph.coordinates)
    variations = expanded_variations(font, name)

    def extremes(group, axis, edge=None):
        values = [base[i][axis] for i in group]
        bounds = (min(values), max(values))
        return [i for i in group if base[i][axis] in (bounds if edge is None else (bounds[edge],))]

    for group, scale_x, scale_y, edge_y in transforms:
        vertical_anchors = edge_y if isinstance(edge_y, list) else extremes(group, 1, edge_y)
        anchors = (extremes(group, 0), vertical_anchors)
        for coordinates in (glyph.coordinates, *variations.values()):
            center = [sum(coordinates[i][axis] for i in anchors[axis]) / len(anchors[axis])
                      for axis in (0, 1)]
            for i in group:
                x, y = coordinates[i]
                coordinates[i] = (otRound(center[0] + (x - center[0]) * scale_x),
                                  otRound(center[1] + (y - center[1]) * scale_y))

    advance, bearing = font["hmtx"][name]
    if name in COMMA_FORMS:
        center_in_cell(glyph.coordinates, variations, advance)
    glyph.recalcBounds(font["glyf"])
    font["hmtx"][name] = (advance, bearing + glyph.xMin - old_x_min)
    font["gvar"].variations[name] = [
        TupleVariation(dict(support), deltas) for support, deltas in variations.items()
    ]


def refine(font):
    selected = [
        *DOTS, *UPRIGHT_MARKS, "exclamdown", "questiondown",
        "exclam_period.liga", "question_period.liga", *QUOTES, *COMMA_FORMS, *TILDES, "asciicircum", MARKER, COMPACT, *LEADERS,
    ]
    changed = []
    for name in selected:
        if name in font.getGlyphOrder():
            transforms = get_transforms(font, name)
            if transforms:
                transform_glyph(font, name, transforms)
                changed.append(name)
    return changed


def release_font(source, family, version):
    from adopt_weighting import stamp
    from io import BytesIO

    font = TTFont(source, recalcTimestamp=False)
    rename = glyph_names(font)
    add_unicode_symbols(font)
    recalibrate(font, family)
    font["post"].mapping.update(rename)
    intermediate = BytesIO()
    font.save(intermediate)
    intermediate.seek(0)
    released = TTFont(intermediate, recalcTimestamp=False)
    refine(released)
    stamp(released, released["name"].getDebugName(5).removeprefix("Version "), version)
    return released


def build(source, output):
    font = TTFont(source, recalcTimestamp=False)
    changed = refine(font)
    for instance in font["fvar"].instances:
        style = font["name"].getDebugName(instance.subfamilyNameID).replace(" ", "")
        instance.postscriptNameID = font["name"].addName(FAMILY.replace(" ", "") + "-" + style)
    stem = name_trial(font, FAMILY, variable=True)
    path = output / "VF" / f"{stem}.ttf"
    font.save(path)
    sanitize(path)

    original, candidate = TTFont(source), TTFont(path)
    assert original.getGlyphOrder() == candidate.getGlyphOrder()
    for tag in ("GSUB", "GPOS", "GDEF", "HVAR", "cmap", "STAT"):
        assert original.getTableData(tag) == candidate.getTableData(tag), tag
    assert all(original["hmtx"][name][0] == candidate["hmtx"][name][0]
               for name in original.getGlyphOrder())
    assert all(original["glyf"][name].compile(original["glyf"]) ==
               candidate["glyf"][name].compile(candidate["glyf"])
               for name in original.getGlyphOrder() if name not in changed)
    candidate.flavor = "woff2"
    web = output / "WOFF2" / f"{stem}.woff2"
    candidate.save(web)
    sanitize(web)
    print(path, len(changed), "punctuation glyphs", flush=True)
    return path



def proof_release(directory, config):
    from italic_texture_proofs import BG, CREAM, MUTED, export, label, rect
    from specimens import Panel

    width, height = 980, 435
    body = [rect(0, 0, width, height, BG),
            label("Daikonic Transit Code punctuation", 28, 43, 26, bold=True)]
    samples = [
        "a,b  a;b   x:y   path::item",
        "wait…  wait...  0..10  0..=10",
        "let s = 'x';  let text = “it’s fine”;",
        "let mask = ~bits ^ flag;",
        "fn read<'a>(x: &'a str) -> &'a str",
        "items::<'static, '_>()",
        "≤ ≥ ≠   a <= b   b != c",
    ]
    for x, weight in ((28, 350), (509, 400)):
        body.append(label(WEIGHTS[weight], x, 83, 16, MUTED, bold=True))
        panel = Panel("punctuation-" + str(weight), config)
        panel.text(".,;:…   ~ ^   ' \" ‘ ’ “ ”", x, 147, 33, weight, CREAM, max_width=433)
        for y, text in enumerate(samples, start=7):
            panel.text(text, x, y * 27, 17, weight, CREAM)
        body.append(panel.body())
    export(directory / "Code-Punctuation.svg", body, width, height)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="directory containing the Code glyph-naming variable fonts")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    for directory in ("VF", "WOFF2", "TTF", "TTC"):
        (args.output / directory).mkdir(parents=True, exist_ok=True)
    stem = SOURCE_FAMILY.replace(" ", "")
    paths = [
        build(args.source / f"{stem}{suffix}.ttf", args.output)
        for suffix in ("-VF", "-Italic-VF")
    ]
    build_static(paths, args.output, FAMILY.replace(" Trial", " Presets"), WEIGHTS)


if __name__ == "__main__":
    main()
