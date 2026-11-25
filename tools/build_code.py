"""Build and proof the Sans-derived Transit Code upright alphabet."""

from argparse import ArgumentParser
from hashlib import sha256
from html import escape
import json
from math import isclose
from pathlib import Path
from unicodedata import normalize

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor
from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont
from fontTools.varLib import build as build_variable
import uharfbuzz as hb

from audit import shape_from_glyphs, spans
from bundle_release import sanitize
from check_code_rebuild import RECIPE_PATH, ROOT, shape
from code_at import build_at
from code_compact_build import build_compact_glyphs, verify_compact
from code_delimiters import build_delimiters
from code_foundation import build_master, horizontal_mirror, sample_sans_weight, scale_ink_width, width_class_scales
from code_layout import align_pipe, build_layout, verify_layout
from code_lifetimes import verify_lifetimes
from code_math import ARROW_FAMILIES, ARROWS, COMPARISONS, SYMBOL_SAMPLES, build_math
from code_outlines import (
    SYMBOLS, build_composed, build_crossbar_letters, build_custom_letters, build_distinct_figures, build_g,
    build_horizontal_punctuation, inherit_width_scales,
)
from code_punctuation import build_diamond_punctuation
from code_syntax_build import build_syntax_glyphs, verify_syntax
from code_weight_width_trial import name_trial
from derive_weights import topology
from glyph_proof import build_proof
from italic_returns import raw_outline
from kern_clearance import ink_extents
from readme_features import highlight_code_line
from render_svg import render
from scaling_study import vertical_stem
from specimens import Panel
from system_metrics import set_vertical_metrics

WEIGHTS = {350: "Book", 400: "Regular", 500: "Medium"}
FEATURES = {"calt": False, "kern": False, "liga": False}
TYPESCRIPT_ALIGNMENT_SAMPLE = (
    "function clamp<T extends number>(",
    "  value: T, min: T, max: T,",
    "): T {",
    "  const clampLow = (n: T) => n <= min ? min : n;",
    "  const clampHigh = (n: T) => n >= max ? max : n;",
    '  if (min > max) throw new RangeError("min > max");',
    "  return min === max ? min : clampHigh(clampLow(value));",
    "}",
)
RUST_LIFETIME_SAMPLE = (
    "pub fn label<'a>(value: &'a str) -> &'a str {",
    "    let prefix = 'a';",
    '    let fallback: &\'static str = "unknown";',
    "    if value.starts_with(prefix) {",
    "        return value;",
    "    }",
    "    fallback",
    "}",
)
RUST_SCOPE_SAMPLE = (
    "pub fn read(text: &str) -> Option<u32> {",
    "    let parsed = text.trim().parse::<u32>();",
    "    // Keep only successful parses.",
    "    match parsed {",
    "        Ok(value) => Some(value),",
    "        Err(_) => None,",
    "    }",
    "}",
)
TYPESCRIPT_COMPACT_SAMPLE = (
    "interface Row { id: number }",
    "function pick(row?: Row): number {",
    "    const id = row?.id;",
    "    if (id == null || id != id) return -1;",
    "    if (id === 0 || id !== 42) return row!.id;",
    "    // Keep the reserved ID out.",
    "    return 0;",
    "}",
)
TYPESCRIPT_SYNTAX_SAMPLE = (
    "function headline(name: string, ...tags: string[]): string {",
    '    const parts = [`Hello, ${name}`, ...tags];',
    "    let flags = 0;",
    "    if (tags.length) {",
    "        flags |= 1;",
    "    }",
    '    return `${parts.join(", ")} (${flags})`;',
    "}",
)
SYNTAX_DETAIL_SAMPLE = (
    "let span = 1..4;    let bound = 1..=4;",
    "let [head, ...tail] = values;",
    "x .= delta;",
    "echo ${name} $[index] $(pwd)",
    "count := 0;     P |= q;     P |- q;",
    "## Overview     ### Inputs",
    "#### Results    ##### Detail",
    "###### Limits",
)


