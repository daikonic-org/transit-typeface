"""Build and proof System’s upright lowercase on the rebuilt Sans curves."""

from argparse import ArgumentParser
from collections import defaultdict
from copy import deepcopy
import json
from math import cos, radians
from pathlib import Path
from string import ascii_lowercase
from unicodedata import normalize

from fontTools.misc.bezierTools import splitQuadratic
from fontTools.misc.roundTools import otRound
from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.varLib.models import VariationModel
import uharfbuzz as hb

from audit import Samples, shape_from_glyphs, spans
from bundle_release import sanitize
from code_weight_width_trial import name_trial
from font_feature_tools import append_glyph, expanded_variations, master_locations
from italic_returns import raw_outline, segments as outline_segments
from kern_clearance import repair_kerning
from sans_baseline_trial import build_variations, clear_hints
from sans_direct_weight import direct_points
from sans_sparse_outline_trial import UPSTREAM, segments as stored_segments
from scaling_study import vertical_stem
from system_accents import install_masters, rebuild_accents
from system_proportions import enlarge_lowercase


FAMILY = "Daikonic Transit System Curve Review"
DOT = "diamond.dot.system"
LETTERS = ascii_lowercase + "ıȷ"
WEIGHTS = (300, 350, 400, 500, 600)


CUT = -80


def donor_hook(upstream, scale):
    """Keep the original quadratic hook segments between two cuts at the same height."""
    outline = raw_outline(upstream.getGlyphSet(), "y").transform(scale, 0, 0, scale, 0, 0)
    edges = outline_segments(next(iter(outline.contours)))
    clipped = []
    for edge in edges:
        if min(edge.start[1], edge.end[1]) < CUT < max(edge.start[1], edge.end[1]):
            if edge.controls:
                clipped.extend(splitQuadratic(edge.start, *edge.controls, edge.end, CUT, True))
            else:
                a, b = edge.start, edge.end
                t = (CUT - a[1]) / (b[1] - a[1])
                cut = (a[0] + (b[0] - a[0]) * t, CUT)
                clipped.extend(((a, cut), (cut, b)))
        else:
            clipped.append((edge.start, *edge.controls, edge.end))
    enter = next(i for i, e in enumerate(clipped) if abs(e[0][1] - CUT) < 0.001 and e[-1][1] < CUT)
    leave = next(i for i, e in enumerate(clipped) if e[0][1] < CUT and abs(e[-1][1] - CUT) < 0.001)
    rotated = clipped[enter:] + clipped[:enter]
    return rotated[:(leave - enter) % len(clipped) + 1]


def rails(reference, xheight):
    """Read the four straight diagonals of the approved Regular C design."""
    probe = Samples()
    reference.draw(probe)
    a, b = 0.54 * xheight, 0.88 * xheight
    prior = [v for span in probe.spans(a, 1) for v in span]
    later = [v for span in probe.spans(b, 1) for v in span]
    assert len(prior) == len(later) == 4
    slopes = [(right - left) / (b - a) for left, right in zip(prior, later)]
    intercepts = [x - a * slope for x, slope in zip(prior, slopes)]
    tips = [(intercept + slope * xheight, xheight)
            for intercept, slope in zip(intercepts, slopes)]
    yl, yr = slopes[1:3]
    x1, x2 = intercepts[1:3]
    fork = (x1 - x2) / (yr - yl)
    return slopes, intercepts, tips, (x1 + yl * fork, fork)


def bridge(pen, start, slope, end, end_slope):
    distance = (end[1] - start[1]) / 3
    pen.curveTo((start[0] + distance * slope, start[1] + distance),
                (end[0] - distance * end_slope, end[1] - distance), end)


def derivative(a, b):
    return (b[0] - a[0]) / (b[1] - a[1])


