"""Render category-by-category upright Sans proofs across the named weights."""

import argparse
from collections import defaultdict
from html import escape
from math import ceil
from pathlib import Path
from string import ascii_lowercase, ascii_uppercase, digits
from unicodedata import category, decomposition

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

from font_feature_tools import feature_subtables
from render_svg import render, render_pdf

WIDTH = 1240
HEIGHT = 795
MARGIN = 28
ROWS = 13
ROW_HEIGHT = 51
GLYPH_SIZE = 36
CENTER_STYLE = "stroke:#7a759a;stroke-dasharray:1.5 2.5"


def alternates(font):
    for tag, subtable in feature_subtables(font):
        for original, replacement in getattr(subtable, "mapping", {}).items():
            if isinstance(replacement, str):
                yield tag, original, replacement
        for original, replacements in getattr(subtable, "alternates", {}).items():
            for replacement in replacements:
                yield tag, original, replacement


def inventory(font):
    cmap = font.getBestCmap()
    sections = [
        (title, [(cmap[ord(char)], char) for char in alphabet])
        for title, alphabet in (
            ("Uppercase", ascii_uppercase), ("Lowercase", ascii_lowercase), ("Numerals", digits)
        )
    ]
    base_forms = {name for _, entries in sections for name, _ in entries}
    letters = {cmap[ord(char)]: char for char in ascii_uppercase + ascii_lowercase}
    substitutions = list(alternates(font))
    letter_alts = {}
    for tag, original, replacement in substitutions:
        if tag.startswith("ss") and original in letters:
            letter_alts.setdefault(replacement, f"{letters[original]} · {tag}")
    sections.append(("Letter alternates", list(letter_alts.items())))

    glyf = font["glyf"]
    composition = {
        name: [part.glyphName for part in glyf[name].components]
        for name in font.getGlyphOrder() if glyf[name].isComposite()
    }
    used_parts = {part for parts in composition.values() for part in parts}
    excluded = base_forms | letter_alts.keys()
    components = used_parts - excluded
    components |= {
        replacement for _, original, replacement in substitutions
        if original in components and replacement not in excluded
    }
    by_name = lambda name: (name.casefold(), name)
    sections.append(("Components and alternates", [
        (name, name) for name in sorted(components, key=by_name)
    ]))

    # A composite that uses a base letter plus a mark does not qualify.
    # Keep encoded punctuation and symbols with entirely category 3 parts.
    by_category = defaultdict(dict)
    for code, name in sorted(cmap.items()):
        kind = category(chr(code))
        parts = composition.get(name)
        if not parts or not set(parts) <= components or name in components | excluded:
            continue
        if kind.startswith("P"):
            by_category["Composite punctuation"].setdefault(name, name)
        elif kind[0] in "SMN" or kind == "Co":
            by_category["Composite symbols and marks"].setdefault(name, name)
    for title, entries in by_category.items():
        sections.append((title, sorted(entries.items(), key=lambda item: by_name(item[0]))))

    shown = {name for _, entries in sections for name, _ in entries}
    ligatures = {}
    for tag, subtable in feature_subtables(font):
        if tag in {"liga", "dlig", "ordn"}:
            for entries in getattr(subtable, "ligatures", {}).values():
                for entry in entries:
                    if entry.LigGlyph not in shown:
                        ligatures[entry.LigGlyph] = entry.LigGlyph
    if ligatures:
        sections.append(("Ligatures", list(ligatures.items())))
        shown.update(ligatures)
    other = {"P": {}, "S": {}, "N": {}}
    for code, name in sorted(cmap.items()):
        char = chr(code)
        kind = category(char)
        if kind == "Lm" and decomposition(char).startswith(("<sub>", "<super>")):
            group = "N"
        else:
            group = "S" if kind == "Co" else kind[0]
        if group in other and name not in shown:
            other[group][name] = name
            shown.add(name)
    titles = (
        ("P", "Other punctuation"), ("S", "Other symbols"), ("N", "Other numerals and script forms")
    )
    for group, title in titles:
        if other[group]:
            sections.append((title, list(other[group].items())))
    return sections


def guide_metrics(font):
    metrics = font["OS/2"]
    glyphs = font.getGlyphSet()
    pen = BoundsPen(glyphs)
    glyphs["equal"].draw(pen)
    math_center = (pen.bounds[1] + pen.bounds[3]) / 2
    return (
        ("Cap height", metrics.sCapHeight, "stroke:#608078;stroke-dasharray:3 2"),
        ("x-height", metrics.sxHeight, "stroke:#608078;stroke-dasharray:1.5 2.5"),
        ("Operator axis", math_center, "stroke:#a17a4c;stroke-dasharray:2 3"),
        ("Baseline", 0, "stroke:#53655e"),
        ("Descender", font["hhea"].descent, "stroke:#608078;stroke-dasharray:3 2"),
    )


def line(x1, y1, x2, y2, style, *, width=0.55):
    return (
        f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
        f'stroke-width="{width}" style="{style}"/>'
    )


def outline_position(glyph_set, name):
    bounds = BoundsPen(glyph_set)
    glyph = glyph_set[name]
    glyph.draw(bounds)
    if bounds.bounds is None:
        raise ValueError(f"Empty proof glyph: {name}")
    left, _, right, _ = bounds.bounds
    # Zero-advance components have no spacing cell. Center their ink.
    origin = glyph.width / 2 if glyph.width else (left + right) / 2
    return origin, max(origin - left, right - origin)


