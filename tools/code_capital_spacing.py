"""Build a fixed-cell uppercase spacing and texture-healing trial for Code."""

from argparse import ArgumentParser
from collections import defaultdict
from copy import deepcopy
from itertools import product
import json
from math import copysign, radians, tan
from pathlib import Path
from statistics import median
from string import ascii_letters, ascii_uppercase
from unicodedata import category

from fontTools.misc.roundTools import otRound
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
import uharfbuzz as hb

from bundle_release import sanitize
from check_code_rebuild import ROOT, STYLES, shape
from code_crossbar_alignment import profile
from code_receiver_texture import FEATURE, HALF_WIDTH, LANGUAGES, OFF_FEATURE, inherited_positions
from code_width import verify_width
from font_feature_tools import add_features, append_glyph, label_stylistic_set
from glyph_proof import build_proof
from render_svg import render, render_pdf
from sans_baseline_trial import build_variations
from specimens import Panel
from system_italic import designspace


SOURCE = ROOT / "releases/1.1.1/code/VF"
FAMILY = "Daikonic Transit Code Capitals"
STEM = FAMILY.replace(" ", "")
CELL = 600
RECEIVERS = "MW"
DONORS = ascii_letters + ".,:;!?()[]{}"
TEXTURE_GAP = 108
SPACING_GAP = 68
STRESS_LOCATIONS = tuple(
    {"wght": weight, "wdth": width}
    for weight, width in product((350, 375, 400, 450, 500), (94, 97, 100, 104, 108))
)
SAMPLES = (
    "MAX_WIDTH  MIN_VALUE  HTTPServer  isXMLName",
    "AVATAR  FALLBACK  TYPE  WRITE  JSON",
    "MIM  IMI  IWI  WIM  MMM  WWW  MiWiM",
    "parseHTTPResponse  loadXMLFile  JSRuntime",
    "I l 1   O 0   W V   M N   F E   L I",
    "type XMLNode = Record<URL, HTMLValue>;",
    "return MAX_WIDTH >= MIN_VALUE ? rows?.map(Wrap) : [];",
)


def glyph_name(font, char):
    return font.getBestCmap()[ord(char)]


def names_with_alternates(font, chars):
    originals = {glyph_name(font, char) for char in chars}
    return [name for name in font.getGlyphOrder() if name.partition(".texture.")[0] in originals]


def profiles(font, names, locations):
    for location in locations:
        glyphs = font.getGlyphSet(location=location)
        yield {
            name: (profile(glyphs, name), glyphs[name].width)
            for name in names
        }


def gaps(left, right):
    rows, width = left
    ahead, _ = right
    return [width + ahead[y][0] - rows[y][1] for y in rows.keys() & ahead.keys()]


def texture_donors(font):
    names = names_with_alternates(font, DONORS)
    # Keep tall neighbors distinct. A receiver should never donate based on
    # clearance measured against its narrower base drawing.
    names = [name for name in names if name.partition(".texture.")[0] not in RECEIVERS]
    pairs = {(side, receiver): set(names) for side, receiver in product(("Left", "Right"), RECEIVERS)}
    for rows in profiles(font, names + list(RECEIVERS), STRESS_LOCATIONS):
        for (side, receiver), candidates in pairs.items():
            for candidate in tuple(candidates):
                order = (candidate, receiver) if side == "Left" else (receiver, candidate)
                clearances = gaps(*(rows[name] for name in order))
                if not clearances or min(clearances) < TEXTURE_GAP:
                    candidates.remove(candidate)
    return {key: sorted(values, key=font.getGlyphID) for key, values in pairs.items()}


