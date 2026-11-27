"""Proof Code's revised delimiters, bidirectional arrows, and lifetime hooks."""

from argparse import ArgumentParser
from copy import deepcopy
from itertools import product
from math import ceil
from pathlib import Path

from fontTools.misc.roundTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib import TTFont
import pathops
import uharfbuzz as hb

from audit import shape_from_glyphs, spans
from check_code_rebuild import STYLES, shape
from code_boundary_spacing import identifier_glyphs
from code_foundation import ink_columns
from code_hairline_study import MARKER
from code_hairline_toggle import OFF_FEATURE
from code_layout import angle_styles
from code_math import BIDIRECTIONAL_ARROWS
from code_spread import SPREAD_PREFIXES
from code_structural_fit import nested_offsets
from font_feature_tools import add_features, expanded_variations
from render_svg import render, render_pdf
from sans_baseline_trial import build_variations, install
from specimens import ROOT, Panel
from system_italic import designspace

FAMILY = "Daikonic Transit Code Delimiter Review"
RELEASE = ROOT / "releases/1.1.2/code/VF"
AMPERSAND_GAIN = 18
HOOK_END = 1.60
CLEARANCE = 18
HEIGHT_STEP = 24
HOOK_LIFT = 24
LINES = (
    "f((x))  map(a, b)  $(value)",
    "([{x}])  Vec<[{T}]>  [[...items]]",
    "a & b  &'a  &'static  &'T",
    "'a  'g  'i  'l  'T  'Á  'a'",
    "<'a>  <x>  <'a'>  Vec<Vec<T>>",
    "<>    a <> b    a<>b    Vec<>T",
    "vec<>  Vec<Vec<>>  Vec< <> >",
    "->  <-  <->  =>  <=>  ->>  <<-",
    "fn read<'a>(x: &'a T) -> &'a T { x }",
)
SPREAD_LINES = (
    "f(x,...rest)  f(x, ...rest)",
    "(...rest)  ,...rest  [...rest]",
    "( ...rest)  , ...rest  [ ...rest]",
    "{...rest}   { ...rest}",
    "[[...items]]  ...rest",
    "wait... later  [...]  […rest]",
)


def draw(glyphs, name):
    glyph, offset = glyphs[name]._getGlyphAndOffset()
    drawing = deepcopy(glyph)
    drawing.coordinates.translate((offset, 0))
    return drawing


def revise_drawings(font):
    locations, model, default = designspace(font)
    masters = [font.getGlyphSet(location=location) for location in locations]
    ampersand, marker = [], []
    for glyphs in masters:
        glyph = draw(glyphs, "ampersand")
        left, bottom, right, top = glyph.coordinates.calcBounds()
        stem_left, stem_right = spans(shape_from_glyphs(glyphs, "l"), 400, 1)[0]
        expansion = ink_columns(glyph, 2, 1, stem_right - stem_left)
        gain = AMPERSAND_GAIN * glyphs["ampersand"].width / 600
        factor = gain / (max(expansion) - min(expansion) - (right - left))
        columns = [x + factor * (new - x)
                   for (x, _), new in zip(glyph.coordinates, expansion, strict=True)]
        center = (left + right - min(columns) - max(columns)) / 2
        ampersand.append(GlyphCoordinates((otRound(x + center), otRound(y))
                                          for x, (_, y) in zip(columns, glyph.coordinates, strict=True)))

        hook = draw(glyphs, MARKER)
        end = max(x for x, _ in hook.coordinates)
        reach = otRound(glyphs[MARKER].width * HOOK_END)
        marker.append(GlyphCoordinates((reach if x >= end - 1 else otRound(x), otRound(y))
                                        for x, y in hook.coordinates))

    for name, coordinates in (("ampersand", ampersand), (MARKER, marker)):
        original = deepcopy(font["glyf"][name])
        original.coordinates = coordinates[default]
        install(font, name, original, build_variations(model, coordinates, expanded_variations(font, name)))