def alphabet_font(source, recipe, *, stage="Alphabet"):
    config = recipe["alphabet_review"]
    anchor = recipe["anchor"]
    weights = {int(weight): value for weight, value in config["weights"].items()}
    assert weights[anchor["code_weight"]] == anchor["sans_weight"]
    assert list(weights) == list(WEIGHTS)
    family = f"Daikonic Transit Code {stage} Review"
    math = stage in ("Operators", "Layout")
    custom_letters = stage == "Letters" or math

    masters = {weight: build_master(source, weights[weight], weight, config) for weight in WEIGHTS}
    scales, stems, width_report = width_class_scales(masters, recipe)
    if stage != "Alphabet":
        width_report["deferred"] = width_report["deferred"].replace("r", "")
    if custom_letters:
        letters = recipe["custom_lowercase_review"]
        followers = letters["width_followers"]
        inherit_width_scales(masters[400], scales, followers)
        width_report["followers"] = followers
        finished = set(letters["accepted_foundation"]) | set(followers) | set("ifgjlt")
        width_report["deferred"] = "".join(ch for ch in width_report["deferred"] if ch not in finished)

    for weight, master in masters.items():
        if custom_letters:
            build_at(master, recipe)
        scale_ink_width(master, scales, stems[weight])
        if stage != "Alphabet":
            build_composed(master, recipe)
    if custom_letters:
        build_custom_letters(masters.values(), recipe)
        for weight, master in masters.items():
            build_crossbar_letters(master, recipe)
            build_g(master, recipe)
            build_distinct_figures(master, recipe)
            build_horizontal_punctuation(master, recipe)
            build_diamond_punctuation(master, recipe)
            build_delimiters(master, recipe)
            if math:
                with sample_sans_weight(source, weights[weight]) as sans:
                    build_math(master, sans, recipe)
            if stage == "Layout":
                align_pipe(master, recipe["horizontal_punctuation_review"]["minus_center"])
                build_compact_glyphs(master, recipe)
                build_syntax_glyphs(master, recipe)

    designspace = DesignSpaceDocument()
    designspace.addAxis(AxisDescriptor(name="Weight", tag="wght", minimum=350, default=400, maximum=500))
    for weight, style in WEIGHTS.items():
        master = masters[weight]
        master["name"].setName(f"Version 0.100; Code {stage.lower()} review", 5, 3, 1, 0x409)
        name_trial(master, family, weight_style=style)
        location = {"Weight": weight}
        designspace.addSource(SourceDescriptor(
            name=style, familyName=family, styleName=style, location=location, font=master,
        ))
        designspace.addInstance(InstanceDescriptor(
            name=style, familyName=family, styleName=style, location=location,
        ))

    font, _, _ = build_variable(designspace)
    buildStatTable(font, [{
        "tag": "wght", "name": "Weight",
        "values": [{"name": style, "value": weight, "flags": 2 if weight == 400 else 0}
                   for weight, style in WEIGHTS.items()],
    }])
    name_trial(font, family, variable=True)
    font.recalcTimestamp = False
    return font, width_report


def measures(font, weight):
    glyphs = font.getGlyphSet(location={"wght": weight})
    return {
        name: {
            "ink_bounds": [round(v, 1) for v in shape_from_glyphs(glyphs, name).bounds],
            **({"vertical_stem": round(vertical_stem(shape_from_glyphs(glyphs, name), .4), 1)}
               if name in {"H", "n", "o"} else {}),
        }
        for name in "HxnromwW"
    }


def verify(font, path, config):
    engine = hb.Font(hb.Face(path.read_bytes()))
    cell = config["cell"]
    cmap = font.getBestCmap()
    glyphs_checked = set(cmap.values())
    metrics = dict(font["hmtx"].metrics)
    marks = [g for g in glyphs_checked if font["GDEF"].table.GlyphClassDef.classDefs.get(g) == 3]
    assert marks and all(metrics[g][0] == 0 for g in marks)
    for weight in range(350, 501, 25):
        engine.set_variations({"wght": weight})
        for text in ("HAMBURGEFONTS 0123456789", "abcdefghijklmnopqrstuvwxyz", "normalize(value)"):
            assert all(row[2] == cell for row in shape(engine, text, FEATURES)), (weight, text)
        for text in ("áéíóú ñçšž", "Český Ångström", "ŕř"):
            composed = shape(engine, text, FEATURES)
            decomposed = shape(engine, normalize("NFD", text), FEATURES)
            assert [row[:1] + row[2:] for row in composed] == [
                row[:1] + row[2:] for row in decomposed
            ], (weight, text)
        mark = shape(engine, "q́", FEATURES)
        assert len(mark) == 2 and sum(row[2] for row in mark) == cell and mark[-1][2] == 0, mark

    for name in ("i", "j", "adieresis", "nacute"):
        assert font["glyf"][name].isComposite(), name
    return {"weights": list(range(350, 501, 25)), "ascii_grid": cell, "zero_advance_marks": len(marks),
            "encoded_characters": len(cmap), "accent_equivalence": "NFC/NFD"}


def verify_latin_topology(source, candidate, config):
    for weight, donor_weight in config["weights"].items():
        donor = source.getGlyphSet(location={"wght": donor_weight})
        revised = candidate.getGlyphSet(location={"wght": int(weight)})
        for name in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
            assert topology(shape_from_glyphs(donor, name)) == topology(
                shape_from_glyphs(revised, name)
            ), (name, weight)


def verify_mirrors(source, candidate, cell, weights):
    pairs = {name: pair[0] for name in source.getGlyphOrder()
             if (pair := horizontal_mirror(source["glyf"][name]))
             and candidate["hmtx"][name][0] == candidate["hmtx"][pair[0]][0] == cell}
    for weight in weights:
        glyphs = candidate.getGlyphSet(location={"wght": weight})
        for name, donor in pairs.items():
            left, bottom, right, top = shape_from_glyphs(glyphs, donor).bounds
            expected = (cell - right, bottom, cell - left, top)
            actual = shape_from_glyphs(glyphs, name).bounds
            assert all(isclose(a, b, abs_tol=1e-6) for a, b in zip(actual, expected, strict=True)), (
                weight, name, donor, actual, expected
            )
    return pairs


