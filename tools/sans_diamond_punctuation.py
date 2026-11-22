"""Proof sharp and rounded diamond joins on existing Transit Sans punctuation."""

import argparse
from pathlib import Path

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

from code_weight_width_trial import name_trial, sanitize
from font_feature_tools import expanded_variations
from sans_baseline_trial import DOT, clear_hints, components, install
from specimens import DATA, Panel

# First point of each horizontal edge in the reviewed component baseline.
EDGES = {
    "comma": (5,),
    "quotesingle": (1,),
    "quoteleft": (4,),
    "quoteright": (4,),
    "quotedbl": (1, 7),
    "quotedblleft": (4, 15),
    "quotedblright": (4, 15),
}
ROUNDED_FLAGS = (1, 0, 1, 1, 1, 0, 1)
SHARP_FLAGS = (1, 1, 1)
INSET_TRIANGLE = (None, True, True)
VARIANTS = {"Full edge": (None, True, False), "Inset triangle": INSET_TRIANGLE}


def period_top(font):
    period = font["glyf"]["period"]
    component, = period.components
    if component.glyphName != DOT:
        raise ValueError("Expected the period to use the shared diamond")
    dot = font["glyf"][DOT]
    top_index = max(range(len(dot.coordinates)), key=lambda i: dot.coordinates[i][1])
    period_deltas = expanded_variations(font, "period")
    dot_deltas = expanded_variations(font, DOT)
    return component.y + dot.coordinates[top_index][1], {
        support: (
            period_deltas[support][0][1] if support in period_deltas else 0
        ) + (
            dot_deltas[support][top_index][1] if support in dot_deltas else 0
        )
        for support in period_deltas.keys() | dot_deltas.keys()
    }


def edit_crowns(font, name, scale, sharp, inset):
    full_edge = scale is None
    crown_flags = (1,) if full_edge else SHARP_FLAGS if sharp else ROUNDED_FLAGS
    glyph = font["glyf"][name]
    coordinates = glyph.coordinates
    edges = EDGES[name]
    directions = {}
    for i in edges:
        (x1, y1), (x2, y2) = coordinates[i : i + 2]
        if y1 != y2 or x1 == x2 or not (glyph.flags[i] & glyph.flags[i + 1] & 1):
            raise ValueError(f"{name}: expected a horizontal on-curve edge at point {i}")
        directions[i] = 1 if x2 > x1 else -1

    def splice(points, diamond, ceiling):
        result = []
        pending_shoulder = 0
        for i, (x1, y1) in enumerate(points):
            result.append((x1, y1 + pending_shoulder))
            pending_shoulder = 0
            if i not in directions:
                continue
            x2, y2 = points[i + 1]
            center = (x1 + x2) / 2
            edge_y = (y1 + y2) / 2
            if full_edge:
                # Turn half the directed edge 90° outward from the midpoint.
                apex_x = otRound(center - (y2 - y1) / 2)
                rise = otRound((x2 - x1) / 2)
                apex_y = otRound(edge_y) + rise
                if inset:
                    target = otRound(edge_y) if ceiling is None else ceiling
                    adjustment = target - apex_y
                    result[-1] = (x1, y1 + adjustment)
                    result.append((apex_x, target))
                    # The second shoulder appears in the next iteration.
                    pending_shoulder = adjustment
                else:
                    result.append((apex_x, apex_y))
                continue
            direction = directions[i]
            tip = diamond[0 if direction > 0 else 2][1]
            radius = otRound((diamond[1][0] - diamond[3][0]) * scale / 2) * direction
            height = otRound(tip * scale)
            if sharp:
                offsets = ((-radius, 0), (0, height), (radius, 0))
            else:
                fillet = (x2 - x1) * 0.05
                offsets = (
                    (-radius - fillet, 0),
                    (-radius, 0),
                    (-radius + fillet, fillet),
                    (0, height),
                    (radius - fillet, fillet),
                    (radius, 0),
                    (radius + fillet, 0),
                )
            result.extend(
                (otRound(center + dx), otRound(edge_y + dy)) for dx, dy in offsets
            )
        return result

    original_deltas = expanded_variations(font, name)
    diamond = font["glyf"][DOT].coordinates
    diamond_deltas = {} if full_edge else expanded_variations(font, DOT)
    old_count = len(coordinates)
    ceiling, ceiling_deltas = period_top(font) if inset and name == "comma" else (None, {})
    glyph.coordinates = GlyphCoordinates(splice(coordinates, diamond, ceiling))
    zero = (0, 0)
    variations = []
    for support in sorted(original_deltas.keys() | diamond_deltas.keys() | ceiling_deltas.keys()):
        values = original_deltas.get(support, [zero] * (old_count + 4))
        limit = None if ceiling is None else ceiling_deltas.get(support, 0)
        delta = splice(values[:-4], diamond_deltas.get(support, [zero] * 4), limit)
        variations.append(TupleVariation(dict(support), delta + values[-4:]))
    font["gvar"].variations[name] = variations
    flags = bytearray()
    for i, flag in enumerate(glyph.flags):
        flags.append(flag)
        if i in directions:
            flags.extend(crown_flags)
    glyph.flags = flags
    glyph.endPtsOfContours = [
        end + len(crown_flags) * sum(edge < end for edge in edges)
        for end in glyph.endPtsOfContours
    ]
    clear_hints(glyph)