def regular_y(font, upstream):
    xheight = font["OS/2"].sxHeight
    gs = font.getGlyphSet(location={"wght": 400})
    reference = shape_from_glyphs(gs, "y")
    slopes, intercepts, tips, inner = rails(reference, xheight)
    original = donor_hook(upstream, xheight / upstream["OS/2"].sxHeight)
    left, right = spans(reference, CUT, 1)[0]
    end, start = original[-1][-1][0], original[0][0][0]
    factor = (right - left) / (start - end)
    transform = Transform(factor, 0, 0, 1, left - factor * end, 0)
    preserved = [tuple(map(transform.transformPoint, part)) for part in original]
    hook_in, hook_out = preserved[0][0], preserved[-1][-1]
    outer_join_y = -32
    outer_join = (intercepts[3] + slopes[3] * outer_join_y, outer_join_y)
    fork = (intercepts[0], 0)

    true_type = TTGlyphPen(None)
    pen = Cu2QuPen(true_type, max_err=0.35)
    pen.moveTo(tips[0])
    pen.lineTo(tips[1])
    pen.lineTo(inner)
    pen.lineTo(tips[2])
    pen.lineTo(tips[3])
    pen.lineTo(outer_join)
    bridge(pen, outer_join, slopes[3], hook_in, derivative(*preserved[0][:2]))
    for part in preserved:
        if len(part) == 2:
            pen.lineTo(part[-1])
        else:
            pen.qCurveTo(*part[1:])
    bridge(pen, hook_out, derivative(*preserved[-1][-2:]), fork, -slopes[0])
    pen.closePath()
    return true_type.glyph()


def add_primary_y(font, upstream):
    system = deepcopy(font)
    regular = regular_y(system, upstream)
    _, locations = master_locations(system)
    normalized = [{k: v for k, v in system.normalizeLocation(loc).items() if v}
                  for loc in locations]
    model = VariationModel(normalized, axisOrder=["wght", "opsz"])
    default = normalized.index({})
    original_width = system["hmtx"]["y"][0]
    base = vertical_stem(shape_from_glyphs(system.getGlyphSet(location={"wght": 400}), "n"), .4)
    weighted = {}
    for loc in locations:
        weight = loc["wght"]
        if weight not in weighted:
            gs = system.getGlyphSet(location={"wght": weight})
            measured = vertical_stem(shape_from_glyphs(gs, "n"), .4)
            weighted[weight] = direct_points(regular, measured - base, .72, 3, 0)

    coordinates = []
    for loc in locations:
        current = system.getGlyphSet(location=loc)
        target_left = shape_from_glyphs(current, "y").bounds[0]
        points = weighted[loc["wght"]].copy()
        shift = otRound(target_left - min(x for x, _ in points))
        points.translate((shift, 0))
        coordinates.append(points)
    drawing = deepcopy(regular)
    drawing.coordinates = coordinates[default]
    append_glyph(font, "y", drawing,
                 build_variations(model, coordinates, expanded_variations(system, "y")),
                 original_width, metric_source="y")


def draw_text(font, engine, loc, text, origin, baseline, size):
    glyphs = font.getGlyphSet(location=loc)
    scale = size / font["head"].unitsPerEm
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(engine, buffer)
    pieces = []
    cursor = origin
    for item, position in zip(buffer.glyph_infos, buffer.glyph_positions):
        glyph = font.getGlyphName(item.codepoint)
        pen = SVGPathPen(glyphs)
        glyphs[glyph].draw(pen)
        x = cursor + position.x_offset * scale
        y = baseline - position.y_offset * scale
        pieces.append(f'<path d="{pen.getCommands()}" transform="translate({x:.5f} {y:.5f}) scale({scale} {-scale})"/>')
        cursor += position.x_advance * scale
    return "".join(pieces)


def bbox(glyphs, name):
    pen = BoundsPen(glyphs)
    glyphs[name].draw(pen)
    return pen.bounds


def rounded_points(values):
    return GlyphCoordinates((otRound(p.real), otRound(p.imag)) for p in values)


def joined_y(template, glyph):
    """Carry the direction through smooth joins in the original curve topology."""
    points = [complex(x, y) for x, y in glyph.coordinates]
    original = [complex(x, y) for x, y in template.coordinates]
    for contour in stored_segments(template):
        for index, (start, control, end) in enumerate(contour):
            incoming = contour[index - 1][1] or contour[index - 1][0]
            outgoing = control or end
            if not all(len(part) == 1 for part in (incoming, start, outgoing)):
                continue
            a, b, c = (next(iter(part)) for part in (incoming, start, outgoing))
            u, v = original[b] - original[a], original[c] - original[b]
            if not u or not v or (u.conjugate() * v).real < abs(u * v) * cos(radians(8)):
                continue
            if control and contour[index - 1][1]:
                fraction = abs(u) / (abs(u) + abs(v))
                points[b] = points[a] + (points[c] - points[a]) * fraction
            elif control:
                direction = (points[b] - points[a]) / abs(points[b] - points[a])
                points[c] = points[b] + direction * abs(points[c] - points[b])
            elif contour[index - 1][1]:
                direction = (points[b] - points[c]) / abs(points[b] - points[c])
                points[a] = points[b] + direction * abs(points[a] - points[b])
    return rounded_points(points)