def verify_composed(font, path, cell, weights):
    cmap = font.getBestCmap()
    assert all(cmap.get(code) == name for code, name in SYMBOLS.items())
    engine = hb.Font(hb.Face(path.read_bytes()))
    names = {name: [part.glyphName for part in font["glyf"][name].components]
             for name in ("universal", "existential", "notequal", "greaterequal")}
    assert names == {"universal": ["A"], "existential": ["E"],
                     "notequal": ["equal", "slash"], "greaterequal": ["lessequal"]}
    for name in (cmap[ord("ŕ")], cmap[ord("ř")]):
        assert font["glyf"][name].components[0].glyphName == "r"

    text = "".join(map(chr, SYMBOLS))
    for weight in weights:
        engine.set_variations({"wght": weight})
        rows = shape(engine, text, FEATURES)
        assert [(row[0], row[2]) for row in rows] == [(name, cell) for name in SYMBOLS.values()], (weight, rows)
        glyphs = font.getGlyphSet(location={"wght": weight})
        paths = {name: shape_from_glyphs(glyphs, name) for name in ("n", "r", *SYMBOLS.values())}
        assert topology(paths["n"]) == topology(paths["r"]), weight
        assert abs(paths["n"].bounds[3] - paths["r"].bounds[3]) <= 1, weight
        assert paths["notequal"].bounds[2] - paths["notequal"].bounds[0] < cell, weight
        for name in ("logicalnot", "notequal", "lessequal", "greaterequal"):
            assert topology(paths[name]) == ((2 if name in ("lessequal", "greaterequal") else 1), 0), (name, weight)
    return names


