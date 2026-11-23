"""Build an upright-derived Transit Sans Italic and its proof."""

import argparse
from copy import deepcopy
from functools import lru_cache
from io import BytesIO
import json
from math import ceil
from pathlib import Path
import unicodedata

import pathops
import uharfbuzz as hb

from fontTools.misc.roundTools import otRound
from fontTools.misc.transform import Transform
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import (
    GlyphCoordinates, SCALED_COMPONENT_OFFSET, UNSCALED_COMPONENT_OFFSET,
)

from adopt_weighting import stamp
from audit import Samples, shape_from_glyphs
from build_sans import complete_outline_pipeline, name_upright, validate_outlines
from bundle_release import sanitize
from font_feature_tools import add_features, expanded_variations
from italic_companions import (
    ANGLE, SHEAR, add_proportional_italic_kerning, apply_shape,
    italicize_anchors, set_style, shear_drawn_outlines,
)
from italic_letterforms import redraw_italic_letters, related_glyphs
from italic_texture_proofs import italic_letterform_proof
from sans_complete_rebuild import intersects
from sans_baseline_trial import build_variations, components, install, load_baseline
from sans_glyph_proof import build_proof
from sans_weight_refinement import fitting_context
from specimens import DATA


def reuse_single_storey_a(font):
    """Share the existing alternate, keeping the established italic advances."""
    glyf = font["glyf"]
    _, _, _, _, model, masters, _ = fitting_context(font)
    alternate = "a.ss01"
    source_metrics = expanded_variations(font, alternate)
    advance = font["hmtx"][alternate][0]
    widths = font["HVAR"].table.AdvWidthMap.mapping
    sources = {}
    for name, base in related_glyphs(font).items():
        if base != "a" or name == alternate:
            continue
        if name == base:
            glyph = components([(alternate, (0, 0))])
            placements = [GlyphCoordinates([(0, 0)]) for _ in masters]
        else:
            glyph = glyf[name]
            if not glyph.isComposite() or glyph.components[0].glyphName != base:
                raise ValueError(f"Expected a reusable a body in {name}")
            placements = []
            for master in masters:
                current, _ = master[name]._getGlyphAndOffset()
                shift = otRound((master[alternate].width - master[name].width) / 2)
                placements.append(GlyphCoordinates(
                    [(part.x + (shift if i else 0), part.y)
                     for i, part in enumerate(current.components)]
                ))
            for part, (x, y) in zip(glyph.components, placements[0]):
                part.x, part.y = x, y
        font["hmtx"][name] = advance, font["hmtx"][name][1]
        widths[name] = widths[alternate]
        install(font, name, glyph, build_variations(model, placements, source_metrics))
        sources[name] = alternate
    return sources


def transformed_components(font, name, slant, pivot):
    """Conjugate each component so its already-slanted source can stay live."""
    original = font["glyf"][name]
    glyph = deepcopy(original)
    deltas = expanded_variations(font, name)
    inverse = slant.inverse()
    for i, part in enumerate(glyph.components):
        base, matrix = part.getComponentInfo()
        parent = slant
        if name == "i":
            # The previous italic carries the i tittle along the slant as an upright diamond.
            mark = font["glyf"][base]
            if mark.yMin + part.y > font["OS/2"].sxHeight + 30:
                dot_center = (original.yMax + font["OS/2"].sxHeight + 30) / 2
                parent = Transform(1, 0, 0, 1, SHEAR * (dot_center - pivot), 0)
        xx, xy, yx, yy, x, y = parent.transform(Transform(*matrix)).transform(inverse)
        part.x, part.y = otRound(x), otRound(y)
        if (xx, xy, yx, yy) != (1, 0, 0, 1):
            part.transform = [[xx, xy], [yx, yy]]
            part.flags = (part.flags & ~SCALED_COMPONENT_OFFSET) | UNSCALED_COMPONENT_OFFSET
        elif hasattr(part, "transform"):
            del part.transform
        for changes in deltas.values():
            dx, dy = parent.transformVector(changes[i])
            changes[i] = otRound(x + dx) - part.x, otRound(y + dy) - part.y
    return glyph, deltas


def overlaps(left, right):
    try:
        return intersects(left, right)
    except pathops.PathOpsError:
        # Near-tangent quadratic curves can make the Boolean operation fail.
        bottom = max(left.bounds[1], right.bounds[1])
        top = min(left.bounds[3], right.bounds[3])
        rows = range(ceil(bottom - 0.5), ceil(top - 0.5))
        scan_edges = []
        for path in (left, right):
            pen = Samples()
            path.draw(pen)
            by_row = {row: [] for row in rows}
            for start, end in pen.lines:
                lo, hi = sorted((start[1], end[1]))
                for row in range(max(rows.start, ceil(lo - 0.5)), min(rows.stop, ceil(hi - 0.5))):
                    by_row[row].append((start, end))
            scan_edges.append(by_row)
        for row in rows:
            a_spans, b_spans = (Samples.spans_from_edges(edges[row], row + 0.5, 1) for edges in scan_edges)
            if any(min(b, d) - max(a, c) > 0.02 for a, b in a_spans for c, d in b_spans):
                return True
        return False


