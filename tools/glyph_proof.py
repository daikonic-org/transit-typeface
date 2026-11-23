"""Render the shared Transit glyph proof across named weights."""

import argparse
from base64 import b64encode
from collections import defaultdict
from html import escape
from io import BytesIO
import json
from math import ceil
from pathlib import Path
from string import Template, ascii_lowercase, ascii_uppercase, digits
from unicodedata import category, decomposition

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

from font_feature_tools import feature_subtables
from render_svg import render, render_pdf

WIDTH = 1240
HEIGHT = 795
MARGIN = 28
ROWS = 13
ROW_HEIGHT = 51
GLYPH_SIZE = 36
LABEL_WIDTH = 154
BASELINE_OFFSET = 37
ROW_TOP = 115
HEADER_Y = 106
DETAIL_HEADER_HEIGHT = 21
CENTER_STYLE = "stroke:#7a759a;stroke-dasharray:1.5 2.5"


def alternates(subtables):
    for tag, subtable in subtables:
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
    subtables = list(feature_subtables(font, contextual=True))
    substitutions = list(alternates(subtables))
    letter_alts = {}
    for tag, original, replacement in substitutions:
        if (tag.startswith("ss") or tag == "calt") and original in letters:
            letter_alts.setdefault(replacement, f"{letters[original]} · {tag}")
    sections.append(("Letter alternates", list(letter_alts.items())))
    numerals = {cmap[ord(char)]: char for char in digits + ".,:" if ord(char) in cmap}
    numeral_alts = {replacement: f"{numerals[original]} · {tag}"
                    for tag, original, replacement in substitutions
                    if tag in {"tnum", "onum"} and original in numerals}
    if numeral_alts:
        sections.append(("Numeral alternates", list(numeral_alts.items())))

    glyf = font["glyf"]
    composition = {
        name: [part.glyphName for part in glyf[name].components]
        for name in font.getGlyphOrder() if glyf[name].isComposite()
    }
    used_parts = {part for parts in composition.values() for part in parts}
    excluded = base_forms | letter_alts.keys() | numeral_alts.keys()
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
    for tag, subtable in subtables:
        if tag in {"liga", "dlig", "ordn", "calt"} or tag.startswith("ss"):
            for entries in getattr(subtable, "ligatures", {}).values():
                for entry in entries:
                    if entry.LigGlyph not in shown and glyf[entry.LigGlyph].numberOfContours:
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
    return [(title, [(name, label) for name, label in entries if glyf[name].numberOfContours])
            for title, entries in sections]


def guide_metrics(font, location):
    metrics = font["OS/2"]
    glyphs = font.getGlyphSet(location=location)
    pen = BoundsPen(glyphs)
    glyphs[font.getBestCmap()[ord("=")]].draw(pen)
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


def sheet(font, title, entries, weights, target, *, family, location):
    upm = font["head"].unitsPerEm
    pieces = [
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>',
        f'<text x="28" y="43" font-size="27" font-weight="700">{escape(family)}</text>',
        f'<text x="28" y="76" font-size="20" font-weight="700">{escape(title)}</text>',
    ]
    if location:
        coordinates = " · ".join(f"{tag} {value:.4g}" for tag, value in location.items())
        pieces.append(f'<text x="1212" y="43" text-anchor="end" font-size="13" '
                      f'fill="#435451">{escape(coordinates)}</text>')
    guides = guide_metrics(font, location)
    legend_x = 473
    for label, units, color in (*guides, ("Center", None, CENTER_STYLE)):
        pieces.append(line(legend_x, 73, legend_x + 17, 73, color))
        text = f"{label} {units:g}" if units is not None else "Advance / ink center"
        pieces.append(f'<text x="{legend_x + 22}" y="77" font-size="10" fill="#454b47">{text}</text>')
        legend_x += 28 + len(text) * 5.5
    block_width = (WIDTH - 3 * MARGIN) / 2
    name_width = LABEL_WIDTH
    cell_width = (block_width - name_width) / len(weights)
    half = ceil(len(entries) / 2)
    wide_rows = False
    rows = []
    for column, start in enumerate((0, half)):
        origin = MARGIN + column * (block_width + MARGIN)
        for i, (label, _, _) in enumerate(weights):
            center = origin + name_width + (i + 0.5) * cell_width
            label_size = min(11, (cell_width - 8) / max(1, len(label)) / 0.57)
            pieces.append(
                f'<text x="{center:.3f}" y="{HEADER_Y}" text-anchor="middle" '
                f'font-size="{label_size:g}" fill="#435451">{escape(label)}</text>'
            )
        for row, (name, label) in enumerate(entries[start:start + half]):
            y = ROW_TOP + row * ROW_HEIGHT
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
            baseline = y + BASELINE_OFFSET
            positions = [outline_position(glyph_set, name) for _, glyph_set, _ in weights]
            max_extent = max(extent for _, extent in positions)
            rows.append({
                "name": name, "label": label, "shade": shade, "box": [origin, y, block_width, ROW_HEIGHT],
                "extent": max_extent, "inkCenter": positions[0][0],
            })
            nominal = GLYPH_SIZE / upm
            scale = min(nominal, (cell_width / 2 - 4) / max(1, max_extent))
            wide_rows |= scale < nominal
            for _, units, color in guides:
                guide_y = baseline - units * scale
                pieces.append(line(origin + name_width, guide_y, origin + block_width, guide_y, color))
            for i, (_, glyph_set, _) in enumerate(weights):
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

    return rows


