"""Build a local Code trial for spacing the parts of ligatures with GPOS."""

from argparse import ArgumentParser
from copy import deepcopy
from itertools import product
import json
from pathlib import Path

from fontTools.misc.roundTools import otRound
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib.varStore import VarStoreInstancer
import uharfbuzz as hb

from build_code import RECIPE_PATH, alphabet_font, code_review_proof
from build_code_italic import build_italic
from bundle_release import sanitize
from check_code_rebuild import fixtures, shape
from code_compact_build import CONTEXT_PAIRS, DIRECT, LOOSE_NAMES, SCOPE
from code_layout import build_layout
from code_gpos_lateral import (
    add_horizontal_positions, add_lateral_positioning, component_positions,
    retire_lateral_drawings, split_advance,
)
from code_math import ARROWS, COMPARISONS
from code_spread import bracket_openers, register_spread_context
from code_syntax_build import BRACKET_SPREAD_SUFFIX, SPREAD_SUFFIX, spread_offsets, syntax_names, uses_bracket_spread
from code_weight_width_trial import name_trial
from code_width import add_code_width
from font_feature_tools import add_features, append_glyph, label_stylistic_set
from render_svg import render
from repeated_stems import add_monospace_repeats
from specimens import ROOT
from system_italic import designspace
from system_metrics import set_vertical_metrics


FAMILY = "Daikonic Transit Code Component Spacing Trial"
FEATURE = "ss08"
DOTS = tuple(f"period.spread{i}" for i in (1, 2, 3))
OPERATOR_GLYPHS = sorted({name for group in (ARROWS, COMPARISONS, DIRECT, CONTEXT_PAIRS, LOOSE_NAMES)
                          for name in group.values()})
SAMPLE = (
    "const same = left === right;",
    "const b = left !== right && input >= min;",
    "const all = [...items, ...tail];",
    "const value = obj?.field;",
    "let value = T::item::<Vec<U>>();",
    "let bits = a || b; // Preserve the grid",
)
SPREAD_CASES = ("...items", "[...items]", "f(...rest)", "f(a,...rest)", "f(a, ...args)", "{...record}",
                "[...['a']]", "...é", "f(...x, ...y)")
CONTROLS = ("wait... later", "1...2", "x...y", "f(... args)", "....items", "a ...b", "a...b",
            "((x)) [[x]] {{x}}", "a >> b", "https://host", "map(|| x)", "a | b", "a:::b",
            "[<T>] <[T]> Vec<Vec<Vec<T>>>", "x//y x||y", "obj?.a!.b",
            "::", "x::", "//", "x//", "?.", "x?.", "...", "a...", "Vec<Vec<T>>", "Vec<Vec<T>>;")


def add_spread_positioning(font, recipe, replacements):
    cell = recipe["alphabet_review"]["cell"]
    ellipsis = syntax_names(font)["..."]
    assert ellipsis + SPREAD_SUFFIX not in font["glyf"]
    regular = replacements[ellipsis]
    definitions = []
    for i, (name, dot) in enumerate(zip(regular, DOTS, strict=True), 1):
        pen = TTGlyphPen(font.getGlyphSet())
        pen.addComponent("period", (1, 0, 0, 1, 0, 0))
        append_glyph(font, dot, pen.glyph(), [], cell, metric_source="period")
        definitions.append(f"lookup SpreadDot{i} {{ sub {name} by {dot}; }} SpreadDot{i};")
    marked = " ".join(f"{name}'" for name in regular)
    calls = " ".join(f"{name}' lookup SpreadDot{i}" for i, name in enumerate(regular, 1))
    register_spread_context(font, ellipsis, f"sub {calls} @SpreadOperand;", feature=FEATURE,
                            definitions=definitions, marked=marked)

    locations, model, default = designspace(font)
    layout = recipe["layout_review"]
    masters = [font.getGlyphSet(location=loc) for loc in locations]
    nominal = [cell] * len(DOTS)
    placements = [spread_offsets(gs, cell, layout) for gs in masters]
    positions = tuple(component_positions(2 * cell, nominal, placements))
    values = dict(zip(DOTS, positions, strict=True))
    label_stylistic_set(font, FEATURE, "Positioned Ligature Components")
    add_horizontal_positions(font, model, default, values, FEATURE)
    if uses_bracket_spread(layout):
        compact = [spread_offsets(gs, cell, layout, bracket=True) for gs in masters]
        parts = []
        for dot, (advance, offsets), (full_advance, full_offsets) in zip(
            DOTS, component_positions(cell, nominal, compact), positions, strict=True
        ):
            dx, = {new - old for new, old in zip(offsets, full_offsets, strict=True)}
            parts.append(f"{dot}' <{dx} 0 {advance - full_advance} 0>")
        add_features(font, "\n".join([
            "languagesystem DFLT dflt;", "languagesystem latn dflt;",
            f"feature {FEATURE} {{",
            f"pos [{bracket_openers(font)}] {' '.join(parts)};",
            f"}} {FEATURE};",
        ]))


