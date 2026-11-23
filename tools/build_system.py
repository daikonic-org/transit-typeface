"""Build System’s upright and italic from a single rebuilt Sans variable font."""

from argparse import ArgumentParser
from copy import deepcopy
from hashlib import file_digest
import json
from pathlib import Path
from string import ascii_lowercase

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.varLib.instancer import instantiateVariableFont

from audit import shape_from_glyphs
from bundle_release import sanitize
from font_feature_tools import append_glyph, feature_subtables, master_locations
from glyph_proof import build_proof
from kern_clearance import repair_kerning, repair_near_contacts
from sans_baseline_trial import build_variations, clear_hints
from sans_complete_rebuild import box_center
from sans_direct_weight import direct_points
from scaling_study import vertical_stem
from system_accents import bounds, install_masters, rebuild_accents
from system_caption_spacing import add_spacing, spacing_glyphs
from system_figures import optical_diamonds, rebuild_figures
from system_foundation import FAMILY, PROFILES, from_sans
from system_italic import designspace, make_italic, rebuild_ligatures
from system_marks import reflected_mark_attachment
from system_metrics import set_advances, set_vertical_metrics
from system_proportions import FACTOR, enlarge_lowercase, set_ascender
from system_width import add_system_width


ROOT = Path(__file__).resolve().parents[1]
DOT = "diamond.dot.system"
LETTERS = ascii_lowercase + "ıȷ"


def lowercase_dot(glyf, weight, xheight):
    """Keep the shared tittle within System's approved vertical range."""
    dot = deepcopy(glyf["diamond.dot"])
    points = glyf["uni0307"].getCoordinates(glyf)[0]
    left, bottom, right, top = points.calcBounds()
    target = 720 + otRound(max(0, weight - 400) * 22 / 200)
    scale = min(1, (target - xheight - 45) / (top - bottom))
    cx = box_center((left, bottom, right, top), 0)
    cy = box_center((left, bottom, right, top), 1)
    dot.coordinates = GlyphCoordinates(
        (otRound(cx + (x - cx) * scale), otRound(cy + (y - cy) * scale))
        for x, y in points
    )
    return dot, target - max(y for _, y in dot.coordinates)


def primary_y(donors):
    recipe = json.loads((ROOT / "recipes/system-y.json").read_text())
    base = Glyph()
    base.numberOfContours = 1
    base.coordinates = GlyphCoordinates(recipe["points"])
    base.endPtsOfContours = [len(base.coordinates) - 1]
    base.flags = bytearray(recipe["on_curve"])
    clear_hints(base)
    outlines = {weight: master.getGlyphSet() for weight, master in donors.items()}
    anchor = outlines[recipe["weight"]]
    stem = vertical_stem(shape_from_glyphs(anchor, "n"), .4)
    left = bounds(anchor, "y")[0]
    for weight, master in outlines.items():
        amount = vertical_stem(shape_from_glyphs(master, "n"), .4) - stem
        origin = bounds(master, "y")[0] - left
        points = direct_points(base, amount, .72, 3, origin)
        glyph = deepcopy(base)
        glyph.coordinates = points
        yield weight, glyph


def lowercase(font, source, donors, locations, model, default):
    cmap = font.getBestCmap()
    bases = {cmap[ord(char)] for char in LETTERS}
    alternates = {target for tag, table in feature_subtables(source) if tag.startswith("ss")
                  for name, target in getattr(table, "mapping", {}).items()
                  if name in bases and target in font["glyf"]}
    names = bases | alternates
    masters = {weight: enlarge_lowercase(master, alternates=alternates)[0]
               for weight, master in donors.items()}
    cap = font["OS/2"].sCapHeight
    ascenders = dict.fromkeys("b d h k l".split(), cap) | {"t": 610, "f": 730}
    drawings = {}
    widths = {}
    hooks = dict(primary_y(donors))
    height = otRound(source["OS/2"].sxHeight * FACTOR)
    font["OS/2"].sxHeight = height

    for weight, master in masters.items():
        glyf = master["glyf"]
        glyphs = master.getGlyphSet()
        for name, top in ascenders.items():
            if not glyf[name].isComposite():
                glyph = glyf[name]
                set_ascender(glyph, height, bounds(glyphs, name)[3], top)
        dot, dot_shift = lowercase_dot(glyf, weight, height)
        for name in ("i", "j"):
            for part in glyf[name].components:
                if part.glyphName == "uni0307":
                    part.glyphName = DOT
                    part.y = dot_shift
        glyf[DOT] = dot
        glyf["y"] = hooks[weight]
        drawings[weight] = {name: glyf[name] for name in names | {DOT}}
        widths[weight] = {name: master["hmtx"][name][0] for name in names}

    face = drawings[locations[default]["wght"]]
    dot = deepcopy(face[DOT])
    append_glyph(font, DOT, dot, build_variations(
        model, [drawings[loc["wght"]][DOT].coordinates for loc in locations]), 0)
    font["GDEF"].table.GlyphClassDef.classDefs[DOT] = 3
    order = sorted(names, key=lambda name: (face[name].isComposite(), name))
    for name in order:
        drawing = deepcopy(face[name])
        items = [drawings[loc["wght"]][name] for loc in locations]
        points = ([GlyphCoordinates((part.x, part.y) for part in item.components) for item in items]
                  if drawing.isComposite() else [item.coordinates for item in items])
        install_masters(font, source, name, drawing, points, model, default)
    return bases, {name: [widths[loc["wght"]][name] for loc in locations] for name in names}


