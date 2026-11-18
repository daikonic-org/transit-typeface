"""Order empty nested Logic forms as two adjacent closed shapes."""

from itertools import product
from pathlib import Path
import pathops
from audit import shape_from_glyphs
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
from font_feature_tools import compose, add_features, remap_lookup_records
from specimens import ROOT, DATA, Panel, specimen_families
from code_balance_study import bind
from check_syntax_numerals import run

SOURCE = ROOT / "previews/code-1.032/VF/DaikonicTransitCode-VF.ttf"
OUT = ROOT / "sources/code-logic-sequences/DaikonicTransitCodeLogic-VF.ttf"
SEQUENCES = {
    "[<>]": ("code.logicBoxDiamond", ["code.enclosureBox", "code.enclosureDiamond"]),
    "<[]>": ("code.logicDiamondBox", ["code.enclosureDiamond", "code.enclosureBox"]),
}


def check(path):
    f = TTFont(path)
    source = TTFont(SOURCE)
    baseline = (
        ROOT / "releases/2026.11.18/code/VF/DaikonicTransitCode-VF.ttf"
        if "anglePair0.shortLeft" in f.getGlyphOrder()
        else SOURCE
    )
    set_record = next(
        (
            r
            for r in f["GSUB"].table.FeatureList.FeatureRecord
            if r.FeatureTag == "ss01"
        ),
        None,
    )
    hooked = bool(
        set_record
        and f["name"].getDebugName(set_record.Feature.FeatureParams.UINameID)
        == "Extended Rust lifetime hooks"
    )
    changed = (
        {
            "quotesingle.lifetime",
            "quotesingle.lifetime.compact",
            "code.lifetimeOpen",
            "code.lifetimeBorrow",
        }
        if hooked
        else set()
    )
    for name in source.getGlyphOrder():
        if name in changed:
            continue  # Geometry and fixed-anchor fitting are verified by check_rust_lifetimes.
        assert f["glyf"][name].compile(f["glyf"]) == source["glyf"][name].compile(
            source["glyf"]
        ), name
        assert f["gvar"].variations.get(name) == source["gvar"].variations.get(
            name
        ), name
        assert f["hmtx"][name] == source["hmtx"][name], name
    carets = dict(
        zip(
            f["GDEF"].table.LigCaretList.Coverage.glyphs,
            f["GDEF"].table.LigCaretList.LigGlyph,
        )
    )
    for weight, calt, compact, logic in product(
        range(300, 401, 10), [False, True], [False, True], [False, True]
    ):
        features = {"calt": calt, "ss01": compact, "ss02": logic}
        for text, (glyph, _) in SEQUENCES.items():
            result = run(path, text, {"wght": weight}, features)
            assert sum(p[1] for p in result) == 2400
            if logic:
                assert [p[0] for p in result] == [glyph], (text, features, result)
            else:
                assert result == run(baseline, text, {"wght": weight}, features), (
                    text,
                    features,
                )
        for text in ["<[T]>", "[<T>]", "<> []", "-> ->> =>", "&'a <'a>"]:
            if hooked and text == "&'a <'a>":
                continue
            assert run(path, text, {"wght": weight}, features) == run(
                baseline, text, {"wght": weight}, features
            ), (text, features)
    for weight in range(300, 401, 10):
        gs = f.getGlyphSet(location={"wght": weight})
        for text, (glyph, parts) in SEQUENCES.items():
            expected = pathops.op(
                shape_from_glyphs(gs, parts[0]),
                shape_from_glyphs(gs, parts[1]).transform(1, 0, 0, 1, 1200, 0),
                pathops.PathOp.UNION,
            )
            difference = pathops.op(
                shape_from_glyphs(gs, glyph), expected, pathops.PathOp.XOR
            )
            assert abs(difference.area) < 0.01, (weight, text, difference.area)
        if "anglePair0.shortLeft" in f.getGlyphOrder():
            for text, (glyph, _) in SEQUENCES.items():
                wrapped = run(
                    path,
                    "Vec<" + text + ">",
                    {"wght": weight},
                    {"calt": True, "ss02": True},
                )
                names = [p[0] for p in wrapped]
                assert names == [
                    "V",
                    "e",
                    "c",
                    "less.generic",
                    glyph,
                    "greater.generic",
                ], names
    for glyph, _ in SEQUENCES.values():
        assert f["GDEF"].table.GlyphClassDef.classDefs[glyph] == 2
        assert [v.Coordinate for v in carets[glyph].CaretValue] == [600, 1200, 1800]
    print(
        "Logic sequence order: 11 weights, eight toggle combinations, four-cell widths and three carets verified",
        flush=True,
    )


