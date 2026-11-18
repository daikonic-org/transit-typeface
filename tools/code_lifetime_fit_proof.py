"""Prove opening-quote lifetime marks centered on the target cell boundary."""

from copy import deepcopy
import hashlib
import json
import shutil

import pathops
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from audit import shape_from_glyphs
import uharfbuzz as hb
from check_rust_lifetimes import check
from code_balance_study import bind
from specimens import ROOT, DATA, Panel
from syntax_numeral_study import OUT as STUDY, RECIPE

OUT = ROOT / "trials/2026-11-17-lifetime-quote-shift"


def main():
    OUT.mkdir(exist_ok=True)
    source = STUDY / "code/DaikonicTransitCodeSyntaxStudy-VF.ttf"
    target = OUT / source.name
    shutil.copy2(source, target)
    vf = TTFont(target)
    fit = RECIPE["code"]["rust_lifetime"]
    results = []
    h = hb.Font(hb.Face(target.read_bytes()))
    h.scale = (1000, 1000)
    for weight in range(300, 401, 10):
        gs = vf.getGlyphSet(location={"wght": weight})
        h.set_variations({"wght": weight})
        for letter in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_é":
            for prefix in ("'", "&'", "<'"):
                text = prefix + letter
                b = hb.Buffer()
                b.add_str(text)
                b.guess_segment_properties()
                hb.shape(h, b, {"calt": True, "ss01": True})
                items = []
                x = 0
                for info, pos in zip(b.glyph_infos, b.glyph_positions):
                    name = vf.getGlyphName(info.codepoint)
                    path = shape_from_glyphs(gs, name).transform(
                        1, 0, 0, 1, x + pos.x_offset, pos.y_offset
                    )
                    items.append((name, path))
                    x += pos.x_advance
                assert x == len(text) * 600, (weight, text, x)
                mark = next(
                    path
                    for name, path in items
                    if name == "quotesingle.lifetime.compact"
                )
                target_left = len(prefix) * 600
                assert abs((mark.bounds[0] + mark.bounds[2]) / 2 - target_left) < 1
                for name, path in items:
                    if name != "quotesingle.lifetime.compact":
                        assert (
                            pathops.op(mark, path, pathops.PathOp.INTERSECTION).area < 1
                        ), (weight, text, name)
                if len(prefix) == 2:
                    name, front = items[0]
                    original = "ampersand" if prefix.startswith("&") else "less.generic"
                    expected = shape_from_glyphs(gs, original).bounds
                    assert (
                        max(
                            abs(v - z)
                            for v, z in zip(
                                front.bounds,
                                (
                                    expected[0] + 600,
                                    expected[1],
                                    expected[2] + 600,
                                    expected[3],
                                ),
                            )
                        )
                        < 1
                    )
                results.append(
                    {
                        "weight": weight,
                        "text": text,
                        "quote_bounds": list(mark.bounds),
                        "advance": x,
                    }
                )
    report = check(target)
    report["cell_fitting"] = results
    report["recipe"] = fit
    report["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    (OUT / "validation.json").write_text(json.dumps(report, indent=2) + "\n")
    parts = []
    for row, (weight, label) in enumerate(
        [(300, "Light"), (350, "Book"), (400, "Regular")]
    ):
        f = instantiateVariableFont(deepcopy(vf), {"wght": weight}, inplace=True)
        p = Panel("lifetime-fit-" + label, DATA["families"]["code"])
        bind(p, f)
        y = 45 + row * 235
        p.text(label, 25, y, 23, 400, "#194454")
        for col, text in enumerate(["&'a", "<'a>"]):
            x = 160 + col * 440
            for cell in range(len(text)):
                fill = "#E2E0CE" if cell == 0 else "none"
                parts.append(
                    f'<rect x="{x+cell*72}" y="{y+15}" width="72" height="105" fill="{fill}" stroke="#C06D3E" stroke-width="0.7"/>'
                )
            p.text(
                text,
                x,
                y + 95,
                120,
                400,
                "#101712",
                features={"calt": True, "ss01": True},
            )
        p.text(
            "fn get<'a>(x: &'a str) -> &'a str",
            25,
            y + 180,
            29,
            400,
            "#101712",
            features={"calt": True, "ss01": True},
            max_width=960,
        )
        parts.append(p.body())
    f = instantiateVariableFont(deepcopy(vf), {"wght": 350}, inplace=True)
    p = Panel("lifetime-fit-text", DATA["families"]["code"])
    bind(p, f)
    p.text("Book / text sizes", 25, 775, 22, 400, "#194454")
    for row, size in enumerate([14, 18, 24]):
        p.text(
            f"{size}px   fn borrow<'a>(value: &'a T) -> &'a T",
            25,
            820 + row * 48,
            size,
            400,
            "#101712",
            features={"calt": True, "ss01": True},
            max_width=950,
        )
    parts.append(p.body())
    (OUT / "Lifetime-Boundary.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="950" viewBox="0 0 1000 950"><title>Lifetime pairs: opening quote centered on the target cell boundary</title><rect width="1000" height="950" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    toggles = []
    for row, (weight, label) in enumerate(
        [(300, "Light"), (350, "Book"), (400, "Regular")]
    ):
        f = instantiateVariableFont(deepcopy(vf), {"wght": weight}, inplace=True)
        for col, (title, enabled) in enumerate(
            [("Normal / ss01 off", False), ("Boundary / ss01 on", True)]
        ):
            p = Panel("toggle-" + label + str(col), DATA["families"]["code"])
            bind(p, f)
            x, y = 25 + 650 * col, 45 + 250 * row
            p.text(label + " / " + title, x, y, 21, 400, "#194454")
            for n, text in enumerate(
                ["&'a  <'a>  'static", "fn f<'b>(x: &'b T)", "'a'  '_'  ->  ==  ###"]
            ):
                p.text(
                    text,
                    x,
                    y + 65 + 65 * n,
                    33,
                    400,
                    "#101712",
                    features={"calt": True, "ss01": enabled},
                    max_width=610,
                )
            toggles.append(p.body())
    (OUT / "Lifetime-Toggle.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="800" viewBox="0 0 1300 800"><title>Independent lifetime placement switch</title><rect width="1300" height="800" fill="#EEECD9"/>'
        + "".join(toggles)
        + "</svg>"
    )
    print(
        "Opening quote centers on target cell boundary; leaders shift exactly600; no overlaps across11weights"
    )


if __name__ == "__main__":
    main()
