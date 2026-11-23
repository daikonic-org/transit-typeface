"""Build System’s tabular grid from the proportional Sans drawings."""

from copy import deepcopy
from math import ceil
from string import digits

from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

from font_feature_tools import add_features, append_glyph, feature_subtables
from sans_baseline_trial import build_variations, components
from sans_complete_rebuild import box_center
from system_accents import bounds, install_masters
from system_foundation import PROFILES
from system_metrics import set_advances


def tabular_substitutions(font):
    return {name: alternate for tag, table in feature_subtables(font) if tag == "tnum"
            for name, alternate in table.mapping.items()}


def optical_diamonds(font, donors, locations, model, default):
    """Apply System's optical profiles to the common punctuation diamond."""
    optical = next(axis for axis in font["fvar"].axes if axis.axisTag == "opsz")
    scales = dict(zip((optical.minValue, optical.defaultValue, optical.maxValue),
                      (profile[-1] for profile in PROFILES)))
    name = "diamond.dot"
    points = [GlyphCoordinates((otRound(x * scales[loc["opsz"]]), otRound(y * scales[loc["opsz"]]))
                                for x, y in donors[loc["wght"]]["glyf"][name].coordinates)
              for loc in locations]
    glyph = deepcopy(donors[locations[default]["wght"]]["glyf"][name])
    install_masters(font, font, name, glyph, points, model, default)


def rebuild_figures(font, locations, model, default):
    """Install tabular substitutions and live derivatives from the same digit shapes."""
    cmap = font.getBestCmap()
    numerals = [cmap[ord(char)] for char in digits]
    separators = [cmap[ord(char)] for char in ".,:"]
    pairs = {name: name + ".tnum" for name in numerals + separators}
    masters = [font.getGlyphSet(location=loc) for loc in locations]
    cells = [ceil(max(glyphs[name].width for name in numerals) / 10) * 10 for glyphs in masters]
    advances = {}
    for name, tabular in pairs.items():
        widths = cells if name in numerals else [cell // 2 for cell in cells]
        placements = []
        for glyphs, width in zip(masters, widths):
            box = bounds(glyphs, name)
            x = otRound(width / 2 - box_center(box, 0))
            y = otRound(font["OS/2"].sCapHeight / 2 - box_center(box, 1)) if name == cmap[ord(":")] else 0
            placements.append(GlyphCoordinates([(x, y)]))
        glyph = components([(name, placements[default][0])])
        append_glyph(font, tabular, glyph, build_variations(model, placements), widths[default])
        advances[tabular] = widths
    # Round the digit grid in half-cell units so each variation delta is twice
    # the corresponding separator delta.
    set_advances(font, advances, model, multiples={pairs[name]: 2 for name in numerals})

    lines = ["languagesystem DFLT dflt;", "languagesystem latn dflt;"]
    for tag, mapping in (("tnum", pairs), ("pnum", {right: left for left, right in pairs.items()})):
        lines.append(f"feature {tag} {{")
        lines.extend(f"sub {left} by {right};" for left, right in mapping.items())
        lines.append(f"}} {tag};")
    add_features(font, "\n".join(lines))
    return pairs