def build(source, donor, output):
    result = deepcopy(source)
    cmap = source.getBestCmap()
    names = {cmap[ord(c)] for c in LETTERS}
    _, locations = master_locations(source)
    normalized = [{tag: value for tag, value in source.normalizeLocation(loc).items() if value}
                  for loc in locations]
    model = VariationModel(normalized, axisOrder=["wght", "opsz"])
    default = normalized.index({})
    donor_masters = {weight: instantiateVariableFont(donor, {"wght": weight})
                     for weight in sorted({loc["wght"] for loc in locations})}
    weight_donors = {weight: enlarge_lowercase(master)[0] for weight, master in donor_masters.items()}
    source_y = source.getGlyphSet(location={"wght": 400})["y"]._getGlyphInstance()
    masters = []

    for loc in locations:
        authored = weight_donors[loc["wght"]]
        target = source.getGlyphSet(location=loc)
        drawing = deepcopy(authored)
        alphabet = drawing["glyf"]
        adjusted = {}

        def place(name):
            if name in adjusted:
                return adjusted[name]
            glyph = alphabet[name]
            desired = bbox(target, name)
            if glyph.isComposite():
                for part in glyph.components:
                    if part.glyphName in names:
                        shift = place(part.glyphName)
                        dx, dy = Transform(*part.getComponentInfo()[1]).transformVector((shift, 0))
                        part.x -= otRound(dx)
                        part.y -= otRound(dy)
            elif desired[3] > source["OS/2"].sxHeight + 10:
                # Ascenders retain System's existing heights above the enlarged x-height.
                reference = drawing["OS/2"].sxHeight
                top = bbox(authored.getGlyphSet(), name)[3]
                if top > reference:
                    multiplier = (desired[3] - reference) / (top - reference)
                    glyph.coordinates = GlyphCoordinates(
                        (x, otRound(reference + (y - reference) * multiplier) if y > reference else y)
                        for x, y in glyph.coordinates
                    )
            current = bbox(drawing.getGlyphSet(), name)
            shift = otRound((desired[0] + desired[2] - current[0] - current[2]) / 2)
            if glyph.isComposite():
                for part in glyph.components:
                    part.x += shift
            else:
                glyph.coordinates.translate((shift, 0))
            glyph.recalcBounds(alphabet)
            drawing["hmtx"][name] = drawing["hmtx"][name][0], glyph.xMin
            adjusted[name] = shift
            return shift

        for name in sorted(names - {"y"}):
            place(name)
        y = deepcopy(target["y"]._getGlyphInstance())
        y.coordinates = joined_y(source_y, y)
        alphabet["y"] = y
        dot = deepcopy(alphabet["diamond.dot"])
        dot.coordinates = deepcopy(alphabet["uni0307"].getCoordinates(alphabet)[0])
        alphabet[DOT] = dot
        for name in ("i", "j"):
            for part in alphabet[name].components:
                if part.glyphName == "uni0307":
                    part.glyphName = DOT
        masters.append({name: alphabet[name] for name in names | {DOT}})

    dot = deepcopy(masters[default][DOT])
    clear_hints(dot)
    append_glyph(result, DOT, dot,
                 build_variations(model, [items[DOT].coordinates for items in masters]), 0)
    result["GDEF"].table.GlyphClassDef.classDefs[DOT] = 3

    # Component base glyphs must be installed before their dependants.
    order = sorted(names, key=lambda name: (masters[default][name].isComposite(), name))
    for name in order:
        drawing = deepcopy(masters[default][name])
        if drawing.isComposite():
            points = [GlyphCoordinates((part.x, part.y) for part in owned[name].components)
                      for owned in masters]
        else:
            points = [owned[name].coordinates for owned in masters]
        assert all(len(p) == len(points[0]) for p in points), name
        install_masters(result, source, name, drawing, points, model, default)

    accents = rebuild_accents(result, source, donor_masters, locations, model,
                              locations[default], names, DOT)
    name_trial(result, FAMILY, variable=True)
    result.recalcTimestamp = False
    result.save(output)
    with TTFont(output) as built:
        sanitize(built)
        for tag in ("cmap", "GPOS", "GSUB", "fvar", "STAT"):
            assert built.getTableData(tag) == source.getTableData(tag), tag
        for loc in locations:
            a, b = (f.getGlyphSet(location=loc) for f in (source, built))
            for name in names | {cmap[codepoint] for codepoint in accents}:
                assert a[name].width == b[name].width, (loc, name)
    return order, accents


