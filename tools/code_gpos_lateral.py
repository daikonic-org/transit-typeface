"""Position existing Code ligature parts while retaining the input character indices."""

from fontTools.misc.roundTools import otRound
from fontTools.otlLib.builder import (
    buildCoverage, buildLigatureSubstSubtable, buildLookup, buildSinglePos, buildSingleSubstSubtable, buildValue,
)
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.subset import Options, Subsetter
from fontTools.ttLib.tables import otTables
from fontTools.varLib.builder import buildVarDevTable
from fontTools.varLib.varStore import OnlineVarStoreBuilder

from code_compact_build import SCOPE
from font_feature_tools import add_features, append_glyph, append_layout_variations, feature_subtables
from system_italic import designspace


def split_advance(total, count):
    """Distribute a run's advance across its inputs, rounding the boundaries."""
    stops = [otRound(i * total / count) for i in range(count + 1)]
    return [end - start for start, end in zip(stops[:-1], stops[1:], strict=True)]


def component_positions(total, nominal, origins_by_master):
    """Keep the drawn origins fixed when the advances between them change."""
    cursor = 0
    for original, advance, origins in zip(
        nominal, split_advance(total, len(nominal)), zip(*origins_by_master, strict=True), strict=True
    ):
        yield advance - original, tuple(origin - cursor for origin in origins)
        cursor += advance


def lateral_ligatures(font, masters):
    """Select translated components with real advances and a spacing change."""
    glyf, metrics = font["glyf"], font["hmtx"]
    ligatures = {form.LigGlyph for _, table in feature_subtables(font, contextual=True)
                 for forms in getattr(table, "ligatures", {}).values() for form in forms}
    ligatures.update(name + ".hairline" for name in sorted(ligatures) if name + ".hairline" in glyf)
    for name in sorted(ligatures):
        glyph = glyf[name]
        if not glyph.isComposite() or len(glyph.components) < 2:
            continue
        parts = [part.getComponentInfo() for part in glyph.components]
        advance = metrics[name][0]
        if not advance or any(
            matrix[:4] != (1, 0, 0, 1) or matrix[5] or not metrics[donor][0]
            for donor, matrix in parts
        ):
            continue
        samples = [gs[name]._getGlyphAndOffset()[0].components for gs in masters]
        nominal = [metrics[donor][0] for donor, _ in parts]
        cursor = 0
        shifted = advance != sum(nominal)
        for i, width in enumerate(nominal):
            shifted |= any(master[i].x != cursor for master in samples)
            cursor += width
        if shifted:
            origins = [[otRound(part.x) for part in master] for master in samples]
            yield name, [
                (donor, adjustment, placements)
                for (donor, _), (adjustment, placements) in zip(
                    parts, component_positions(advance, nominal, origins), strict=True
                )
            ]


def add_horizontal_positions(font, model, default, positions, feature):
    store = font["GDEF"].table.VarStore
    offset = len(store.VarData) << 16
    builder = OnlineVarStoreBuilder(["wght"])
    builder.setModel(model)
    values = {}
    for name, (advance, placements) in positions.items():
        value = {"XPlacement": placements[default], "XAdvance": advance}
        if len(set(placements)) > 1:
            base, index = builder.storeMasters(placements)
            assert base == value["XPlacement"]
            value["XPlaDevice"] = buildVarDevTable(offset + index)
        values[name] = buildValue(value)
    append_layout_variations(font, builder.finish())
    table = font["GPOS"].table
    index = len(table.LookupList.Lookup)
    table.LookupList.Lookup.append(buildLookup(buildSinglePos(values, font.getReverseGlyphMap())))
    table.LookupList.LookupCount = index + 1
    for record in table.FeatureList.FeatureRecord:
        if record.FeatureTag == feature:
            record.Feature.LookupListIndex.append(index)
            record.Feature.LookupCount = len(record.Feature.LookupListIndex)


