"""Build composed Code drawings from the completed foundation masters."""

from fontTools.misc.roundTools import otRound
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_l_y_f import OVERLAP_COMPOUND
import pathops

from audit import shape_from_glyphs


SYMBOLS = {
    0x2200: "universal", 0x2203: "existential", 0x00AC: "logicalnot",
    0x2260: "notequal", 0x2264: "lessequal", 0x2265: "greaterequal",
}


def polygon(points):
    path = pathops.Path()
    pen = path.getPen()
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()
    return path


def shoulder(n, cut, cell):
    """Keep the stem and shoulder of n, trimming only the right leg."""
    _, bottom, right, _ = n.bounds
    split = cell / 2
    cutter = polygon(((split, bottom - 1), (split, cut), (right + 1, cut), (right + 1, bottom - 1)))
    return pathops.op(n, cutter, pathops.PathOp.DIFFERENCE, fix_winding=True, clockwise=True)


def equal_bars(equal):
    lower, upper = sorted((contour.bounds for contour in equal.contours), key=lambda box: box[1])
    return lower, upper


def logical_not(equal):
    lower, upper = equal_bars(equal)
    left, bar_bottom, right, top = upper
    bottom = lower[1]
    hook = right - (top - bar_bottom)
    return polygon(((left, top), (right, top), (right, bottom), (hook, bottom),
                    (hook, bar_bottom), (left, bar_bottom)))


def less_equal(angle, equal):
    """Use the angle's rise and the equals' bar weight and spacing."""
    lower, upper = equal_bars(equal)
    left, bar_bottom, right, bar_top = upper
    thickness = bar_top - bar_bottom
    half_bar = thickness / 2
    spacing = (bar_bottom + bar_top - lower[1] - lower[3]) / 2
    mid = (bar_top + lower[1] + spacing) / 2
    rise = (angle.bounds[3] - angle.bounds[1]) / 2
    tip = thickness / 4
    inset = (right - left) * (half_bar + tip) / (rise + tip)
    path = polygon((
        (left, mid + tip), (right, mid + rise + half_bar),
        (right, mid + rise - half_bar), (left + inset, mid),
        (right, mid - rise + half_bar), (right, mid - rise - half_bar), (left, mid - tip),
    ))
    rule_y = mid - spacing
    rule_rise = rise + tip
    path.addPath(polygon((
        (left, rule_y + half_bar), (right, rule_y - rule_rise + half_bar),
        (right, rule_y - rule_rise - half_bar), (left, rule_y - half_bar),
    )))
    return path


def install(font, name, pen, advance):
    glyf = font["glyf"]
    if name not in glyf:
        font.setGlyphOrder(font.getGlyphOrder() + [name])
        font["GDEF"].table.GlyphClassDef.classDefs[name] = 1
    glyph = pen.glyph()
    glyf[name] = glyph
    glyph.recalcBounds(glyf)
    font["hmtx"][name] = advance, glyph.xMin
    return glyph


def install_outline(font, name, shape, advance):
    pen = TTGlyphPen(None)
    shape.draw(pen)
    install(font, name, pen, advance)


def install_components(font, name, parts, advance):
    pen = TTGlyphPen(font.getGlyphSet())
    for donor, transform in parts:
        pen.addComponent(donor, transform)
    glyph = install(font, name, pen, advance)
    if len(parts) > 1:
        glyph.components[0].flags |= OVERLAP_COMPOUND


def build_composed(font, recipe):
    """Construct each review glyph before variable compilation."""
    metrics = font["OS/2"]
    baseline = recipe["alphabet_review"]["baseline"]
    cell = recipe["alphabet_review"]["cell"]
    glyphs = font.getGlyphSet()
    n, equal, angle, slash = (shape_from_glyphs(glyphs, name) for name in ("n", "equal", "less", "slash"))

    r_recipe = recipe["constructed_forms"]["r"]
    cut = otRound(baseline + (metrics.sxHeight - baseline) * r_recipe["cut_at_x_height"])
    install_outline(font, "r", shoulder(n, cut, cell), cell)
    for name in font.getGlyphOrder():
        glyph = font["glyf"][name]
        if glyph.isComposite() and any(part.glyphName == "r" for part in glyph.components):
            glyph.recalcBounds(font["glyf"])
            advance, _ = font["hmtx"][name]
            font["hmtx"][name] = advance, glyph.xMin

    reflected = (-1, 0, 0, 1, cell, 0)
    install_components(font, "universal", [("A", (-1, 0, 0, -1, cell, metrics.sCapHeight + baseline))], cell)
    install_components(font, "existential", [("E", reflected)], cell)
    install_outline(font, "logicalnot", logical_not(equal), cell)

    # Use a fixed scale so the component relationship survives interpolation.
    # The slash keeps its horizontal weight and is centered on the bars.
    slash_scale = 9 / 16
    l, b, r, t = slash.bounds
    equal_center_y = (equal.bounds[1] + equal.bounds[3]) / 2
    sx, sy = otRound((cell - l - r) / 2), otRound(equal_center_y - (b + t) / 2 * slash_scale)
    install_components(font, "notequal", [
        ("equal", (1, 0, 0, 1, 0, 0)),
        ("slash", (1, 0, 0, slash_scale, sx, sy)),
    ], cell)
    install_outline(font, "lessequal", less_equal(angle, equal), cell)
    install_components(font, "greaterequal", [("lessequal", reflected)], cell)

    for table in font["cmap"].tables:
        if table.isUnicode() and table.format in (4, 12):
            table.cmap.update(SYMBOLS)
    metrics.recalcUnicodeRanges(font)