def proof_instances(font, coordinates):
    names = font["name"]
    regular = font["OS/2"].usWeightClass
    if "fvar" not in font:
        if coordinates:
            raise ValueError("Axis selection requires a variable font")
        return {}, [(f"{names.getBestSubFamilyName()} {regular}",
                     font.getGlyphSet(), regular)]
    axes = {axis.axisTag: axis for axis in font["fvar"].axes if axis.axisTag != "wght"}
    for tag, value in coordinates.items():
        if tag not in axes or not axes[tag].minValue <= value <= axes[tag].maxValue:
            raise ValueError(f"Axis selection is unavailable: {tag}={value:g}")
    location = {tag: coordinates.get(tag, axis.defaultValue) for tag, axis in axes.items()}
    instances = defaultdict(list)
    for instance in font["fvar"].instances:
        instances[instance.coordinates.get("wght", regular)].append(instance)
    if not instances:
        return location, [(f"{names.getBestSubFamilyName()} {regular}",
                           font.getGlyphSet(location=location), regular)]
    selected = [(weight, min(items, key=lambda item: sum(
        abs(value - item.coordinates[tag]) for tag, value in location.items())))
                for weight, items in sorted(instances.items())]
    labels = [names.getDebugName(item.subfamilyNameID).removesuffix(" Italic") for _, item in selected]
    split = [label.rsplit(" ", 1) for label in labels]
    if location and len(split) > 1 and all(len(parts) == 2 for parts in split):
        if len({parts[-1] for parts in split}) == 1:
            labels = [parts[0] for parts in split]
    weights = [(f"{label} {weight:g}", font.getGlyphSet(location=item.coordinates | location), weight)
               for label, (weight, item) in zip(labels, selected)]
    return location, weights


def axis_comparison(font, display, location, weights, rows):
    if "fvar" not in font or not font["fvar"].axes:
        return None
    glyphs = {row["name"] for page in rows.values() for row in page}
    # A private character for each proof glyph also exposes unencoded components and ligatures.
    codepoints = {name: 0xF0000 + i for i, name in enumerate(sorted(glyphs))}
    private_cmap = CmapSubtable.newSubtable(12)
    private_cmap.platformID, private_cmap.platEncID, private_cmap.language = 3, 10, 0
    private_cmap.cmap = font.getBestCmap() | {value: name for name, value in codepoints.items()}
    guides = guide_metrics(font, location)
    font["cmap"].tables = [table for table in font["cmap"].tables
                           if (table.platformID, table.platEncID) != (3, 10)] + [private_cmap]
    font.flavor = "woff2"
    data = BytesIO()
    font.save(data)
    axes = {}
    for axis in font["fvar"].axes:
        tag = axis.axisTag
        low, default, high = axis.minValue, axis.defaultValue, axis.maxValue
        labels, unit = {
            "wdth": (("Narrow", "Normal", "Wide"), "%"),
            "opsz": (("Caption", "Text", "Display"), " pt"),
        }.get(tag, (("", "", ""), ""))
        stops = {value: f"{label} {value:.4g}{unit}".strip()
                 for label, value in zip(labels, (low, default, high))}
        if tag == "wght":
            stops = {weight: label for label, _, weight in weights}
            stops.setdefault(low, f"{low:g}")
            stops.setdefault(high, f"{high:g}")
        axes[tag] = {
            "label": font["name"].getDebugName(axis.axisNameID) or tag,
            "min": low, "max": high, "value": location.get(tag, default),
            "stops": sorted(stops.items()),
        }
    return {
        "family": display, "axes": axes, "codepoints": codepoints, "font": b64encode(data.getvalue()).decode("ascii"),
        "guides": guides, "centerStyle": CENTER_STYLE, "upm": font["head"].unitsPerEm,
        "labelWidth": LABEL_WIDTH, "fontSize": GLYPH_SIZE, "margin": MARGIN,
        "pageWidth": WIDTH, "pageHeight": HEIGHT,
        "baselineOffset": BASELINE_OFFSET, "headerY": HEADER_Y, "detailHeader": DETAIL_HEADER_HEIGHT,
    }


def json_for_script(value):
    return json.dumps(value).replace("<", "\\u003c")