def redirect_ligature_inputs(font, replacements):
    """Reuse the original lookup order and syntax guards, tagging each input in place."""
    listing = font["GSUB"].table.LookupList
    lookups = listing.Lookup
    mapping = font.getReverseGlyphMap()
    selectors = {}

    def selector(before, after, *, joined=False):
        key = before, after
        if key not in selectors:
            sub = (buildLigatureSubstSubtable({before: after}) if joined
                   else buildSingleSubstSubtable({before: after}))
            selectors[key] = len(lookups)
            lookups.append(buildLookup([sub]))
        return selectors[key]

    for lookup in tuple(lookups):
        subtables = [getattr(sub, "ExtSubTable", sub) for sub in lookup.SubTable]
        if not all(isinstance(sub, otTables.LigatureSubst) for sub in subtables):
            continue
        ordered = [(first, form) for sub in subtables for first, forms in sub.ligatures.items() for form in forms]
        if not any(form.LigGlyph in replacements for _, form in ordered):
            continue
        contexts = []
        for first, form in ordered:
            inputs = (first, *form.Component)
            parts = replacements.get(form.LigGlyph)
            context = otTables.ContextSubst()
            context.Format = 3
            context.GlyphCount = len(inputs)
            context.Coverage = [buildCoverage([name], mapping) for name in inputs]
            if parts:
                pairs = [(i, selector(before, after))
                         for i, (before, after) in enumerate(zip(inputs, parts, strict=True))]
            else:
                pairs = [(0, selector(inputs, form.LigGlyph, joined=True))]
            context.SubstLookupRecord = []
            for i, index in pairs:
                record = otTables.SubstLookupRecord()
                record.SequenceIndex, record.LookupListIndex = i, index
                context.SubstLookupRecord.append(record)
            context.SubstCount = len(pairs)
            contexts.append(context)
        lookup.LookupType = 5
        lookup.SubTable = contexts
        lookup.SubTableCount = len(contexts)
    listing.LookupCount = len(lookups)

    for feature, sub in feature_subtables(font, contextual=True):
        if feature != "ss05" or not isinstance(sub, otTables.SingleSubst):
            continue
        for parent, variant in tuple(sub.mapping.items()):
            if parent in replacements and variant in replacements:
                sub.mapping.update(zip(replacements[parent], replacements[variant], strict=True))


def retire_lateral_drawings(font, replacements):
    """Remove the replaced glyphs and any intermediate caret records."""
    carets = font["GDEF"].table.LigCaretList
    retained = [(name, value) for name, value in zip(carets.Coverage.glyphs, carets.LigGlyph, strict=True)
                if name not in replacements]
    carets.Coverage.glyphs = [name for name, _ in retained]
    carets.LigGlyph = [value for _, value in retained]
    carets.LigGlyphCount = len(retained)
    removed = replacements.keys() - {SCOPE}
    options = Options(layout_features=["*"], notdef_outline=True, glyph_names=True,
                      name_IDs=["*"], name_languages=["*"], name_legacy=True)
    subsetter = Subsetter(options=options)
    subsetter.populate(glyphs=set(font.getGlyphOrder()) - removed)
    subsetter.subset(font)
    assert removed.isdisjoint(font.getGlyphOrder())


def add_lateral_positioning(font, recipe, feature):
    locations, model, default = designspace(font)
    masters = [font.getGlyphSet(location=location) for location in locations]
    replacements, aliases, positions = {}, {}, {}
    outlines = font.getGlyphSet()

    for name, settings in list(lateral_ligatures(font, masters)):
        sequence = []
        for i, (donor, advance, placements) in enumerate(settings):
            # Keep the scope tail's lookup name so angle and hairline
            # rules can still recognize it as the turbofish prefix.
            scope_tail = name == SCOPE and i == len(settings) - 1
            key = (donor, advance, placements, scope_tail)
            if key not in aliases:
                alias = SCOPE if scope_tail else f"{donor}.positioned{len(aliases)}"
                pen = TTGlyphPen(outlines)
                pen.addComponent(donor, (1, 0, 0, 1, 0, 0))
                append_glyph(font, alias, pen.glyph(), [], font["hmtx"][donor][0], metric_source=donor)
                positions[alias] = advance, placements
                aliases[key] = alias
            sequence.append(aliases[key])
        replacements[name] = sequence

    redirect_ligature_inputs(font, replacements)
    first, last = replacements[SCOPE]
    inset = recipe["layout_review"]["turbofish_inset"]
    angles = " ".join(name for name in ("less.generic", "less.generic.hairline") if name in font["glyf"])
    add_features(font, f"""
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        feature {feature} {{
            pos {first}' <{inset} 0 0 0> {last} [{angles}];
        }} {feature};
    """)
    add_horizontal_positions(font, model, default, positions, feature)
    return replacements