def proof(font_path, output):
    font = TTFont(font_path)
    engine = hb.Font(hb.Face(font_path.read_bytes()))
    optical = next(a.defaultValue for a in font["fvar"].axes if a.axisTag == "opsz")
    rows = ['<rect width="1260" height="1135" fill="#f5f1e8"/>',
            '<text x="36" y="54" font-size="32" font-weight="700">Daikonic Transit System</text>',
            '<text x="37" y="83" font-size="18" fill="#5a4739">Lowercase curve review · Text optical size</text>']
    for row, weight in enumerate(WEIGHTS):
        loc = {"wght": weight, "opsz": optical}
        engine.set_variations(loc)
        top = 108 + 198 * row
        rows += [f'<rect x="22" y="{top}" width="1216" height="182" rx="6" fill="white"/>',
                 f'<text x="42" y="{top+44}" font-size="16">{weight}</text>',
                 f'<path d="M135 {top+96}H1217 M135 {top+61}H1217" stroke="#e9dfd4"/>',
                 draw_text(font, engine, loc, "wayfinding · play · typography", 135, top+96, 70),
                 draw_text(font, engine, loc, ascii_lowercase, 135, top+157, 36) ]
    output.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1260" height="1135" '
        'viewBox="0 0 1260 1135" font-family="Arial,sans-serif" fill="#16252a">'
        + "".join(rows) + "</svg>")


def accent_proof(font_path, output, codepoints):
    font = TTFont(font_path)
    engine = hb.Font(hb.Face(font_path.read_bytes()))
    optical = next(axis.defaultValue for axis in font["fvar"].axes if axis.axisTag == "opsz")
    families = defaultdict(str)
    for codepoint in codepoints:
        char = chr(codepoint)
        families[normalize("NFD", char)[0]] += char
    height = 155 + 45 * len(families)
    width = 1520
    rows = [f'<rect width="{width}" height="{height}" fill="#f5f1e8"/>',
            '<text x="36" y="54" font-size="32" font-weight="700">Daikonic Transit System</text>',
            '<text x="37" y="83" font-size="18" fill="#5a4739">Lowercase accents · Text optical size</text>']
    for col, weight in enumerate(WEIGHTS):
        x = 27 + 300 * col
        loc = {"wght": weight, "opsz": optical}
        engine.set_variations(loc)
        rows += [f'<rect x="{x}" y="106" width="266" height="{height - 126}" rx="6" fill="white"/>',
                 f'<text x="{x + 24}" y="133" font-size="16">{weight}</text>']
        for row, base in enumerate(sorted(families)):
            baseline = 172 + 45 * row
            rows.append(draw_text(font, engine, loc, " ".join(families[base]), x + 24, baseline, 27))
    output.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Arial,sans-serif" fill="#16252a">'
        + "".join(rows) + "</svg>")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("system", type=Path)
    parser.add_argument("sans", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--metropolitan", type=Path, default=UPSTREAM)
    sampling = parser.add_mutually_exclusive_group()
    sampling.add_argument("--outline-only", action="store_true", help="reproduce the outline proof")
    sampling.add_argument("--named-instances", action="store_true",
                          help="check pair clearance at the named weight and optical-size locations")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    font = args.output / "DaikonicTransitSystemCurveReview-VF.ttf"
    with TTFont(args.system, recalcTimestamp=False) as source, TTFont(args.sans) as donor:
        with TTFont(args.metropolitan) as upstream:
            add_primary_y(source, upstream)
        changed, accents = build(source, donor, font)
    if not args.outline_only:
        with TTFont(font, recalcTimestamp=False) as finished:
            locations = master_locations(finished)[1] if args.named_instances else None
            spacing = repair_kerning(finished, locations=locations)
            finished.save(font)
            sanitize(finished)
        font.with_suffix(".kerning.json").write_text(json.dumps(spacing, indent=2) + "\n")
    proof(font, args.output / "System-Lowercase-Curves.svg")
    accent_proof(font, args.output / "System-Lowercase-Accents.svg", accents)
    print("Rebuilt", len(changed), "lowercase bases and", len(accents), "accented forms")