def positioned(rows):
    """Pair each glyph with its actual horizontal origin, after positioning."""
    cursor = 0
    output = []
    for name, cluster, advance, _, dx, dy in rows:
        output.append((name, cluster, cursor + dx, dy))
        cursor += advance
    return output, cursor


def carets_at(font, location, names):
    gdef = font["GDEF"].table
    table = gdef.LigCaretList
    values = VarStoreInstancer(gdef.VarStore, font["fvar"].axes, font.normalizeLocation(location))

    def adjusted(caret):
        assert caret.Format in (1, 3)
        if caret.Format == 1:
            return caret.Coordinate
        dev = caret.DeviceTable
        return otRound(caret.Coordinate + values[dev.StartSize << 16 | dev.EndSize])

    return {name: [adjusted(caret) for caret in glyph.CaretValue]
            for name, glyph in zip(table.Coverage.glyphs, table.LigGlyph, strict=True)
            if name in names}


def verify_positions(before, after, glyphs, replacements):
    old_positions, old_width = positioned(before)
    new_positions, new_width = positioned(after)
    expected = []
    advances = []
    for (name, cluster, x, y), row in zip(old_positions, before, strict=True):
        aliases = replacements.get(name)
        if aliases:
            advances.extend(split_advance(row[2], len(aliases)))
            glyph, _ = glyphs[name]._getGlyphAndOffset()
            expected.extend((alias, cluster + i, x + part.x, y + part.y)
                            for i, (alias, part) in enumerate(zip(aliases, glyph.components, strict=True)))
        else:
            advances.append(row[2])
            expected.append((name, cluster, x, y))
    assert len(new_positions) == len(expected) and old_width == new_width, (before, after)
    assert [row[2] for row in after] == advances, (before, after, advances)
    assert all(a[:2] == b[:2] and abs(a[2] - b[2]) <= 2 and a[3] == b[3]
               for a, b in zip(new_positions, expected, strict=True)), (new_positions, expected)


def verify(source, target, recipe, replacements):
    before, after = [hb.Font(hb.Face(p.read_bytes())) for p in (source, target)]
    with TTFont(source) as old, TTFont(target) as trial:
        tags = {r.FeatureTag for table in ("GSUB", "GPOS") for r in old[table].table.FeatureList.FeatureRecord}
        cases = {(item["text"], tuple(sorted(flags.items()))) for item in fixtures(tags, recipe)
                 for flags in item["states"].values()}
        cases.update((text, ()) for text in (*SAMPLE, *CONTROLS, *SPREAD_CASES))
        assert old.getBestCmap() == trial.getBestCmap()
        ellipsis = syntax_names(old)["..."]
        spread = ellipsis + SPREAD_SUFFIX
        bracket_spread = ellipsis + BRACKET_SPREAD_SUFFIX
        assert all(name not in trial["glyf"] for name in (spread, bracket_spread))
        assert all(dot in trial["glyf"] for dot in DOTS)
        fixed_operators = set(OPERATOR_GLYPHS) - replacements.keys()
        caret_glyphs = set(trial["GDEF"].table.LigCaretList.Coverage.glyphs)
        assert caret_glyphs.isdisjoint(replacements)
        for name, aliases in replacements.items():
            if name == SCOPE:
                assert [part.glyphName for part in trial["glyf"][name].components] == ["colon"]
            else:
                assert name not in trial["glyf"], name
            assert caret_glyphs.isdisjoint(aliases), name
        spread_forms = {name: DOTS for name in (spread, bracket_spread) if name in old["glyf"]}
        replacements = replacements | spread_forms
        checked = 0
        for weight, width in product(recipe["sample_coordinates"]["wght"], recipe["sample_coordinates"]["wdth"]):
            location = {"wght": weight, "wdth": width}
            cell = otRound(recipe["alphabet_review"]["cell"] * width / 100)
            for engine in (before, after):
                engine.set_variations(location)
            old_glyphs, new_glyphs = [font.getGlyphSet(location=location) for font in (old, trial)]
            for text, values in sorted(cases):
                flags = dict(values)
                expected = shape(before, text, flags)
                active = shape(after, text, flags | {FEATURE: True})
                if any(row[0] in replacements for row in expected):
                    verify_positions(expected, active, old_glyphs, replacements)
                else:
                    assert active == expected, (location, text, flags, active, expected)
                inactive = shape(after, text, flags | {FEATURE: False})
                assert all(row[0] not in replacements or row[0] == SCOPE for row in inactive)
                checked += 1
            for name in sorted(fixed_operators):
                assert old_glyphs[name].width == new_glyphs[name].width, (name, location)
                old_shape, new_shape = [DecomposingRecordingPen(gs) for gs in (old_glyphs, new_glyphs)]
                old_glyphs[name].draw(old_shape)
                new_glyphs[name].draw(new_shape)
                assert old_shape.value == new_shape.value, (name, location)
            old_carets = carets_at(old, location, fixed_operators)
            assert old_carets == carets_at(trial, location, fixed_operators)
            for text in SPREAD_CASES:
                new_rows = shape(after, text, {FEATURE: True})
                dots = [row[2] for row in new_rows if row[0] in DOTS]
                expected_dots = [step for name, _, advance, *_ in shape(before, text, {})
                                 if name in spread_forms for step in split_advance(advance, len(DOTS))]
                assert dots == expected_dots, (weight, width, text, dots)
                assert any(row[0] in DOTS for row in new_rows)
                assert all(row[0] not in DOTS for row in shape(after, text, {FEATURE: False}))
                checked += 1
    return checked