def position_hooks(font):
    axes = font["fvar"].axes
    locations = [dict(zip((axis.axisTag for axis in axes), setting, strict=True))
                 for setting in product(*[(axis.minValue, axis.defaultValue, axis.maxValue) for axis in axes])]
    masters = [font.getGlyphSet(location=location) for location in locations]
    letters = identifier_glyphs(font, contextual=True) - {".notdef"}
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    marks = sorted(name for name, kind in classes.items() if kind == 3)
    targets = {}
    lowest_bar = float("inf")
    for gs in masters:
        hook = shape_from_glyphs(gs, MARKER)
        (bottom, _), = spans(hook, gs[MARKER].width * 1.5, 0)
        lowest_bar = min(lowest_bar, bottom)
        for name in letters:
            pen = BoundsPen(gs)
            gs[name].draw(pen)
            if pen.bounds:
                targets[name] = max(pen.bounds[3], targets.get(name, 0))
    heights = {}
    for name, top in targets.items():
        rise = HOOK_LIFT + max(0, ceil((top + CLEARANCE - lowest_bar) / HEIGHT_STEP) * HEIGHT_STEP)
        heights.setdefault(rise, []).append(name)

    # Decomposed accents can sit above the precomposed cap. Use the same
    # highest group with a little more clearance for the combining form.
    marked_rise = max(heights) + HEIGHT_STEP * 2
    rules = [
        "languagesystem DFLT dflt;", "languagesystem latn dflt;",
        f"@HookTarget = [{' '.join(sorted(targets))}];",
        f"@HookMark = [{' '.join(marks)}];",
        "feature calt {",
        f"pos {MARKER}' <0 {marked_rise} 0 0> @HookTarget @HookMark;",
    ]
    rules.extend(f"pos {MARKER}' <0 {rise} 0 0> [{' '.join(sorted(names))}];"
                 for rise, names in sorted(heights.items()))
    rules.append("} calt;")
    add_features(font, "\n".join(rules))
    top = max(shape_from_glyphs(gs, MARKER).bounds[3] for gs in masters)
    font["OS/2"].usWinAscent = max(font["OS/2"].usWinAscent, ceil(top + marked_rise))


def apply_delimiter_revision(font):
    revise_drawings(font)
    position_hooks(font)


def positioned_paths(glyphs, rows):
    origin = 0
    paths = []
    for name, _, advance, _, dx, dy in rows:
        path = shape_from_glyphs(glyphs, name)
        paths.append((name, path.transform(translateX=origin + dx, translateY=dy)))
        origin += advance
    return paths


