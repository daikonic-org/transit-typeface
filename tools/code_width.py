"""Restore the Code width axis without disconnecting shared arrow components."""

from fontTools.misc.roundTools import otRound
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables import otTables

from font_feature_tools import append_glyph
from sans_baseline_trial import build_variations
from system_italic import designspace
from system_width import scale_layout
from transit_width_trial import add_width
from code_weight_width_trial import WIDTH_PRESETS


def normalize_component_matrices(font):
    """Create shared transformed donors when the matrix couples x and y."""
    locations, model, default = designspace(font)
    masters = [font.getGlyphSet(location=location) for location in locations]
    glyf = font["glyf"]
    names = {}
    for parent in font.getGlyphOrder():
        glyph = glyf[parent]
        if not glyph.isComposite():
            continue
        for part in glyph.components:
            donor, matrix = part.getComponentInfo()
            if matrix[1:3] == (0, 0):
                continue
            key = (donor, matrix[:4])
            if key not in names:
                forms = []
                for glyphs in masters:
                    recorded = DecomposingRecordingPen(glyphs)
                    glyphs[donor].draw(recorded)
                    pen = TTGlyphPen(None)
                    recorded.replay(TransformPen(pen, (*matrix[:4], 0, 0)))
                    forms.append(pen.glyph())
                drawing = forms[default]
                assert all(g.flags == drawing.flags and g.endPtsOfContours == drawing.endPtsOfContours
                           for g in forms), key
                name = f"{donor}.axisTransform{len(names)}"
                points = [form.coordinates for form in forms]
                append_glyph(font, name, drawing, build_variations(model, points), 0)
                names[key] = name
            part.glyphName = names[key]
            del part.transform
        glyph.recalcBounds(glyf)
        advance, _ = font["hmtx"][parent]
        font["hmtx"][parent] = advance, glyph.xMin
    return list(names.values())


def add_code_width(font, cell):
    components = normalize_component_matrices(font)
    grids = {name: advance // cell for name, (advance, _) in font["hmtx"].metrics.items()
             if advance > 0 and advance % cell == 0}
    add_width(font, grids=grids, scale_layout=scale_layout)
    stat = font["STAT"].table
    for width, name in WIDTH_PRESETS.items():
        value = otTables.AxisValue()
        value.Format = 1
        value.AxisIndex = stat.DesignAxisCount - 1
        value.Flags = 2 if width == 100 else 0
        value.Value = width
        value.ValueNameID = font["name"].addName(name or "Normal")
        stat.AxisValueArray.AxisValue.append(value)
    stat.AxisValueCount = len(stat.AxisValueArray.AxisValue)
    return components


def verify_width(font, cell):
    thresholds = {
        "wght": (350, 400, 500), "wdth": (94, 100, 108),
    }
    assert {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes} == thresholds
    for weight in (350, 375, 400, 450, 500):
        for width in (94, 97, 100, 104, 108):
            location = {"wght": weight, "wdth": width}
            glyphs = font.getGlyphSet(location=location)
            for name, (advance, _) in font["hmtx"].metrics.items():
                if advance % cell == 0:
                    assert otRound(glyphs[name].width) == advance // cell * cell * width / 100, (
                        name, location, glyphs[name].width)
    return {str(width): cell * width // 100 for width in thresholds["wdth"]}
