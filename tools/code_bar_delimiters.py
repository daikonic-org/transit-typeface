"""Contextual Code bars using the existing delimiter metrics and inward fit."""

from copy import deepcopy
import unicodedata
import pathops
from fontTools.varLib.instancer import instantiateVariableFont
from audit import shape, spans
from font_feature_tools import add_features, from_paths, master_locations


def add_bar_delimiters(font, recipe, tokens):
    _, locations = master_locations(font)
    opening, closing = [], []
    for location in locations:
        sample = instantiateVariableFont(deepcopy(font), location, inplace=True)
        delimiter = shape(sample, "parenleft")
        bottom, top = delimiter.bounds[1], delimiter.bounds[3]
        stem = spans(delimiter, (bottom + top) / 2, 1)[0]
        thickness = stem[1] - stem[0]
        for paths, direction in ((opening, 1), (closing, -1)):
            center = 300 + direction * recipe["inward_units"]
            left, right = center - thickness / 2, center + thickness / 2
            path = pathops.Path()
            pen = path.getPen()
            pen.moveTo((left, bottom))
            pen.lineTo((right, bottom))
            pen.lineTo((right, top))
            pen.lineTo((left, top))
            pen.closePath()
            paths.append(path)
    from_paths(font, "bar.delimiterOpen", locations, opening, 600)
    from_paths(font, "bar.delimiterClose", locations, closing, 600)
    cmap = font.getBestCmap()
    inside = {n for cp, n in cmap.items() if unicodedata.category(chr(cp))[0] in "LNM"}
    inside |= {cmap[ord(c)] for c in " _,:&'<>!?=.[]"}
    inside |= {
        "less.generic",
        "greater.generic",
        "quotesingle.lifetime",
        "quotesingle.lifetime.compact",
        "dotlessi",
        "dotlessj",
        "code.lifetimeBorrow",
        "code.lifetimeOpen",
        "code.scope",
    }
    before = {cmap[ord(c)] for c in "=([{,:;"}
    before |= {tokens[":="]}  # :=
    all_glyphs = " ".join(font.getGlyphOrder())
    lines = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "@BarAny=[" + all_glyphs + "];",
        "@BarInside=[" + " ".join(sorted(inside)) + "];",
        "@BarBefore=[" + " ".join(sorted(before)) + "];",
        "lookup BarStart {",
        "lookupflag IgnoreMarks;",
        "ignore sub @BarAny bar';",
    ]
    limit = recipe["context_limit"]
    for count in range(1, limit + 1):
        content = " ".join(["@BarInside"] * count)
        lines.append("sub bar' " + content + " bar by bar.delimiterOpen;")
    lines += ["} BarStart;", "lookup BarAfterSyntax {", "lookupflag IgnoreMarks;"]
    contexts = ["@BarBefore" + " space" * n for n in range(3)]
    for word in ("move", "async", "do"):
        contexts.append(" ".join(cmap[ord(c)] for c in word) + " space")
    for context in contexts:
        for count in range(limit + 1):
            content = " ".join(["@BarInside"] * count)
            lines.append(
                "sub " + context + " bar' " + content + " bar by bar.delimiterOpen;"
            )
    lines += ["} BarAfterSyntax;", "lookup BarClose {", "lookupflag IgnoreMarks;"]
    for count in range(limit + 1):
        content = " ".join(["@BarInside"] * count)
        lines.append(
            "sub bar.delimiterOpen " + content + " bar' by bar.delimiterClose;"
        )
    lines += [
        "} BarClose;",
        "feature calt { lookup BarStart; lookup BarAfterSyntax; lookup BarClose; } calt;",
    ]
    add_features(font, "\n".join(lines))
    return {
        **recipe,
        "metrics": "vertical span and midpoint stem weight from parenleft at each master",
        "advance": 600,
        "feature": "calt",
        "scope": "paired bars at run start or after closure-introducing punctuation / keywords; bounded parameter-like content",
    }
