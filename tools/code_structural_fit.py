"""Separate mixed enclosures, fit generic closer runs, and center interpolation dollars."""

from pathlib import Path
from itertools import product
from fontTools.ttLib import TTFont
from font_feature_tools import compose, add_features
from audit import shape_from_glyphs
from check_syntax_numerals import run
from specimens import ROOT, DATA, Panel

SOURCE = ROOT / "sources/code-lifetime-hook/VF/DaikonicTransitCode-VF.ttf"
OUT = ROOT / "sources/code-structural-fit/VF/DaikonicTransitCode-VF.ttf"
MIXED = {
    "code.squareAngleOpen",
    "code.angleSquareOpen",
    "code.squareAngleClose",
    "code.angleSquareClose",
}
INTERPOLATION = {
    "code.syntax02": "braceleft",
    "code.syntax03": "bracketleft",
    "code.syntax04": "parenleft",
}


def separate_enclosures(font):
    return not any(
        form.LigGlyph in MIXED
        for lookup in font["GSUB"].table.LookupList.Lookup
        for subtable in lookup.SubTable
        if hasattr(subtable, "ligatures")
        for forms in subtable.ligatures.values()
        for form in forms
    )


def mixed_angle_rules(features, shift):
    lines = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "lookup SeparateMixedAngles {",
        "sub less' bracketleft by less.generic;",
        "sub bracketleft less' by less.generic;",
        "sub bracketright greater' by greater.generic;",
        "sub greater' bracketright by greater.generic;",
        "} SeparateMixedAngles;",
    ]
    for feature in features:
        lines.append(f"feature {feature} {{ lookup SeparateMixedAngles; }} {feature};")
    pairs = [
        ("less.generic", "bracketleft"),
        ("bracketleft", "less.generic"),
        ("bracketright", "greater.generic"),
        ("greater.generic", "bracketright"),
    ]
    lines += ["lookup MixedPairFirst {"]
    for first, last in pairs:
        lines.append(f"pos {first}' <{shift} 0 0 0> {last};")
    lines += ["} MixedPairFirst;", "lookup MixedPairLast {"]
    for first, last in pairs:
        lines.append(f"pos {first} {last}' <{-shift} 0 0 0>;")
    lines += ["} MixedPairLast;"]
    for feature in features:
        lines.append(
            f"feature {feature} {{ lookup MixedPairFirst; lookup MixedPairLast; }} {feature};"
        )
    return lines


def generic_closer_rules(font, cell, depth, install_closer):
    for count in range(2, depth + 1):
        extent = min(30 * (count - 1), 90)
        parts = [
            (
                "greater.generic",
                1,
                1,
                cell * i + extent - 2 * extent * i / (count - 1),
                0,
            )
            for i in range(count)
        ]
        name = f"code.genericClose{count}"
        if install_closer is None:
            compose(font, name, parts, count * cell, sum_metrics=True)
        else:
            install_closer(name, parts, count * cell)
        font["GDEF"].table.GlyphClassDef.classDefs[name] = 2
    lines = ["feature calt { lookup GenericCloserRuns {"]
    for count in range(depth, 1, -1):
        lines.append(
            "sub "
            + " ".join(["greater.generic"] * count)
            + f" by code.genericClose{count};"
        )
    lines += ["} GenericCloserRuns; } calt;", "table GDEF {"]
    for count in range(2, depth + 1):
        lines.append(
            f"LigatureCaretByPos code.genericClose{count} "
            + " ".join(str(i * cell) for i in range(1, count))
            + ";"
        )
    lines += ["} GDEF;"]
    return lines


def build_structural_angles(font, cell, depth, *, features=("calt",), shift=30, install_closer=None):
    lines = mixed_angle_rules(features, shift)
    lines.extend(generic_closer_rules(font, cell, depth, install_closer))
    add_features(font, "\n".join(lines))


