"""Build and proof the Sans-derived Transit Code upright alphabet."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from math import isclose
from pathlib import Path
from unicodedata import normalize

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor
from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont
from fontTools.varLib import build as build_variable
import uharfbuzz as hb

from audit import shape_from_glyphs
from bundle_release import sanitize
from check_code_rebuild import RECIPE_PATH, ROOT, shape
from code_at import build_at
from code_foundation import build_master, horizontal_mirror, scale_ink_width, width_class_scales
from code_outlines import (
    SYMBOLS, build_composed, build_crossbar_letters, build_custom_letters, build_distinct_figures, build_g,
    build_horizontal_punctuation, inherit_width_scales,
)
from code_punctuation import build_diamond_punctuation
from code_weight_width_trial import name_trial
from derive_weights import topology
from glyph_proof import build_proof
from render_svg import render
from scaling_study import vertical_stem
from specimens import Panel
from system_metrics import set_vertical_metrics

WEIGHTS = {350: "Book", 400: "Regular", 500: "Medium"}
FEATURES = {"calt": False, "kern": False, "liga": False}


def alphabet_font(source, recipe, *, stage="Alphabet"):
    config = recipe["alphabet_review"]
    anchor = recipe["anchor"]
    weights = {int(weight): value for weight, value in config["weights"].items()}
    assert weights[anchor["code_weight"]] == anchor["sans_weight"]
    assert list(weights) == list(WEIGHTS)
    family = f"Daikonic Transit Code {stage} Review"

    masters = {weight: build_master(source, weights[weight], weight, config) for weight in WEIGHTS}
    scales, stems, width_report = width_class_scales(masters, recipe)
    if stage != "Alphabet":
        width_report["deferred"] = width_report["deferred"].replace("r", "")
    if stage == "Letters":
        letters = recipe["custom_lowercase_review"]
        followers = letters["width_followers"]
        inherit_width_scales(masters[400], scales, followers)
        width_report["followers"] = followers
        finished = set(letters["accepted_foundation"]) | set(followers) | set("ifgjlt")
        width_report["deferred"] = "".join(ch for ch in width_report["deferred"] if ch not in finished)

    for weight, master in masters.items():
        if stage == "Letters":
            build_at(master, recipe)
        scale_ink_width(master, scales, stems[weight])
        if stage != "Alphabet":
            build_composed(master, recipe)
    if stage == "Letters":
        build_custom_letters(masters.values(), recipe)
        for master in masters.values():
            build_crossbar_letters(master, recipe)
            build_g(master, recipe)
            build_distinct_figures(master, recipe)
            build_horizontal_punctuation(master, recipe)
            build_diamond_punctuation(master, recipe)

    designspace = DesignSpaceDocument()
    designspace.addAxis(AxisDescriptor(name="Weight", tag="wght", minimum=350, default=400, maximum=500))
    for weight, style in WEIGHTS.items():
        master = masters[weight]
        master["name"].setName(f"Version 0.100; Code {stage.lower()} review", 5, 3, 1, 0x409)
        name_trial(master, family, weight_style=style)
        location = {"Weight": weight}
        designspace.addSource(SourceDescriptor(
            name=style, familyName=family, styleName=style, location=location, font=master,
        ))
        designspace.addInstance(InstanceDescriptor(
            name=style, familyName=family, styleName=style, location=location,
        ))

    font, _, _ = build_variable(designspace)
    buildStatTable(font, [{
        "tag": "wght", "name": "Weight",
        "values": [{"name": style, "value": weight, "flags": 2 if weight == 400 else 0}
                   for weight, style in WEIGHTS.items()],
    }])
    name_trial(font, family, variable=True)
    font.recalcTimestamp = False
    return font, width_report


def measures(font, weight):
    glyphs = font.getGlyphSet(location={"wght": weight})
    return {
        name: {
            "ink_bounds": [round(v, 1) for v in shape_from_glyphs(glyphs, name).bounds],
            **({"vertical_stem": round(vertical_stem(shape_from_glyphs(glyphs, name), .4), 1)}
               if name in {"H", "n", "o"} else {}),
        }
        for name in "HxnromwW"
    }


def verify(font, path, config):
    engine = hb.Font(hb.Face(path.read_bytes()))
    cell = config["cell"]
    cmap = font.getBestCmap()
    glyphs_checked = set(cmap.values())
    metrics = dict(font["hmtx"].metrics)
    marks = [g for g in glyphs_checked if font["GDEF"].table.GlyphClassDef.classDefs.get(g) == 3]
    assert marks and all(metrics[g][0] == 0 for g in marks)
    for weight in range(350, 501, 25):
        engine.set_variations({"wght": weight})
        for text in ("HAMBURGEFONTS 0123456789", "abcdefghijklmnopqrstuvwxyz", "normalize(value)"):
            assert all(row[2] == cell for row in shape(engine, text, FEATURES)), (weight, text)
        for text in ("áéíóú ñçšž", "Český Ångström", "ŕř"):
            composed = shape(engine, text, FEATURES)
            decomposed = shape(engine, normalize("NFD", text), FEATURES)
            assert [row[:1] + row[2:] for row in composed] == [
                row[:1] + row[2:] for row in decomposed
            ], (weight, text)
        mark = shape(engine, "q́", FEATURES)
        assert len(mark) == 2 and sum(row[2] for row in mark) == cell and mark[-1][2] == 0, mark

    for name in ("i", "j", "adieresis", "nacute"):
        assert font["glyf"][name].isComposite(), name
    return {"weights": list(range(350, 501, 25)), "ascii_grid": cell, "zero_advance_marks": len(marks),
            "encoded_characters": len(cmap), "accent_equivalence": "NFC/NFD"}


def verify_latin_topology(source, candidate, config):
    for weight, donor_weight in config["weights"].items():
        donor = source.getGlyphSet(location={"wght": donor_weight})
        revised = candidate.getGlyphSet(location={"wght": int(weight)})
        for name in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
            assert topology(shape_from_glyphs(donor, name)) == topology(
                shape_from_glyphs(revised, name)
            ), (name, weight)


def verify_mirrors(source, candidate, cell, weights):
    pairs = {name: pair[0] for name in source.getGlyphOrder()
             if (pair := horizontal_mirror(source["glyf"][name]))
             and candidate["hmtx"][name][0] == candidate["hmtx"][pair[0]][0] == cell}
    for weight in weights:
        glyphs = candidate.getGlyphSet(location={"wght": weight})
        for name, donor in pairs.items():
            left, bottom, right, top = shape_from_glyphs(glyphs, donor).bounds
            expected = (cell - right, bottom, cell - left, top)
            actual = shape_from_glyphs(glyphs, name).bounds
            assert all(isclose(a, b, abs_tol=1e-6) for a, b in zip(actual, expected, strict=True)), (
                weight, name, donor, actual, expected
            )
    return pairs


def verify_composed(font, path, cell, weights):
    cmap = font.getBestCmap()
    assert all(cmap.get(code) == name for code, name in SYMBOLS.items())
    engine = hb.Font(hb.Face(path.read_bytes()))
    names = {name: [part.glyphName for part in font["glyf"][name].components]
             for name in ("universal", "existential", "notequal", "greaterequal")}
    assert names == {"universal": ["A"], "existential": ["E"],
                     "notequal": ["equal", "slash"], "greaterequal": ["lessequal"]}
    for name in (cmap[ord("ŕ")], cmap[ord("ř")]):
        assert font["glyf"][name].components[0].glyphName == "r"

    text = "".join(map(chr, SYMBOLS))
    for weight in weights:
        engine.set_variations({"wght": weight})
        rows = shape(engine, text, FEATURES)
        assert [(row[0], row[2]) for row in rows] == [(name, cell) for name in SYMBOLS.values()], (weight, rows)
        glyphs = font.getGlyphSet(location={"wght": weight})
        paths = {name: shape_from_glyphs(glyphs, name) for name in ("n", "r", *SYMBOLS.values())}
        assert topology(paths["n"]) == topology(paths["r"]), weight
        assert abs(paths["n"].bounds[3] - paths["r"].bounds[3]) <= 1, weight
        assert paths["notequal"].bounds[2] - paths["notequal"].bounds[0] < cell, weight
        for name in ("logicalnot", "notequal", "lessequal", "greaterequal"):
            assert topology(paths[name]) == ((2 if name in ("lessequal", "greaterequal") else 1), 0), (name, weight)
    return names


def signed_units(delta):
    return f"{delta:+.0f}" if round(delta) else "0"


def cell_guides(fonts, sample, x, size, top, bottom, delta_y, cell):
    cmaps = [font.getBestCmap() for font in fonts]
    names = [[cmap[ord(char)] for char in sample] for cmap in cmaps]
    upm = fonts[0]["head"].unitsPerEm
    assert all(font["head"].unitsPerEm == upm for font in fonts)
    assert all(font["hmtx"][name][0] == cell
               for font, run in zip(fonts, names, strict=True) for name in run), sample
    pitch = size * cell / upm
    boundaries = " ".join(f"M{x + pitch * index:.3f} {top}V{bottom}"
                          for index in range(len(sample) + 1))
    yield f'<path d="{boundaries}" stroke="#d5e1e2" stroke-width=".65"/>'
    if delta_y is None:
        return
    glyph_sets = [font.getGlyphSet() for font in fonts]
    for index, pair in enumerate(zip(*names, strict=True)):
        widths = []
        for glyph_set, name in zip(glyph_sets, pair, strict=True):
            left, _, right, _ = shape_from_glyphs(glyph_set, name).bounds
            widths.append(right - left)
        delta = round(widths[1] - widths[0])
        color = "#14675d" if delta > 0 else "#96432e" if delta < 0 else "#677b7f"
        center = x + pitch * (index + .5)
        yield (f'<text x="{center:.3f}" y="{delta_y}" text-anchor="middle" '
               f'font-size="8.5" fill="{color}">{signed_units(delta)}</text>')


def comparison(candidate, reference, output, width_report, cell, measurements):
    width, height = 1190, 1046
    sheets = [Panel("released", {"font": str(reference.resolve())}),
              Panel("candidate", {"font": str(candidate.resolve())})]
    bands = (
        (34, 76, 115, (
            (166, "Lowercase", "abcdefghijklmnopqrstuvwxyz", 30, True),
            (650, "Uppercase foundation", "ABCDEFGHIJKLMNOPQRSTUVWXYZ", 30, True),
        )),
        (174, 207, 239, (
            (166, "12 px", "let trim = n;", 12, False),
            (412, "14 px", "rows[index].value", 14, False),
            (658, "16 px", "fn narrow(n: u8)", 16, False),
            (910, "Digit foundation", "0123456789", 30, True),
        )),
    )
    rows = [
        f'<rect width="{width}" height="{height}" fill="#eaf1f0"/>',
        '<text x="36" y="46" font-size="31" font-weight="700">Transit Code · Upright alphabet</text>',
        f'<text x="37" y="74" font-size="15" fill="#415d62">'
        'Lowercase width classes · Published Code 1.042 above the candidate</text>',
        f'<text x="1154" y="46" text-anchor="end" font-size="13" fill="#415d62">{cell}-unit cells · Width differences in design units</text>',
        '<text x="1154" y="74" text-anchor="end" font-size="13">'
        '<tspan fill="#14675d">+ candidate wider</tspan><tspan fill="#415d62">  ·  </tspan>'
        '<tspan fill="#96432e">− 1.042 wider</tspan></text>',
    ]
    for index, (weight, style) in enumerate(WEIGHTS.items()):
        y = 101 + index * 285
        fonts = [panel.font(weight)[0] for panel in sheets]
        previous, current = (measurements[weight][key] for key in ("released", "candidate"))
        stem_deltas = (current[name]["vertical_stem"] - previous[name]["vertical_stem"] for name in "Hno")
        stems = " · ".join(f"{name} {signed_units(delta)}" for name, delta in zip("Hno", stem_deltas, strict=True))
        rows.extend((
            f'<rect x="36" y="{y}" width="1118" height="274" rx="6" fill="#f8faf9" stroke="#c7d6d7"/>',
            f'<text x="54" y="{y + 34}" font-size="16" font-weight="700">{style} {weight}</text>',
            f'<text x="1136" y="{y + 34}" text-anchor="end" font-size="12" fill="#415d62">Stem Δ · {stems}</text>',
            f'<path d="M54 {y + 151}H1136" stroke="#dce5e5"/>',
        ))
        for heading, old_baseline, new_baseline, specimens in bands:
            rows.append(f'<text x="54" y="{y + new_baseline + 23}" font-size="11" fill="#415d62">Ink width Δ</text>')
            for x, label, sample, size, annotate in specimens:
                rows.append(f'<text x="{x}" y="{y + heading}" font-size="13" fill="#415d62">{label}</text>')
                rows.extend(cell_guides(fonts, sample, x, size, y + heading + 7, y + new_baseline + 10,
                                        y + new_baseline + 23 if annotate else None, cell))
            for panel, label, baseline in zip(
                sheets, ("1.042", "Candidate"), (old_baseline, new_baseline), strict=True
            ):
                rows.append(f'<text x="54" y="{y + baseline}" font-size="13" fill="#415d62">{label}</text>')
                for x, _, sample, size, _ in specimens:
                    panel.text(sample, x, y + baseline, size, weight, "#153b40", features=FEATURES)
    active = [(name, row) for name, row in width_report["classes"].items() if row["sample"]]
    for index, (name, row) in enumerate(active):
        x = 37 + index * 230
        rows.extend((
            f'<text x="{x}" y="980" font-size="15" font-weight="700">{name} · {row["factor"] - 1:+.1%}</text>',
            f'<text x="{x}" y="1000" font-family="monospace" font-size="13">{row["sample"]}</text>',
        ))
    deferred = " ".join(width_report["deferred"])
    rows.append(f'<text x="37" y="1025" font-size="13" fill="#415d62">Custom drawings pending · {deferred}</text>')
    write_comparison(output, width, height, rows, sheets)


def write_comparison(output, width, height, rows, sheets):
    output.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Arial,sans-serif" fill="#153b40">'
        + '<defs>' + ''.join(path for panel in sheets for path in panel.defs.values()) + '</defs>'
        + ''.join(rows) + ''.join(line for panel in sheets for line in panel.elements) + '</svg>'
    )


def detail_comparison(candidate, reference, output, title, samples, subtitle="Published Code 1.042 above the candidate"):
    width = 1050
    row_height = 207 if reference else 134
    height = 123 + 3 * row_height
    samples_to_draw = [(Panel("candidate", {"font": str(candidate.resolve())}), "Candidate",
                        157 if reference else 92)]
    if reference:
        samples_to_draw.insert(0, (Panel("released", {"font": str(reference.resolve())}), "1.042", 92))
    rows = [
        f'<rect width="{width}" height="{height}" fill="#eaf1f0"/>',
        f'<text x="36" y="46" font-size="31" font-weight="700">Transit Code · {title}</text>',
        f'<text x="37" y="74" font-size="15" fill="#415d62">{subtitle}</text>',
    ]
    for index, (weight, style) in enumerate(WEIGHTS.items()):
        y = 101 + index * row_height
        rows.extend((
            f'<rect x="36" y="{y}" width="978" height="{row_height - 20}" rx="6" fill="#f8faf9" stroke="#c7d6d7"/>',
            f'<text x="54" y="{y + 32}" font-size="16" font-weight="700">{style} {weight}</text>',
        ))
        for x, label, _ in samples:
            rows.append(f'<text x="{x}" y="{y + 32}" font-size="13" fill="#415d62">{label}</text>')
        for panel, label, offset in samples_to_draw:
            rows.append(f'<text x="54" y="{y + offset}" font-size="13" fill="#415d62">{label}</text>')
            for x, _, sample in samples:
                panel.text(sample, x, y + offset, 49, weight, "#153b40", features=FEATURES)
    write_comparison(output, width, height, rows, [panel for panel, _, _ in samples_to_draw])


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, default=RECIPE_PATH)
    parser.add_argument("--output", type=Path, required=True)
    stages = parser.add_mutually_exclusive_group()
    stages.add_argument("--composed", action="store_true", help="also build the donor-derived review glyphs")
    stages.add_argument("--letters", action="store_true", help="add the custom lowercase review")
    parser.add_argument("--render", action="store_true", help="also write the comparison as PNG and PDF")
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text())
    config = recipe["alphabet_review"]
    source = ROOT / (recipe["fonts"]["sans"] + "-VF.ttf")
    reference = ROOT / (recipe["fonts"]["code"] + "-VF.ttf")
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    stage = "Letters" if args.letters else "Composed" if args.composed else "Alphabet"
    candidate = output / f"DaikonicTransitCode{stage}Review-VF.ttf"
    with TTFont(source, recalcTimestamp=False) as sans:
        font, width_report = alphabet_font(sans, recipe, stage=stage)
        verify_latin_topology(sans, font, config)
        vertical = set_vertical_metrics(
            font, minimum_ascent=config["line_metrics"]["ascent"],
            maximum_descent=config["line_metrics"]["descent"],
        )
        font["OS/2"].sTypoAscender = vertical["ascent"]
        font["OS/2"].sTypoDescender = vertical["descent"]
        font.save(candidate)

    with TTFont(candidate) as built, TTFont(reference) as released, TTFont(source) as sans:
        check = verify(built, candidate, config)
        check["horizontal_mirrors"] = verify_mirrors(sans, built, config["cell"], check["weights"])
        if stage != "Alphabet":
            check["composed_components"] = verify_composed(built, candidate, config["cell"], check["weights"])
        sanitize(built)
        report = {
            "source": str(source.relative_to(ROOT)), "source_sha256": sha256(source.read_bytes()).hexdigest(),
            "comparison_reference": str(reference.relative_to(ROOT)),
            "construction": config,
            "width_classes": width_report,
            "validation": check,
            "vertical_metrics": vertical,
            "measurements": {weight: {"candidate": measures(built, weight), "released": measures(released, weight)}
                             for weight in WEIGHTS},
        }
    (output / "alphabet.json").write_text(json.dumps(report, indent=2) + "\n")
    build_proof(candidate, output / "glyphs", svg_only=True, interactive_axes=True)
    panel = output / "Code-Alphabet-Comparison.svg"
    comparison(candidate, reference, panel, width_report, config["cell"], report["measurements"])
    panels = [panel]
    if stage == "Composed":
        composed_panel = output / "Code-Composed-Comparison.svg"
        detail_comparison(candidate, reference, composed_panel, "Composed glyphs",
                          ((166, "Stem and shoulder", "n r   ŕ ř"), (447, "Quantifiers", "A ∀   E ∃"),
                           (720, "Operators", "= ¬ ≠ ≤ ≥")))
        panels.append(composed_panel)
    elif stage == "Letters":
        letters_panel = output / "Code-Custom-Lowercase.svg"
        detail_comparison(candidate, reference, letters_panel, "Custom lowercase",
                          ((166, "Bowl width", "a s   a n"), (447, "Letter spacing", "banana"),
                           (720, "Hook donor and accented forms", "l i í ï in")),
                          "Published Code 1.042 above the candidate · a uses the width scale from s")
        panels.append(letters_panel)
        hook_panel = output / "Code-Hook-Letters.svg"
        detail_comparison(candidate, reference, hook_panel, "Hook letters",
                          ((166, "Trimmed upper hooks", "i j l"), (447, "Accents", "í ĵ ľ ĺ"),
                           (720, "In text", "jill nil")))
        panels.append(hook_panel)
        crossbar_panel = output / "Code-Crossbar-Letters.svg"
        detail_comparison(candidate, reference, crossbar_panel, "Crossbars and hooks",
                          ((166, "Lower return", "t ț ţ"), (447, "Flipped upper return", "f ft ff"),
                           (720, "In text", "after fit")))
        panels.append(crossbar_panel)
        bowl_panel = output / "Code-G-Bowl.svg"
        detail_comparison(candidate, reference, bowl_panel, "Lowercase g",
                          ((166, "Upper bowl", "a g o"), (447, "Accents", "g ğ ġ"),
                           (720, "g and y in text", "gray day")))
        panels.append(bowl_panel)
        figures_panel = output / "Code-Letter-Figure-Distinctions.svg"
        detail_comparison(candidate, reference, figures_panel, "Letter and figure distinctions",
                          ((166, "Narrow letters and one", "I l 1 i"), (447, "Zero and capital O", "0 O 00"),
                           (720, "In an identifier", "IO10l")))
        panels.append(figures_panel)
        punctuation_panel = output / "Code-Underscore-and-Hyphen.svg"
        detail_comparison(candidate, reference, punctuation_panel, "Underscore and hyphen",
                          ((166, "Inline underscore", "snake_x"), (447, "Adjacent underscores", "__init__"),
                           (720, "Hyphen and minus", "x-y x−y")))
        panels.append(punctuation_panel)
        at_panel = output / "Code-At-Sign.svg"
        detail_comparison(candidate, reference, at_panel, "At sign",
                          ((166, "Body and shell", "a c @"), (447, "Height against o", "o@o"),
                           (720, "In an address", "a@host")))
        panels.append(at_panel)
        diamonds_panel = output / "Code-Diamond-Punctuation.svg"
        detail_comparison(candidate, reference, diamonds_panel, "Diamond punctuation",
                          ((166, "Comma, semicolon, period, colon", "a,a;a.a:a"), (447, "Ellipsis and middle dot", "a…a·a"),
                           (720, "Sentence marks", "¿Qué?!")))
        panels.append(diamonds_panel)
        quote_panel = output / "Code-Quotation-Marks.svg"
        detail_comparison(candidate, None, quote_panel, "Quotation marks",
                          ((166, "Straight quotes", "'a' \"b\""), (447, "Opening and closing", "‘a’ “b”"),
                           (720, "Low quotes", "‚a‘ „b“")),
                          "Sans-derived forms with tips sized to the shared punctuation diamond")
        panels.append(quote_panel)
        comma_panel = output / "Code-Comma-and-Closing-Quote.svg"
        detail_comparison(candidate, None, comma_panel, "Comma and closing quote",
                          ((166, "Closing and low quotes", "’ ‚"), (447, "Comma and semicolon", "a,a;a"),
                           (720, "With the period and colon", "a.,;:a")),
                          "Shared closing-quote curve with a shorter comma tail and a period-height crown")
        panels.append(comma_panel)
    if args.render:
        for proof in panels:
            render(proof, scale=2)
    print(f"Verified Code {stage.lower()} review and wrote the proof to {output}")


if __name__ == "__main__":
    main()