def write_viewer(output, title, pages, pdfs, *, rows, comparison, site=None):
    first, first_label = pages[0]
    site = site or {}
    prefix = site.get("prefix", "")
    template = Template(Path(__file__).with_name("glyph_proof_viewer.html").read_text())
    options = "".join(f'<option value="{escape(page.name)}" data-title="{escape(label)}">{i}. {escape(label)}</option>'
                      for i, (page, label) in enumerate(pages, 1))
    downloads = " ".join(f'<a href="{escape(path.name)}">{escape(label)}</a>' for path, label in pdfs)
    (output / "index.html").write_text(template.substitute(
        title=escape(title), options=options, downloads=downloads,
        initial_page=escape(prefix + first.name), initial_label=escape(first_label), width=WIDTH, height=HEIGHT,
        rows=json_for_script(rows), header_y=ROW_TOP - DETAIL_HEADER_HEIGHT, detail_header=DETAIL_HEADER_HEIGHT,
        comparison=json_for_script(comparison),
        compare_script=(Path(__file__).with_name("glyph_proof_compare.js").read_text()
                        if comparison or site else ""),
        site_style='<link rel="stylesheet" href="assets/proof-site.css">' if site else "",
        site_class=' class="public-proof"' if site else "",
        site_controls=site.get("controls", ""),
        site_navigation=site.get("navigation", ""),
        site_status=site.get("status", ""),
        site_footer=site.get("footer", ""),
        site_script=site.get("script", ""),
        prefix=json_for_script(prefix),
    ))


def collect_proof(source, output, *, flagged=(), coordinates=None, interactive_axes=False):
    output.mkdir(parents=True, exist_ok=True)
    pages = []
    rows = {}
    with TTFont(source) as font:
        family = font["name"].getBestFamilyName()
        stem = "".join(family.split())
        display = f"{family} Italic" if font["post"].italicAngle else family
        location, weights = proof_instances(font, coordinates or {})
        capacity = 2 * ROWS
        sections = inventory(font)
        for title, entries in sections:
            count = ceil(len(entries) / capacity)
            for i in range(count):
                suffix = f" ({i + 1}/{count})" if count > 1 else ""
                page_name = f"{len(pages) + 1:02d}-{title.lower().replace(' ', '-')}"
                page = output / (page_name + ".svg")
                rows[page.name] = sheet(font, title + suffix, entries[i * capacity:(i + 1) * capacity],
                                        weights, page, family=display, location=location)
                pages.append((page, title + suffix))
        labels = {name: label for _, entries in sections for name, label in entries}
        cmap = font.getBestCmap()
        names = {name: chr(cp) for cp, name in cmap.items()}
        requested = set(flagged)
        review = [(name, label) for name, label in labels.items() if name in requested]
        review.extend((name, f"{names[name]} · {name}" if name in names else name)
                      for name in sorted(requested - labels.keys())
                      if name in font["glyf"] and font["glyf"][name].numberOfContours)
        review_pages = []
        for start in range(0, len(review), capacity):
            number = start // capacity + 1
            page = output / f"review-{number:02d}-flagged-outlines.svg"
            rows[page.name] = sheet(font, "Flagged outlines", review[start:start + capacity], weights, page,
                                    family=display, location=location)
            review_pages.append((page, f"Flagged outlines ({number})"))
        comparison = axis_comparison(font, display, location, weights, rows) if interactive_axes else None
    return f"{display} Glyph Proof", stem, pages, review_pages, rows, comparison


def build_proof(source, output, *, flagged=(), coordinates=None, svg_only=False, interactive_axes=False):
    title, stem, pages, review_pages, rows, comparison = collect_proof(
        source, output, flagged=flagged, coordinates=coordinates, interactive_axes=interactive_axes,
    )
    all_pages = [*pages, *review_pages]
    if svg_only:
        write_viewer(output, title, all_pages, [], rows=rows, comparison=comparison)
        return
    for page, _ in all_pages:
        render(page, scale=2, pdf=False)
    pdf = output / f"{stem}-Glyph-Proof.pdf"
    render_pdf([page for page, _ in pages], pdf, title=title)
    pdfs = [(pdf, "PDF")]
    if review_pages:
        review_pdf = output / f"{stem}-Flagged-Outlines.pdf"
        render_pdf([page for page, _ in review_pages], review_pdf, title=title.replace("Glyph Proof", "Flagged Outlines"))
        pdfs.append((review_pdf, "Review PDF"))
    write_viewer(output, title, all_pages, pdfs, rows=rows, comparison=comparison)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("font", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--axis", action="append", default=[], metavar="TAG=VALUE",
                        help="hold a non-weight axis at this coordinate")
    parser.add_argument("--review-glyph", action="append", default=[], metavar="NAME",
                        help="also show this glyph in a focused proof")
    parser.add_argument("--svg-only", action="store_true", help="make the browser proof without PNG or PDF exports")
    parser.add_argument("--interactive-axes", action="store_true", help="allow live axis comparisons in the browser")
    args = parser.parse_args()
    try:
        axes = {tag: float(value) for tag, value in (pair.split("=", 1) for pair in args.axis)}
        build_proof(args.font, args.output, flagged=args.review_glyph, coordinates=axes,
                    svg_only=args.svg_only, interactive_axes=args.interactive_axes)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
