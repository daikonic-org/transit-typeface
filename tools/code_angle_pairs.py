"""Keep adjacent angle pairs ordinary unless both qualify as delimiters."""

from pathlib import Path
from copy import deepcopy
import json
import unicodedata
from fontTools.ttLib import TTFont
from font_feature_tools import add_features, compose
from specimens import ROOT, DATA, Panel
from code_balance_study import bind
from check_syntax_numerals import run

SOURCE = ROOT / "sources/code-logic-symbols/DaikonicTransitCodeLogicSymbols-VF.ttf"
OUT = ROOT / "sources/code-rust-generics"


ANGLE_CASES = {
    "<>": [False, False],
    "a<>b": [False, False],
    "<>T": [False, False],
    "Vec<>": [True, True],
    "HashMap<>": [True, True],
    "fooBar<>": [True, True],
    "vec<>": [False, False],
    "12<>34": [False, False],
    "<_>": [True, True],
    "<[_]>": [True, True],
    "::<_>": [True, True],
    "::<u8>": [True, True],
    "::<usize>": [True, True],
    "::<[_]>": [True, True],
    "Vec<vec<_>>": [True] * 4,
    "::<": [False],
    "Vec<T>": [True, True],
    "Vec<u8>": [True, True],
    "get<T>": [True, True],
    "<T>": [True, True],
    "a<b": [False],
    "a > b": [False],
    "Vec<Vec<T>>": [True] * 4,
    "Vec<vec<a>>": [True] * 4,
    "Vec< vec<a>>": [True] * 4,
    "Tuple<vec<a>, vec<b>>": [True] * 6,
    "Vec<T> a<>b": [True, True, False, False],
    "Foo<Bar<Baz<>>>": [True] * 6,
    "Vec<T": [False],
    "T>": [False],
    "<": [False],
    ">": [False],
    "Vec<Vec<T>": [False, True, True],
    "Vec<T>>": [True, True, False],
}


def check(path):
    source = TTFont(SOURCE)
    font = TTFont(path)
    for tag in ["cmap", "fvar"]:
        assert source.getTableData(tag) == font.getTableData(tag), tag
    gpos = deepcopy(font["GPOS"])
    count = len(source["GPOS"].table.LookupList.Lookup)
    gpos.table.LookupList.Lookup = gpos.table.LookupList.Lookup[:count]
    gpos.table.LookupList.LookupCount = count
    for record in gpos.table.FeatureList.FeatureRecord:
        record.Feature.LookupListIndex = [
            index for index in record.Feature.LookupListIndex if index < count
        ]
        record.Feature.LookupCount = len(record.Feature.LookupListIndex)
    assert gpos.compile(font) == source.getTableData("GPOS")
    gdef = deepcopy(font["GDEF"])
    gdef.table.GlyphClassDef.classDefs = {
        name: value
        for name, value in gdef.table.GlyphClassDef.classDefs.items()
        if name in source.getGlyphOrder()
    }
    assert gdef.compile(font) == source.getTableData("GDEF")
    for name in source.getGlyphOrder():
        assert source["glyf"][name].compile(source["glyf"]) == font["glyf"][
            name
        ].compile(font["glyf"]), name
        assert source["gvar"].variations.get(name) == font["gvar"].variations.get(
            name
        ), name
        assert source["hmtx"][name] == font["hmtx"][name], name
    expected = ANGLE_CASES
    cases = list(expected) + ["-> ->> => <= >=", "&'a <'a>"]
    for weight in range(300, 401, 10):
        for calt in [False, True]:
            for compact in [False, True]:
                for logic in [False, True]:
                    features = {"calt": calt, "ss01": compact, "ss02": logic}
                    for text in cases:
                        before = run(SOURCE, text, {"wght": weight}, features)
                        after = run(path, text, {"wght": weight}, features)
                        assert sum(p[1] for p in after) == len(text) * 600
                        if not calt or text not in expected:
                            if not (compact and not calt and "<'" in text):
                                assert before == after, (text, features)
                        elif not (
                            logic and any(token in text for token in ("<>", "<[", "[<"))
                        ):
                            angles = [
                                name.endswith(".generic")
                                for name, *_ in after
                                if name
                                in (
                                    "less",
                                    "greater",
                                    "less.generic",
                                    "greater.generic",
                                )
                            ]
                            assert angles == expected[text], (
                                text,
                                weight,
                                features,
                                angles,
                            )
    for count, tall in [(60, True), (61, False)]:
        text = "Vec<" + "T" * count + ">"
        angles = [
            p[0].endswith(".generic")
            for p in run(path, text, {"wght": 350}, {"calt": True})
            if p[0] in ("less", "greater", "less.generic", "greater.generic")
        ]
        assert angles == [tall, tall], (count, angles)
    for compact in [False, True]:
        actual = run(path, "<'a", {"wght": 350}, {"calt": True, "ss01": compact})
        assert actual[0][0] == ("code.lifetimeOpen.short" if compact else "less")
    for text in ["::<T>", "::<_>"]:
        shaped = run(path, text, {"wght": 350}, {"calt": True})
        assert (
            shaped[0][0] == "code.scope" and shaped[0][2] == 18 and shaped[0][3] == 50
        )
        assert shaped[1][0] == "less.generic" and shaped[1][2] == -18
        assert sum(item[1] for item in shaped) == len(text) * 600
    incomplete = run(path, "::<", {"wght": 350}, {"calt": True})
    assert incomplete[0][2] == incomplete[1][2] == 0
    deep = "A<" * 16 + "T" + ">" * 16
    assert (
        sum(
            p[0] in ("less.generic", "greater.generic")
            for p in run(path, deep, {"wght": 350}, {"calt": True})
        )
        == 32
    )
    print(
        "Angle pairs: 11 weights, eight toggle combinations, retained drawings and unrelated syntax verified",
        flush=True,
    )