def proof(output, config, target, original, replacements):
    engine = hb.Font(hb.Face(original.read_bytes()))

    with TTFont(original) as font:
        ellipsis = syntax_names(font)["..."]
    counts = {name: len(aliases) for name, aliases in replacements.items()}
    counts.update({ellipsis + suffix: len(DOTS) for suffix in (SPREAD_SUFFIX, BRACKET_SPREAD_SUFFIX)})

    def expected(line, features):
        rows = shape(engine, line, {})
        return sum(row[2] if features[FEATURE] or row[0] not in counts
                   else counts[row[0]] * config["cell"] for row in rows)

    code_review_proof(output, config, "Code · Positioned ligature components",
                      "Regular 400 · Component drawings with two spacing settings",
                      SAMPLE, (("Positioning on · ss08", target, {FEATURE: True}),
                               ("Positioning off · full input widths", target, {FEATURE: False})),
                      expected_advance=expected)


def layout_faces(recipe, *, spread_glyph):
    sans = ROOT / (recipe["fonts"]["sans"] + "-VF.ttf")
    with TTFont(sans, recalcTimestamp=False) as source:
        upright, _ = alphabet_font(source, recipe, stage="Layout", spread_glyph=spread_glyph)
    italic = deepcopy(upright)
    build_layout(upright, recipe, spread_glyph=spread_glyph)
    add_monospace_repeats(upright)
    build_italic(italic, recipe, FAMILY, version="0.100", spread_glyph=spread_glyph)
    return (("upright", "", upright), ("italic", "-Italic", italic))


def build(recipe, reference, output):
    config = recipe["alphabet_review"]
    spacing = recipe["layout_review"].get("edge_spacing", {})
    if reference is None:
        reference = output / "reference"
        reference.mkdir(exist_ok=True)
        for style, suffix, font in layout_faces(recipe, spread_glyph=True):
            add_code_width(font, config["cell"], boundaries=spacing.get(style, {}).get("boundaries", ()))
            font.save(reference / f"DaikonicTransitCode{suffix}-VF.ttf")
    report = {}
    for style, suffix, font in layout_faces(recipe, spread_glyph=False):
        replacements = add_lateral_positioning(font, recipe, FEATURE)
        add_spread_positioning(font, recipe, replacements)
        name_trial(font, FAMILY, variable=True)
        set_vertical_metrics(font, minimum_ascent=config["line_metrics"]["ascent"],
                             maximum_descent=config["line_metrics"]["descent"])
        add_code_width(font, config["cell"], boundaries=spacing.get(style, {}).get("boundaries", ()))
        retire_lateral_drawings(font, replacements)
        target = output / f"{FAMILY.replace(' ', '')}{suffix}-VF.ttf"
        font.save(target)
        sanitize(font)
        original = reference / f"DaikonicTransitCode{suffix}-VF.ttf"
        count = verify(original, target, recipe, replacements)
        report[target.name] = {"shaping_cases": count, "positioned_components": replacements}
        if style == "upright":
            panel = output / "Code-GPOS-Components.svg"
            proof(panel, config, target, original, replacements)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return panel


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=RECIPE_PATH)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reference", type=Path,
                        help="Directory holding comparison VFs; defaults to rebuilding them from the recipe")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    panel = build(json.loads(args.recipe.read_text()), args.reference, args.output)
    if args.render:
        render(panel, scale=2)
    print(f"Wrote the positioned ligature-spacing trial to {args.output}")


if __name__ == "__main__":
    main()