def verify_math(font, path, recipe):
    config = recipe["alphabet_review"]
    axis = recipe["horizontal_punctuation_review"]["minus_center"]
    settings = recipe["math_review"]
    cell, pitch = config["cell"], settings["rule_pitch"]
    tokens = COMPARISONS | ARROWS
    cmap = font.getBestCmap()
    repeated = ARROWS["->>"]
    parts = font["glyf"][repeated].components
    assert [part.glyphName for part in parts] == [repeated + ".shaft", "operator.arrowHead", "operator.arrowHead"]
    comparison = font["glyf"]["lessequal"].components
    assert [part.glyphName for part in comparison] == ["less", "operator.comparisonRule"]
    engine = hb.Font(hb.Face(path.read_bytes()))
    for weight in range(350, 501, 5):
        engine.set_variations({"wght": weight})
        glyphs = font.getGlyphSet(location={"wght": weight})
        for token, name in tokens.items():
            expected = cell if token in ("<=", ">=") else 2 * cell
            shaped = shape(engine, token, {})
            assert len(shaped) == 1 and shaped[0][:3] == [name, 0, expected], (weight, token, shaped)
            literal = shape(engine, token, FEATURES)
            assert [(row[0], row[2]) for row in literal] == [(cmap[ord(c)], cell) for c in token]
        for character in "".join(ARROW_FAMILIES) + "+−×÷=≠<>≤≥*~":
            name = cmap[ord(character)]
            assert shape(engine, character, FEATURES)[0][2] == cell
            outline = shape_from_glyphs(glyphs, name)
            left, bottom, right, top = outline.bounds
            assert 0 <= left < right <= cell and abs((top + bottom) / 2 - axis) <= 1, (weight, character)
            if character in "".join(ARROW_FAMILIES):
                assert topology(outline) == (1, int(character in "⇔⇕")), (weight, character)
        for name, probe, count in (("equal", cell / 2, 2),
                                    (COMPARISONS["==="], cell, 3),
                                    (ARROWS["=>"], cell / 2, 2)):
            bars = spans(shape_from_glyphs(glyphs, name), probe, 0)
            midpoints = [(bottom + top) / 2 for bottom, top in bars]
            assert len(bars) == count and all(
                abs(second - first - pitch) <= 1 for first, second in zip(midpoints, midpoints[1:])
            ), (weight, name, bars)
        lower, upper = spans(shape_from_glyphs(glyphs, "equal"), cell / 2, 0)
        _, first_head, second_head = raw_outline(glyphs, repeated).contours
        attached, detached = (ink_extents(head, step=1) for head in (first_head, second_head))
        gap = min(detached[row][0] - attached[row][1] for row in attached.keys() & detached.keys())
        assert abs(gap - (upper[0] - lower[1])) <= 1.5, (weight, gap, lower, upper)
        for token in ARROWS:
            assert topology(shape_from_glyphs(glyphs, ARROWS[token])) == (1 + (len(token) == 3), 0), (weight, token)

    caret_list = font["GDEF"].table.LigCaretList
    carets = {name: [value.Coordinate for value in glyph.CaretValue]
              for name, glyph in zip(caret_list.Coverage.glyphs, caret_list.LigGlyph, strict=True)}
    for token, name in tokens.items():
        advance = font["hmtx"][name][0]
        assert carets[name] == [advance * i // len(token) for i in range(1, len(token))], token
    return {"math_axis": axis, "bar_center_spacing": pitch, "ligature_carets": {
        token: carets[name] for token, name in tokens.items()
    }}


def signed_units(delta):
    return f"{delta:+.0f}" if round(delta) else "0"


def cell_guides(fonts, sample, x, size, top, bottom, delta_y, cell):
    cmaps = [font.getBestCmap() for font in fonts]
    names = [[cmap[ord(char)] for char in sample] for cmap in cmaps]
    upm = fonts[0]["head"].unitsPerEm
    assert all(font["head"].unitsPerEm == upm for font in fonts)
    assert all(font["hmtx"][name][0] == cell
               for font, run in zip(fonts, names, strict=True) for name in run), sample
    pitch = size * cell / upm
    boundaries = " ".join(f"M{x + pitch * index:.3f} {top}V{bottom}"
                          for index in range(len(sample) + 1))
    yield f'<path d="{boundaries}" stroke="#d5e1e2" stroke-width=".65"/>'
    if delta_y is None:
        return
    glyph_sets = [font.getGlyphSet() for font in fonts]
    for index, pair in enumerate(zip(*names, strict=True)):
        widths = []
        for glyph_set, name in zip(glyph_sets, pair, strict=True):
            left, _, right, _ = shape_from_glyphs(glyph_set, name).bounds
            widths.append(right - left)
        delta = round(widths[1] - widths[0])
        color = "#14675d" if delta > 0 else "#96432e" if delta < 0 else "#677b7f"
        center = x + pitch * (index + .5)
        yield (f'<text x="{center:.3f}" y="{delta_y}" text-anchor="middle" '
               f'font-size="8.5" fill="{color}">{signed_units(delta)}</text>')


def comparison(candidate, reference, output, width_report, cell, measurements):
    width, height = 1190, 1046
    sheets = [Panel("released", {"font": str(reference.resolve())}),
              Panel("candidate", {"font": str(candidate.resolve())})]
    bands = (
        (34, 76, 115, (
            (166, "Lowercase", "abcdefghijklmnopqrstuvwxyz", 30, True),
            (650, "Uppercase foundation", "ABCDEFGHIJKLMNOPQRSTUVWXYZ", 30, True),
        )),
        (174, 207, 239, (
            (166, "12 px", "let trim = n;", 12, False),
            (412, "14 px", "rows[index].value", 14, False),
            (658, "16 px", "fn narrow(n: u8)", 16, False),
            (910, "Digit foundation", "0123456789", 30, True),
        )),
    )
    rows = [
        f'<rect width="{width}" height="{height}" fill="#eaf1f0"/>',
        '<text x="36" y="46" font-size="31" font-weight="700">Transit Code · Upright alphabet</text>',
        f'<text x="37" y="74" font-size="15" fill="#415d62">'
        'Lowercase width classes · Published Code 1.042 above the candidate</text>',
        f'<text x="1154" y="46" text-anchor="end" font-size="13" fill="#415d62">{cell}-unit cells · Width differences in design units</text>',
        '<text x="1154" y="74" text-anchor="end" font-size="13">'
        '<tspan fill="#14675d">+ candidate wider</tspan><tspan fill="#415d62">  ·  </tspan>'
        '<tspan fill="#96432e">− 1.042 wider</tspan></text>',
    ]
    for index, (weight, style) in enumerate(WEIGHTS.items()):
        y = 101 + index * 285
        fonts = [panel.font(weight)[0] for panel in sheets]
        previous, current = (measurements[weight][key] for key in ("released", "candidate"))
        stem_deltas = (current[name]["vertical_stem"] - previous[name]["vertical_stem"] for name in "Hno")
        stems = " · ".join(f"{name} {signed_units(delta)}" for name, delta in zip("Hno", stem_deltas, strict=True))
        rows.extend((
            f'<rect x="36" y="{y}" width="1118" height="274" rx="6" fill="#f8faf9" stroke="#c7d6d7"/>',
            f'<text x="54" y="{y + 34}" font-size="16" font-weight="700">{style} {weight}</text>',
            f'<text x="1136" y="{y + 34}" text-anchor="end" font-size="12" fill="#415d62">Stem Δ · {stems}</text>',
            f'<path d="M54 {y + 151}H1136" stroke="#dce5e5"/>',
        ))
        for heading, old_baseline, new_baseline, specimens in bands:
            rows.append(f'<text x="54" y="{y + new_baseline + 23}" font-size="11" fill="#415d62">Ink width Δ</text>')
            for x, label, sample, size, annotate in specimens:
                rows.append(f'<text x="{x}" y="{y + heading}" font-size="13" fill="#415d62">{label}</text>')
                rows.extend(cell_guides(fonts, sample, x, size, y + heading + 7, y + new_baseline + 10,
                                        y + new_baseline + 23 if annotate else None, cell))
            for panel, label, baseline in zip(
                sheets, ("1.042", "Candidate"), (old_baseline, new_baseline), strict=True
            ):
                rows.append(f'<text x="54" y="{y + baseline}" font-size="13" fill="#415d62">{label}</text>')
                for x, _, sample, size, _ in specimens:
                    panel.text(sample, x, y + baseline, size, weight, "#153b40", features=FEATURES)
    active = [(name, row) for name, row in width_report["classes"].items() if row["sample"]]
    for index, (name, row) in enumerate(active):
        x = 37 + index * 230
        rows.extend((
            f'<text x="{x}" y="980" font-size="15" font-weight="700">{name} · {row["factor"] - 1:+.1%}</text>',
            f'<text x="{x}" y="1000" font-family="monospace" font-size="13">{row["sample"]}</text>',
        ))
    deferred = " ".join(width_report["deferred"])
    rows.append(f'<text x="37" y="1025" font-size="13" fill="#415d62">Custom drawings pending · {deferred}</text>')
    write_comparison(output, width, height, rows, sheets)


def write_comparison(output, width, height, rows, sheets):
    output.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Arial,sans-serif" fill="#153b40">'
        + '<defs>' + ''.join(path for panel in sheets for path in panel.defs.values()) + '</defs>'
        + ''.join(rows) + ''.join(line for panel in sheets for line in panel.elements) + '</svg>'
    )


