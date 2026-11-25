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
from fontTools.varLib.builder import buildVarDevTable
from fontTools.varLib.varStore import OnlineVarStoreBuilder, VarStoreInstancer
import uharfbuzz as hb

from build_code import RECIPE_PATH, alphabet_font, code_review_proof
from build_code_italic import build_italic
from bundle_release import sanitize
from check_code_rebuild import fixtures, shape
from code_compact_build import CONTEXT_PAIRS, DIRECT, LOOSE_NAMES
from code_layout import build_layout
from code_gpos_lateral import add_lateral_positioning, following_glyphs
from code_math import ARROWS, COMPARISONS
from code_spread import register_spread_context
from code_syntax_build import SPREAD_SUFFIX, spread_offsets, syntax_names
from code_weight_width_trial import name_trial
from code_width import add_code_width
from font_feature_tools import add_features, append_glyph, append_layout_variations, label_stylistic_set
from render_svg import render
from repeated_stems import add_monospace_repeats
from specimens import ROOT
from system_italic import designspace
from system_metrics import set_vertical_metrics


FAMILY = "Daikonic Transit Code Spacing Trial"
FEATURE = "ss08"
DOT = "period.spread"
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
SPREAD_CASES = ("...items", "[...items]", "f(...x)", "f(a, ...args)", "{...record}",
                "[...['a']]", "...é", "f(...x, ...y)")
CONTROLS = ("wait... later", "1...2", "x...y", "f(... args)", "....items", "a ...b", "a...b",
            "((x)) [[x]] {{x}}", "a >> b", "https://host", "map(|| x)", "a | b", "a:::b",
            "[<T>] <[T]> Vec<Vec<Vec<T>>>", "x//y x||y", "obj?.a!.b",
            "::", "x::", "//", "x//", "?.", "x?.", "...", "a...", "Vec<Vec<T>>", "Vec<Vec<T>>;")