def return_clearance(font):
    """Measure kerning for the descending f forms after applying the shear."""
    buffer = BytesIO()
    font.save(buffer)
    shaped = hb.Font(hb.Face(buffer.getvalue()))
    prefixes = [
        chr(cp) for cp in font.getBestCmap() if unicodedata.category(chr(cp))[0] in "LNPS"
    ]
    prefixes += ["li", "QU"]
    suffixes = {"f": "f", "fi": "fi", "fl": "fl", "ff": "f_f"}
    corrections = {}
    for weight in range(300, 601, 25):
        glyphs = font.getGlyphSet(location={"wght": weight})
        shaped.set_variations({"wght": weight})
        outline = lru_cache(None)(lambda name: shape_from_glyphs(glyphs, name))
        for prefix in prefixes:
            for suffix, expected in suffixes.items():
                run = hb.Buffer()
                run.add_str(prefix + suffix)
                run.guess_segment_properties()
                if run.direction != "ltr":
                    continue
                hb.shape(shaped, run)
                if len(run.glyph_infos) != 2:
                    continue
                left, right = (font.getGlyphName(g.codepoint) for g in run.glyph_infos)
                if right != expected:
                    continue
                first, second = run.glyph_positions
                a = outline(left).transform(translateX=first.x_offset, translateY=first.y_offset)
                x = first.x_advance + second.x_offset
                b = outline(right).transform(translateX=x, translateY=second.y_offset)
                if not overlaps(a, b):
                    continue
                shift = 4
                while overlaps(a, b.transform(translateX=shift)):
                    shift += 4
                pair = left, right
                corrections[pair] = max(corrections.get(pair, 0), shift + 8)
    return corrections


def add_descender_kerning(font):
    clearance = return_clearance(font)
    if clearance:
        rules = "\n".join(f"pos {left} {right} {space};"
                          for (left, right), space in sorted(clearance.items()))
        add_features(font, f"""
            languagesystem DFLT dflt;
            languagesystem latn dflt;
            feature kern {{
                {rules}
            }} kern;
        """)


def italicize(font, config):
    metric_sources = reuse_single_storey_a(font)
    custom, _ = redraw_italic_letters(
        font, "cursive", family="sans", descending_f=True, live_components=True,
        donor_returns=True,
    )
    glyf = font["glyf"]
    order = font.getGlyphOrder()
    pivot = font["OS/2"].sxHeight / 2
    slant = Transform(1, 0, SHEAR, 1, -SHEAR * pivot, 0)
    composites = sorted(
        (name for name in order if glyf[name].isComposite()),
        key=lambda name: glyf[name].getCompositeMaxpValues(glyf).maxComponentDepth,
    )
    revised_parts = {name: transformed_components(font, name, slant, pivot) for name in composites}
    shear_drawn_outlines(font, set(order), pivot, {})
    for name in composites:
        apply_shape(font, name, *revised_parts[name])
    italicize_anchors(font, set(order), pivot, {}, metric_sources)
    add_proportional_italic_kerning(font)
    add_descender_kerning(font)
    set_style(font, config)
    return metric_sources, sorted(custom), composites


def validate_italic(upright, italic, metric_sources):
    assert upright.getGlyphOrder() == italic.getGlyphOrder()
    assert upright.getBestCmap() == italic.getBestCmap()
    assert italic["post"].italicAngle == -ANGLE
    assert list(italic["glyf"]["a"].getComponentNames(italic["glyf"])) == ["a.ss01"]
    assert italic["fvar"].axes[0].axisTag == "wght"
    for weight in range(300, 601):
        regular = upright.getGlyphSet(location={"wght": weight})
        slanted = italic.getGlyphSet(location={"wght": weight})
        assert all(abs(slanted[name].width - regular[metric_sources.get(name, name)].width) < 0.01
                   for name in italic.getGlyphOrder()), weight


def build_fonts(output, *, version=None):
    payload, report = load_baseline()
    flavor = DATA["families"]["sans"]
    output.mkdir(parents=True, exist_ok=True)
    target = output / (flavor["stem"] + "-Italic-VF.ttf")
    with TTFont(BytesIO(payload), recalcTimestamp=False) as font:
        _, mirrors, _, ligatures, _ = complete_outline_pipeline(font)
        original_version = font["name"].getDebugName(5).removeprefix("Version ")
        if version is not None:
            stamp(font, original_version, version)
            name_upright(font, flavor)
        buffer = BytesIO()
        font.save(buffer)
        if version is not None:
            (output / (flavor["stem"] + "-VF.ttf")).write_bytes(buffer.getvalue())
        buffer.seek(0)
        with TTFont(BytesIO(payload)) as baseline, TTFont(buffer) as upright:
            validate_outlines(baseline, upright, mirrors, ligatures)
            config = {**flavor, "version": font["name"].getDebugName(5).removeprefix("Version ")}
            metrics, custom, composites = italicize(font, config)
            font.save(target)
            with TTFont(target) as italic:
                validate_italic(upright, italic, metrics)
                sanitize(italic)
    return target, {
        "source_sha256": report["variable_sha256"],
        "angle": ANGLE,
        "alternate": "a.ss01",
        "custom_drawings": custom,
        "live_composites": composites,
        "advance_sources": metrics,
    }


def build(output):
    target, report = build_fonts(output)
    (output / "italic-build.json").write_text(json.dumps(report, indent=2) + "\n")
    build_proof(target, output / "Proof")
    italic_letterform_proof(output, {"sans": DATA["families"]["sans"]}, refined=True,
                            italic_paths={"sans": target})
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(build(parser.parse_args().output))
