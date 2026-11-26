"""Build the three-width texture feature for the rebuilt Code upright."""

from collections import defaultdict
from functools import lru_cache
import json
import unicodedata

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables

from audit import shape_from_glyphs
from code_boundary_spacing import identifier_glyphs
from code_receiver_shapes import fit_m, fit_w
from font_feature_tools import (
    add_features, from_paths, inherit_pair_positioning, label_stylistic_set,
    master_locations,
)
from specimens import ROOT


FEATURE = "ss03"
OFF_FEATURE = "ss04"
DONORS = "aijl"
RECEIVERS = "mw"
PUNCTUATION = '.,:;!?"‘’“”'
HALF_WIDTH = 18
CELL = 600
LANGUAGES = ["languagesystem DFLT dflt;", "languagesystem latn dflt;"]


def metrics_map(font, alias, source):
    for table_name in ("AdvWidthMap", "LsbMap", "RsbMap"):
        table = getattr(font["HVAR"].table, table_name, None)
        if table is not None:
            table.mapping[alias] = table.mapping[source]


def inherited_positions(font, aliases):
    inherit_pair_positioning(font, aliases)

    def replacements(coverage):
        return {alias: source for source in coverage.glyphs for alias in aliases.get(source, ())}

    for lookup in font["GPOS"].table.LookupList.Lookup:
        for wrapped in lookup.SubTable:
            table = getattr(wrapped, "ExtSubTable", wrapped)
            if isinstance(table, otTables.SinglePos):
                coverage = table.Coverage
                added = replacements(coverage)
                if added:
                    names = sorted(set(coverage.glyphs) | added.keys(), key=font.getGlyphID)
                    if table.Format == 2:
                        values = dict(zip(coverage.glyphs, table.Value, strict=True))
                        table.Value = [values[added.get(name, name)] for name in names]
                        table.ValueCount = len(names)
                    coverage.glyphs = names
            for field in ("BacktrackCoverage", "InputCoverage", "LookAheadCoverage"):
                for coverage in getattr(table, field, ()):
                    coverage.glyphs = sorted(
                        set(coverage.glyphs) | replacements(coverage).keys(),
                        key=font.getGlyphID,
                    )


def receiver_drawings(font):
    recipe = json.loads((ROOT / "recipes/code-rebuild.json").read_text())
    sans_path = ROOT / (recipe["fonts"]["sans"] + "-VF.ttf")
    _, locations = master_locations(font)
    aliases = defaultdict(list)
    with TTFont(sans_path) as sans:
        @lru_cache(maxsize=128)
        def sans_at(letter, weight):
            return shape_from_glyphs(sans.getGlyphSet(location={"wght": weight}), letter)

        for receiver in RECEIVERS:
            originals = [shape_from_glyphs(font.getGlyphSet(location=loc), receiver) for loc in locations]
            middle, wide = f"{receiver}.texture.middle", f"{receiver}.texture.wide"
            for name, added in ((middle, HALF_WIDTH), (wide, 2 * HALF_WIDTH)):
                paths = []
                for location, original in zip(locations, originals, strict=True):
                    left, _, right, _ = original.bounds
                    width = right - left + added
                    drawn = (fit_m(sans_at("m", location["wght"]), original, width)
                             if receiver == "m" else fit_w(sans_at, original, width))
                    paths.append(drawn.transform(1, 0, 0, 1, (left + right - CELL) / 2, 0))
                from_paths(font, name, locations, paths, CELL)
                metrics_map(font, name, receiver)
            aliases[receiver].extend((middle, wide))
    inherited_positions(font, aliases)


def common_classes(font):
    glyph_classes = font["GDEF"].table.GlyphClassDef.classDefs
    cmap = font.getBestCmap()
    marks = {g for g, kind in glyph_classes.items() if kind == 3}
    marks.update(g for cp, g in cmap.items() if unicodedata.category(chr(cp)).startswith("M"))
    groups = {
        "Receiver": list(RECEIVERS),
        "Donor": list(DONORS),
        "TextureMark": sorted(marks),
        "SingleQuote": [name for name in font.getGlyphOrder() if name.partition(".")[0] == "quotesingle"],
    }
    groups["Available"] = list(DONORS) + [cmap[ord(c)] for c in PUNCTUATION]
    groups["Run"] = sorted(identifier_glyphs(font))
    for form in ("middle", "wide"):
        groups[f"Receiver{form.title()}"] = [f"{letter}.texture.{form}" for letter in RECEIVERS]
    return [f"@{name} = [{' '.join(glyphs)}];" for name, glyphs in groups.items()]


def add_texture(font, *, shift_intermediate=False):
    receiver_drawings(font)
    quote_guard = ("ignore sub @SingleQuote @Receiver', @Receiver' @SingleQuote, "
                   "@SingleQuote @Donor @Receiver', @Receiver' @Donor @SingleQuote;")
    rules = [
        "lookup IsolatedPairs {",
        "ignore sub @Receiver' @TextureMark;",
        quote_guard,
        "ignore sub @Run i @Receiver', i @Receiver' @Run, "
        "@Run @Receiver' i, @Receiver' i @Run;",
        "sub i @Receiver' by @ReceiverWide;",
        "sub @Receiver' i by @ReceiverWide;",
        "} IsolatedPairs;",
        "lookup ReceiverWidths {",
        "ignore sub @Receiver' @TextureMark;",
        quote_guard,
        "sub @Available @Receiver' @Available by @ReceiverWide;",
        "sub @Available @Receiver' by @ReceiverMiddle;",
        "sub @Receiver' @Available by @ReceiverMiddle;",
        "} ReceiverWidths;",
    ]
    calls = "lookup IsolatedPairs; lookup ReceiverWidths;"
    if shift_intermediate:
        rules.extend([
            "lookup PlaceIntermediate {",
            "ignore pos @Available @ReceiverMiddle' @Available;",
            f"pos @Available @ReceiverMiddle' <-{HALF_WIDTH // 2} 0 0 0>;",
            f"pos @ReceiverMiddle' <{HALF_WIDTH // 2} 0 0 0> @Available;",
            "} PlaceIntermediate;",
        ])
        calls += " lookup PlaceIntermediate;"
    restore = " ".join(f"sub [{letter}.texture.middle {letter}.texture.wide] by {letter};"
                       for letter in RECEIVERS)
    add_features(font, "\n".join([
        *LANGUAGES, *common_classes(font), *rules,
        f"feature calt {{ {calls} }} calt;",
        f"feature {FEATURE} {{ {calls} }} {FEATURE};",
        f"feature {OFF_FEATURE} {{ {restore} }} {OFF_FEATURE};",
    ]))
    label_stylistic_set(font, FEATURE, "Texture healing")
    label_stylistic_set(font, OFF_FEATURE, "Disable texture healing")
