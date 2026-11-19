"""Build 9-degree variable italic candidates from the selected Transit fonts."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

from code_receiver_shapes import build_receivers
from font_feature_tools import add_features, expanded_variations
from italic_letterforms import redraw_italic_letters
from specimens import ROOT, specimen_families

ANGLE = 9
SHEAR = math.tan(math.radians(ANGLE))
CODE_FIT = dict.fromkeys(("A", "H", "N", "X", "Z", "x"), 14)


def contours(glyph):
    start = 0
    for end in glyph.endPtsOfContours:
        yield range(start, end + 1)
        start = end + 1


def shaped_copy(font, target, source, indices, transform):
    """Transform compatible points and their variation deltas, retaining metrics."""
    source_glyph = font["glyf"][source]
    target_glyph = font["glyf"][target]
    glyph = deepcopy(source_glyph)
    base = list(source_glyph.coordinates)
    source_deltas = expanded_variations(font, source)
    metric_deltas = expanded_variations(font, target)
    glyph.coordinates = GlyphCoordinates(
        [tuple(map(otRound, transform(i, *base[i]))) for i in indices]
    )
    glyph.flags = bytearray(source_glyph.flags[i] & ~0x40 for i in indices)
    if any(source_glyph.flags[i] & 0x40 for i in indices):
        glyph.flags[0] |= 0x40
    ends = set(source_glyph.endPtsOfContours)
    glyph.endPtsOfContours = [j for j, i in enumerate(indices) if i in ends]
    glyph.numberOfContours = len(glyph.endPtsOfContours)
    variations = {}
    for key in source_deltas.keys() | metric_deltas.keys():
        geometry = source_deltas.get(key)
        metric = metric_deltas.get(key)
        deltas = []
        for j, i in enumerate(indices):
            x, y = base[i]
            dx, dy = geometry[i] if geometry is not None else (0, 0)
            actual = transform(i, x + dx, y + dy)
            x0, y0 = glyph.coordinates[j]
            deltas.append((otRound(actual[0]) - x0, otRound(actual[1]) - y0))
        deltas.extend(metric[-4:] if metric is not None else [(0, 0)] * 4)
        variations[key] = deltas
    return glyph, variations


def apply_shape(font, name, glyph, variations):
    font["glyf"][name] = glyph
    glyph.recalcBounds(font["glyf"])
    font["gvar"].variations[name] = [
        TupleVariation(dict(key), variations[key]) for key in sorted(variations)
    ]
    font["hmtx"][name] = (font["hmtx"][name][0], glyph.xMin)


def italicize_anchors(font, selected, pivot, fit, metric_sources):
    def move(anchors, name):
        if name in selected:
            for anchor in anchors:
                if anchor is not None:
                    anchor.XCoordinate += otRound(
                        SHEAR * (anchor.YCoordinate - pivot)
                    ) + fit.get(name, 0)

    for lookup in font["GPOS"].table.LookupList.Lookup:
        for table in lookup.SubTable:
            table = getattr(table, "ExtSubTable", table)
            if hasattr(table, "MarkArray"):
                for name, record in zip(
                    table.MarkCoverage.glyphs, table.MarkArray.MarkRecord
                ):
                    move([record.MarkAnchor], name)
            if hasattr(table, "BaseArray"):
                records = dict(zip(table.BaseCoverage.glyphs, table.BaseArray.BaseRecord))
                for name, source in metric_sources.items():
                    if name in records and source in records:
                        records[name].BaseAnchor = deepcopy(records[source].BaseAnchor)
                for name, record in records.items():
                    move(record.BaseAnchor, name)
            if hasattr(table, "LigatureArray"):
                for name, record in zip(
                    table.LigatureCoverage.glyphs, table.LigatureArray.LigatureAttach
                ):
                    move(
                        (
                            anchor
                            for part in record.ComponentRecord
                            for anchor in part.LigatureAnchor
                        ),
                        name,
                    )
            if hasattr(table, "Mark1Array"):
                for name, record in zip(
                    table.Mark1Coverage.glyphs, table.Mark1Array.MarkRecord
                ):
                    move([record.MarkAnchor], name)
                for name, record in zip(
                    table.Mark2Coverage.glyphs, table.Mark2Array.Mark2Record
                ):
                    move(record.Mark2Anchor, name)


def set_style(font, config):
    family = config["name"]
    stem = config["stem"]
    style = {
        1: family,
        2: "Italic",
        3: stem + "-Italic-VF " + config["version"],
        4: family + " Italic",
        6: stem + "-Italic-VF",
        16: family,
        17: "Italic",
        25: stem + "Italic",
    }
    names = font["name"]
    for record in names.names:
        if record.nameID in style:
            record.string = style[record.nameID].encode(record.getEncoding())
    for instance in font["fvar"].instances:
        label = names.getDebugName(instance.subfamilyNameID)
        if not label.endswith(" Italic"):
            instance.subfamilyNameID = names.addName(label + " Italic")
        instance.postscriptNameID = names.addName(
            stem + "-" + label.replace(" ", "") + "Italic"
        )
    stat = font["STAT"].table
    axis = otTables.AxisRecord()
    axis.AxisTag, axis.AxisNameID, axis.AxisOrdering = (
        "ital",
        names.addName("Italic"),
        stat.DesignAxisCount,
    )
    stat.DesignAxisRecord.Axis.append(axis)
    stat.DesignAxisCount += 1
    value = otTables.AxisValue()
    value.Format, value.AxisIndex, value.Flags, value.ValueNameID, value.Value = (
        1,
        axis.AxisOrdering,
        0,
        names.addName("Italic"),
        1,
    )
    stat.AxisValueArray.AxisValue.append(value)
    stat.AxisValueCount += 1
    font["post"].italicAngle = -ANGLE
    font["head"].macStyle |= 2
    font["OS/2"].fsSelection = (font["OS/2"].fsSelection | 1) & ~64


def build(key, config, output, g_source=None, *, descending_f=False):
    original = ROOT / config["font"]
    font = TTFont(original, recalcTimestamp=False)
    cmap = font.getBestCmap()
    glyphs = font["glyf"]
    marks = {
        n for n, cls in font["GDEF"].table.GlyphClassDef.classDefs.items() if cls == 3
    }
    selected = (
        set(glyphs.keys())
        if key != "code"
        else {name for cp, name in cmap.items() if chr(cp).isalpha()}
        | marks
        | {"fi", "fl", "dotlessi", "dotlessj"}
    )
    if key == "code":
        build_receivers(font, alternates=False)

    metric_sources = {}
    if g_source:
        redrawn, metric_sources = redraw_italic_letters(
            font, g_source, family=key, descending_f=descending_f
        )
        selected.update(redrawn)

    pivot = font["OS/2"].sxHeight / 2
    # Shift only the handful of Code letters that collide with the upright
    # ampersand at Regular. Leave their advances and the ampersand unchanged.
    fit = CODE_FIT if key == "code" else {}
    for name in font.getGlyphOrder():
        glyph = glyphs[name]
        if name not in selected or glyph.numberOfContours <= 0:
            continue
        top = font["OS/2"].sxHeight
        dots = {
            i
            for contour in contours(glyph)
            if name == "i" and min(glyph.coordinates[i][1] for i in contour) > top + 30
            for i in contour
        }
        dot_center = (glyph.yMax + top + 30) / 2

        def transform(i, x, y):
            return (
                x
                + SHEAR * ((dot_center if i in dots else y) - pivot)
                + fit.get(name, 0),
                y,
            )

        new, variations = shaped_copy(
            font, name, name, range(len(glyph.coordinates)), transform
        )
        apply_shape(font, name, new, variations)
    italicize_anchors(font, selected, pivot, fit, metric_sources)
    if key == "code":
        has_descender = descending_f or g_source in ("a", "q", "refined")
        f_clearance = "pos at f' <24 0 0 0>;" if has_descender else ""
        # A gapless underscore takes the full cell at the baseline. Leave
        # overhang enabled elsewhere and offset these neighbors only here.
        add_features(
            font,
            f"""
            languagesystem DFLT dflt;
            languagesystem latn dflt;
            feature kern {{
                {f_clearance}
                pos underscore [m D M]' <20 0 0 0>;
                pos underscore [p x A H K N X]' <8 0 0 0>;
                pos underscore Z' <6 0 0 0>;
            }} kern;
        """,
        )
    elif g_source == "refined" or descending_f:
        add_features(
            font,
            """
            languagesystem DFLT dflt;
            languagesystem latn dflt;
            feature kern {
                pos g [fi fl] 40;
                pos underscore [fi fl] 52;
                pos [parenleft bracketleft braceleft] [fi fl] 24;
                lookup BracketF {
                    pos [bracketleft braceleft] f 24;
                } BracketF;
            } kern;
            """,
        )
    set_style(font, config)
    output.mkdir(parents=True, exist_ok=True)
    target = output / (config["stem"] + "-Italic-VF.ttf")
    font.save(target)
    actual = TTFont(target)
    baseline = TTFont(original)
    assert actual.getGlyphOrder() == baseline.getGlyphOrder()
    assert actual.getBestCmap() == baseline.getBestCmap()
    if not g_source or key != "sans":
        assert actual.getTableData("GSUB") == baseline.getTableData("GSUB")
    for loc in [i.coordinates for i in actual["fvar"].instances]:
        a = actual.getGlyphSet(location=loc)
        b = baseline.getGlyphSet(location=loc)
        assert all(
            abs(a[n].width - b[metric_sources.get(n, n)].width) < 0.01
            for n in actual.getGlyphOrder()
        )
    assert all(
        actual["hmtx"][n][0] == baseline["hmtx"][metric_sources.get(n, n)][0]
        for n in actual.getGlyphOrder()
    )
    print(f"{key}: {target.name}, {len(selected)} italicized outlines", flush=True)
    return {
        "font": target.name,
        "sha256": sha256(target.read_bytes()).hexdigest(),
        "source": config["font"],
        "source_sha256": sha256(original.read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--g-source", choices=("a", "q", "refined", "johnston", "cursive"))
    parser.add_argument("--descending-f", action="store_true")
    args = parser.parse_args()
    g_source = args.g_source or ("johnston" if args.descending_f else None)
    report = {
        key: build(key, config, args.output, g_source, descending_f=args.descending_f)
        for key, config in specimen_families().items()
    }
    (args.output / "italic-build.json").write_text(
        json.dumps(
            {
                "angle": ANGLE,
                "g_source": g_source,
                "descending_f": args.descending_f,
                "families": report,
            },
            indent=2,
        )
        + "\n"
    )