def receiver_drawings(font):
    locations, model, default = designspace(font)
    shear = -tan(radians(font["post"].italicAngle))
    aliases = {}
    for letter in RECEIVERS:
        drawings = []
        for location in locations:
            glyphs = font.getGlyphSet(location=location)
            pen = TTGlyphPen(None)
            glyphs[letter].draw(pen)
            drawings.append(pen.glyph())
        source = drawings[default]
        assert all(g.flags == source.flags and g.endPtsOfContours == source.endPtsOfContours
                   for g in drawings), letter
        aliases[letter] = []
        for form, step in (("middle", HALF_WIDTH), ("wide", HALF_WIDTH * 2)):
            name = f"{letter}.texture.{form}"
            points = []
            for location, drawing in zip(locations, drawings, strict=True):
                width = CELL * location["wdth"] / 100
                unslanted = [x - shear * y for x, y in drawing.coordinates]
                center = (min(unslanted) + max(unslanted)) / 2
                # Hold the middle join and move the outer stroke bands intact.
                # Italic letterfit can offset the unslanted drawing from its cell.
                distance = [(x - center) / width for x in unslanted]
                points.append([
                    (otRound(x + copysign(step / 2 * min(1, max(0, (abs(d) - .08) / .012)), d)), y)
                    for (x, y), d in zip(drawing.coordinates, distance, strict=True)
                ])
            variant = deepcopy(source)
            variant.coordinates[:] = points[default]
            append_glyph(font, name, variant, build_variations(model, points), CELL, letter)
            aliases[letter].append(name)
    inherited_positions(font, aliases)


def add_texture(font, donors):
    receiver_drawings(font)
    marks = {name for cp, name in font.getBestCmap().items() if category(chr(cp)).startswith("M")}
    marks.update(name for name, kind in font["GDEF"].table.GlyphClassDef.classDefs.items() if kind == 3)
    mark_class = f"@CapTextureMarks = [{' '.join(sorted(marks))}];"
    definitions, lookups, restore = [mark_class], [], []
    for letter in RECEIVERS:
        left, right = (f"@Cap{letter}{side}" for side in ("Left", "Right"))
        for side, cls in (("Left", left), ("Right", right)):
            definitions.append(f"{cls} = [{' '.join(donors[side, letter])}];")
        middle, wide = f"{letter}.texture.middle", f"{letter}.texture.wide"
        lookups.extend([
            f"lookup CapTexture{letter} {{",
            f"ignore sub @CapTextureMarks {letter}', {letter}' @CapTextureMarks;",
            f"sub {left} {letter}' {right} by {wide};",
            f"sub {left} {letter}' by {middle};",
            f"sub {letter}' {right} by {middle};",
            f"}} CapTexture{letter};",
        ])
        restore.append(f"sub [{middle} {wide}] by {letter};")
        shift = HALF_WIDTH // 2
        lookups.extend([
            f"lookup CapPlace{letter} {{",
            f"pos {left} {middle}' <-{shift} 0 0 0>;",
            f"pos {middle}' <{shift} 0 0 0> {right};",
            f"}} CapPlace{letter};",
        ])
    calls = " ".join(f"lookup CapTexture{c}; lookup CapPlace{c};" for c in RECEIVERS)
    add_features(font, "\n".join([
        *LANGUAGES, *definitions, *lookups,
        f"feature calt {{ {calls} }} calt;",
        f"feature {FEATURE} {{ {calls} }} {FEATURE};",
        f"feature {OFF_FEATURE} {{ {' '.join(restore)} }} {OFF_FEATURE};",
    ]))
    if font["post"].italicAngle:
        label_stylistic_set(font, FEATURE, "Texture healing")
        label_stylistic_set(font, OFF_FEATURE, "Disable texture healing")


def edge_class(rows, advance, side, shear, height):
    margins = [
        median(
            x0 - shear * y if side == "Left" else advance - x1 + shear * y
            for y, (x0, x1) in rows.items() if lo * height <= y < hi * height
        )
        for lo, hi in ((.12, .29), (.38, .62), (.72, .89))
    ]
    low, middle, high = margins
    if min(margins) >= 90:
        return "Inset"
    if low - high > 58:
        return "OpenLow"
    if high - low > 58:
        return "OpenHigh"
    return "Curved" if max(low, high) - middle > 45 else "Stem"


def spacing_classes(font):
    cmap = font.getBestCmap()
    base_names = {char: cmap[ord(char)] for char in ascii_letters}
    glyphs = font.getGlyphSet()
    shear = -tan(radians(font["post"].italicAngle))
    classes = defaultdict(list)
    for char, name in base_names.items():
        rows = profile(glyphs, name)
        height = font["OS/2"].sCapHeight if char.isupper() else font["OS/2"].sxHeight
        aliases = names_with_alternates(font, char)
        for side in ("Left", "Right"):
            form = edge_class(rows, glyphs[name].width, side, shear, height)
            classes[side, char.isupper(), form].extend(aliases)
    return dict(classes)


