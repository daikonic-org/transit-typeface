"""Regenerate selected Sans weights from their approved Regular curves."""

import json

import pathops
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.varLib.models import VariationModel, normalizeLocation

from audit import shape_from_glyphs
from derive_weights import grow, topology, weighted
from font_feature_tools import expanded_variations
from sans_baseline_trial import build_variations
from sans_component_relationships import DELIMITER_PAIRS, LETTER_PAIRS
from sans_sparse_outline_trial import fit

from specimens import ROOT

REFINED_GLYPHS = (
    "six", "eight", "four", "s", "integral", "ordmasculine",
    "quotesingle", "quotedbl", "quoteleft", "quoteright", "quotedblleft", "quotedblright",
)


def keep_vertical_extrema(original, fitted):
    """Keep the Regular terminal heights and prevent overshooting its envelope."""
    low = min(y for _, y in original)
    high = max(y for _, y in original)
    return GlyphCoordinates(
        (x, old_y if old_y in (low, high) else max(low, min(high, y)))
        for (_, old_y), (x, y) in zip(original, fitted)
    )


SAMPLE_WEIGHTS = range(300, 601, 25)

# These are established shared constructions. Measure the common fit on them
# too, then keep their geometry rules when producing the trial font.
CONSTRUCTION_GLYPHS = {
    "diamond.dot", "uni208A", "uni208C", "minus", "equal", "divide.diamondBody",
    *(target for _, target in (*DELIMITER_PAIRS, *LETTER_PAIRS)),
}


def fitting_context(font):
    recipe = json.loads((ROOT / "recipes/weights.json").read_text())
    family = recipe["families"]["sans"]
    settings = {**recipe["defaults"], "geometry_classes": family["geometry_classes"]}
    anchor = settings["anchor_weight"]
    stems = family["target_H_stems"]
    weights = [anchor, *(int(weight) for weight in stems if int(weight) != anchor)]
    axis = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
    model = VariationModel([normalizeLocation({"wght": weight}, axis) for weight in weights])
    named = [font.getGlyphSet(location={"wght": weight}) for weight in weights]
    regular = font.getGlyphSet()
    return settings, anchor, stems, weights, model, named, regular


def fit_variations(font, name, context, *, reduce_on_topology, growth=1):
    settings, anchor, stems, weights, model, named, regular = context
    glyph = font["glyf"][name]
    original = shape_from_glyphs(regular, name)
    masters = [glyph.coordinates]
    targets = []
    for weight, instance in zip(weights[1:], named[1:]):
        amount = (stems[str(weight)] - stems[str(anchor)]) * growth
        ratio, miter = settings["horizontal_growth_ratio"], settings["miter_limit"]
        if reduce_on_topology:
            target, _ = weighted(original, amount, ratio, miter)
        else:
            target = grow(original, amount, ratio, miter)
        shift = (instance[name].width - named[0][name].width) / 2
        target = target.transform(1, 0, 0, 1, shift, 0)
        fitted = fit(glyph, target, x_offset=shift)
        masters.append(keep_vertical_extrema(glyph.coordinates, fitted))
        targets.append((weight, target))
    return build_variations(model, masters, expanded_variations(font, name)), targets, topology(original)


def samples(font):
    return {weight: font.getGlyphSet(location={"wght": weight}) for weight in SAMPLE_WEIGHTS}


def refine_weights(font):
    context = fitting_context(font)
    replacements = {
        name: fit_variations(font, name, context, reduce_on_topology=True)[0]
        for name in REFINED_GLYPHS
    }
    font["gvar"].variations.update(replacements)
    locations = samples(font)
    for name in REFINED_GLYPHS:
        outlines = [shape_from_glyphs(glyphs, name) for glyphs in locations.values()]
        if len({topology(path) for path in outlines}) != 1:
            raise ValueError(f"Weight refinement changed contour structure for {name}")
        if any(a.area >= b.area for a, b in zip(outlines, outlines[1:])):
            raise ValueError(f"Weight refinement did not consistently grow {name}")


def fit_all_outlines(font):
    context = fitting_context(font)
    locations = samples(font)
    variations = font["gvar"].variations
    report = {}
    for name in font.getGlyphOrder():
        glyph = font["glyf"][name]
        if glyph.numberOfContours <= 0:
            continue
        old = variations[name]
        try:
            replacement, targets, original_topology = fit_variations(
                font, name, context, reduce_on_topology=False
            )
            variations[name] = replacement
            outlines = {w: shape_from_glyphs(g, name) for w, g in locations.items()}
            reasons = []
            if any(topology(target) != original_topology for _, target in targets):
                reasons.append("target changed contour structure")
            if any(topology(path) != original_topology for path in outlines.values()):
                reasons.append("fit changed contour structure")
            areas = [shape.area for shape in outlines.values()]
            if any(a >= b for a, b in zip(areas, areas[1:])):
                reasons.append("ink did not grow at every sample")
            result = {"points": len(glyph.coordinates), "findings": reasons}
        except (pathops.PathOpsError, ValueError) as exc:
            result = {"points": len(glyph.coordinates), "findings": [str(exc)]}
        if name in CONSTRUCTION_GLYPHS:
            result["status"] = "use established construction"
        elif result["findings"]:
            result["status"] = "retain reviewed curves"
        else:
            result["status"] = "use shared fit"
        if result["status"] != "use shared fit":
            variations[name] = old
        report[name] = result
        if len(report) % 40 == 0:
            print(f"Fit {len(report)} drawn outlines", flush=True)
    return report


def check_composites(reference, trial):
    prior, updated = samples(reference), samples(trial)
    result = {}
    for name in trial.getGlyphOrder():
        if not trial["glyf"][name].isComposite():
            continue
        changed = []
        thinner = []
        previous_area = None
        for weight in SAMPLE_WEIGHTS:
            old = shape_from_glyphs(prior[weight], name)
            new = shape_from_glyphs(updated[weight], name)
            if topology(old) != topology(new):
                changed.append(weight)
            if previous_area is not None and new.area < previous_area - 0.01:
                thinner.append(weight)
            previous_area = new.area
        result[name] = {
            "component_names": [part.glyphName for part in trial["glyf"][name].components],
            "contour_differences": changed, "ink_loss_weights": thinner,
        }
    return result