def detail_comparison(candidate, reference, output, title, samples, subtitle="Published Code 1.042 above the candidate",
                      *, features=FEATURES):
    width = 1050
    row_height = 207 if reference else 134
    height = 123 + 3 * row_height
    samples_to_draw = [(Panel("candidate", {"font": str(candidate.resolve())}), "Candidate",
                        157 if reference else 92)]
    if reference:
        samples_to_draw.insert(0, (Panel("released", {"font": str(reference.resolve())}), "1.042", 92))
    rows = [
        f'<rect width="{width}" height="{height}" fill="#eaf1f0"/>',
        f'<text x="36" y="46" font-size="31" font-weight="700">Transit Code · {title}</text>',
        f'<text x="37" y="74" font-size="15" fill="#415d62">{subtitle}</text>',
    ]
    for index, (weight, style) in enumerate(WEIGHTS.items()):
        y = 101 + index * row_height
        rows.extend((
            f'<rect x="36" y="{y}" width="978" height="{row_height - 20}" rx="6" fill="#f8faf9" stroke="#c7d6d7"/>',
            f'<text x="54" y="{y + 32}" font-size="16" font-weight="700">{style} {weight}</text>',
        ))
        for x, label, _ in samples:
            rows.append(f'<text x="{x}" y="{y + 32}" font-size="13" fill="#415d62">{label}</text>')
        for panel, label, offset in samples_to_draw:
            rows.append(f'<text x="54" y="{y + offset}" font-size="13" fill="#415d62">{label}</text>')
            for x, _, sample in samples:
                panel.text(sample, x, y + offset, 49, weight, "#153b40", features=features)
    write_comparison(output, width, height, rows, [panel for panel, _, _ in samples_to_draw])


def operator_detail(candidate, output, config, axis):
    width, height = 1050, 744
    upm, cell = config["units_per_em"], config["cell"]
    size = 150
    samples = ((154, "->>"), (347, "<<-"), (548, "<"), (639, "≤"),
               (730, ">"), (821, "≥"), (912, "="))
    panel = Panel("operators", {"font": str(candidate.resolve())})
    rows = [
        f'<rect width="{width}" height="{height}" fill="#eaf1f0"/>',
        '<text x="36" y="46" font-size="31" font-weight="700">Transit Code · Operator detail</text>',
        '<text x="37" y="74" font-size="15" fill="#415d62">&lt; and &gt; share their chevrons with ≤ and ≥.</text>',
    ]
    for x, sample in samples:
        cells = 2 if sample in ARROWS else 1
        center = x + cells * cell * size / upm / 2
        rows.append(f'<text x="{center:.2f}" y="110" font-size="16" text-anchor="middle">{escape(sample)}</text>')
    for index, (weight, style) in enumerate(WEIGHTS.items()):
        y = 211 + 207 * index
        rows.extend((
            f'<rect x="36" y="{y - 86}" width="978" height="172" rx="6" fill="#f8faf9" stroke="#c7d6d7"/>',
            f'<text x="54" y="{y + 5}" font-size="16" font-weight="700">{style} {weight}</text>',
            f'<path d="M150 {y}H995" stroke="#bed0d0" stroke-dasharray="3 5" fill="none"/>',
        ))
        for x, sample in samples:
            panel.text(sample, x, y + axis * size / upm, size, weight, "#153b40",
                       features={**FEATURES, "liga": True})
    write_comparison(output, width, height, rows, [panel])


def angle_context_detail(candidate, output, config, axis):
    width, height = 1050, 744
    upm = config["units_per_em"]
    size = 34
    samples = ((158, "Comparisons and generics", "a<>b Vec<>"),
               (377, "Nested and unmatched", "Vec<Vec<T>> T>"),
               (686, "Delimiter alignment", "() [] {} | <[T]>"))
    panel = Panel("context", {"font": str(candidate.resolve())})
    rows = [
        f'<rect width="{width}" height="{height}" fill="#eaf1f0"/>',
        '<text x="36" y="46" font-size="31" font-weight="700">Transit Code · Contextual delimiters</text>',
        '<text x="37" y="74" font-size="15" fill="#415d62">Tall generic pairs and enclosure alignment on the same vertical center.</text>',
    ]
    for index, (weight, style) in enumerate(WEIGHTS.items()):
        y = 101 + 207 * index
        rows.append(f'<rect x="36" y="{y}" width="978" height="187" rx="6" fill="#f8faf9" stroke="#c7d6d7"/>')
        rows.append(f'<text x="54" y="{y + 32}" font-size="16" font-weight="700">{style} {weight}</text>')
        for x, label, _ in samples:
            rows.append(f'<text x="{x}" y="{y + 32}" font-size="13" fill="#415d62">{label}</text>')
        for offset, label, enabled in ((90, "On", True), (151, "Off", False)):
            center = y + offset - axis * size / upm
            rows.append(f'<path d="M676 {center:.2f}H994" stroke="#bed0d0" stroke-dasharray="3 5" fill="none"/>')
            rows.append(f'<text x="54" y="{y + offset}" font-size="13" fill="#415d62">{label}</text>')
            for x, _, sample in samples:
                panel.text(sample, x, y + offset, size, weight, "#153b40",
                           features={"calt": enabled, "liga": True, "kern": False})
    write_comparison(output, width, height, rows, [panel])


