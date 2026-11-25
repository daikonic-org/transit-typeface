"""Build the Code italic from the current upright’s letter and mark components."""

from argparse import ArgumentParser
import json
from pathlib import Path

from fontTools.ttLib import TTFont
import uharfbuzz as hb

from build_code import RECIPE_PATH, alphabet_font
from build_sans_italic import apply_slant, reuse_single_storey_a
from bundle_release import sanitize
from check_code_rebuild import shape
from code_layout import build_layout
from font_feature_tools import add_features
from italic_companions import ANGLE, set_style
from italic_letterforms import redraw_italic_letters
from italic_returns import raw_outline
from repeated_stems import add_monospace_repeats
from specimens import ROOT
from system_italic import designspace
from system_metrics import set_vertical_metrics


def build_italic(font, recipe, family, *, version, spread_glyph=True):
    build_layout(font, recipe, hairlines=False, spread_glyph=spread_glyph, spacing_style="italic")
    locations, model, default = designspace(font)
    masters = [font.getGlyphSet(location=location) for location in locations]
    metric_sources = reuse_single_storey_a(font, designspace=(model, masters, default))
    redrawn, _ = redraw_italic_letters(
        font, "cursive", family="code", descending_f=True, live_components=True, donor_returns=True,
    )
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    selected = {name for cp, name in font.getBestCmap().items() if chr(cp).isalpha()}
    selected |= redrawn | {name for name, cls in classes.items() if cls == 3}
    selected.update(name for name in ("fi", "fl", "f_f", "t_t") if name in classes)
    glyf = font["glyf"]
    pending = list(selected)
    while pending:
        name = pending.pop()
        if glyf[name].isComposite():
            donors = set(glyf[name].getComponentNames(glyf)) - selected
            selected.update(donors)
            pending.extend(donors)

    apply_slant(font, metric_sources, dotted=("i", "j"), variable_anchors=True, selected=selected)
    set_style(font, {"name": family, "stem": family.replace(" ", ""), "version": version})
    add_monospace_repeats(font)
    fixed = recipe["layout_review"].get("edge_spacing", {}).get("fixed", "")
    strong_underscore = " ".join(char for char in "mDM" if char not in fixed)
    light_underscore = " ".join(char for char in "pxAHKNX" if char not in fixed)
    add_features(font, f"""
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        feature kern {{
            pos at f' <24 0 0 0>;
            pos underscore [{strong_underscore}]' <20 0 0 0>;
            pos underscore [{light_underscore}]' <8 0 0 0>;
            pos underscore Z' <6 0 0 0>;
        }} kern;
    """)
    bounds = recipe["alphabet_review"]["line_metrics"]
    set_vertical_metrics(font, minimum_ascent=bounds["ascent"], maximum_descent=bounds["descent"])


def verify_italic(font, path, cell):
    assert font["post"].italicAngle == -ANGLE and font["OS/2"].fsSelection & 1
    glyf = font["glyf"]
    assert glyf["a"].getComponentNames(glyf) == ["a.ss01"]
    assert glyf["i"].getComponentNames(glyf) == ["dotlessi", "uni0307"]
    engine = hb.Font(hb.Face(path.read_bytes()))
    for weight in range(350, 501, 25):
        engine.set_variations({"wght": weight})
        gs = font.getGlyphSet(location={"wght": weight})
        for name in ("f", "g"):
            outline = raw_outline(gs, name)
            assert outline.bounds[1] < -100
        assert raw_outline(gs, "i").bounds[1] >= 0
        assert abs(raw_outline(gs, "j").bounds[1] - raw_outline(gs, "uni0237").bounds[1]) <= 1
        for text in ("ff", "tt", "ll"):
            name = "_".join(text)
            assert shape(engine, text, {})[0][:3] == [name, 0, 2 * cell], text
            assert [row[2] for row in shape(engine, text, {"liga": False})] == [cell, cell]
        for text in ("áéíóú ñçšž", "Český Ångström", "ŕř"):
            assert all(row[2] == cell for row in shape(engine, text, {})), (weight, text)
        assert shape(engine, "a | b", {})[2][0] == "bar"
        assert shape(engine, "&'a", {})[1][0] == "quotesingle.lifetime"
        assert shape(engine, "(a)", {})[0][0] == "parenleft"
    return {"italic_angle": -ANGLE, "live_a_and_i": True, "repeat_ligatures": ["ff", "tt", "ll"]}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=RECIPE_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text())
    source = ROOT / (recipe["fonts"]["sans"] + "-VF.ttf")
    with TTFont(source, recalcTimestamp=False) as sans:
        font, _ = alphabet_font(sans, recipe, stage="Layout")
    build_italic(font, recipe, font["name"].getBestFamilyName(), version="0.100")
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "DaikonicTransitCodeLayoutReview-Italic-VF.ttf"
    font.save(path)
    with TTFont(path) as built:
        print(verify_italic(built, path, recipe["alphabet_review"]["cell"]), flush=True)
        sanitize(built)


if __name__ == "__main__":
    main()