def build():
    font = TTFont(SOURCE, recalcTimestamp=False)
    for lookup in font["GSUB"].table.LookupList.Lookup:
        for subtable in lookup.SubTable:
            if hasattr(subtable, "ligatures"):
                subtable.ligatures = {
                    first: [f for f in forms if f.LigGlyph not in MIXED]
                    for first, forms in subtable.ligatures.items()
                }
                subtable.ligatures = {
                    first: forms for first, forms in subtable.ligatures.items() if forms
                }
    for name, delimiter in INTERPOLATION.items():
        compose(
            font, name, [("dollar", 1, 1, 35, -50), (delimiter, 1, 1, 565, 0)], 1200
        )
    build_structural_angles(font, 600, 16, features=("calt", "ss02"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    font.save(OUT)
    return OUT


def check(path):
    f = TTFont(path)
    source = TTFont(SOURCE)
    assert separate_enclosures(f)
    carets = dict(
        zip(
            f["GDEF"].table.LigCaretList.Coverage.glyphs,
            f["GDEF"].table.LigCaretList.LigGlyph,
        )
    )
    for count in range(2, 17):
        assert [
            v.Coordinate for v in carets[f"code.genericClose{count}"].CaretValue
        ] == list(range(600, count * 600, 600))
    for n in source.getGlyphOrder():
        if n not in INTERPOLATION:
            assert f["glyf"][n].compile(f["glyf"]) == source["glyf"][n].compile(
                source["glyf"]
            ), n
            assert f["gvar"].variations.get(n) == source["gvar"].variations.get(n), n
            assert f["hmtx"][n] == source["hmtx"][n], n
    for weight, calt, logic, compact in product(
        range(300, 401, 10), [False, True], [False, True], [False, True]
    ):
        features = {"calt": calt, "ss02": logic, "ss01": compact}
        for text in ["<[T]>", "[<T>]", "<[T", "[<T", "T]>", "T>]"]:
            shaped = run(path, text, {"wght": weight}, features)
            assert sum(v[1] for v in shaped) == 600 * len(text)
            assert not any(n in MIXED for n, *_ in shaped)
            if calt or logic:
                for ch, (n, *_) in zip(text, shaped):
                    if ch in "<>":
                        assert n.endswith(".generic"), (text, features, shaped)
        for text in ["<[T", "[<T", "T]>", "T>]"]:
            shaped = run(path, text, {"wght": weight}, features)
            if calt or logic:
                pair = shaped[:2] if text.startswith(("<[", "[<")) else shaped[-2:]
                assert [item[2] for item in pair] == [30, -30], (text, features, shaped)
        for text, glyph in [
            ("[<>]", "code.logicBoxDiamond"),
            ("<[]>", "code.logicDiamondBox"),
        ]:
            shaped = run(path, text, {"wght": weight}, features)
            if logic:
                assert shaped == [(glyph, 2400, 0, 0)], (text, features, shaped)
        for count in [2, 3, 4, 8, 16]:
            text = "A<" * count + "T" + ">" * count
            shaped = run(path, text, {"wght": weight}, features)
            assert sum(v[1] for v in shaped) == 600 * len(text)
            assert any(n == f"code.genericClose{count}" for n, *_ in shaped) == calt, (
                count,
                features,
                shaped,
            )
        for text in ["a >> b", "a >>> b", "Vec<T>>", "->>"]:
            assert run(path, text, {"wght": weight}, features) == run(
                SOURCE, text, {"wght": weight}, features
            ), (text, features)
    for weight in range(300, 401, 10):
        gs = f.getGlyphSet(location={"wght": weight})
        for delimiter in INTERPOLATION.values():
            dollar = shape_from_glyphs(gs, "dollar").bounds
            other = shape_from_glyphs(gs, delimiter).bounds
            assert abs((dollar[1] + dollar[3]) / 2 - 50 - (other[1] + other[3]) / 2) < 1
    print(
        "Structural fit: separate mixed enclosures, fixed-cell nested closers, operators and dollar centers verified across11weights"
    )


def proof(path):
    cfg = {**DATA["families"]["code"], "font": str(path.relative_to(ROOT))}
    p = Panel("structure", cfg)
    headers = [
        '<rect width="1180" height="760" fill="#eeeddb"/>',
        "<style>text{font-family:Arial,sans-serif;fill:#172331}</style>",
        '<text x="30" y="40" font-size="24">Code · nested closers and separate mixed enclosures</text>',
    ]
    for row, (label, text) in enumerate(
        [
            ("Nested generics", "Vec<Vec<T>>  A<B<C<T>>>"),
            ("Mixed enclosures", "<[T]>  [<T>]  <[T  [<T"),
            ("Empty Logic order", "[<>]  <[]>  <>  []"),
            ("Interpolation", "${value}  $[index]  $(value)"),
            ("Operator controls", "a >> b  a >>> b  ->>"),
        ]
    ):
        y = 105 + 125 * row
        headers.append(f'<text x="30" y="{y}" font-size="14">{label}</text>')
        for x, logic in [(30, False), (625, True)]:
            p.text(
                text,
                x,
                y + 55,
                28,
                350,
                "#172331",
                features={"ss02": logic},
                max_width=550,
            )
    headers += [
        '<text x="30" y="75" font-size="14">Logic off</text>',
        '<text x="625" y="75" font-size="14">Logic on</text>',
    ]
    target = ROOT / "specimens/features/Code-Structural-Fit.svg"
    target.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="760"><defs>'
        + "".join(p.defs.values())
        + "</defs>"
        + "".join(headers)
        + "".join(p.elements)
        + "</svg>"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--font", type=Path)
    args = parser.parse_args()
    path = args.font or (OUT if args.check else build())
    check(path)
    if not args.check:
        proof(path)
