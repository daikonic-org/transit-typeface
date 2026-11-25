"""Build a local Code trial with GPOS-based operator advances and spread positioning."""

from argparse import ArgumentParser
from collections import defaultdict
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


FAMILY = "Daikonic Transit Code Positioning Trial"
FEATURE = "ss08"
DOT = "period.spread"
SAMPLE = (
    "const same = left === right;",
    "const b = left !== right && input >= min;",
    "const all = [...items, ...tail];",
    "const value = obj?.field;",
    "let value = T::item::<Vec<U>>();",
    "const map = (x) => x;",
)
SPREAD_CASES = ("...items", "[...items]", "f(...x)", "f(a, ...args)", "{...record}",
                "[...['a']]", "...é", "f(...x, ...y)")
CONTROLS = ("wait... later", "1...2", "x...y", "f(... args)", "....items", "a ...b", "a...b")


def add_compaction(font, recipe):
    cell = recipe["alphabet_review"]["cell"]
    metrics = font["hmtx"]
    changes = defaultdict(list)
    for group in (ARROWS, COMPARISONS, DIRECT, CONTEXT_PAIRS, LOOSE_NAMES):
        for token, name in group.items():
            advance, side = metrics[name]
            full = len(token) * cell
            if advance < full:
                changes[advance - full].append(name)
                metrics[name] = full, side

    ellipsis = syntax_names(font)["..."]
    assert ellipsis + SPREAD_SUFFIX not in font["glyf"]
    pen = TTGlyphPen(font.getGlyphSet())
    pen.addComponent("period", (1, 0, 0, 1, 0, 0))
    append_glyph(font, DOT, pen.glyph(), [], cell, metric_source="period")
    register_spread_context(
        font, ellipsis, f"sub {ellipsis}' lookup SpreadDots @SpreadOperand;", feature=FEATURE,
        definitions=[f"lookup SpreadDots {{ sub {ellipsis} by {DOT} {DOT} {DOT}; }} SpreadDots;"],
    )
    label_stylistic_set(font, FEATURE, "Positioned Operator Compaction")

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
    lines.extend((f"feature {FEATURE} {{", f"pos {rules};",
                  *(f"pos [{' '.join(names)}] {difference};" for difference, names in sorted(changes.items())),
                  f"}} {FEATURE};"))

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
    return [name for names in changes.values() for name in names]


def positioned(rows):
    """Pair each glyph with its actual horizontal origin, after positioning."""
    cursor = 0
    output = []
    for name, cluster, advance, _, dx, _ in rows:
        output.append((name, cluster, cursor + dx))
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


def verify(source, target, recipe, names):
    before, after = [hb.Font(hb.Face(p.read_bytes())) for p in (source, target)]
    with TTFont(source) as old, TTFont(target) as trial:
        tags = {r.FeatureTag for table in ("GSUB", "GPOS") for r in old[table].table.FeatureList.FeatureRecord}
        cases = {(item["text"], tuple(sorted(flags.items()))) for item in fixtures(tags, recipe)
                 for flags in item["states"].values()}
        cases.update((text, ()) for text in (*SAMPLE, *CONTROLS))
        assert old.getBestCmap() == trial.getBestCmap()
        spread = syntax_names(old)["..."] + SPREAD_SUFFIX
        assert spread not in trial["glyf"] and DOT in trial["glyf"]
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
                if any(row[0] == spread for row in expected):
                    continue
                actual = shape(after, text, flags | {FEATURE: True})
                assert actual == expected, (location, text, flags, actual, expected)
                literal_grid = shape(after, text, flags)
                if any(row[0] in names for row in actual):
                    assert [r[:2] for r in literal_grid] == [r[:2] for r in actual]
                    assert all(r[2] == otRound(new_glyphs[r[0]].width)
                               for r in literal_grid if r[0] in names)
                checked += 1
            for name in names:
                old_shape, new_shape = [DecomposingRecordingPen(gs) for gs in (old_glyphs, new_glyphs)]
                old_glyphs[name].draw(old_shape)
                new_glyphs[name].draw(new_shape)
                assert old_shape.value == new_shape.value, (name, location)
            old_carets = carets_at(old, location, {*names, spread})
            expected_carets = old_carets.pop(spread)
            assert old_carets == carets_at(trial, location, names)
            for text in SPREAD_CASES:
                old_rows = shape(before, text, {})
                new_rows = shape(after, text, {FEATURE: True})
                old_positions, old_width = positioned(old_rows)
                positions, new_width = positioned(new_rows)
                target_glyph, _ = old_glyphs[spread]._getGlyphAndOffset()
                expected = []
                for name, cluster, x in old_positions:
                    if name == spread:
                        expected.extend((DOT, cluster, x + part.x) for part in target_glyph.components)
                    else:
                        expected.append((name, cluster, x))
                assert len(positions) == len(expected) and old_width == new_width, (location, text, new_rows)
                assert all(a[:2] == b[:2] and abs(a[2] - b[2]) <= 2
                           for a, b in zip(positions, expected, strict=True)), (location, text, positions, expected)
                assert all(row[2] == 2 * cell // 3 for row in new_rows if row[0] == DOT)
                assert expected_carets == [2 * cell // 3, 4 * cell // 3]
                assert all(row[0] != DOT for row in shape(after, text, {FEATURE: False}))
                checked += 1
    return checked


def proof(output, config, target, original):
    engine = hb.Font(hb.Face(original.read_bytes()))

    def expected(line, features):
        return (sum(row[2] for row in shape(engine, line, {}))
                if features[FEATURE] else len(line) * config["cell"])

    code_review_proof(output, config, "Code · Positioned compaction",
                      "Regular 400 · The same operator drawings with two advance settings",
                      SAMPLE, (("Positioning on · ss08", target, {FEATURE: True}),
                               ("Positioning off · full input columns", target, {FEATURE: False})),
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
        names = add_compaction(font, recipe)
        name_trial(font, FAMILY, variable=True)
        set_vertical_metrics(font, minimum_ascent=config["line_metrics"]["ascent"],
                             maximum_descent=config["line_metrics"]["descent"])
        add_code_width(font, config["cell"])
        title = "-Italic" if is_italic else ""
        target = output / f"{FAMILY.replace(' ', '')}{title}-VF.ttf"
        font.save(target)
        sanitize(font)
        original = reference / f"DaikonicTransitCode{title}-VF.ttf"
        count = verify(original, target, recipe, names)
        report[target.name] = {"shaping_cases": count, "positioned_ligatures": names}
        if not is_italic:
            panel = output / "Code-GPOS-Compaction.svg"
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
    print(f"Wrote the positioned compaction trial to {args.output}")


if __name__ == "__main__":
    main()