def verify_delimiter_spacing(engine, glyphs, location, flags, *, even_spread=False):
    width = location["wdth"]
    cell = width * 6
    for left, right in (("((", "))"), ("[[", "]]"), ("{{", "}}"),
                        ("([{", "}])"), ("<[{", "}]>"), ("(((([", "]))))")):
        sample = left + "x" + right
        rows = shape(engine, sample, flags)
        positions = [otRound(dx * width / 100) for dx in nested_offsets(len(left), 30)]
        for edge in (rows[:len(left)], rows[-len(right):]):
            assert all(abs(row[4] - dx) <= 1 for row, dx in zip(edge, positions, strict=True)), (
                location, sample, rows)
        assert all(row[2] == cell for row in rows), (location, sample, rows)
        paths = positioned_paths(glyphs, rows)
        assert all(abs(pathops.op(a, b, pathops.PathOp.INTERSECTION).area) < 1
                   for (_, a), (_, b) in zip(paths, paths[1:])), (location, sample)
    bracket_savings = 1 if even_spread else 2
    for sample, saved in (("[...items]", bracket_savings), ("[[...rest]]", bracket_savings),
                          ("[...more]", bracket_savings), ("f(x,...rest)", 1), (",...rest", 1),
                          ("[ ...items]", 1), ("...items", 1), ("f(...rest)", 1),
                          ("[...]", 0), ("[…items]", 0)):
        rows = shape(engine, sample, flags)
        assert sum(row[2] for row in rows) == (len(sample) - saved) * cell, (location, sample, rows)
        if saved:
            first = sample.index(".")
            dots = rows[first:first + 3]
            assert [row[2] for row in dots] == [(3 - saved) * cell // 3] * 3
            paths = positioned_paths(glyphs, rows)
            if even_spread and first == 0:
                start = sum(row[2] for row in rows[:first])
                for index, (_, path) in enumerate(paths[first:first + 3]):
                    left, _, right, _ = path.bounds
                    target = start + (2 * index + 1) * cell / 3
                    assert abs((left + right) / 2 - target) <= 2, (location, sample, index, path.bounds)
            paths = paths[max(first - 1, 0):first + 4]
            assert all(abs(pathops.op(a, b, pathops.PathOp.INTERSECTION).area) < 1
                       for (_, a), (_, b) in zip(paths, paths[1:])), (location, sample)
    if even_spread:
        verify_spread_boundaries(engine, glyphs, location, flags)


def verify_spread_boundaries(engine, glyphs, location, flags):
    cell = location["wdth"] * 6
    for prefix, blank in product(SPREAD_PREFIXES, ("", " ")):
        sample = prefix + blank + "...rest"
        first = 1 + len(blank)
        rows = shape(engine, sample, flags)
        assert [row[2] for row in rows[:first]] == [cell] * first, (location, sample, rows)
        assert [row[2] for row in rows[first:first + 3]] == [2 * cell // 3] * 3, (location, sample, rows)
        assert sum(row[2] for row in rows) == (len(sample) - 1) * cell
        paths = [path for _, path in positioned_paths(glyphs, rows)]
        first_dot, second_dot, last_dot = [path.bounds for path in paths[first:first + 3]]
        level = (first_dot[1] + first_dot[3]) / 2
        leading = spans(paths[0], level, 1)[-1][1]
        trailing = spans(paths[first + 3], level, 1)[0][0]
        gaps = (first_dot[0] - leading, second_dot[0] - first_dot[2],
                last_dot[0] - second_dot[2], trailing - last_dot[2])
        assert max(gaps) - min(gaps) <= 26, (location, sample, gaps)
        assert ((first_dot[0] + first_dot[2]) / 2 < first * cell) == bool(blank), (
            location, sample, first_dot)


def verify(source, path, *, even_spread=False):
    before, after = [hb.Font(hb.Face(p.read_bytes())) for p in (source, path)]
    prior, font = TTFont(source), TTFont(path)
    glyphs = set(font.getGlyphOrder())
    upright = not font["OS/2"].fsSelection & 1
    parentheses = {"parenleft", "parenright"}
    expected = parentheses | {MARKER}
    if upright:
        for base in parentheses:
            rail = base + ".rail"
            alias = base + ".hairline"
            expected.update((rail, alias))
            assert font["glyf"][alias].getComponentNames(font["glyf"]) == [base, rail]
    assert {name for name in glyphs if name.startswith(("parenleft", "parenright", MARKER))} == expected
    pairs = {
        "<'a>": [True, True], "<'a'>": [True, True], "<x>": [True, True],
        "a<b>c": [True, True], "Vec<Vec<T>>": [True] * 4,
        "Vec<Vec<>>": [True] * 4, "<>": [True, True], "<>T": [True, True],
        "Vec<>": [True, True], "HashMap<>()": [True, True], "Vec<>.new": [True, True],
        "a<>b": [True, True], "Vec<>T": [True, True], "Vec<>_item": [True, True],
        "vec<>": [True, True], "vec::<>": [True, True],
        "a <> b": [False, False], "a\u00a0<>\u00a0b": [False, False],
        "a << b >> c": [False] * 4,
        "a<> b": [True, True], "a <>b": [True, True], "Vec< >": [True, True],
        "Vec< <> >": [True, False, False, True],
        "<x": [False], "x>": [False], "[<x": [False],
        "Vec<\nx>": [False, False], "Vec<" + "t" * 60 + ">": [True, True],
        "Vec<" + "t" * 61 + ">": [False, False],
    }
    controls = ("a <= b >= c", "a <- b -> c", "'a'", "'_'", "'💡'",
                "HTTPServer ParseResponse Read Key Index fileI IMI IWI",
                "window windows exit sweep namespace",)
    lifetimes = ("'a", "'static", "'l", "'i", "'T", "'Á", "'f\u0301", "'Q\u0308", "'_", "'ff", "&'a",
                 "&'T", "<'a>", "Vec<'l>", "use<'a, 'T>")
    for weight, width in product((350, 375, 400, 450, 500), (94, 97, 100, 104, 108)):
        location = {"wght": weight, "wdth": width}
        for engine in (before, after):
            engine.set_variations(location)
        cell = width * 6
        old, new = [f.getGlyphSet(location=location) for f in (prior, font)]
        (bar_bottom, _), = spans(shape_from_glyphs(new, MARKER), 1.5 * cell, 0)
        amp = [shape_from_glyphs(gs, "ampersand").bounds for gs in (old, new)]
        assert amp[1][2] - amp[1][0] > amp[0][2] - amp[0][0] + 12, location
        for sample in controls:
            assert shape(before, sample, {}) == shape(after, sample, {}), (location, sample)
        for sample in ("()", "f((x))", "map(a, b)", "$(x)"):
            plain = shape(after, sample, {OFF_FEATURE: True})
            active = shape(after, sample, {})
            assert all(not row[0].endswith(".hairline") for row in plain), (location, sample, plain)
            assert active == [[name + ".hairline" if upright and name in parentheses else name, *rest]
                              for name, *rest in plain], (location, sample, active, plain)
        for flags in ({}, {OFF_FEATURE: True}):
            verify_delimiter_spacing(after, new, location, flags, even_spread=even_spread)
            for token, name in BIDIRECTIONAL_ARROWS.items():
                rows = shape(after, token + "x", flags)
                assert [row[:3] for row in rows] == [[name, 0, 2 * cell], ["x", 3, cell]], (location, rows)
                literal = shape(after, token, flags | {"liga": False, "calt": False})
                assert [(row[0], row[2]) for row in literal] == [
                    (font.getBestCmap()[ord(char)], cell) for char in token
                ], (location, literal)
            for sample, expected in pairs.items():
                rows = shape(after, sample, flags)
                assert angle_styles(rows) == expected, (location, sample, rows)
                advance = sum(row[2] for row in shape(before, sample, flags))
                assert sum(row[2] for row in rows) == advance, (location, sample, rows)
            for sample in lifetimes:
                rows = shape(after, sample, flags)
                paths = positioned_paths(new, rows)
                assert sum(row[2] for row in rows) == sum(row[2] for row in shape(before, sample, flags)), (
                    location, sample)
                hook_index = next(i for i, (name, _) in enumerate(paths) if name == MARKER)
                letter_top = paths[hook_index + 1][1].bounds[3]
                gap = bar_bottom + rows[hook_index][5] - letter_top
                assert gap >= CLEARANCE + HOOK_LIFT, (location, sample, gap)
                assert all(abs(pathops.op(hook, p, pathops.PathOp.INTERSECTION).area) < 1
                           for name, hook in paths if name == MARKER
                           for other, p in paths if other != MARKER and len(p)), (location, sample, rows)
        rows = shape(after, "$(x)", {OFF_FEATURE: True})
        assert [row[0] for row in rows] == ["dollar", "parenleft", "x", "parenright"], rows
        assert rows[0][4] > 0 > rows[1][4] and all(row[2] == cell for row in rows), rows
    print(path.name, "verified at 25 axis settings", flush=True)


def proof(output, source, target, style, *, target_label="Delimiter trial",
          source_label="1.1.2", title="Delimiters, arrows and Rust lifetimes", lines=LINES):
    height = 242 + 51 * (len(lines) - 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1220" height="{height}" viewBox="0 0 1220 {height}">',
        f'<rect width="1220" height="{height}" fill="#f7f5ee"/>',
        f'<path d="M610 102V{height - 35}" stroke="#d6ddd7"/>',
        '<g font-family="Arial,sans-serif" fill="#182b31">',
        f'<text x="36" y="38" font-size="15">DAIKONIC TRANSIT CODE · {style.upper()}</text>',
        f'<text x="36" y="76" font-size="31" font-weight="700">{title}</text>',
        '</g>',
    ]
    for col, (file, label) in enumerate(((source, f"Before · {source_label}"), (target, f"After · {target_label}"))):
        x = 36 + 610 * col
        parts.append(f'<text x="{x}" y="125" fill="#526971" font-size="19" font-family="Arial">{label}</text>')
        panel = Panel(f"delim{col}", {"font": file.resolve()})
        for i, text in enumerate(lines):
            panel.text(text, x, 177 + 51 * i, 25, 400, "#182b31")
        parts.append(panel.body())
    dest = output / f"Code-Delimiters-{style.title()}.svg"
    dest.write_text("".join(parts) + "</svg>\n")
    return dest


def main():
    from code_working_spacing import build_fonts

    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--code-build", type=Path)
    parser.add_argument("--even-spread", action="store_true", help="proof equal dot spacing over two cells")
    args = parser.parse_args()
    output = args.output
    family = "Daikonic Transit Code Spread Review" if args.even_spread else FAMILY
    build_fonts(output, "1.1.3" if args.even_spread else "1.1.2", family,
                source=args.code_build, capital_spacing=True, delimiter_revision=True,
                even_spread=args.even_spread)
    pages = []
    for style, suffix in STYLES.items():
        source = RELEASE / ("DaikonicTransitCode" + suffix)
        trial = output / (family.replace(" ", "") + suffix)
        verify(source, trial, even_spread=args.even_spread)
        if args.even_spread:
            published = ROOT / "releases/1.1.3/code/VF" / source.name
            pages.append(proof(output, published, trial, style, source_label="1.1.3",
                               target_label="Balanced two-cell spread", title="Rest and spread spacing",
                               lines=SPREAD_LINES))
        else:
            pages.append(proof(output, source, trial, style))
    render_pdf(pages, output / ("Code-Spread.pdf" if args.even_spread else "Code-Delimiters.pdf"))
    for page in pages:
        render(page, scale=2, pdf=False)


if __name__ == "__main__":
    main()
