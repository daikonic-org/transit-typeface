"""Proof a shared lowercase enlargement while retaining original curves and components."""

from argparse import ArgumentParser
from copy import deepcopy
from hashlib import file_digest
from html import escape
import json
from pathlib import Path
from string import ascii_lowercase

from fontTools.misc.roundTools import otRound
from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.varLib.instancer import instantiateVariableFont

from audit import shape_from_glyphs
from derive_weights import topology
from sans_aperture import apertures_for
from sans_direct_weight import direct_points
from scaling_study import vertical_stem

FACTOR = 1.12
MITER = 3
WEIGHTS = {"Light": 300, "Book": 350, "Regular": 400, "Medium": 500, "SemiBold": 600}


def lowercase_compensation(glyphs):
    return -vertical_stem(shape_from_glyphs(glyphs, "n"), .4) * (FACTOR - 1)


def scale_lowercase_outline(glyph, compensation):
    glyph.coordinates = GlyphCoordinates((otRound(x * FACTOR), otRound(y * FACTOR))
                                         for x, y in glyph.coordinates)
    apertures = apertures_for(glyph, abs(compensation) * MITER)
    glyph.coordinates = direct_points(glyph, compensation, 1, MITER, 0, apertures=apertures)


def set_ascender(glyph, xheight, old_top, new_top):
    if old_top > xheight:
        multiplier = (new_top - xheight) / (old_top - xheight)
        glyph.coordinates = GlyphCoordinates(
            (x, otRound(xheight + (y - xheight) * multiplier) if y > xheight else y)
            for x, y in glyph.coordinates
        )


def enlarge_lowercase(original):
    """Scale around the baseline and offset the existing contours in place."""
    font = deepcopy(original)
    source, target = original["glyf"], font["glyf"]
    glyphs = original.getGlyphSet()
    compensation = lowercase_compensation(glyphs)
    names = {original.getBestCmap()[ord(c)] for c in ascii_lowercase + "ıȷ"}
    shifts = {}

    def enlarge(name):
        if name in shifts:
            return
        old, new = source[name], target[name]
        if old.isComposite():
            for old_part, new_part in zip(old.components, new.components):
                base, matrix = old_part.getComponentInfo()
                transform = Transform(*matrix)
                x, y = transform.dx * FACTOR, transform.dy * FACTOR
                if base in names:
                    enlarge(base)
                    dx, dy = transform.transformVector((shifts[base], 0))
                    x, y = x - dx, y - dy
                else:
                    # Carry shared marks to their scaled position at their existing size.
                    bounds = BoundsPen(glyphs)
                    glyphs[base].draw(bounds)
                    left, bottom, right, top = bounds.bounds
                    dx, dy = transform.transformVector(((left + right) / 2, (bottom + top) / 2))
                    x, y = x + dx * (FACTOR - 1), y + dy * (FACTOR - 1)
                new_part.x, new_part.y = otRound(x), otRound(y)
        else:
            scale_lowercase_outline(new, compensation)
        new.recalcBounds(target)
        shift = old.xMin - new.xMin
        if old.isComposite():
            for part in new.components:
                part.x += shift
        else:
            new.coordinates.translate((shift, 0))
        new.recalcBounds(target)
        advance = original["hmtx"][name][0] + new.xMax - old.xMax
        font["hmtx"][name] = (advance, original["hmtx"][name][1])
        shifts[name] = shift

    for name in sorted(names):
        enlarge(name)
    font["OS/2"].sxHeight = otRound(original["OS/2"].sxHeight * FACTOR)
    revised = font.getGlyphSet()
    failures = []
    for name in sorted(names):
        before, after = [shape_from_glyphs(gs, name) for gs in (glyphs, revised)]
        if topology(before) != topology(after):
            failures.append(name)
        source_points = source[name].getCoordinates(source)[0]
        target_points = target[name].getCoordinates(target)[0]
        assert len(source_points) == len(target_points), name
        assert source[name].isComposite() == target[name].isComposite(), name
    assert font["glyf"]["H"].compile(target) == original["glyf"]["H"].compile(source)
    assert font["hmtx"]["H"] == original["hmtx"]["H"]
    flat_crossing = shape_from_glyphs(revised, "x")
    assert flat_crossing.bounds[1] == 0 and flat_crossing.bounds[3] == font["OS/2"].sxHeight
    return font, {
        "n_stem_before": round(-compensation / (FACTOR - 1), 2),
        "n_stem_after": round(vertical_stem(shape_from_glyphs(revised, "n"), .4), 2),
        "compensation": round(compensation, 2),
        "topology_changes": failures,
        "letters_checked": len(names),
        "e_points": len(target["e"].coordinates),
    }


def words(font, value, x, y, size):
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale, paths = size / font["head"].unitsPerEm, []
    for char in value:
        name = cmap[ord(char)]
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(pen)
        paths.append(
            f'<path d="{pen.getCommands()}" transform="translate({x:.4f} {y}) scale({scale} {-scale})"/>'
        )
        x += glyphs[name].width * scale
    return '<g fill="#1b2327">' + ''.join(paths) + '</g>'


def make_proof(source, output):
    rows = ['<rect width="1120" height="790" fill="#f6f3ea"/>',
            '<text x="38" y="48" font-size="32" font-weight="700">Daikonic Transit System</text>',
            '<text x="39" y="78" font-size="17">Lowercase proportions · 112% with stroke compensation</text>']
    report = {}
    for row, (style, weight) in enumerate(WEIGHTS.items()):
        with TTFont(source) as variable:
            original = instantiateVariableFont(variable, {"wght": weight})
        font, report[style] = enlarge_lowercase(original)
        y = 103 + row * 130
        rows += [
            f'<rect x="22" y="{y}" width="1076" height="120" rx="5" fill="#ffffff"/>',
            f'<text x="38" y="{y+28}" font-size="14" fill="#574b41">{escape(style)} {weight}</text>',
            f'<path d="M163 {y+73}H1080 M163 {y+46.4}H1080 M163 {y+38}H1080" '
            'fill="none" stroke="#e7dcce"/>',
            words(font, "H abcdefghijklmnopqrstuvwxyz", 164, y + 73, 50),
            words(font, "Wayfinder  /  Context menu  /  Quick settings", 164, y + 109, 15),
        ]
    rows.append('<text x="38" y="772" font-size="13" fill="#574b41">Guides show baseline, lowercase height, and cap height.</text>')
    output.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="790" '
        'viewBox="0 0 1120 790" font-family="Arial,sans-serif" fill="#1b2327">'
        + "".join(rows) + "</svg>"
    )
    with source.open("rb") as stream:
        digest = file_digest(stream, "sha256").hexdigest()
    output.with_suffix(".json").write_text(json.dumps({
        "source_sha256": digest,
        "scale": FACTOR,
        "x_height": 532,
        "cap_height": 700,
        "weights": report,
    }, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("specimen", type=Path)
    args = parser.parse_args()
    make_proof(args.source, args.specimen)