def add_spacing(font):
    classes = spacing_classes(font)
    labels = {key: f"@CapFit{key[0]}{int(key[1])}{key[2]}" for key in classes}
    pairs = {
        (left, right): float("inf")
        for left, right in product(classes, repeat=2)
        if left[0] == "Right" and right[0] == "Left" and (left[1] or right[1])
    }
    pairs_to_classes = defaultdict(set)
    for left, right in pairs:
        for a, b in product(classes[left], classes[right]):
            pairs_to_classes[a, b].add((left, right))
    all_names = sorted({name for pair in pairs_to_classes for name in pair})
    for rows in profiles(font, all_names, STRESS_LOCATIONS):
        for (a, b), pair_classes in pairs_to_classes.items():
            clearance = min(gaps(rows[a], rows[b]), default=0)
            for pair in pair_classes:
                pairs[pair] = min(pairs[pair], clearance)
    rules = {"Trailing": [], "Leading": []}
    moved = {}
    for (left, right), gap in pairs.items():
        contraction = 20 if gap >= SPACING_GAP + 20 else 12 if gap >= SPACING_GAP + 12 else 0
        if not contraction:
            continue
        a, b = labels[left], labels[right]
        shift = contraction // 2 if left[1] and right[1] else contraction
        if left[1]:
            rules["Trailing"].append(f"pos {a}' <{shift} 0 0 0> {b};")
        if right[1]:
            rules["Leading"].append(f"pos {a} {b}' <-{shift} 0 0 0>;")
        moved[f"{a[1:]} / {b[1:]}"] = contraction
    assert moved
    add_features(font, "\n".join([
        *LANGUAGES,
        *(f"{labels[key]} = [{' '.join(names)}];" for key, names in classes.items()),
        "feature calt {",
        *(f"lookup {name}CapFit {{\n" + "\n".join(rows) + f"\n}} {name}CapFit;"
          for name, rows in rules.items() if rows),
        "} calt;",
    ]))
    return {
        "classes": {labels[key].lstrip("@"): names for key, names in classes.items()},
        "contractions": moved,
    }


def build(source, target):
    with TTFont(source, recalcTimestamp=False) as font:
        donors = texture_donors(font)
        add_texture(font, donors)
        spacing = add_spacing(font)
        for record in font["name"].names:
            name = record.toUnicode().replace("Daikonic Transit Code", FAMILY)
            record.string = name.replace("DaikonicTransitCode", STEM).encode(record.getEncoding())
        verify_width(font, CELL)
        sanitize(font)
        font.save(target)
    return spacing | {"texture_donors": {"".join(key): values for key, values in donors.items()}}


def verify(source, target):
    baseline, candidate = [hb.Font(hb.Face(path.read_bytes())) for path in (source, target)]
    with TTFont(source) as original, TTFont(target) as font:
        assert original.getBestCmap() == font.getBestCmap()
        assert set(original.getGlyphOrder()) | {f"{c}.texture.{form}" for c, form in
                                                  product(RECEIVERS, ("middle", "wide"))} == set(font.getGlyphOrder())
        assert all(original["glyf"][name].compile(original["glyf"]) == font["glyf"][name].compile(font["glyf"])
                   for name in original.getGlyphOrder())
        assert all(original["gvar"].variations.get(name) == font["gvar"].variations.get(name)
                   for name in original.getGlyphOrder())
        names = names_with_alternates(font, ascii_letters)
        for location, rows in zip(STRESS_LOCATIONS, profiles(font, names, STRESS_LOCATIONS), strict=True):
            for engine in (baseline, candidate):
                engine.set_variations(location)
            for sample in ("exit hexit window windows sweep", "namespace awwi imi", "a === b && c?.d", "fn f<'a>(arg: &'a str)"):
                assert shape(baseline, sample, {}) == shape(candidate, sample, {}), (location, sample)
            for sample in ("IMI", "IWI", "IW", "WI", "MMM", "WWW", *SAMPLES):
                on = shape(candidate, sample, {})
                off = shape(candidate, sample, {OFF_FEATURE: True})
                prior = shape(baseline, sample, {})
                assert [r[2] for r in on] == [r[2] for r in off] == [r[2] for r in prior], (location, sample)
                assert all(".texture." not in r[0] for r in off), (location, sample)
                assert shape(candidate, sample, {FEATURE: True}) == on
            assert shape(candidate, "IMI", {})[1][0] == "M.texture.wide"
            assert shape(candidate, "WI", {})[0][0] == "W.texture.middle"
            assert shape(candidate, "MMM WWW", {}) == shape(candidate, "MMM WWW", {OFF_FEATURE: True})
            assert shape(candidate, "AM\u0301I", {})[1][0] == "M"
            for pair in map("".join, product(ascii_letters, repeat=2)):
                if pair.islower():
                    continue
                before = shape(baseline, pair, {})
                after = shape(candidate, pair, {})
                minimum = []
                for left, right in (before, after):
                    local = gaps(rows[left[0]], rows[right[0]])
                    minimum.append(min(local) + right[4] - left[4])
                assert minimum[1] >= min(minimum[0], 16) - 1, (location, pair, minimum)