def main():
    f = TTFont(SOURCE, recalcTimestamp=False)
    for glyph, components in SEQUENCES.values():
        compose(
            f,
            glyph,
            [(name, 1, 1, 1200 * i, 0) for i, name in enumerate(components)],
            2400,
            sum_metrics=True,
        )
    for glyph, _ in SEQUENCES.values():
        f["GDEF"].table.GlyphClassDef.classDefs[glyph] = 2
    feature = next(
        r for r in f["GSUB"].table.FeatureList.FeatureRecord if r.FeatureTag == "ss02"
    )
    table = {}
    for less, greater in product(
        ["less", "less.generic"], ["greater", "greater.generic"]
    ):
        for text, components in [
            ("[<>]", ["bracketleft", less, greater, "bracketright"]),
            ("<[]>", [less, "bracketleft", "bracketright", greater]),
        ]:
            ligature = otTables.Ligature()
            ligature.Component = components[1:]
            ligature.CompCount = len(components)
            ligature.LigGlyph = SEQUENCES[text][0]
            table.setdefault(components[0], []).append(ligature)
    lookup = otTables.Lookup()
    lookup.LookupType, lookup.LookupFlag = 4, 0
    subtable = otTables.LigatureSubst()
    subtable.ligatures = table
    lookup.SubTable = [subtable]
    lookup.SubTableCount = 1
    layout = f["GSUB"].table
    assert not getattr(layout, "FeatureVariations", None)
    position = feature.Feature.LookupListIndex[0]
    remap_lookup_records(layout.LookupList.Lookup, 1, position)
    for record in layout.FeatureList.FeatureRecord:
        record.Feature.LookupListIndex = [
            index + (index >= position) for index in record.Feature.LookupListIndex
        ]
    layout.LookupList.Lookup.insert(position, lookup)
    layout.LookupList.LookupCount += 1
    feature.Feature.LookupListIndex.insert(0, position)
    feature.Feature.LookupCount += 1
    add_features(
        f,
        "table GDEF {\n"
        + "\n".join(
            "LigatureCaretByPos " + glyph + " 600 1200 1800;"
            for glyph, _ in SEQUENCES.values()
        )
        + "\n} GDEF;",
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    f.save(OUT)
    check(OUT)


def proof():
    from fontTools.varLib.instancer import instantiateVariableFont
    from copy import deepcopy

    source = ROOT / specimen_families()["code"]["font"]
    vf = TTFont(source)
    parts = []
    for row, (weight, label) in enumerate(
        [(300, "Light"), (350, "Book"), (400, "Regular")]
    ):
        f = instantiateVariableFont(deepcopy(vf), {"wght": weight}, inplace=True)
        for col, enabled in enumerate([True, False]):
            p = Panel("logic-order-" + str(weight) + str(col), DATA["families"]["code"])
            bind(p, f)
            x, y = 25 + 650 * col, 40 + 180 * row
            p.text(
                label + " / Logic " + ("on" if enabled else "off"),
                x,
                y,
                23,
                400,
                "#194454",
            )
            p.text(
                "[<>]  <[]>  []<>  <>[]",
                x,
                y + 65,
                34,
                400,
                "#101712",
                features={"calt": True, "ss02": enabled},
            )
            p.text(
                "Vec<[<>]>  Vec<<[]>>",
                x,
                y + 115,
                27,
                400,
                "#101712",
                features={"calt": True, "ss02": enabled},
            )
            parts.append(p.body())
    (ROOT / "specimens/features/Logic-Order.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="570" viewBox="0 0 1300 570"><rect width="1300" height="570" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    print("Current-font Logic sequence proof generated")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--proof", action="store_true")
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    if args.proof:
        proof()
    elif args.check:
        check((args.font or OUT).resolve())
    else:
        main()