def reuse_comma_in_semicolon(font):
    """Place the semicolon's diamond over the approved full-edge comma."""
    glyf = font["glyf"]
    _, dot = glyf["semicolon"].components
    if dot.glyphName != DOT:
        raise ValueError("Expected the semicolon to use the shared diamond")
    apex = EDGES["comma"][0] + 1
    center = glyf["comma"].coordinates[apex][0]
    comma_deltas = expanded_variations(font, "comma")
    old_deltas = expanded_variations(font, "semicolon")
    variations = []
    zero = (0, 0)
    for support in sorted(comma_deltas.keys() | old_deltas.keys()):
        old = old_deltas.get(support, [zero] * 6)
        shift = comma_deltas[support][apex][0] if support in comma_deltas else 0
        variations.append(TupleVariation(dict(support), [zero, (shift, old[1][1]), *old[-4:]]))
    glyph = components([("comma", (0, 0)), (DOT, (center, dot.y))])
    install(font, "semicolon", glyph, variations)


def build_variant(source, label, scale, sharp, inset, output):
    with TTFont(source, recalcTimestamp=False) as font:
        for name in EDGES:
            edit_crowns(font, name, scale, sharp, inset)
        family = f"Transit Sans Punctuation {label}"
        for instance in font["fvar"].instances:
            style = font["name"].getDebugName(instance.subfamilyNameID)
            instance.postscriptNameID = font["name"].addName(
                family.replace(" ", "") + "-" + style.replace(" ", "")
            )
        stem = name_trial(font, family, variable=True)
        dest = output / f"{stem}.ttf"
        font.save(dest)
    sanitize(dest)
    return dest


def proof(paths, output):
    width, height = 1030, 650
    body = [
        f'<rect width="{width}" height="{height}" fill="#f6f5ef"/>',
        '<text x="32" y="48" font-size="30" font-weight="700">Transit Sans · diamond punctuation</text>',
        '<text x="32" y="77" font-size="15" fill="#42605b">Full-width 90° triangles · the inset comma aligns with the period</text>',
    ]
    for column, (label, path) in enumerate(paths.items()):
        x = 32 + 328 * column
        body.append(f'<text x="{x}" y="119" font-size="17" font-weight="700">{label}</text>')
        panel = Panel(f"punctuation-{column}", {**DATA["families"]["sans"], "font": str(path.resolve())})
        panel.text(".,  '  ’  ‘", x, 245, 142, 400, "#121818", max_width=285)
        panel.text('"  “  ”  „  ‚', x, 366, 119, 400, "#121818", max_width=285)
        for row, (weight, style) in enumerate(((300, "Light"), (400, "Regular"), (600, "SemiBold"))):
            y = 430 + row * 68
            body.append(f'<text x="{x}" y="{y}" font-size="12" fill="#42605b">{style} {weight}</text>')
            panel.text('“Wait,” she said. Don’t go.', x, y + 29, 23, weight, "#121818", max_width=290)
        body.append(panel.body())
    output.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Arial,sans-serif">'
        + "".join(body) + "</svg>"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    paths = {"Baseline": args.baseline}
    for label, (scale, sharp, inset) in VARIANTS.items():
        paths[label] = build_variant(args.baseline, label, scale, sharp, inset, args.output)
    proof(paths, args.output / "Inset-Triangle.svg")


if __name__ == "__main__":
    main()