def build_angle_pairs(font, depth_limit, span_limit, cell=600, *, alias=None,
                      scope="code.scope", scope_inset=(18, 50)):
    original_names = set(font.getGlyphOrder())
    use_lifetimes = "code.lifetimeOpen" in original_names
    if alias is None:
        def alias(name, donor):
            compose(font, name, [(donor, 1, 1, 0, 0)], cell, metric_source=donor)

    alias("less.pairIntent", "less")
    sources = {
        "shortLeft": "less", "shortRight": "greater",
        "tallLeft": "less.generic", "tallRight": "greater.generic",
    }
    if use_lifetimes:
        compose(font, "code.lifetimeOpen.short", [("less", 1, 1, cell, 0)], cell, metric_source="less")
        sources["compactLeft"] = "code.lifetimeOpen"

    markers = []
    for depth in range(depth_limit):
        names = {kind: f"anglePair{depth}.{kind}" for kind in sources}
        for kind, original in sources.items():
            alias(names[kind], original)
        markers.append(names)
    cmap = font.getBestCmap()
    words = sorted(
        {name for cp, name in cmap.items() if chr(cp).isalnum() or chr(cp) == "_"}
    )
    capitals = sorted(
        {
            name
            for cp, name in cmap.items()
            if unicodedata.category(chr(cp)) in ("Lu", "Lt")
        }
    )
    # Unresolved angles block a match. Only completed lower-level pairs may be
    # crossed, so malformed input cannot lend a tall angle to an unmatched one.
    ordinary = original_names - {
        ".notdef", *(cmap[cp] for cp in (10, 13) if cp in cmap),
        "less",
        "greater",
        "less.generic",
        "greater.generic",
        "code.lifetimeOpen",
    }
    rules = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "@PairWord=[" + " ".join(words) + "];",
        "@PairCapital=[" + " ".join(capitals) + "];",
    ]
    tall_openers = ["less.pairIntent"]
    if use_lifetimes:
        tall_openers += ["code.lifetimeOpen", "code.lifetimeOpen.short"]
    opener_class = "[" + " ".join(tall_openers) + "]"
    for depth, names in enumerate(markers):
        body = sorted(
            ordinary | {name for lower in markers[:depth] for name in lower.values()}
        )
        rules.append(f"@PairBody{depth}=[" + " ".join(body) + "];")
        tall_left = [names["tallLeft"]]
        if use_lifetimes:
            tall_left += [names["compactLeft"]] * 2
        rules += [
            f"lookup TallLeft{depth} {{ sub {opener_class} by [{' '.join(tall_left)}]; }} TallLeft{depth};",
            f"lookup TallRight{depth} {{ sub greater by {names['tallRight']}; }} TallRight{depth};",
            f"lookup ShortLeft{depth} {{ sub less by {names['shortLeft']}; }} ShortLeft{depth};",
            f"lookup ShortRight{depth} {{ sub greater by {names['shortRight']}; }} ShortRight{depth};",
        ]
    if use_lifetimes:
        rules.append("feature ss01 { sub code.lifetimeOpen by code.lifetimeOpen.short; } ss01;")
    rules += [
        "feature calt {",
        "lookup ResetAngles { sub less.generic by less; sub greater.generic by greater; } ResetAngles;",
        "lookup TypePairIntent { lookupflag IgnoreMarks;",
        "sub less' underscore greater by less.pairIntent;",
        "sub less' bracketleft underscore bracketright greater by less.pairIntent;",
    ]
    if use_lifetimes:
        rules.append("sub less' [quotesingle.lifetime quotesingle.lifetime.compact] by less.pairIntent;")
    elif "quotesingle.lifetime" in original_names:
        rules.append("sub less' quotesingle.lifetime by less.pairIntent;")
    else:
        rules.extend((
            "ignore sub less' quotesingle @PairWord quotesingle;",
            "sub less' quotesingle @PairWord by less.pairIntent;",
        ))
    if scope in original_names:
        rules.append(f"sub {scope} less' by less.pairIntent;")
    else:
        rules.append("sub colon colon less' by less.pairIntent;")
    for count in range(32):
        middle = " ".join(["@PairWord"] * count)
        rules += [
            "sub @PairCapital " + middle + " less' by less.pairIntent;",
            "sub less' " + middle + " @PairCapital by less.pairIntent;",
        ]
    rules.append("} TypePairIntent;")
    for depth in range(depth_limit):
        rules += [f"lookup MatchAnglePairs{depth} {{", "lookupflag IgnoreMarks;"]
        for count in range(span_limit + 1):
            middle = " ".join([f"@PairBody{depth}'"] * count)
            rules += [
                f"sub {opener_class}' lookup TallLeft{depth} "
                + middle
                + f" greater' lookup TallRight{depth};",
                f"sub less' lookup ShortLeft{depth} "
                + middle
                + f" greater' lookup ShortRight{depth};",
            ]
        rules.append(f"}} MatchAnglePairs{depth};")
    # Inherit a generic parent's style top-down. The parent's closing marker
    # is excluded from its body class, preventing style from leaking outside.
    for depth in reversed(range(1, depth_limit)):
        left = [m[k] for m in markers[:depth] for k in ("shortLeft", "shortRight")]
        right = [m[k] for m in markers[:depth] for k in ("tallLeft", "tallRight")]
        parent = markers[depth]
        parent_openers = " ".join(parent[kind] for kind in ("tallLeft", "compactLeft") if kind in parent)
        rules += [f"lookup InheritPairStyle{depth} {{", "lookupflag IgnoreMarks;"]
        for count in range(span_limit + 1):
            middle = " ".join([f"@PairBody{depth}"] * count)
            rules.append(
                f"sub [{parent_openers}] "
                + middle
                + " ["
                + " ".join(left)
                + "]' by ["
                + " ".join(right)
                + "];"
            )
        rules.append(f"}} InheritPairStyle{depth};")
    rules += ["lookup FinishAnglePairs {", "sub less.pairIntent by less;"]
    if use_lifetimes:
        rules.append("sub code.lifetimeOpen by code.lifetimeOpen.short;")
    for names in markers:
        for kind, final in sources.items():
            rules.append(f"sub {names[kind]} by {final};")
    rules += ["} FinishAnglePairs;", "} calt;"]
    if scope in original_names:
        dx, dy = scope_inset
        rules += [
            "feature calt {",
            f"pos {scope}' <{dx} {dy} 0 0> less.generic' <{-dx} 0 0 0>;",
            "} calt;",
        ]
    add_features(font, "\n".join(rules))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    font = TTFont(SOURCE, recalcTimestamp=False)
    build_angle_pairs(font, depth_limit=16, span_limit=60)
    for record in font["name"].names:
        text = record.toUnicode()
        if record.nameID == 3:
            text = "DaikonicTransitCode-VF 1.036"
        elif record.nameID == 5:
            text = "Version 1.036"
        elif record.nameID == 10:
            text = "Daikonic Transit Code; balanced angle pairs, independent Logic and lifetime features."
        record.string = text.encode(record.getEncoding())
    font["head"].fontRevision = 1.036
    target = OUT / "VF/DaikonicTransitCode-VF.ttf"
    target.parent.mkdir(exist_ok=True)
    font.save(target)
    (OUT / "selection.json").write_text(
        json.dumps(
            {
                "family": "Daikonic Transit Code",
                "version": "1.036",
                "status": "release",
                "weight_range": [300, 400],
            },
            indent=2,
        )
        + "\n"
    )
    check(target)
    proof(target)


def proof(target):
    p = Panel("angle-pairs", DATA["families"]["code"])
    from fontTools.varLib.instancer import instantiateVariableFont

    bind(p, instantiateVariableFont(TTFont(target), {"wght": 350}, inplace=True))
    for row, (label, features) in enumerate(
        [("Logic off", {"ss02": False}), ("Logic on", {"ss02": True})]
    ):
        p.text(label, 25, 40 + row * 150, 22, 400, "#194454")
        p.text(
            "a<>b  Vec<>  Vec<Vec<T>>  Vec<T  T>",
            25,
            105 + row * 150,
            34,
            400,
            "#101712",
            features={"calt": True, **features},
        )
    (ROOT / "specimens/features/Angle-Pairs.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1450" height="310" viewBox="0 0 1450 310"><rect width="1450" height="310" fill="#EEECD9"/>'
        + p.body()
        + "</svg>"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--proof", action="store_true")
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    if args.proof:
        from specimens import specimen_families

        proof(args.font or ROOT / specimen_families()["code"]["font"])
    elif args.check:
        check(args.font or OUT / "VF/DaikonicTransitCode-VF.ttf")
    else:
        main()