def specimen(target, style, output):
    paper, ink, dark = "#f7f5ee", "#182b31", "#171e22"
    page = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="940" height="810" viewBox="0 0 940 810" role="img">',
        f'<rect width="940" height="810" fill="{paper}"/>',
        '<g font-family="Arial, sans-serif">',
        f'<text x="40" y="44" font-size="15" fill="#526971">DAIKONIC TRANSIT CODE · {style.upper()}</text>',
        f'<text x="40" y="85" font-size="33" font-weight="700" fill="{ink}">Uppercase spacing</text>',
        '</g>',
    ]
    for index, (weight, width, label) in enumerate(((350, 100, "Book"),
                                                   (400, 100, "Regular"),
                                                   (500, 94, "Medium Narrow"))):
        top = 109 + 184 * index
        panel = Panel(f"caps{index}", {"font": target.resolve(), "axes": {"wdth": width}})
        page.extend([
            f'<line x1="40" x2="900" y1="{top}" y2="{top}" stroke="#d6ddd7"/>',
            f'<text x="40" y="{top+23}" font-family="Arial" font-size="14" fill="#526971">{label} {weight}</text>',
        ])
        panel.text(SAMPLES[0], 40, top + 54, 27, weight, ink)
        panel.text(SAMPLES[1], 40, top + 87, 27, weight, ink)
        for x, features in ((40, {}), (475, {OFF_FEATURE: True})):
            panel.text("IMI IWI WIM MMM WWW MiWiM", x, top + 128, 26, weight, ink,
                       features=features)
        for x, text in ((40, "Texture healing on"), (475, "Texture healing off")):
            page.append(f'<text x="{x}" y="{top+149}" font-family="Arial" font-size="12" fill="#526971">{text}</text>')
        page.append(panel.body())
    page.append(f'<rect y="663" width="940" height="147" fill="{dark}"/>')
    panel = Panel("editor-size", {"font": target.resolve(), "axes": {"wdth": 100}})
    page.append('<text x="40" y="696" font-family="Arial" font-size="14" fill="#a8c3c4">Editor samples · 16 px</text>')
    for line, text in enumerate((SAMPLES[-2], SAMPLES[-1], SAMPLES[3], SAMPLES[4])):
        panel.text(text, 40, 724 + line * 21, 16, 400, "#eeefeb")
    page.append(panel.body())
    destination = output / f"Code-Capitals-{style.title()}.svg"
    destination.write_text("".join(page) + "</svg>\n")
    return destination


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", type=Path, default=SOURCE,
                        help="directory containing the upright and italic Code variable fonts")
    parser.add_argument("--proofs", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report, pages = {}, []
    for style, suffix in STYLES.items():
        source = args.source / f"DaikonicTransitCode{suffix}"
        target = args.output / f"{STEM}{suffix}"
        report[style] = build(source, target)
        verify(source, target)
        print(target, flush=True)
        if args.proofs:
            pages.append(specimen(target, style, args.output))
            build_proof(target, args.output / style, svg_only=True, interactive_axes=True,
                        sample="\n".join(SAMPLES))
    if pages:
        render_pdf(pages, args.output / "Code-Capitals.pdf")
        for page in pages:
            render(page, scale=2, pdf=False)
    (args.output / "spacing.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