def code_review_proof(output, config, title, subtitle, sample, cuts, *, axis=None, extra_keywords=(), extra_types=()):
    width, height = 1050, 744
    weight, size, leading = 400, 26, 28
    x = 58
    scale = size / config["units_per_em"]
    assert x + max(map(len, sample)) * config["cell"] * scale < width - 36
    rows = [
        f'<rect width="{width}" height="{height}" fill="#0d1218"/>',
        f'<text x="36" y="48" font-size="31" font-weight="700" fill="#eeeddb">{escape(title)}</text>',
        f'<text x="37" y="76" font-size="15" fill="#aebbc6">{escape(subtitle)}</text>',
    ]
    panels = []
    for index, (label, font_path, features) in enumerate(cuts):
        y = 103 + index * 310
        rows.append(f'<rect x="36" y="{y}" width="978" height="282" rx="6" fill="#141c24" stroke="#2c3945"/>')
        rows.append(f'<text x="{x}" y="{y + 31}" font-size="16" font-weight="700" fill="#aebbc6">{label}</text>')
        panel = Panel(f"review-{index}", {"font": str(font_path.resolve())})
        for row, line in enumerate(sample):
            baseline = y + 65 + row * leading
            if axis is not None:
                center = baseline - axis * scale
                rows.append(f'<path d="M{x} {center:.2f}H992" stroke="#344654" stroke-dasharray="2 5"/>')
            panel.text(line, x, baseline, size, weight, "#eeeddb", features=features)
            highlight_code_line(panel, line, features, extra_keywords=extra_keywords, extra_types=extra_types)
        panels.append(panel)
    write_comparison(output, width, height, rows, panels)


def typescript_operator_proof(candidate, reference, output, config, axis):
    features = {"calt": True, "liga": True, "kern": False, "ss02": False, "ss04": True, "ss06": False, "ss07": True}
    cuts = (("Published 1.042", reference, features), ("Rebuilt Code", candidate, features))
    code_review_proof(output, config, "TypeScript · Operator alignment",
                      "Regular 400 · Dotted guide marks the math axis.", TYPESCRIPT_ALIGNMENT_SAMPLE, cuts, axis=axis,
                      extra_keywords=("extends", "function", "if", "new", "throw"), extra_types=("number",))


def rust_lifetime_proof(candidate, output, config):
    features = {"calt": True, "liga": True, "kern": False}
    cuts = (("Hairlining on · default", candidate, features),
            ("Hairlining off · left hook", candidate, {**features, "ss07": True}))
    code_review_proof(output, config, "Rust · Lifetime markers",
                      "Regular 400 · In both settings the character literal keeps its straight quotes.",
                      RUST_LIFETIME_SAMPLE, cuts, extra_keywords=("if",))


def compact_operator_proofs(candidate, output, config):
    features = {"calt": True, "liga": True, "kern": False}
    rust = output / "Code-Rust-Scope.svg"
    code_review_proof(
        rust, config, "Rust · Scope and turbofish",
        "Regular 400 · The scope separator and comment slashes each use one cell.",
        RUST_SCOPE_SAMPLE, (("Contextual alternates on", candidate, features),
                            ("Contextual alternates off", candidate, {**features, "calt": False})),
        extra_keywords=("match",), extra_types=("u32",),
    )
    typescript = output / "Code-TypeScript-Compact-Operators.svg"
    code_review_proof(
        typescript, config, "TypeScript · Compact operators",
        "Regular 400 · Access, comment and OR ligatures keep their one-cell forms in both settings.",
        TYPESCRIPT_COMPACT_SAMPLE, (("Loose Equality off · default", candidate, features),
                                   ("Loose Equality on", candidate, {**features, "ss06": True})),
        extra_keywords=("interface", "function", "if", "null"), extra_types=("number",),
    )
    return rust, typescript


