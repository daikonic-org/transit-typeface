"""Fit repeated f and t strokes as variable two-character ligatures."""

from collections import defaultdict
from copy import deepcopy
from math import ceil, floor

from fontTools.otlLib.builder import buildLigCaretList
from fontTools.varLib.builder import buildVarData
import pathops

from audit import Samples, shape_from_glyphs
from font_feature_tools import add_features, from_paths, master_locations


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


def pair_outline(outline, advance):
    left, _, right, _ = outline.bounds
    separation = max(advance * 0.83, min(advance, horizontal_extent(outline) + 32))
    # Stay within the pair's original outer bounds so surrounding glyphs
    # have at least the clearance they had with the separately set letters.
    start = max(0, min(advance - separation, advance - (left + right + separation) / 2))
    pair = pathops.Path()
    for x in (start, start + separation):
        pair.addPath(outline.transform(1, 0, 0, 1, x, 0))
    return pair


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


def inherit_pair_positioning(font, aliases):
    """Use the boundary letters' positioning on either side of the ligature."""
    sort = font.getGlyphID
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for wrapped in lookup.SubTable:
            table = getattr(wrapped, "ExtSubTable", wrapped)
            if not hasattr(table, "ValueFormat2"):
                continue
            if table.Format == 1:
                records = dict(zip(table.Coverage.glyphs, table.PairSet))
                for pair_set in records.values():
                    additions = []
                    for record in pair_set.PairValueRecord:
                        if record.SecondGlyph in aliases:
                            added = deepcopy(record)
                            added.SecondGlyph = aliases[record.SecondGlyph]
                            additions.append(added)
                    pair_set.PairValueRecord.extend(additions)
                    pair_set.PairValueRecord.sort(key=lambda record: sort(record.SecondGlyph))
                    pair_set.PairValueCount = len(pair_set.PairValueRecord)
                records.update({alias: records[base] for base, alias in aliases.items() if base in records})
                table.Coverage.glyphs = sorted(records, key=sort)
                table.PairSet = [records[n] for n in table.Coverage.glyphs]
                table.PairSetCount = len(table.PairSet)
            elif table.Format == 2:
                for classes in (table.ClassDef1, table.ClassDef2):
                    classes.classDefs.update({alias: classes.classDefs[base] for base, alias in aliases.items() if base in classes.classDefs})
                table.Coverage.glyphs = sorted(
                    set(table.Coverage.glyphs) | {aliases[n] for n in table.Coverage.glyphs if n in aliases}, key=sort,
                )


def add_repeated_stems(font):
    _, locations = master_locations(font)
    glyphsets = [font.getGlyphSet(location=loc) for loc in locations]
    carets = {}
    for letter in "ft":
        name = letter + "_" + letter
        assert name not in font.getGlyphOrder(), name
        advance = font["hmtx"][letter][0]
        paths = [pair_outline(shape_from_glyphs(gs, letter), gs[letter].width) for gs in glyphsets]
        from_paths(font, name, locations, paths, 2 * advance)
        double_advance(font, letter, name)
        font["GDEF"].table.GlyphClassDef.classDefs[name] = 2
        carets[name] = [advance]

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
    inherit_pair_positioning(font, {"f": "f_f", "t": "t_t"})
    add_features(font, """
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        feature liga {
            sub f f by f_f;
            sub t t by t_t;
        } liga;
    """)
