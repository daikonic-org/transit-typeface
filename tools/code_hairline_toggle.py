"""Build the heavier Code hairlines as an optional stylistic set."""

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
        f"pos ampersand' <{study.BORROW_INSET} 0 0 0> [{leaders}];",
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
                assert old == unchanged, (text, weight, features)
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
            expected = study.shape(original, engines[0], value, {})
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--proof", action="store_true", help="Render the selected release font")
    args = parser.parse_args()
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    config = study.specimen_families()["code"]
    source = study.ROOT / config["font"]
    if args.proof:
        cuts = [("Off", source, {FEATURE: False}), ("Hairlining · ss05", source, ON)]
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