def build(source):
    font = from_sans(source)
    pristine = deepcopy(font)
    locations, model, default = designspace(font)
    donors = {weight: instantiateVariableFont(source, {"wght": weight})
              for weight in sorted({loc["wght"] for loc in locations})}
    bases, advances = lowercase(font, pristine, donors, locations, model, default)
    accents = rebuild_accents(font, pristine, donors, locations, model, locations[default], bases, DOT)
    cmap = font.getBestCmap()
    for codepoint in accents:
        name = cmap[codepoint]
        if font["glyf"][name].isComposite():
            base = font["glyf"][name].components[0].glyphName
            if base in advances:
                advances[name] = advances[base].copy()
    optical = next(axis for axis in font["fvar"].axes if axis.axisTag == "opsz")
    gaps = dict(zip((optical.minValue, optical.defaultValue, optical.maxValue),
                    (profile[2] for profile in PROFILES)))
    samples = [pristine.getGlyphSet(location=loc) for loc in locations]
    for name in spacing_glyphs(font):
        values = advances.get(name, [sample[name].width for sample in samples])
        advances[name] = [value + 2 * gaps[loc["opsz"]] for value, loc in zip(values, locations)]
    set_advances(font, advances, model)
    optical_diamonds(font, donors, locations, model, default)
    rebuild_ligatures(font, pristine, locations, model, default)
    figures = rebuild_figures(font, locations, model, default)
    reflected_mark_attachment(font, locations, model)
    add_spacing(font, tabular=figures)
    return font, len(bases), len(accents)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("sans", type=Path)
    parser.add_argument("output", type=Path)
    sampling = parser.add_mutually_exclusive_group()
    sampling.add_argument("--outline-only", action="store_true", help="build before the kerning pass")
    sampling.add_argument("--named-instances", action="store_true",
                          help="check pair clearance at the weight, optical-size and width masters")
    parser.add_argument("--review-glyph", action="append", default=[], metavar="NAME",
                        help="also show this glyph in a focused proof")
    parser.add_argument("--export-proof", action="store_true", help="also export the proof as PNG and PDF")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with TTFont(args.sans, recalcTimestamp=False) as source:
        upright, bases, accents = build(source)
    italic = make_italic(upright)
    add_system_width(upright)
    vertical = set_vertical_metrics(upright, italic)
    stem = FAMILY.replace(" ", "")
    pair_review = json.loads((ROOT / "recipes/system-pair-spacing.json").read_text())
    for font, suffix, folder in ((upright, "", "Proof"), (italic, "-Italic", "Proof Italic")):
        path = args.output / f"{stem}{suffix}-VF.ttf"
        if not args.outline_only:
            locations = master_locations(font)[1] if args.named_instances else None
            spacing = repair_kerning(font, locations=locations)
            style = "italic" if suffix else "upright"
            spacing["near_contact"] = repair_near_contacts(
                font, map(tuple, pair_review[style]),
                trigger=pair_review["trigger"], target=pair_review["target"],
            )
            path.with_suffix(".kerning.json").write_text(json.dumps(spacing, indent=2) + "\n")
        font.save(path)
        sanitize(font)
        build_proof(path, args.output / folder, flagged=args.review_glyph, svg_only=not args.export_proof,
                    interactive_axes=True)
    with args.sans.open("rb") as source:
        digest = file_digest(source, "sha256").hexdigest()
    report = {
        "source_sha256": digest,
        "units_per_em": upright["head"].unitsPerEm,
        "axes": {axis.axisTag: [axis.minValue, axis.defaultValue, axis.maxValue]
                 for axis in upright["fvar"].axes},
        "encoded_characters": len(upright.getBestCmap()),
        "vertical_metrics": vertical,
    }
    (args.output / "build.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Rebuilt", bases, "lowercase bases and", accents, "accented forms from Sans")


if __name__ == "__main__":
    main()