def syntax_ligature_proofs(candidate, output, config):
    features = {"calt": True, "liga": True, "kern": False}
    cuts = (("Contextual alternates on", candidate, features),
            ("Contextual alternates off", candidate, {**features, "calt": False}))
    detail = output / "Code-Syntax-Ligatures.svg"
    code_review_proof(
        detail, config, "Code · Syntax ligatures",
        "Regular 400 · Ranges, interpolation, turnstiles, and joined hashes retain their grid positions.",
        SYNTAX_DETAIL_SAMPLE, cuts,
    )
    typescript = output / "Code-TypeScript-Syntax-Ligatures.svg"
    code_review_proof(
        typescript, config, "TypeScript · Syntax ligatures",
        "Regular 400 · Spread, template interpolation, and bitwise assignment.",
        TYPESCRIPT_SYNTAX_SAMPLE, cuts, extra_keywords=("function", "if"), extra_types=("string",),
    )
    return detail, typescript


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=RECIPE_PATH)
    parser.add_argument("--output", type=Path, required=True)
    stages = parser.add_mutually_exclusive_group()
    stages.add_argument("--composed", action="store_true", help="also build the donor-derived review glyphs")
    stages.add_argument("--letters", action="store_true", help="add the custom lowercase review")
    stages.add_argument("--operators", action="store_true", help="add the math signs and operator ligatures")
    stages.add_argument("--layout", action="store_true", help="add contextual angle pairs and delimiter alignment")
    parser.add_argument("--render", action="store_true", help="also write the comparison as PNG and PDF")
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text())
    config = recipe["alphabet_review"]
    source = ROOT / (recipe["fonts"]["sans"] + "-VF.ttf")
    reference = ROOT / (recipe["fonts"]["code"] + "-VF.ttf")
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    stage = "Layout" if args.layout else "Operators" if args.operators else (
        "Letters" if args.letters else "Composed" if args.composed else "Alphabet"
    )
    candidate = output / f"DaikonicTransitCode{stage}Review-VF.ttf"
    with TTFont(source, recalcTimestamp=False) as sans:
        font, width_report = alphabet_font(sans, recipe, stage=stage)
        if stage == "Layout":
            build_layout(font, recipe)
        verify_latin_topology(sans, font, config)
        vertical = set_vertical_metrics(
            font, minimum_ascent=config["line_metrics"]["ascent"],
            maximum_descent=config["line_metrics"]["descent"],
        )
        font["OS/2"].sTypoAscender = vertical["ascent"]
        font["OS/2"].sTypoDescender = vertical["descent"]
        font.save(candidate)

    with TTFont(candidate) as built, TTFont(reference) as released, TTFont(source) as sans:
        check = verify(built, candidate, config)
        check["horizontal_mirrors"] = verify_mirrors(sans, built, config["cell"], check["weights"])
        if stage != "Alphabet":
            check["composed_components"] = verify_composed(built, candidate, config["cell"], check["weights"])
        if stage in ("Operators", "Layout"):
            check["operators"] = verify_math(built, candidate, recipe)
        if stage == "Layout":
            check["contextual_delimiters"] = verify_layout(built, candidate, recipe, check["weights"])
            check["rust_lifetimes"] = verify_lifetimes(built, candidate, config["cell"], check["weights"])
            check["compact_operators"] = verify_compact(built, candidate, recipe, check["weights"])
            check["syntax_ligatures"] = verify_syntax(built, candidate, recipe, check["weights"])
        sanitize(built)
        report = {
            "source": str(source.relative_to(ROOT)), "source_sha256": sha256(source.read_bytes()).hexdigest(),
            "comparison_reference": str(reference.relative_to(ROOT)),
            "construction": config,
            "width_classes": width_report,
            "validation": check,
            "vertical_metrics": vertical,
            "measurements": {weight: {"candidate": measures(built, weight), "released": measures(released, weight)}
                             for weight in WEIGHTS},
        }
    (output / "alphabet.json").write_text(json.dumps(report, indent=2) + "\n")
    build_proof(candidate, output / "glyphs", svg_only=True, interactive_axes=True)
    panel = output / "Code-Alphabet-Comparison.svg"
    comparison(candidate, reference, panel, width_report, config["cell"], report["measurements"])
    panels = [panel]
    if stage in ("Operators", "Layout"):
        math_panel = output / "Code-Math-Signs.svg"
        detail_comparison(candidate, reference, math_panel, "Math signs",
                          tuple(zip((166, 447, 720), ("Arithmetic", "Comparisons", "Other signs"), SYMBOL_SAMPLES)),
                          "Published Code 1.042 above the candidate · shared math axis and bar weight")
        arrow_panel = output / "Code-Math-Arrows.svg"
        single, double = ARROW_FAMILIES
        detail_comparison(candidate, reference, arrow_panel, "Arrows",
                          ((166, "Single shafts", " ".join(single)), (525, "Double shafts", " ".join(double))))
        ligature_panel = output / "Code-Operator-Ligatures.svg"
        detail_comparison(candidate, reference, ligature_panel, "Operator ligatures",
                          ((166, "Comparisons", "== === != !=="), (500, "Order", "<= >="),
                           (613, "Arrows", "-> ->> => <- <<-")),
                          "Published Code 1.042 above the candidate · default ligatures enabled",
                          features={"calt": True, "liga": True, "kern": False})
        detail_panel = output / "Code-Operator-Detail.svg"
        operator_detail(candidate, detail_panel, config, recipe["horizontal_punctuation_review"]["minus_center"])
        panels.extend((math_panel, arrow_panel, ligature_panel, detail_panel))
        if stage == "Layout":
            context_panel = output / "Code-Contextual-Delimiters.svg"
            axis = recipe["horizontal_punctuation_review"]["minus_center"]
            angle_context_detail(candidate, context_panel, config, axis)
            code_panel = output / "Code-TypeScript-Operator-Alignment.svg"
            typescript_operator_proof(candidate, reference, code_panel, config, axis)
            rust_panel = output / "Code-Rust-Lifetimes.svg"
            rust_lifetime_proof(candidate, rust_panel, config)
            panels.extend((context_panel, code_panel, rust_panel))
            panels.extend(compact_operator_proofs(candidate, output, config))
            panels.extend(syntax_ligature_proofs(candidate, output, config))
    elif stage == "Composed":
        composed_panel = output / "Code-Composed-Comparison.svg"
        detail_comparison(candidate, reference, composed_panel, "Composed glyphs",
                          ((166, "Stem and shoulder", "n r   ŕ ř"), (447, "Quantifiers", "A ∀   E ∃"),
                           (720, "Operators", "= ¬ ≠ ≤ ≥")))
        panels.append(composed_panel)
    elif stage == "Letters":
        letters_panel = output / "Code-Custom-Lowercase.svg"
        detail_comparison(candidate, reference, letters_panel, "Custom lowercase",
                          ((166, "Bowl width", "a s   a n"), (447, "Letter spacing", "banana"),
                           (720, "Hook donor and accented forms", "l i í ï in")),
                          "Published Code 1.042 above the candidate · a uses the width scale from s")
        panels.append(letters_panel)
        hook_panel = output / "Code-Hook-Letters.svg"
        detail_comparison(candidate, reference, hook_panel, "Hook letters",
                          ((166, "Trimmed upper hooks", "i j l"), (447, "Accents", "í ĵ ľ ĺ"),
                           (720, "In text", "jill nil")))
        panels.append(hook_panel)
        crossbar_panel = output / "Code-Crossbar-Letters.svg"
        detail_comparison(candidate, reference, crossbar_panel, "Crossbars and hooks",
                          ((166, "Lower return", "t ț ţ"), (447, "Flipped upper return", "f ft ff"),
                           (720, "In text", "after fit")))
        panels.append(crossbar_panel)
        bowl_panel = output / "Code-G-Bowl.svg"
        detail_comparison(candidate, reference, bowl_panel, "Lowercase g",
                          ((166, "Upper bowl", "a g o"), (447, "Accents", "g ğ ġ"),
                           (720, "g and y in text", "gray day")))
        panels.append(bowl_panel)
        figures_panel = output / "Code-Letter-Figure-Distinctions.svg"
        detail_comparison(candidate, reference, figures_panel, "Letter and figure distinctions",
                          ((166, "Narrow letters and one", "I l 1 i"), (447, "Zero and capital O", "0 O 00"),
                           (720, "In an identifier", "IO10l")))
        panels.append(figures_panel)
        punctuation_panel = output / "Code-Underscore-and-Hyphen.svg"
        detail_comparison(candidate, reference, punctuation_panel, "Underscore and hyphen",
                          ((166, "Inline underscore", "snake_x"), (447, "Adjacent underscores", "__init__"),
                           (720, "Hyphen and minus", "x-y x−y")))
        panels.append(punctuation_panel)
        at_panel = output / "Code-At-Sign.svg"
        detail_comparison(candidate, reference, at_panel, "At sign",
                          ((166, "Body and shell", "a c @"), (447, "Height against o", "o@o"),
                           (720, "In an address", "a@host")))
        panels.append(at_panel)
        diamonds_panel = output / "Code-Diamond-Punctuation.svg"
        detail_comparison(candidate, reference, diamonds_panel, "Diamond punctuation",
                          ((166, "Comma, semicolon, period, colon", "a,a;a.a:a"), (447, "Ellipsis and middle dot", "a…a·a"),
                           (720, "Sentence marks", "¿Qué?!")))
        panels.append(diamonds_panel)
        quote_panel = output / "Code-Quotation-Marks.svg"
        detail_comparison(candidate, None, quote_panel, "Quotation marks",
                          ((166, "Straight quotes", "'a' \"b\""), (447, "Opening and closing", "‘a’ “b”"),
                           (720, "Low quotes", "‚a‘ „b“")),
                          "Smaller straight quotes and a continuous outside curve on the shared comma outline")
        panels.append(quote_panel)
        comma_panel = output / "Code-Comma-and-Closing-Quote.svg"
        detail_comparison(candidate, None, comma_panel, "Comma and closing quote",
                          ((166, "Closing and low quotes", "’ ‚"), (447, "Comma and semicolon", "a,a;a"),
                           (720, "With the period and colon", "a.,;:a")),
                          "One outside curve runs from the diamond's right vertex to the lower tail tip")
        panels.append(comma_panel)
        compound_panel = output / "Code-Compound-Punctuation.svg"
        detail_comparison(candidate, reference, compound_panel, "Sentence punctuation",
                          ((166, "Single marks", "a!a a?a"), (447, "Repeated marks", "!! ‼ ?? ⁇"),
                           (720, "Mixed marks", "?! ⁈ !? ⁉")),
                          "Published Code 1.042 above the candidate · typed pairs followed by one-cell forms")
        panels.append(compound_panel)
        delimiters_panel = output / "Code-Delimiters.svg"
        detail_comparison(candidate, reference, delimiters_panel, "Delimiters",
                          ((166, "Parentheses", "(map(x))"), (447, "Brackets", "[a[b]]"),
                           (720, "Braces", "{a{b}}")),
                          "Published Code 1.042 above the candidate · base outlines")
        panels.append(delimiters_panel)
    if args.render:
        for proof in panels:
            render(proof, scale=2)
    print(f"Verified Code {stage.lower()} review and wrote the proof to {output}")


if __name__ == "__main__":
    main()