def add_spread_positioning(font, recipe):
    cell = recipe["alphabet_review"]["cell"]
    ellipsis = syntax_names(font)["..."]
    assert ellipsis + SPREAD_SUFFIX not in font["glyf"]
    pen = TTGlyphPen(font.getGlyphSet())
    pen.addComponent("period", (1, 0, 0, 1, 0, 0))
    append_glyph(font, DOT, pen.glyph(), [], cell, metric_source="period")
    register_spread_context(
        font, ellipsis, f"sub {ellipsis}' lookup SpreadDots @SpreadOperand;", feature=FEATURE,
        definitions=[f"lookup SpreadDots {{ sub {ellipsis} by {DOT} {DOT} {DOT}; }} SpreadDots;"],
    )
    label_stylistic_set(font, FEATURE, "Positioned Ligature Spacing")

    locations, model, default = designspace(font)
    placements = [spread_offsets(font.getGlyphSet(location=loc), cell, recipe["layout_review"])
                  for loc in locations]
    placement_columns = [[value - i * (2 * cell // 3) for value in column]
                         for i, column in enumerate(zip(*placements, strict=True))]
    lines = ["languagesystem DFLT dflt;", "languagesystem latn dflt;"]
    advance = 2 * cell // 3
    for i, values in enumerate(placement_columns, 1):
        lines.append(f"lookup SpreadPos{i} {{ pos {DOT} <{values[default]} 0 {advance - cell} 0>; }} SpreadPos{i};")
    rules = " ".join(f"{DOT}' lookup SpreadPos{i}" for i in range(1, 4))
    lines.append(f"feature {FEATURE} {{ pos {rules}; }} {FEATURE};")

    lookups = font["GPOS"].table.LookupList.Lookup
    first = len(lookups)
    add_features(font, "\n".join(lines))
    dot_tables = {
        sub.Value.XPlacement: sub
        for lookup in lookups[first:] if lookup.LookupType == 1
        for sub in lookup.SubTable if sub.Coverage.glyphs == [DOT]
    }
    store = font["GDEF"].table.VarStore
    first_data = len(store.VarData) << 16
    builder = OnlineVarStoreBuilder(["wght"])
    builder.setModel(model)
    for values in placement_columns:
        base, index = builder.storeMasters(values)
        table = dot_tables[base]
        table.ValueFormat |= 0x10
        table.Value.XPlaDevice = buildVarDevTable(first_data + index)
    append_layout_variations(font, builder.finish())


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


def verify_positions(before, after, glyphs, replacements, following):
    old_positions, old_width = positioned(before)
    new_positions, new_width = positioned(after)
    expected = []
    last = max((i for i, (name, *_rest) in enumerate(old_positions) if name in following), default=-1)
    for i, (name, cluster, x, y) in enumerate(old_positions):
        aliases = replacements.get(name) if i < last else None
        if aliases:
            glyph, _ = glyphs[name]._getGlyphAndOffset()
            expected.extend((alias, cluster, x + part.x, y + part.y)
                            for alias, part in zip(aliases, glyph.components, strict=True))
        else:
            expected.append((name, cluster, x, y))
    assert len(new_positions) == len(expected) and old_width == new_width, (before, after)
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
        spread = syntax_names(old)["..."] + SPREAD_SUFFIX
        assert spread not in trial["glyf"] and DOT in trial["glyf"]
        replacements = replacements | {spread: [DOT] * 3}
        following = set(following_glyphs(old))
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
                enabled = shape(after, text, flags | {FEATURE: True})
                if any(row[0] in replacements for row in expected):
                    verify_positions(expected, enabled, old_glyphs, replacements, following)
                else:
                    assert enabled == expected, (location, text, flags, enabled, expected)
                disabled = shape(after, text, flags | {FEATURE: False})
                if not any(row[0] == spread for row in expected):
                    assert disabled == expected, (location, text, flags, disabled, expected)
                checked += 1
            for name in OPERATOR_GLYPHS:
                assert old_glyphs[name].width == new_glyphs[name].width, (name, location)
                old_shape, new_shape = [DecomposingRecordingPen(gs) for gs in (old_glyphs, new_glyphs)]
                old_glyphs[name].draw(old_shape)
                new_glyphs[name].draw(new_shape)
                assert old_shape.value == new_shape.value, (name, location)
            old_carets = carets_at(old, location, {*OPERATOR_GLYPHS, spread})
            expected_carets = old_carets.pop(spread)
            assert old_carets == carets_at(trial, location, OPERATOR_GLYPHS)
            for text in SPREAD_CASES:
                new_rows = shape(after, text, {FEATURE: True})
                assert all(row[2] == 2 * cell // 3 for row in new_rows if row[0] == DOT)
                assert any(row[0] == DOT for row in new_rows)
                assert expected_carets == [2 * cell // 3, 4 * cell // 3]
                assert all(row[0] != DOT for row in shape(after, text, {FEATURE: False}))
                checked += 1
    return checked


def proof(output, config, target, original):
    engine = hb.Font(hb.Face(original.read_bytes()))

    with TTFont(original) as font:
        spread = syntax_names(font)["..."] + SPREAD_SUFFIX

    def expected(line, features):
        rows = shape(engine, line, {})
        saved = 0 if features[FEATURE] else sum(row[0] == spread for row in rows)
        return sum(row[2] for row in rows) + saved * config["cell"]

    code_review_proof(output, config, "Code · Positioned ligature spacing",
                      "Regular 400 · Reused drawings and contextual spacing",
                      SAMPLE, (("Positioning on · two cells for spread", target, {FEATURE: True}),
                               ("Positioning off · three cells for spread", target, {FEATURE: False})),
                      expected_advance=expected)


def build(recipe, reference, output):
    sans = ROOT / (recipe["fonts"]["sans"] + "-VF.ttf")
    with TTFont(sans, recalcTimestamp=False) as source:
        upright, _ = alphabet_font(source, recipe, stage="Layout", spread_glyph=False)
    italic = deepcopy(upright)
    build_layout(upright, recipe, spread_glyph=False)
    add_monospace_repeats(upright)
    build_italic(italic, recipe, FAMILY, version="0.100", spread_glyph=False)
    report = {}
    config = recipe["alphabet_review"]
    for is_italic, font in ((False, upright), (True, italic)):
        add_spread_positioning(font, recipe)
        replacements = add_lateral_positioning(font, recipe, FEATURE)
        name_trial(font, FAMILY, variable=True)
        set_vertical_metrics(font, minimum_ascent=config["line_metrics"]["ascent"],
                             maximum_descent=config["line_metrics"]["descent"])
        add_code_width(font, config["cell"])
        title = "-Italic" if is_italic else ""
        target = output / f"{FAMILY.replace(' ', '')}{title}-VF.ttf"
        font.save(target)
        sanitize(font)
        original = reference / f"DaikonicTransitCode{title}-VF.ttf"
        count = verify(original, target, recipe, replacements)
        report[target.name] = {"shaping_cases": count, "positioned_components": replacements}
        if not is_italic:
            panel = output / "Code-GPOS-Spacing.svg"
            proof(panel, config, target, original)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return panel


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path, help="Directory holding the packaged Code VFs")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    panel = build(json.loads(RECIPE_PATH.read_text()), args.reference, args.output)
    if args.render:
        render(panel, scale=2)
    print(f"Wrote the positioned ligature-spacing trial to {args.output}")


if __name__ == "__main__":
    main()