def outline(glyph_set, name, center, baseline, origin, scale):
    x = center - origin * scale
    y = baseline
    path = SVGPathPen(glyph_set)
    glyph_set[name].draw(path)
    return (
        f'<path d="{path.getCommands()}" fill="#151b1b" '
        f'transform="translate({x:.4f} {y:.4f}) scale({scale:.6f} {-scale:.6f})"/>'
    )


def sheet(font, title, entries, weights, target):
    upm = font["head"].unitsPerEm
    pieces = [
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>',
        '<text x="28" y="43" font-size="27" font-weight="700">Daikonic Transit Sans</text>',
        f'<text x="28" y="76" font-size="20" font-weight="700">{escape(title)}</text>',
    ]
    guides = guide_metrics(font)
    legend_x = 473
    for label, units, color in (*guides, ("Center", None, CENTER_STYLE)):
        pieces.append(line(legend_x, 73, legend_x + 17, 73, color))
        text = f"{label} {units:g}" if units is not None else "Advance / ink center"
        pieces.append(f'<text x="{legend_x + 22}" y="77" font-size="10" fill="#454b47">{text}</text>')
        legend_x += 28 + len(text) * 5.5
    block_width = (WIDTH - 3 * MARGIN) / 2
    name_width = 154
    cell_width = (block_width - name_width) / len(weights)
    half = ceil(len(entries) / 2)
    wide_rows = False
    for column, start in enumerate((0, half)):
        origin = MARGIN + column * (block_width + MARGIN)
        for i, (label, _) in enumerate(weights):
            center = origin + name_width + (i + 0.5) * cell_width
            pieces.append(
                f'<text x="{center:.3f}" y="106" text-anchor="middle" '
                f'font-size="11" fill="#435451">{escape(label)}</text>'
            )
        for row, (name, label) in enumerate(entries[start:start + half]):
            y = 115 + row * ROW_HEIGHT
            shade = "#f0efe9" if row % 2 == 0 else "#f7f6f2"
            pieces.append(
                f'<rect x="{origin:.3f}" y="{y}" width="{block_width:.3f}" '
                f'height="{ROW_HEIGHT - 1}" fill="{shade}"/>'
            )
            label_size = min(12, (name_width - 12) / max(1, len(label)) / 0.57)
            pieces.append(
                f'<text x="{origin + 8:.3f}" y="{y + 29}" fill="#454b47" '
                f'font-size="{label_size:.2f}">{escape(label)}</text>'
            )
            baseline = y + 37
            positions = [outline_position(glyph_set, name) for _, glyph_set in weights]
            max_extent = max(extent for _, extent in positions)
            nominal = GLYPH_SIZE / upm
            scale = min(nominal, (cell_width / 2 - 4) / max(1, max_extent))
            wide_rows |= scale < nominal
            for _, units, color in guides:
                guide_y = baseline - units * scale
                pieces.append(line(origin + name_width, guide_y, origin + block_width, guide_y, color))
            for i, (_, glyph_set) in enumerate(weights):
                center = origin + name_width + (i + 0.5) * cell_width
                pieces.append(line(center, y + 3, center, y + ROW_HEIGHT - 3, CENTER_STYLE))
                pieces.append(outline(glyph_set, name, center, baseline, positions[i][0], scale))
    if wide_rows:
        pieces.append('<text x="1212" y="91" text-anchor="end" font-size="10" fill="#53655e">'
                      'Wide glyphs and guides use a reduced scale for their entire row.</text>')
    target.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" font-family="Arial,sans-serif">'
        + "".join(pieces) + "</svg>"
    )


def build_proof(source, output, *, flagged=()):
    output.mkdir(parents=True, exist_ok=True)
    pages = []
    with TTFont(source) as font:
        weights = []
        instances = sorted(font["fvar"].instances, key=lambda item: item.coordinates["wght"])
        for instance in instances:
            name = font["name"].getDebugName(instance.subfamilyNameID)
            weights.append((f'{name} {instance.coordinates["wght"]:g}',
                            font.getGlyphSet(location=instance.coordinates)))
        capacity = 2 * ROWS
        sections = inventory(font)
        for title, entries in sections:
            count = ceil(len(entries) / capacity)
            for i in range(count):
                suffix = f" ({i + 1}/{count})" if count > 1 else ""
                stem = f"{len(pages) + 1:02d}-{title.lower().replace(' ', '-')}"
                page = output / (stem + ".svg")
                sheet(font, title + suffix, entries[i * capacity:(i + 1) * capacity],
                      weights, page)
                pages.append(page)
        review = [entry for _, entries in sections for entry in entries if entry[0] in flagged]
        review_pages = []
        for start in range(0, len(review), capacity):
            number = start // capacity + 1
            page = output / f"review-{number:02d}-flagged-outlines.svg"
            sheet(font, "Flagged outlines", review[start:start + capacity], weights, page)
            review_pages.append(page)
    for page in [*pages, *review_pages]:
        render(page, scale=2, pdf=False)
    render_pdf(pages, output / "DaikonicTransitSans-Glyph-Proof.pdf",
               title="Daikonic Transit Sans Glyph Proof")
    if review_pages:
        render_pdf(review_pages, output / "DaikonicTransitSans-Flagged-Outlines.pdf",
                   title="Daikonic Transit Sans Flagged Outlines")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("font", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build_proof(args.font, args.output)
