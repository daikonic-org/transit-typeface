"""Build and verify Code Hairlining and its default-on candidate."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from string import ascii_letters
import subprocess
from tempfile import TemporaryDirectory

from fontTools.ttLib import TTFont
import ots
import uharfbuzz as hb

import code_hairline_study as study
from font_feature_tools import add_features, append_glyph, label_stylistic_set, master_locations


FEATURE = "ss05"
OFF_FEATURE = "ss07"
BAR_OPEN, BAR_CLOSE = "bar.delimiterOpen", "bar.delimiterClose"
PAIRS = (
    ("less.generic", "bracketleft"), ("bracketleft", "less.generic"),
    ("bracketright", "greater.generic"), ("greater.generic", "bracketright"),
)
ON = {FEATURE: True}


def build(source, candidate, directory, *, release=False):
    font = TTFont(source, recalcTimestamp=False)
    updated = TTFont(candidate)
    names = {name for pair in study.PAIRS for name in pair}
    names.update((*study.TALL_OPENERS, study.TALL_CLOSER, "code.scope", *study.INTERPOLATION))
    names.update(name for name in font.getGlyphOrder() if name.startswith("code.genericClose"))
    aliases = {name: name + ".hairline" for name in sorted(names)}
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    for base, alternate in [*aliases.items(), *((n, n) for n in study.LEADERS)]:
        append_glyph(
            font, alternate, deepcopy(updated["glyf"][base]),
            deepcopy(updated["gvar"].variations.get(base, [])), updated["hmtx"][base][0],
            metric_source=base if base in aliases else "space",
        )
        if base in aliases:
            classes[alternate] = classes.get(base, 1)

    cmap = font.getBestCmap()
    parameters = {cmap[ord(c)] for c in ascii_letters + "_"}
    parameters |= {
        n for n in font.getGlyphOrder() if ".heal." in n and n.split(".")[0] in parameters
    }
    leaders = " ".join(study.LEADERS)
    preview_borrow_rule = [] if release else [
        f"pos ampersand' <{study.BORROW_INSET} 0 0 0> [{leaders}];"
    ]
    lines = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "@EchoParameter = [" + " ".join(sorted(parameters)) + "];",
        "feature ss05 {",
        "lookup RecoverBarOpen {",
        f"sub {BAR_CLOSE} space bar' @EchoParameter bar by {BAR_OPEN};",
        f"sub {BAR_CLOSE} space space bar' @EchoParameter bar by {BAR_OPEN};",
        "} RecoverBarOpen;",
        f"sub {BAR_OPEN} @EchoParameter bar' by {BAR_CLOSE};",
    ]
    lines.extend(f"sub {base} by {alternate};" for base, alternate in aliases.items())
    lines += ["} ss05;", "feature ss05 {"]
    for left, right in PAIRS:
        lines.append(f"pos {aliases[left]}' <30 0 0 0> {aliases[right]}' <-30 0 0 0>;")
    lines += [
        f"pos {aliases['code.scope']}' <18 0 0 0> {aliases['less.generic']}' <-18 0 0 0>;",
        *preview_borrow_rule,
        "} ss05;",
        f"feature ss01 {{ pos {aliases['code.lifetimeOpen']} <40 45 0 0>; }} ss01;",
        "table GDEF {",
    ]
    carets = font["GDEF"].table.LigCaretList
    for name, record in zip(carets.Coverage.glyphs, carets.LigGlyph):
        if name in aliases:
            assert all(value.Format == 1 for value in record.CaretValue)
            coords = " ".join(str(value.Coordinate) for value in record.CaretValue)
            lines.append(f"LigatureCaretByPos {aliases[name]} {coords};")
    lines.append("} GDEF;")
    add_features(font, "\n".join(lines))
    _, locations = master_locations(font)
    study.lifetime_context(font, [font.getGlyphSet(location=loc) for loc in locations], FEATURE)
    label_stylistic_set(font, FEATURE, "Hairline delimiters and markers")
    if release:
        remove_lifetime_toggle(font)
        position_lifetime_ampersand(font, include_hairlines=True)
        return font, aliases
    return study.save_trial(font, directory, "Hairline Toggle"), aliases


def remove_lifetime_toggle(font):
    """Remove the ss01 feature and its language-system references."""
    for tag in ("GSUB", "GPOS"):
        table = font[tag].table
        assert getattr(table, "FeatureVariations", None) is None
        kept = []
        new_indices = {}
        for index, record in enumerate(table.FeatureList.FeatureRecord):
            if record.FeatureTag != "ss01":
                new_indices[index] = len(kept)
                kept.append(record)
        table.FeatureList.FeatureRecord = kept
        table.FeatureList.FeatureCount = len(kept)
        for script in table.ScriptList.ScriptRecord:
            languages = [script.Script.DefaultLangSys]
            languages.extend(record.LangSys for record in script.Script.LangSysRecord)
            for lang in languages:
                if lang is None:
                    continue
                if lang.ReqFeatureIndex != 65535:
                    lang.ReqFeatureIndex = new_indices.get(lang.ReqFeatureIndex, 65535)
                lang.FeatureIndex = [new_indices[i] for i in lang.FeatureIndex if i in new_indices]
                lang.FeatureCount = len(lang.FeatureIndex)


def position_lifetime_ampersand(font, *, include_hairlines=False):
    markers = (study.MARKER, *study.LEADERS) if include_hairlines else (study.MARKER,)
    add_features(font, f"""
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        feature calt {{
            pos ampersand' <{study.BORROW_INSET} 0 0 0> [{' '.join(markers)}];
        }} calt;
    """)


def inward_ampersand(shaped, x_offset_index):
    """Apply the permanent lifetime position to the released shaping reference."""
    adjusted = []
    for index, (name, *values) in enumerate(shaped):
        if (name == "ampersand" and index + 1 < len(shaped)
                and shaped[index + 1][0] == study.MARKER):
            values[x_offset_index] += study.BORROW_INSET
        adjusted.append((name, *values))
    return adjusted


def verify(source, candidate, trial, aliases, *, release=False):
    paths = (source, candidate, trial)
    fonts = [TTFont(path) for path in paths]
    engines = [hb.Font(hb.Face(path.read_bytes())) for path in paths]
    original, automatic, toggle = fonts
    for name in original.getGlyphOrder():
        old, new = original["glyf"], toggle["glyf"]
        assert old[name].compile(old) == new[name].compile(new), name
        assert original["hmtx"][name] == toggle["hmtx"][name], name
    for base, alternate in aliases.items():
        old, new = automatic["glyf"], toggle["glyf"]
        assert old[base].compile(old) == new[alternate].compile(new), alternate
        assert automatic["hmtx"][base] == toggle["hmtx"][alternate], alternate
        assert automatic["gvar"].variations.get(base, []) == toggle["gvar"].variations.get(alternate, [])
    alias_sources = {alternate: base for base, alternate in aliases.items()}
    samples = (*study.EXAMPLE, study.CONTROL, "Vec<[T]> [<T>]", "T::item::<Vec<Vec<T>>>",
               "$[x] $(x)", "map(|w| w) |w|", "|w|", "&'é &'a' a & b", "a|w|b",
               "<'a> & 'static 'a' '_'", "() [] {}", "mwm wwm != ->")
    for weight in study.WEIGHTS:
        for engine in engines:
            engine.set_variations({"wght": weight})
        combinations = ({}, {"ss02": True})
        if not release:
            combinations += ({"ss01": True}, {"ss01": True, "ss02": True})
        for features in combinations:
            for text in samples:
                old, auto, unchanged = [
                    study.shape(f, h, text, features) for f, h in zip(fonts, engines)
                ]
                expected = inward_ampersand(old, 2) if release else old
                assert expected == unchanged, (text, weight, features)
                switched = study.shape(toggle, engines[2], text, features | ON)
                normalized = [(alias_sources.get(name, name), *rest) for name, *rest in switched]
                assert auto == normalized, (text, weight, features, auto, normalized)
        example = study.shape(toggle, engines[2], "|x|  |w|  a | b", ON)
        assert [n for n, *_ in example if n.startswith("bar")] == [
            aliases[BAR_OPEN], aliases[BAR_CLOSE], aliases[BAR_OPEN], aliases[BAR_CLOSE], "bar",
        ], (weight, example)
    with TemporaryDirectory() as tmp:
        subprocess.run(
            [ots.OTS_SANITIZE, str(trial), str(Path(tmp) / "checked.ttf")],
            check=True, capture_output=True,
        )


def check_release(reference, path):
    original, font = TTFont(reference), TTFont(path)
    engines = [hb.Font(hb.Face(p.read_bytes())) for p in (reference, path)]
    for tag in ("GSUB", "GPOS"):
        assert all(r.FeatureTag != "ss01" for r in font[tag].table.FeatureList.FeatureRecord)
    upright = not bool(font["OS/2"].fsSelection & 1)
    features = {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}
    assert (FEATURE in features) == upright
    for weight in study.WEIGHTS:
        for engine in engines:
            engine.set_variations({"wght": weight})
        for value in (*study.EXAMPLE, study.CONTROL, "|x|  |w|  a | b", "'a' '_'", "Vec<Vec<T>>"):
            expected = inward_ampersand(study.shape(original, engines[0], value, {}), 2)
            assert study.shape(font, engines[1], value, {"ss01": True}) == expected
            if upright:
                result = study.shape(font, engines[1], value, ON)
                assert sum(row[2] for row in result) == 600 * len(value)
        if upright:
            expected = [BAR_OPEN, BAR_CLOSE, BAR_OPEN, BAR_CLOSE]
            result = study.shape(font, engines[1], "|x|  |w|  a | b", ON)
            assert [n for n, *_ in result if n.startswith("bar")] == [
                *(n + ".hairline" for n in expected), "bar",
            ]
            result = study.shape(font, engines[1], "&'a", ON)
            assert result[0][3] == study.BORROW_INSET and result[1][0] in study.LEADERS
            glyphs = font.getGlyphSet(location={"wght": weight})
            rule = study.shape_from_glyphs(glyphs, "code.scope.hairline")
            assert not study.spans(rule, 600, 0)
            for low, high in study.spans(rule, rule.bounds[0] + 30, 0):
                assert abs(high - low - study.HAIRLINE) < 0.01
        for flags in ({}, ON, {"ss01": True}):
            assert study.shape(font, engines[1], "&'a", flags)[0][3] == study.BORROW_INSET
            assert study.shape(font, engines[1], "&'a'", flags)[0][3] == 0
            assert study.shape(font, engines[1], "a & b", flags)[2][3] == 0


def default_hairlining(font):
    """Run the existing hairline lookups with calt and allow an independent opt-out."""
    for tag in ("GSUB", "GPOS"):
        records = font[tag].table.FeatureList.FeatureRecord
        hairline = next(r.Feature for r in records if r.FeatureTag == FEATURE)
        for record in records:
            if record.FeatureTag == "calt":
                feature = record.Feature
                feature.LookupListIndex = sorted(set(feature.LookupListIndex + hairline.LookupListIndex))
                feature.LookupCount = len(feature.LookupListIndex)

    glyphs = set(font.getGlyphOrder())
    rules = [
        f"sub {name} by {name.removesuffix('.hairline')};"
        for name in sorted(glyphs)
        if name.endswith(".hairline") and name.removesuffix(".hairline") in glyphs
    ]
    rules.extend(f"sub {name} by {study.MARKER};" for name in study.LEADERS)
    add_features(font, "\n".join([
        "languagesystem DFLT dflt;", "languagesystem latn dflt;",
        f"feature {OFF_FEATURE} {{", *rules, f"}} {OFF_FEATURE};",
    ]))
    label_stylistic_set(font, OFF_FEATURE, "Disable Hairlining")


def verify_default(source, path):
    old, new = [TTFont(p) for p in (source, path)]
    engines = [hb.Font(hb.Face(p.read_bytes())) for p in (source, path)]
    samples = (
        *study.EXAMPLE, study.CONTROL, "Vec::<Vec<T>>::new()", "&'a &'é &'a' '_'", "film x.m .w.",
        "map(|| f(x))", "a||b", "a === b || c !== d", "obj?.value obj!.value",
        "Vec<[T]> [<T>]", "[<>] <[]>", "$[x] $(x) ${x}", "|w|", "a | b",
    )
    for weight in study.WEIGHTS:
        for engine in engines:
            engine.set_variations({"wght": weight})
        for heal in (False, True):
            for hairline in (False, True):
                settings = {"ss04": not heal, OFF_FEATURE: not hairline}
                names = [row[0] for row in study.shape(new, engines[1], "film (x)", settings)]
                assert any(name.startswith("m.heal.") for name in names) == heal
                assert ("parenleft.hairline" in names) == hairline
        for extras in ({}, {"ss02": True, "ss06": True}, {"ss04": True}):
            for text in samples:
                before, after = engines
                shaded = study.shape(old, before, text, extras | ON)
                assert study.shape(new, after, text, extras) == shaded, (text, weight, extras)
                assert study.shape(new, after, text, extras | ON) == shaded
                plain = study.shape(old, before, text, extras)
                off = study.shape(new, after, text, extras | {OFF_FEATURE: True})
                assert plain == off, (text, weight, extras, plain, off)
                assert study.shape(new, after, text, extras | ON | {OFF_FEATURE: True}) == off
    for tag in ("glyf", "gvar", "hmtx", "cmap", "GDEF", "STAT"):
        assert old.getTableData(tag) == new.getTableData(tag), tag
    with TemporaryDirectory() as tmp:
        subprocess.run(
            [ots.OTS_SANITIZE, str(path), str(Path(tmp) / "checked.ttf")],
            check=True, capture_output=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--proof", action="store_true", help="Render the selected release font")
    parser.add_argument("--default-on", action="store_true", help="Build and proof default Hairlining")
    args = parser.parse_args()
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    config = study.specimen_families()["code"]
    source = study.ROOT / config["font"]
    if args.default_on:
        font = TTFont(source, recalcTimestamp=False)
        default_hairlining(font)
        trial = study.save_trial(font, directory, "Default Hairlining")
        verify_default(source, trial)
        study.proof(directory, config, [
            ("Hairlining by default", trial, {}),
            ("Hairlining off · ss07", trial, {OFF_FEATURE: True}),
        ])
        print(trial.name, "default and opt-out verified across 11 weights")
        return
    if args.proof:
        cuts = [("Off", source, {FEATURE: False, OFF_FEATURE: True}), ("Hairlining", source, ON)]
        study.proof(directory, config, cuts)
        return
    with TemporaryDirectory() as tmp:
        candidate, targets = study.build(source, Path(tmp), shifted=True)
        study.verify(source, candidate, targets, shifted=True)
        trial, aliases = build(source, candidate, directory)
        verify(source, candidate, trial, aliases)
    cuts = [("Off", trial, {FEATURE: False})]
    if args.compare:
        cuts.append(("16 units", args.compare.resolve()))
    cuts.append((f"{study.HAIRLINE} units · ss05 on", trial, ON))
    study.proof(directory, config, cuts, "Daikonic Transit Code Book · dark and light editor samples")
    (directory / "Review.json").write_text(json.dumps({
        "source": config["font"],
        "feature": FEATURE,
        "stroke_units": study.HAIRLINE,
        "verified_weights": study.WEIGHTS,
        "sha256": sha256(trial.read_bytes()).hexdigest(),
    }, indent=2) + "\n")
    print(trial.name, "passed 11-weight geometry, toggle shaping and OTS checks")


if __name__ == "__main__":
    main()
