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
from code_layout import angle_styles
from code_math import BIDIRECTIONAL_ARROWS
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
LINES = (
    "f((x))  map(a, b)  $(value)",
    "a & b  &'a  &'static  &'T",
    "'a  'g  'l  'T  'Á  'a'",
    "<'a>  <x>  <'a'>  Vec<Vec<T>>",
    "<>    a <> b    a<>b    Vec<>T",
    "vec<>  Vec<Vec<>>  Vec< <> >",
    "->  <-  <->  =>  <=>  ->>  <<-",
    "fn read<'a>(x: &'a T) -> &'a T { x }",
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
        rise = max(0, ceil((top + CLEARANCE - lowest_bar) / HEIGHT_STEP) * HEIGHT_STEP)
        if rise:
            heights.setdefault(rise, []).append(name)

    # Decomposed accents can sit above the precomposed cap. Use the same
    # highest group with a little more clearance for the combining form.
    marked_rise = max(heights, default=0) + HEIGHT_STEP * 2
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


def verify(source, path):
    before, after = [hb.Font(hb.Face(p.read_bytes())) for p in (source, path)]
    prior, font = TTFont(source), TTFont(path)
    glyphs = set(font.getGlyphOrder())
    assert {name for name in glyphs if name.startswith(("parenleft", "parenright", MARKER))} == {
        "parenleft", "parenright", MARKER}
    pairs = {
        "<'a>": [True, True], "<'a'>": [True, True], "<x>": [True, True],
        "a<b>c": [True, True], "Vec<Vec<T>>": [True] * 4,
        "Vec<Vec<>>": [True] * 4, "<>": [True, True], "<>T": [True, True],
        "Vec<>": [True, True], "HashMap<>()": [True, True], "Vec<>.new": [True, True],
        "a<>b": [True, True], "Vec<>T": [True, True], "Vec<>_item": [True, True],
        "vec<>": [True, True], "vec::<>": [True, True],
        "a <> b": [False, False], "a\u00a0<>\u00a0b": [False, False],
        "a<> b": [True, True], "a <>b": [True, True], "Vec< >": [True, True],
        "Vec< <> >": [True, False, False, True],
        "<x": [False], "x>": [False], "[<x": [False],
        "Vec<\nx>": [False, False], "Vec<" + "t" * 60 + ">": [True, True],
        "Vec<" + "t" * 61 + ">": [False, False],
    }
    controls = ("a <= b >= c", "a <- b -> c", "'a'", "'_'", "'💡'")
    lifetimes = ("'a", "'static", "'l", "'T", "'Á", "'f\u0301", "'Q\u0308", "'_", "'ff", "&'a",
                 "&'T", "<'a>", "Vec<'l>", "use<'a, 'T>")
    for weight, width in product((350, 375, 400, 450, 500), (94, 97, 100, 104, 108)):
        location = {"wght": weight, "wdth": width}
        for engine in (before, after):
            engine.set_variations(location)
        cell = width * 6
        old, new = [f.getGlyphSet(location=location) for f in (prior, font)]
        amp = [shape_from_glyphs(gs, "ampersand").bounds for gs in (old, new)]
        assert amp[1][2] - amp[1][0] > amp[0][2] - amp[0][0] + 12, location
        for sample in controls:
            assert shape(before, sample, {}) == shape(after, sample, {}), (location, sample)
        for flags in ({}, {"ss07": True}):
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
            rows = shape(after, "$(x)", flags)
            assert [row[0] for row in rows] == ["dollar", "parenleft", "x", "parenright"], rows
            assert rows[0][4] > 0 > rows[1][4] and all(row[2] == cell for row in rows), rows
            for sample in lifetimes:
                rows = shape(after, sample, flags)
                x = 0
                paths = []
                for name, _, advance, _, dx, dy in rows:
                    p = shape_from_glyphs(new, name)
                    paths.append((name, p.transform(translateX=x + dx, translateY=dy)))
                    x += advance
                assert x == sum(row[2] for row in shape(before, sample, flags)), (location, sample)
                assert any(name == MARKER for name, _ in paths), (location, sample)
                assert all(abs(pathops.op(hook, p, pathops.PathOp.INTERSECTION).area) < 1
                           for name, hook in paths if name == MARKER
                           for other, p in paths if other != MARKER and len(p)), (location, sample, rows)
    print(path.name, "verified at 25 axis settings", flush=True)


def proof(output, source, target, style):
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1220" height="600" viewBox="0 0 1220 600">',
        '<rect width="1220" height="600" fill="#f7f5ee"/>',
        '<path d="M610 102V565" stroke="#d6ddd7"/>',
        '<g font-family="Arial,sans-serif" fill="#182b31">',
        f'<text x="36" y="38" font-size="15">DAIKONIC TRANSIT CODE · {style.upper()}</text>',
        '<text x="36" y="76" font-size="31" font-weight="700">Delimiters, arrows and Rust lifetimes</text>',
        '</g>',
    ]
    for col, (file, title) in enumerate(((source, "Before · 1.1.2"), (target, "After · Delimiter trial"))):
        x = 36 + 610 * col
        parts.append(f'<text x="{x}" y="125" fill="#526971" font-size="19" font-family="Arial">{title}</text>')
        panel = Panel(f"delim{col}", {"font": file.resolve()})
        for i, text in enumerate(LINES):
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
    args = parser.parse_args()
    output = args.output
    build_fonts(output, "1.1.2", FAMILY, source=args.code_build, capital_spacing=True,
                delimiter_revision=True)
    pages = []
    for style, suffix in STYLES.items():
        source = RELEASE / ("DaikonicTransitCode" + suffix)
        trial = output / (FAMILY.replace(" ", "") + suffix)
        verify(source, trial)
        pages.append(proof(output, source, trial, style))
    render_pdf(pages, output / "Code-Delimiters.pdf")
    for page in pages:
        render(page, scale=2, pdf=False)


if __name__ == "__main__":
    main()
