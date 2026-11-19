"""Build an upright Code hairline proof with full-length inset rules."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from math import ceil
import unicodedata
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
import ots
import pathops
import uharfbuzz as hb

from audit import shape_from_glyphs, spans
from code_structural_fit import INTERPOLATION
from font_feature_tools import (
    add_features, append_glyph, compose, expanded_variations, from_paths, master_locations,
)
from italic_texture_proofs import BG, CREAM, MUTED, export, label, rect
from specimens import Panel, ROOT, specimen_families


PLAIN = ROOT / "previews/code-1.029/source/DaikonicTransitCodeSyntaxStudy-VF.ttf"
HAIRLINE = 22
GAP = 38
OUTER_GAP = 62
CELL = 600
ANGLE_THINNING = 26
SCOPE_TAIL = 74
BORROW_INSET = 40
PAIRS = (
    ("parenleft", "parenright"),
    ("bracketleft", "bracketright"),
    ("braceleft", "braceright"),
    ("bar.delimiterOpen", "bar.delimiterClose"),
)
TALL_OPENERS = ("less.generic", "code.lifetimeOpen")
TALL_CLOSER = "greater.generic"
MARKER = "quotesingle.lifetime"
COMPACT = MARKER + ".compact"
OVER = MARKER + ".hairlineOver"
LEADERS = {OVER: 660, OVER + "Tall": 802, OVER + "Marked": 950 - HAIRLINE // 2}
LEADER_END = 1200
WEIGHTS = tuple(range(300, 401, 10))
CONTROL = "let bits = (a | b) || (c != d);"
EXAMPLE = (
    "fn read<'a>(x: &'a [u8]) -> &'a str",
    "map(|v| { entries[i] + v })",
    "let name = T::item::<T>(x);",
    "let bits = a | b; let ch = 'x';",
    "use_refs::<'static, '_>();",
)


def polygon(points):
    shape = pathops.Path()
    pen = shape.getPen()
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()
    return shape


def rectangle(x0, y0, x1, y1):
    return polygon([(x0, y0), (x0, y1), (x1, y1), (x1, y0)])


def joined(a, b):
    return pathops.op(a, b, pathops.PathOp.UNION, clockwise=True)


def delimiter_rail(gs, name, opening, shifted=False):
    primary = shape_from_glyphs(gs, name)
    left, bottom, right, top = primary.bounds
    low, high = round(bottom), round(top)
    direction = 1 if opening else -1
    def edge(y):
        # Sample just inside the terminal where the fill has a nonzero span.
        y = min(top - 0.1, max(bottom + 0.1, y))
        intervals = spans(primary, y, 1)
        toward_right = opening != shifted
        return (max(end for _, end in intervals) if toward_right else
                min(start for start, _ in intervals))

    if name.startswith("bracket"):
        if shifted:
            half = HAIRLINE // 2
            x = round(edge((low + high) / 2)) - direction * (OUTER_GAP + half)
            return [(x - half, low), (x - half, high), (x + half, high), (x + half, low)], 0
        terminal = right - 12 if opening else left + 12
        lower, upper = spans(primary, terminal, 0)
        # Leave a sliver of clearance at both bars through interpolation.
        low, high = ceil(lower[1]) + 3, int(upper[0]) - 3
        inset = round(edge((low + high) / 2)) + direction * GAP
        return [(inset, low), (inset, high),
                (inset + direction * HAIRLINE, high), (inset + direction * HAIRLINE, low)], 0
    ys = [*range(low, high, 8), high]
    side = -direction if shifted else direction
    edges = [edge(y) for y in ys]
    if shifted and name.startswith("brace"):
        # Cover the nose's floor-parallel terminals when the sampled edge jumps.
        envelope = min if opening else max
        edges = [envelope(edges[max(0, i - 2):i + 3]) for i in range(len(edges))]
    gap = OUTER_GAP if shifted else GAP
    inner = [(round(x) + side * gap, y) for x, y in zip(edges, ys)]
    outer = [(x + side * HAIRLINE, y) for x, y in reversed(inner)]
    return inner + outer, 0


def add_delimiter(font, archive, name, forms):
    # Keep the original primary outline and variation deltas point for point.
    primary = deepcopy(archive["glyf"][name])
    primary_deltas = expanded_variations(archive, name)
    (low, light_shift), (middle, book_shift), (high, regular_shift) = forms
    rail_deltas = {
        (("wght", region),): [(x - a, y - b) for (x, y), (a, b) in zip(points, middle)]
        for region, points in (((-1, -1, 0), low), ((0, 1, 1), high))
    }
    primary_zeros = [(0, 0)] * (len(primary.coordinates) + 4)
    primary_shift = {
        (("wght", (-1, -1, 0)),): light_shift - book_shift,
        (("wght", (0, 1, 1)),): regular_shift - book_shift,
    }
    variations = []
    for region in sorted(primary_deltas.keys() | rail_deltas.keys()):
        deltas = primary_deltas.get(region, primary_zeros)
        extra = rail_deltas.get(region, [(0, 0)] * len(middle))
        dx = primary_shift.get(region, 0)
        moved = [(x + dx, y) for x, y in deltas[:-4]]
        variations.append(TupleVariation(dict(region), moved + extra + deltas[-4:]))
    primary.coordinates.translate((book_shift, 0))
    primary.coordinates.extend(middle)
    primary.flags.extend([1] * len(middle))
    primary.endPtsOfContours.append(len(primary.coordinates) - 1)
    primary.numberOfContours += 1
    append_glyph(font, name, primary, variations, 600, metric_source=name)


def lifetime(gs, y):
    dot = max(shape_from_glyphs(gs, "i").contours, key=lambda contour: contour.bounds[3])
    radius = round((dot.bounds[2] - dot.bounds[0]) / 2)
    x = 373
    center = min(y, 950 - radius)
    marker = polygon([
        (x - radius, center), (x, center + radius),
        (x + radius, center), (x, center - radius),
    ])
    half = HAIRLINE / 2
    line = polygon([
        (x, center - half), (600, y - half), (LEADER_END, y - half),
        (LEADER_END, y + half), (600, y + half), (x, center + half),
    ])
    return joined(marker, line)


def scope(gs, outward=False):
    dots = shape_from_glyphs(gs, "code.scope")
    half = HAIRLINE // 2
    if outward:
        contours = sorted(dots.contours, key=lambda path: path.bounds[1])
        for row in (contours[:2], contours[2:]):
            left, right = sorted(path.bounds for path in row)
            for box, sign in ((left, -1), (right, 1)):
                x = (box[0] + box[2]) / 2
                end = (box[0] if sign < 0 else box[2]) + sign * SCOPE_TAIL
                y = round((box[1] + box[3]) / 2)
                dots = joined(dots, rectangle(min(end, x), y - half, max(end, x), y + half))
        return dots
    left, _, right, _ = dots.bounds
    radius = (list(dots.contours)[0].bounds[2] - list(dots.contours)[0].bounds[0]) / 2
    return joined(dots, rectangle(left + radius, 300 - half, right - radius, 300 + half))


def lifetime_context(font, glyphs, feature="calt"):
    targets = {
        name for cp, name in font.getBestCmap().items()
        if unicodedata.category(chr(cp)).startswith("L")
    }
    clearance = {}
    for name in targets:
        top = max(shape_from_glyphs(gs, name).bounds[3] for gs in glyphs)
        leader = next((leader for leader, y in LEADERS.items() if y - 24 > top), OVER + "Marked")
        clearance[name] = leader
    for name in font.getGlyphOrder():
        if ".heal." in name and name.split(".")[0] in clearance:
            clearance[name] = clearance[name.split(".")[0]]
    marks = sorted(name for name, cls in font["GDEF"].table.GlyphClassDef.classDefs.items() if cls == 3)
    rules = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        f"@LifetimeMarker = [{MARKER} {COMPACT}];",
        f"@LifetimeTarget = [{' '.join(sorted(clearance))}];",
        f"@LifetimeMark = [{' '.join(marks)}];",
        f"feature {feature} {{",
        f"sub @LifetimeMarker' @LifetimeTarget @LifetimeMark by {OVER}Marked;",
    ]
    for leader in LEADERS:
        group = sorted(name for name, variant in clearance.items() if variant == leader)
        rules.append(f"sub @LifetimeMarker' [{' '.join(group)}] by {leader};")
    rules.extend([f"sub @LifetimeMarker by {OVER};", f"}} {feature};"])
    add_features(font, "\n".join(rules))
    return clearance


def build(source, directory, shifted=False):
    font = TTFont(source, recalcTimestamp=False)
    archive = TTFont(PLAIN)
    _, locations = master_locations(font)
    glyphs = [font.getGlyphSet(location=loc) for loc in locations]
    plain_glyphs = [archive.getGlyphSet(location=loc) for loc in locations]
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    existing_classes = classes.copy()
    for opening, closing in PAIRS:
        for name, on_right in ((opening, True), (closing, False)):
            paths = [delimiter_rail(gs, name, on_right, shifted) for gs in plain_glyphs]
            add_delimiter(font, archive, name, paths)
    if shifted:
        angle_archive = TTFont(source)
        stretch_angles(angle_archive, (*TALL_OPENERS, TALL_CLOSER))
        lighten_angles(angle_archive)
        angle_glyphs = [angle_archive.getGlyphSet(location=loc) for loc in locations]
        for name in (*TALL_OPENERS, TALL_CLOSER):
            paths = [delimiter_rail(gs, name, name in TALL_OPENERS, True) for gs in angle_glyphs]
            add_delimiter(font, angle_archive, name, paths)
        for count in range(2, 17):
            extent = min(30 * (count - 1), 90)
            parts = [
                (TALL_CLOSER, 1, 1, CELL * i + extent - 2 * extent * i / (count - 1), 0)
                for i in range(count)
            ]
            name = f"code.genericClose{count}"
            compose(font, name, parts, count * CELL, metric_source=name)
        center_scope(font)
    for name, glyph in INTERPOLATION.items():
        compose(font, name, [("dollar", 1, 1, 35, -50), (glyph, 1, 1, 565, 0)], 1200)
    for name, y in LEADERS.items():
        from_paths(font, name, locations, [lifetime(gs, y) for gs in glyphs], 600)
    from_paths(font, "code.scope", locations, [scope(gs, shifted) for gs in glyphs], 1200)
    classes.update(existing_classes)
    clearance = lifetime_context(font, glyphs)
    if shifted:
        leaders = " ".join(LEADERS)
        add_features(font, f"""
            languagesystem DFLT dflt;
            languagesystem latn dflt;
            feature calt {{
                pos ampersand' <{BORROW_INSET} 0 0 0> [{leaders}];
            }} calt;
        """)
    name = "Original Fit Hairlines" if shifted else "Full Inset Hairlines"
    return save_trial(font, directory, name), clearance


def save_trial(font, directory, suffix):
    family = "Daikonic Transit Code"
    trial = family + " " + suffix
    for record in font["name"].names:
        revised = record.toUnicode().replace(family, trial).replace(
            family.replace(" ", ""), trial.replace(" ", "")
        )
        record.string = revised.encode(record.getEncoding())
    destination = directory / (trial.replace(" ", "") + "-VF.ttf")
    font.save(destination)
    return destination


def shape(font, engine, string, features):
    buffer = hb.Buffer()
    buffer.add_str(string)
    buffer.guess_segment_properties()
    hb.shape(engine, buffer, features)
    return [
        (font.getGlyphName(i.codepoint), i.cluster, p.x_advance, p.x_offset, p.y_offset)
        for i, p in zip(buffer.glyph_infos, buffer.glyph_positions)
    ]


def verify(source, candidate, targets, shifted=False):
    fonts = [TTFont(path) for path in (source, candidate)]
    original, font = fonts
    archive = TTFont(PLAIN)
    for tag in ("cmap", "fvar", "STAT") + (() if shifted else ("GPOS",)):
        assert original.getTableData(tag) == font.getTableData(tag), tag
    revised = {name for left, right in PAIRS for name in (left, right)}
    revised.update({*INTERPOLATION, "code.scope"})
    if shifted:
        revised.update((*TALL_OPENERS, TALL_CLOSER))
        revised.update(n for n in original.getGlyphOrder() if n.startswith("code.genericClose"))
        angle_archive = TTFont(source)
        stretch_angles(angle_archive, (*TALL_OPENERS, TALL_CLOSER))
        lighten_angles(angle_archive)
    for name in original.getGlyphOrder():
        assert original["hmtx"][name][0] == font["hmtx"][name][0], name
        if name not in revised:
            old, new = original["glyf"], font["glyf"]
            assert old[name].compile(old) == new[name].compile(new), name
    engines = [hb.Font(hb.Face(path.read_bytes())) for path in (source, candidate)]
    for weight in WEIGHTS:
        location = {"wght": weight}
        for engine in engines:
            engine.set_variations(location)
        glyphs = font.getGlyphSet(location=location)
        baseline = archive.getGlyphSet(location=location)
        for name in (*LEADERS, "code.scope"):
            outline = shape_from_glyphs(glyphs, name)
            probe = 600 if name == "code.scope" else 1100
            if shifted and name == "code.scope":
                assert not spans(outline, 600, 0)
                probe = outline.bounds[0] + SCOPE_TAIL / 2
            rails = spans(outline, probe, 0)
            assert len(rails) == (2 if shifted and name == "code.scope" else 1)
            assert all(abs(hi - lo - HAIRLINE) < 0.01 for lo, hi in rails)
            if name in LEADERS:
                assert outline.bounds[2] == LEADER_END
        for left, right in PAIRS:
            for name, opening in ((left, True), (right, False)):
                primary, rail = shape_from_glyphs(glyphs, name).contours
                assert abs(pathops.op(primary, rail, pathops.PathOp.INTERSECTION).area) < 0.01, (name, weight)
                assert 0 < rail.bounds[0] < rail.bounds[2] < 600, name
                old = shape_from_glyphs(baseline, name)
                assert abs(pathops.op(old, primary, pathops.PathOp.XOR).area) < 1, (name, weight)
                y = sum(rail.bounds[i] for i in (1, 3)) / 2
                [(lo, hi)] = spans(rail, y, 1)
                assert abs(hi - lo - HAIRLINE) < 0.01
        if shifted:
            tall_baseline = angle_archive.getGlyphSet(location=location)
            for name in (*TALL_OPENERS, TALL_CLOSER):
                primary, rail = shape_from_glyphs(glyphs, name).contours
                prior = shape_from_glyphs(tall_baseline, name)
                assert abs(pathops.op(prior, primary, pathops.PathOp.XOR).area) < 1, (name, weight)
                assert abs(pathops.op(primary, rail, pathops.PathOp.INTERSECTION).area) < 0.01
                assert rail.bounds[1] == primary.bounds[1] and rail.bounds[3] == primary.bounds[3]
        for target, leader in targets.items():
            if leader != OVER + "Marked":
                assert shape_from_glyphs(glyphs, target).bounds[3] < LEADERS[leader] - 8
        for string in EXAMPLE + (
            CONTROL, "Vec<[T]> [<T>]", "${x} $[x] $(x)", "map(|x| x)",
            "f<'a, 't, 'i, 'Á, '_>()", "&'é &'e\u0301 'x' '_'",
        ):
            for features in ({}, {"ss01": True, "ss02": True}, {"calt": False}):
                a, b = [shape(f, h, string, features) for f, h in zip(fonts, engines)]
                assert len(a) == len(b), (string, features)
                for index, (before, after) in enumerate(zip(a, b)):
                    if after[0] in LEADERS:
                        assert before[0] in (MARKER, COMPACT) and before[1:3] == after[1:3]
                    else:
                        name, cluster, advance, x, y = before
                        if shifted and name == "code.scope" and y == 50:
                            y = 0
                        if shifted and name == "ampersand" and index + 1 < len(b) and b[index + 1][0] in LEADERS:
                            x += BORROW_INSET
                        assert (name, cluster, advance, x, y) == after, (string, features, before, after)
        if shifted:
            for pair in (
                "()", "[]", "{}", "(]", "{)", "map(|| x)", "${}", "$[]",
                "map(|x| x)", "|_|", "|w|", "|K|", "[K]", "{K}",
                "Vec<>", "Vec<T>", "T::item::<T>", "Vec<Vec<T>>", "<[T]>", "[<T>]",
            ):
                shaped = shape(font, engines[1], pair, {})
                positions = []
                cursor = 0
                for name, _, advance, x, y in shaped:
                    positions.append((name, cursor + x, y))
                    cursor += advance
                assert cursor == CELL * len(pair)
                for (a, x0, y0), (b, x1, y1) in zip(positions, positions[1:]):
                    lhs = shape_from_glyphs(glyphs, a).transform(1, 0, 0, 1, x0, y0)
                    rhs = shape_from_glyphs(glyphs, b).transform(1, 0, 0, 1, x1, y1)
                    overlap = pathops.op(lhs, rhs, pathops.PathOp.INTERSECTION)
                    assert abs(overlap.area) < 1, (pair, a, b, weight)
        assert [g[0] for g in shape(font, engines[1], "'a 'i", {})] == [
            OVER, "a", "space", OVER + "Tall", "i"
        ]
    with TemporaryDirectory() as tmp:
        subprocess.run(
            [ots.OTS_SANITIZE, str(candidate), str(Path(tmp) / "check.ttf")],
            check=True, capture_output=True,
        )


def proof(directory, config, cuts, subtitle=None):
    width, height = 40 + 490 * len(cuts), 942
    body = [
        rect(0, 0, width, height, BG),
        label("Daikonic Transit Code · hairlines", 26, 47, 30, bold=True),
        label(subtitle or f"Upright · pre-bolding outlines with a constant {HAIRLINE}-unit secondary stroke", 26, 75, 15, MUTED),
    ]
    for col, (heading, path, *settings) in enumerate(cuts):
        features = settings[0] if settings else None
        x = 26 + 490 * col
        panel = Panel("hairline-" + str(col), {**config, "font": str(path)})
        body.extend((
            rect(x - 6, 98, 476, 516, "#101821"),
            rect(x - 6, 630, 476, 286, "#eeeddb"),
            label(heading, x + 12, 127, 16, CREAM, True),
            label("Book 350 · 16 px", x + 12, 462, 12, MUTED, True),
        ))
        for y, value in (
            (203, "(x) [x] {x}"),
            (271, "|x|  |w|  a | b"),
            (340, "&'a   'i   'x'"),
            (406, "T::item::<T>"),
        ):
            panel.text(value, x + 12, y, 39, 350, CREAM, features=features)
        for row, value in enumerate(EXAMPLE):
            panel.text(value, x + 12, 488 + 22 * row, 16, 350, CREAM, features=features)
        styles = ((300, "Light 300"), (350, "Book 350"), (400, "Regular 400"))
        for row, (weight, style) in enumerate(styles):
            y = 656 + 86 * row
            body.append(label(style + " · 14 / 18 px", x + 12, y, 12, "#194454", True))
            for size, offset in ((14, 24), (18, 48)):
                panel.text(
                    "map(|x| { T::get::<'a>(x[i]) })",
                    x + 12, y + offset, size, weight, "#15232c", features=features,
                )
        body.append(panel.body())
    export(directory / "Code-Hairlines.svg", body, width, height)


def stretch_angles(font, names):
    glyphs = font.getGlyphSet()

    def vertical_span(name):
        _, low, _, high = shape_from_glyphs(glyphs, name).bounds
        return low, high

    bottom, top = vertical_span("parenleft")
    old_bottom, old_top = vertical_span("less.generic")
    scale = (top - bottom) / (old_top - old_bottom)
    shift = bottom - old_bottom * scale
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    for name in names:
        old_class = classes[name]
        compose(
            font, name, [(name, 1, scale, 0, shift)], font["hmtx"][name][0],
            metric_source=name,
        )
        classes[name] = old_class
    return bottom, top


def lighten_angles(font):
    # Move the inside chevron toward the outside while keeping vertical bevels.
    for name in (*TALL_OPENERS, TALL_CLOSER):
        glyph = font["glyf"][name]
        points = glyph.coordinates
        assert len(points) == 19 and glyph.numberOfContours == 1, name
        run = abs(points[0][0] - points[3][0])
        rise = abs(points[0][1] - points[3][1])
        terminal_move = ANGLE_THINNING * rise / run
        direction = 1 if name == TALL_CLOSER else -1
        for index in range(10, 15):
            x, y = points[index]
            points[index] = (x + direction * ANGLE_THINNING, y)
        for index, portion in ((7, -.25), (8, -.75), (9, -1), (15, 1), (16, .75), (17, .25)):
            x, y = points[index]
            points[index] = (x, y + round(terminal_move * portion))
        glyph.recalcBounds(font["glyf"])


def center_scope(font):
    matches = []
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for table in lookup.SubTable:
            table = getattr(table, "ExtSubTable", table)
            if getattr(getattr(table, "Coverage", None), "glyphs", []) == ["code.scope"]:
                value = getattr(table, "Value", None)
                if getattr(value, "XPlacement", None) == 18 and getattr(value, "YPlacement", None) == 50:
                    matches.append(value)
    assert len(matches) == 1
    matches[0].YPlacement = 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--shifted", action="store_true")
    args = parser.parse_args()
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    config = specimen_families()["code"]
    source = ROOT / config["font"]
    candidate, targets = build(source, directory, args.shifted)
    verify(source, candidate, targets, args.shifted)
    print(candidate.name, "passed 11-weight geometry, shaping and OTS checks", flush=True)
    cuts = [("Released", source), ("Original fit / outward rules" if args.shifted else "Full inset", candidate)]
    proof(directory, config, cuts)
    (directory / "Review.json").write_text(json.dumps({
        "source": config["font"],
        "pre_bolding_delimiters": str(PLAIN.relative_to(ROOT)),
        "units_per_em": TTFont(source)["head"].unitsPerEm,
        "stroke_units": HAIRLINE,
        "weights_verified": WEIGHTS,
        "sha256": {
            path.name: sha256(path.read_bytes()).hexdigest()
            for _, path in cuts
        },
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
