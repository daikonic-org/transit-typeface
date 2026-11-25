"""Position the reusable components of Code's laterally assembled ligatures."""

from fontTools.misc.roundTools import otRound
from fontTools.otlLib.builder import buildLookup, buildSinglePos, buildValue
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.varLib.builder import buildVarDevTable
from fontTools.varLib.varStore import OnlineVarStoreBuilder

from code_compact_build import SCOPE
from font_feature_tools import add_features, append_glyph, append_layout_variations, feature_subtables
from system_italic import designspace


def lateral_ligatures(font, masters):
    """Select translated components with real advances and a spacing change."""
    glyf = font["glyf"]
    metrics = font["hmtx"]
    ligatures = {form.LigGlyph for _, table in feature_subtables(font, contextual=True)
                 for forms in getattr(table, "ligatures", {}).values() for form in forms}
    ligatures.update(name + ".hairline" for name in sorted(ligatures) if name + ".hairline" in glyf)
    for name in sorted(ligatures):
        glyph = glyf[name]
        if not glyph.isComposite() or len(glyph.components) < 2:
            continue
        parts = [part.getComponentInfo() for part in glyph.components]
        advance, remainder = divmod(metrics[name][0], len(parts))
        if remainder or not advance or any(
            matrix[:4] != (1, 0, 0, 1) or matrix[5] or not metrics[donor][0]
            for donor, matrix in parts
        ):
            continue
        samples = [gs[name]._getGlyphAndOffset()[0].components for gs in masters]
        settings = [(donor, advance - metrics[donor][0],
                     tuple(otRound(master[i].x - i * advance) for master in samples))
                    for i, (donor, _) in enumerate(parts)]
        if any(adjustment or any(placements) for _, adjustment, placements in settings):
            yield name, settings


def following_glyphs(font):
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    return [name for name in font.getGlyphOrder() if name != ".notdef"
            and font["hmtx"][name][0] > 0 and classes.get(name) != 3]


def add_lateral_positioning(font, recipe, feature):
    locations, model, default = designspace(font)
    masters = [font.getGlyphSet(location=location) for location in locations]
    replacements = {}
    aliases = {}
    values = {}
    context = ["languagesystem DFLT dflt;", "languagesystem latn dflt;"]
    store = font["GDEF"].table.VarStore
    offset = len(store.VarData) << 16
    builder = OnlineVarStoreBuilder(["wght"])
    builder.setModel(model)
    outlines = font.getGlyphSet()

    for name, settings in lateral_ligatures(font, masters):
        sequence = []
        for donor, advance, positions in settings:
            key = donor, advance, positions
            if key not in aliases:
                alias = f"{donor}.positioned{len(aliases)}"
                pen = TTGlyphPen(outlines)
                pen.addComponent(donor, (1, 0, 0, 1, 0, 0))
                append_glyph(font, alias, pen.glyph(), [], font["hmtx"][donor][0], metric_source=donor)
                value = {"XPlacement": positions[default], "XAdvance": advance}
                if len(set(positions)) > 1:
                    base, index = builder.storeMasters(positions)
                    assert base == value["XPlacement"]
                    value["XPlaDevice"] = buildVarDevTable(offset + index)
                values[alias] = buildValue(value)
                aliases[key] = alias
            sequence.append(aliases[key])
        replacements[name] = sequence

    # Keep GDEF operator carets when the renderer cannot derive them from
    # a following cluster. Core Text needs that cluster for a split ligature.
    follow = following_glyphs(font)
    context.extend((
        "lookup ExpandLateral {",
        *(f"sub {source} by {' '.join(parts)};" for source, parts in replacements.items()),
        "} ExpandLateral;",
        f"@LateralSource = [{' '.join(replacements)}];",
        f"@LateralFollowing = [{' '.join(follow)}];",
        f"feature {feature} {{",
        "lookupflag IgnoreMarks;",
        "sub @LateralSource' lookup ExpandLateral @LateralFollowing;",
        f"}} {feature};",
    ))
    left, right = replacements[SCOPE]
    inset = recipe["layout_review"]["turbofish_inset"]
    scope = f"{left}' <{inset} 0 0 0> {right}' <{inset} 0 0 0>"
    angles = ["less.generic"]
    context.append(f"feature {feature} {{")
    if "less.generic.hairline" in font["glyf"]:
        angles.append("less.generic.hairline")
        shift = recipe["layout_review"]["mixed_angle_shift"]
        # In the original hairline lookup, the scope rule consumes the angle
        # before the mixed pair can move it or the bracket. Recreate that result.
        context.append(f"pos {scope} less.generic.hairline' <-{inset + shift} 0 0 0> "
                       f"bracketleft.hairline' <{shift} 0 0 0>;")
    context.extend((f"pos {scope} [{' '.join(angles)}]' <-{inset} 0 0 0>;", f"}} {feature};"))
    add_features(font, "\n".join(context))
    append_layout_variations(font, builder.finish())
    table = font["GPOS"].table
    index = len(table.LookupList.Lookup)
    table.LookupList.Lookup.append(buildLookup(buildSinglePos(values, font.getReverseGlyphMap())))
    table.LookupList.LookupCount = index + 1
    for record in table.FeatureList.FeatureRecord:
        if record.FeatureTag == feature:
            record.Feature.LookupListIndex.append(index)
            record.Feature.LookupCount = len(record.Feature.LookupListIndex)
    return replacements
