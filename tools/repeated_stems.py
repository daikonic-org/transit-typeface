"""Fit repeated letters as variable two-character ligatures."""

from collections import defaultdict
from copy import deepcopy
from math import ceil, floor, radians, tan
import unicodedata

from fontTools.otlLib.builder import buildLigCaretList
from fontTools.varLib.builder import buildVarData
import pathops

from audit import Samples, shape_from_glyphs, spans
from font_feature_tools import add_features, compose, from_paths, inherit_pair_positioning, master_locations


def horizontal_extent(outline):
    """Measure the maximum width ink occupies at any common height."""
    pen = Samples()
    outline.draw(pen)
    rows = defaultdict(list)
    for (x0, y0), (x1, y1) in pen.lines:
        if y0 == y1:
            continue
        low, high = sorted((y0, y1))
        for row in range(floor(low / 2), ceil(high / 2)):
            y = 2 * row + 1
            if low <= y < high:
                rows[row].append(x0 + (x1 - x0) * (y - y0) / (y1 - y0))
    return max(max(xs) - min(xs) for xs in rows.values())


def pair_positions(outline, advance):
    left, _, right, _ = outline.bounds
    separation = max(advance * 0.83, min(advance, horizontal_extent(outline) + 32))
    # Stay within the pair's original outer bounds so surrounding glyphs
    # have at least the clearance they had with the separately set letters.
    start = max(0, min(advance - separation, advance - (left + right + separation) / 2))
    return start, start + separation


def pair_outline(outline, advance):
    pair = pathops.Path()
    for x in pair_positions(outline, advance):
        pair.addPath(outline.transform(1, 0, 0, 1, x, 0))
    return pair


def fit_monospace_pairs(font, extension=20):
    """Refit existing ligatures to the grid and extend their crossbar ends."""
    assert font["post"].isFixedPitch
    glyphs = font["glyf"]
    glyphset = font.getGlyphSet()
    xheight = font["OS/2"].sxHeight
    shear = tan(radians(-font["post"].italicAngle))
    probe = xheight * 0.91
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    for letter in "ft":
        name = f"{letter}_{letter}"
        assert classes[name] == 2
        left, right = spans(shape_from_glyphs(glyphset, letter), probe, 1)[0]
        ends = {left: [], right: []}
        coordinates = glyphs[letter].coordinates
        for index, (x, y) in enumerate(coordinates):
            if not xheight * 0.76 <= y <= xheight * 1.06:
                continue
            projected = x - shear * (y - probe)
            for end, points in ends.items():
                if abs(projected - end) < 2:
                    points.append(index)
        assert all(len(points) >= 2 for points in ends.values()), (letter, ends)

        deltas = {index: -extension for index in ends[left]}
        deltas.update({index: extension for index in ends[right]})
        place_monospace_pair(font, letter, name, deltas)


def place_monospace_pair(font, letter, name, deltas):
    advance = font["hmtx"][letter][0]
    glyphs = font["glyf"]
    count = len(glyphs[letter].coordinates)
    mapping = font["HVAR"].table.AdvWidthMap.mapping
    advance_index = mapping.get(name)
    parts = [(letter, 1, 1, offset, 0) for offset in (0, advance)]
    compose(font, name, parts, 2 * advance)
    pair = glyphs[name]
    for index, delta in deltas.items():
        for component in (0, count):
            i = index + component
            x, y = pair.coordinates[i]
            pair.coordinates[i] = (x + delta, y)
    pair.recalcBounds(glyphs)
    font["hmtx"][name] = (2 * advance, pair.xMin)
    if advance_index is not None:
        mapping[name] = advance_index
    font["GDEF"].table.GlyphClassDef.classDefs[name] = 2


def add_monospace_l_pair(font, extension=44):
    """Extend the opposing hooks on two l outlines positioned on the grid."""
    assert font["post"].isFixedPitch and "l_l" not in font.getGlyphOrder()
    glyphset = font.getGlyphSet()
    coordinates = font["glyf"]["l"].coordinates
    xheight = font["OS/2"].sxHeight
    probe = xheight * 0.60
    shear = tan(radians(-font["post"].italicAngle))
    projected = [x - shear * (y - probe) for x, y in coordinates]
    left, right = spans(shape_from_glyphs(glyphset, "l"), probe, 1)[0]
    upper = max(left - min(projected) - 35, 1)
    lower = max(max(projected) - right - 35, 1)
    deltas = {}
    for index, (_, y) in enumerate(coordinates):
        x = projected[index]
        if y > xheight and x < left:
            direction, distance = -1, (left - x) / upper
        elif y < xheight * 0.29 and x > right:
            direction, distance = 1, (x - right) / lower
        else:
            continue
        t = min(1, distance)
        deltas[index] = direction * round(extension * t**2 * (3 - 2 * t))
    place_monospace_pair(font, "l", "l_l", deltas)
    register_repeated_stems(
        font, {"l": "l_l"}, protect_marks=True, inherit_kerning=False
    )


def double_advance(font, source, target):
    table = font["HVAR"].table
    mapping = table.AdvWidthMap.mapping
    outer, inner = divmod(mapping[source], 1 << 16)
    store = table.VarStore
    data = store.VarData[outer]
    mapping[target] = len(store.VarData) << 16
    store.VarData.append(
        buildVarData(data.VarRegionIndex, [[2 * delta for delta in data.Item[inner]]])
    )
    store.VarDataCount = len(store.VarData)


def add_repeated_stems(font):
    _, locations = master_locations(font)
    glyphsets = [font.getGlyphSet(location=loc) for loc in locations]
    aliases = {letter: f"{letter}_{letter}" for letter in "ft"}
    for letter, name in aliases.items():
        assert name not in font.getGlyphOrder(), name
        advance = font["hmtx"][letter][0]
        paths = [pair_outline(shape_from_glyphs(gs, letter), gs[letter].width) for gs in glyphsets]
        from_paths(font, name, locations, paths, 2 * advance)
        double_advance(font, letter, name)
        font["GDEF"].table.GlyphClassDef.classDefs[name] = 2
    register_repeated_stems(font, aliases)


def register_repeated_stems(font, aliases, *, protect_marks=False, inherit_kerning=True):
    carets = {name: [font["hmtx"][letter][0]] for letter, name in aliases.items()}
    gdef = font["GDEF"].table
    extra = buildLigCaretList(carets, {}, font.getReverseGlyphMap())
    current = gdef.LigCaretList or extra
    records = dict(zip(current.Coverage.glyphs, current.LigGlyph))
    records.update(zip(extra.Coverage.glyphs, extra.LigGlyph))
    coverage = sorted(records, key=font.getGlyphID)
    current.Coverage.glyphs = coverage
    current.LigGlyph = [records[n] for n in coverage]
    current.LigGlyphCount = len(coverage)
    gdef.LigCaretList = current
    if inherit_kerning:
        inherit_pair_positioning(font, aliases)
    rules = "\n".join(f"sub {letter} {letter} by {name};" for letter, name in aliases.items())
    definitions = ""
    if protect_marks:
        marks = {name for name, cls in gdef.GlyphClassDef.classDefs.items() if cls == 3}
        marks.update(
            name
            for cp, name in font.getBestCmap().items()
            if unicodedata.category(chr(cp)).startswith("M")
        )
        definitions = f"""
            @RepeatedStemMarks = [{' '.join(sorted(marks))}];
            lookup JoinRepeatedStems {{ {rules} }} JoinRepeatedStems;
        """
        rules = "\n".join(
            f"ignore sub {letter}' {letter}' @RepeatedStemMarks;\n"
            f"sub {letter}' lookup JoinRepeatedStems {letter}';"
            for letter in aliases
        )
    add_features(font, f"""
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        {definitions}
        feature liga {{ {rules} }} liga;
    """)
