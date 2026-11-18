"""Code syntax/delimiter and proportional numeral review fonts."""

from copy import deepcopy
import json
import math
from pathlib import Path
import unicodedata
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.misc.roundTools import otRound
import pathops
from specimens import ROOT, specimen_families
from audit import shape, spans
from derive_weights import weighted
from font_feature_tools import (
    compose,
    from_paths,
    master_locations,
    add_features,
    append_glyph,
)

OUT = ROOT / "trials/2026-11-17-syntax-numerals"
DIGITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
]
SUP = [
    "uni2070",
    "uni00B9",
    "uni00B2",
    "uni00B3",
    "uni2074",
    "uni2075",
    "uni2076",
    "uni2077",
    "uni2078",
    "uni2079",
]
SUB = [f"uni208{i}" for i in range(10)]
RECIPE = json.loads((ROOT / "recipes/syntax-numeral-trial.json").read_text())
TOKENS = RECIPE["code"]["ligatures"]


def polygon(points):
    p = pathops.Path()
    pen = p.getPen()
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()
    return p


def move_center(font, name, x, y, scale=1):
    l, b, r, t = shape(font, name).bounds
    return (name, scale, scale, x - scale * (l + r) / 2, y - scale * (b + t) / 2)


def extend_bar_ends(font, name, factor):
    from fontTools.ttLib.tables.TupleVariation import TupleVariation
    from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
    from fontTools.varLib.models import VariationModel, normalizeLocation

    triples, locs = master_locations(font)
    glyphs = []
    values = []
    for loc in locs:
        sample = instantiateVariableFont(deepcopy(font), loc, inplace=True)
        glyph = deepcopy(sample["glyf"][name])
        mid = sample["hmtx"][name][0] / 2
        half = (glyph.xMax - glyph.xMin) / 2
        threshold = half * 0.65
        glyph.coordinates = GlyphCoordinates(
            [
                (
                    otRound(
                        x
                        + math.copysign(
                            half
                            * (factor - 1)
                            * max(0, (abs(x - mid) - threshold) / (half - threshold)),
                            x - mid,
                        )
                    ),
                    y,
                )
                for x, y in glyph.coordinates
            ]
        )
        glyphs.append(glyph)
        values.append(GlyphCoordinates(list(glyph.coordinates) + [(0, 0)] * 4))
    normalized = [
        {k: v for k, v in normalizeLocation(loc, triples).items() if v} for loc in locs
    ]
    model = VariationModel(normalized, axisOrder=list(triples))
    default = normalized.index({})
    variations = [
        TupleVariation(support, list(delta))
        for delta, support in zip(model.getDeltas(values), model.supports)
        if support
    ]
    append_glyph(font, name, glyphs[default], variations, font["hmtx"][name][0])


def code(font):
    # Horizontal-only expansion preserves every bar's vertical thickness and gap.
    factor = RECIPE["code"]["equals_width_factor"]
    for name in ["equal", "code.equal", "code.strictEqual"]:
        advance = font["hmtx"][name][0]
        compose(
            font, name, [(name, factor, 1, -advance * (factor - 1) / 2, 0)], advance
        )
    for name in ["code.notEqual", "code.notStrict"]:
        extend_bar_ends(font, name, factor)
    compose(
        font,
        "ellipsis",
        [move_center(font, "period", x, 55.5, 1) for x in [100, 300, 500]],
        600,
    )
    triples, locs = master_locations(font)
    samples = [
        instantiateVariableFont(deepcopy(font), loc, inplace=True) for loc in locs
    ]
    less = []
    greater = []
    turn = []
    for f in samples:
        _, bracket_bottom, _, bracket_top = shape(f, "bracketleft").bounds
        _, operator_bottom, _, operator_top = shape(f, "less").bounds
        cap = f["OS/2"].sCapHeight
        height = min(
            cap, ((bracket_top - bracket_bottom) + (operator_top - operator_bottom)) / 2
        )
        mid = cap / 2
        bottom = mid - height / 2
        top = mid + height / 2
        bars = list(shape(f, "equal").contours)
        thickness = bars[0].bounds[3] - bars[0].bounds[1]
        slope = (top - mid) / 360
        cut = thickness * math.sqrt(1 + slope * slope)
        points = [
            (480, top),
            (120, mid),
            (480, bottom),
            (480, bottom + cut),
            (120 + cut / slope, mid),
            (480, top - cut),
        ]
        less.append(polygon(points))
        greater.append(polygon([(600 - x, y) for x, y in points]))
        turn.append(thickness)
    from_paths(font, "less.generic", locs, less, 600)
    from_paths(font, "greater.generic", locs, greater, 600)
    rules = ["languagesystem DFLT dflt;", "languagesystem latn dflt;", "feature calt {"]
    caret = []
    mapping = {}
    cmap = font.getBestCmap()

    def ordinary(text):
        return [(cmap[ord(c)], 1, 1, 600 * i, 0) for i, c in enumerate(text)]

    for index, text in enumerate(TOKENS):
        name = f"code.syntax{index:02d}"
        parts = ordinary(text)
        length = len(text)
        if text in ["?.", "!."]:
            fit = RECIPE["code"]["punctuation_pair_offsets"][text]
            parts = [
                (cmap[ord(text[0])], 1, 1, fit["lead"], 0),
                ("period", 1, 1, fit["period"], 0),
            ]
        elif text in ["${", "$[", "$("]:
            parts = [("dollar", 1, 1, 35, 0), (cmap[ord(text[1])], 1, 1, 565, 0)]
        elif text in ["..", ".=", "..="]:
            parts = []
            for i, char in enumerate(text):
                parts.append(
                    move_center(font, "period", 300 + 600 * i, 300, 1)
                    if char == "."
                    else ("equal", 1, 1, 600 * i, 0)
                )
        elif text == "...":
            parts = [move_center(font, "period", x, 55.5, 1) for x in [420, 900, 1380]]
        elif text == ":=":
            bar1, bar2 = sorted(
                [c.bounds for c in shape(font, "equal").contours], key=lambda b: b[1]
            )
            parts = [
                move_center(font, "period", 350, (b[1] + b[3]) / 2, 1)
                for b in [bar1, bar2]
            ] + [("equal", 1, 1, 550, 0)]
        elif text in ["|=", "|-"]:
            # Make a turnstile with operator-sized vertical and horizontal strokes.
            bar = shape(font, "bar")
            l, b, r, t = bar.bounds
            parts = [
                ("bar", 1, 500 / (t - b), 450 - (l + r) / 2, 50 - b * 500 / (t - b))
            ]
            if text == "|=":
                parts += [("equal", 1, 1, 450 - 73.2, 0)]
            else:
                hyphen = shape(font, "hyphen")
                l, b, r, t = hyphen.bounds
                parts += [
                    (
                        "hyphen",
                        550 / (r - l),
                        1,
                        450 - l * 550 / (r - l),
                        300 - (b + t) / 2,
                    )
                ]
        elif text in ("<'", "&'"):
            leader = "less.generic" if text == "<'" else "ampersand"
            parts = [(leader, 1, 1, 0, 0), ("quotesingle", 1, 1, 680, 0)]
        if text.startswith("#"):
            paths = []
            for sample in samples:
                original = shape(sample, "numbersign")
                rails = [
                    (a, b)
                    for a, b in spans(original, 100, 0)
                    if 150 < a < 450 and b - a > 35
                ]
                assert len(rails) == 2, rails
                joined = pathops.Path()
                for j in range(length):
                    shifted = original.transform(1, 0, 0, 1, 600 * j, 0)
                    joined = pathops.op(joined, shifted, pathops.PathOp.UNION)
                for j in range(length - 1):
                    for bottom, top in rails:
                        left, right = 500 + 600 * j, 700 + 600 * j
                        bridge = polygon(
                            [(left, bottom), (right, bottom), (right, top), (left, top)]
                        )
                        joined = pathops.op(joined, bridge, pathops.PathOp.UNION)
                paths.append(joined)
            from_paths(font, name, locs, paths, length * 600)
        else:
            compose(font, name, parts, length * 600)
        mapping[text] = name
        caret.append(
            "LigatureCaretByPos "
            + name
            + " "
            + " ".join(str(600 * i) for i in range(1, length))
            + ";"
        )
    # Longest tokens first; preserve shorter sequences inside independent lookups.
    for text in sorted(TOKENS, key=len, reverse=True):
        rules.append(
            "sub " + " ".join(cmap[ord(c)] for c in text) + " by " + mapping[text] + ";"
        )
    rules.extend(["} calt;", "table GDEF {", *caret, "} GDEF;"])
    add_features(font, "\n".join(rules), prepend=True)
    identifiers = sorted(
        {
            name
            for cp, name in cmap.items()
            if unicodedata.category(chr(cp))[0] in ("L", "N")
        }
        | {"dotlessi", "dotlessj"}
    )
    words = sorted(set(identifiers) | {"underscore"})
    lower = sorted(
        {
            name
            for cp, name in cmap.items()
            if unicodedata.category(chr(cp)) == "Ll" or 48 <= cp <= 57
        }
        | {"underscore", "dotlessi", "dotlessj"}
    )
    upper = sorted(
        {
            name
            for cp, name in cmap.items()
            if unicodedata.category(chr(cp)) in ("Lu", "Lt")
        }
    )
    whitespace = sorted({name for cp, name in cmap.items() if chr(cp).isspace()})
    generic_lines = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "@Identifiers=[" + " ".join(identifiers) + "];",
        "@AngleWord=[" + " ".join(words) + "];",
        "@AngleLower=[" + " ".join(lower) + "];",
        "@AngleUpper=[" + " ".join(upper) + "];",
        "@AngleSpace=[" + " ".join(whitespace) + "];",
        "feature calt {",
        "lookup GenericWordPriority {",
        "lookupflag IgnoreMarks;",
    ]
    # A capital anywhere in an adjacent identifier preserves the generic form.
    # Contiguous word lookback/lookahead handles Vec<u8>, HashMap<key,value>,
    # and mixed-case type arguments without treating a<b or12<34 as generics.
    for n in range(32):
        middle = " ".join(["@AngleWord"] * n)
        generic_lines += [
            "sub @AngleUpper " + middle + " less' @AngleLower by less.generic;",
            "sub @AngleLower less' " + middle + " @AngleUpper by less.generic;",
        ]
    generic_lines += [
        "} GenericWordPriority;",
        "lookup ComparisonLess {",
        "lookupflag IgnoreMarks;",
        "ignore sub @AngleSpace less' @AngleSpace;",
        "ignore sub @AngleLower less' @AngleLower;",
        "sub less' by less.generic;",
        "} ComparisonLess;",
        "lookup ExistingGreater {",
        "lookupflag IgnoreMarks;",
        "sub greater' @Identifiers by greater.generic;",
        "sub @Identifiers greater' by greater.generic;",
        "sub greater.generic greater' by greater.generic;",
        "} ExistingGreater;",
        "} calt;",
    ]
    add_features(font, "\n".join(generic_lines))
    lifetime = RECIPE["code"]["rust_lifetime"]
    from dot_inventory import dots

    prime_paths = []
    for f in samples:
        marker = dots(f.getGlyphSet(), "i")[0][1]
        diameter = min(marker["width"], marker["height"]) * lifetime["head_scale"]
        top = marker["bounds"][3]
        cx = lifetime["head_x"]
        cy = top - diameter / 2
        bottom = shape(f, "x").bounds[3] + lifetime["terminal_above_xheight"]
        angle = math.radians(lifetime["angle_degrees"])
        stem = shape(f, "bar").bounds[2] - shape(f, "bar").bounds[0]
        thickness = stem * lifetime["stem_ratio"]
        dx = (cy - bottom) * math.tan(angle)
        half = thickness / (2 * math.cos(angle))
        terminal = half * lifetime["terminal_ratio"]
        diamond = polygon(
            [
                (cx, top),
                (cx + diameter / 2, cy),
                (cx, cy - diameter / 2),
                (cx - diameter / 2, cy),
            ]
        )
        tail = polygon(
            [
                (cx - half, cy),
                (cx + half, cy),
                (cx - dx + terminal, bottom),
                (cx - dx - terminal, bottom),
            ]
        )
        prime_paths.append(pathops.op(diamond, tail, pathops.PathOp.UNION))
    from_paths(font, "quotesingle.lifetime", locs, prime_paths, 600)
    for name, leader in [
        ("code.lifetimeOpen", "less.generic"),
        ("code.lifetimeBorrow", "ampersand"),
    ]:
        compose(
            font,
            name,
            [
                (leader, 1, 1, lifetime["pair_leader_shift"], 0),
                ("quotesingle.lifetime", 1, 1, lifetime["pair_prime_offset"], 0),
            ],
            1200,
        )
    starts = sorted(
        {
            name
            for cp, name in cmap.items()
            if unicodedata.category(chr(cp)).startswith("L")
        }
        | {"underscore"}
    )
    continues = sorted(set(identifiers) | {"underscore"})
    lines = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "@LifetimeStart=[" + " ".join(starts) + "];",
        "@LifetimeContinue=[" + " ".join(continues) + "];",
        "@LifetimeOpen=[quotesingle " + mapping["<'"] + " " + mapping["&'"] + "];",
        "@LifetimeAlternate=[quotesingle.lifetime code.lifetimeOpen code.lifetimeBorrow];",
        "feature calt {",
        "lookup RustLifetime {",
        "lookupflag IgnoreMarks;",
    ]
    # A finite font context can recognize common lifetime syntax, but cannot
    # parse Rust. Protect quoted characters/identifiers before the positive rule.
    for length in range(1, lifetime["quoted_identifier_limit"] + 1):
        lines.append(
            "ignore sub @LifetimeOpen' "
            + " ".join(["@LifetimeContinue"] * length)
            + " quotesingle;"
        )
    lines += [
        "ignore sub @LifetimeContinue quotesingle';",
        "ignore sub quotesingle quotesingle';",
        "sub @LifetimeOpen' @LifetimeStart by @LifetimeAlternate;",
        "} RustLifetime;",
        "} calt;",
        "table GDEF { LigatureCaretByPos code.lifetimeOpen 600; LigatureCaretByPos code.lifetimeBorrow 600; } GDEF;",
    ]
    add_features(font, "\n".join(lines))
    return {
        "tokens": mapping,
        "equals_width_factor": factor,
        "equals_height_and_thickness": "unchanged",
        "generic_policy": RECIPE["code"]["generics"],
        "generic_height": "halfway between comparison and bracket height, centered within baseline/cap-height limits",
        "ligature_advances": "600 times input length",
        "carets": "every600units",
        "period_policy": "all syntax periods use the unscaled source diamond; only positions change",
        "punctuation_pair_offsets": RECIPE["code"]["punctuation_pair_offsets"],
        "rust_lifetime": lifetime,
        "unicode_ellipsis": "one-cell U+2026 uses three full-size source periods; ASCII ... retains three cells",
    }


def numerals(font, key):
    for digit, sup, sub in zip(DIGITS, SUP, SUB):
        compose(font, digit + ".numr", [(sup, 1, 1, 0, -80)], font["hmtx"][sup][0], sup)
        compose(font, digit + ".dnom", [(sub, 1, 1, 0, 100)], font["hmtx"][sub][0], sub)
    triples, locs = master_locations(font)
    masters = [
        instantiateVariableFont(deepcopy(font), loc, inplace=True) for loc in locs
    ]
    slashes = []
    for f in masters:
        p = shape(f, SUP[0])
        b = p.bounds
        line = spans(p, (b[1] + b[3]) / 2, 1)[0]
        width = (line[1] - line[0]) * math.sqrt(710**2 + 325**2) / 710
        slashes.append(
            polygon(
                [
                    (-37.5 - width / 2, 0),
                    (-37.5 + width / 2, 0),
                    (287.5 + width / 2, 710),
                    (287.5 - width / 2, 710),
                ]
            )
        )
    from_paths(font, "fraction", locs, slashes, 180)
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap[0x2044] = "fraction"
    oldstyle = []
    backoffs = []
    if key == "sans":
        for digit, index in zip(DIGITS, range(10)):
            paths = []
            for f, loc in zip(masters, locs):
                p = shape(f, digit)
                l, b, r, t = p.bounds
                xh = shape(f, "x").bounds[3]
                if index == 0:
                    q = shape(f, "o")
                elif index in (6, 8):
                    q = p
                else:
                    low = -155 if index in (3, 4, 5, 7, 9) else -8 if index == 0 else 0
                    high = xh + (8 if index in (0, 2, 3, 5, 9) else 0)
                    factor = (high - low) / (t - b)
                    q = p.transform(factor, 0, 0, factor, 0, low - b * factor)
                    n = shape(f, "n")
                    runs = spans(n, 200, 1)
                    stem = runs[0][1] - runs[0][0]
                    desired = max(0, (1 - factor) * stem)
                    q, actual = weighted(q, desired, 0.72, 3)
                    q = q.transform(1, 0, 0, 1, l - q.bounds[0], 0)
                    if abs(actual - desired) > 0.01:
                        backoffs.append(
                            {
                                "glyph": digit,
                                "location": loc,
                                "desired": desired,
                                "actual": actual,
                            }
                        )
                paths.append(q)
            default = next(
                i
                for i, l in enumerate(locs)
                if all(l[a.axisTag] == a.defaultValue for a in font["fvar"].axes)
            )
            p = paths[default]
            advance = round(p.bounds[2] - p.bounds[0] + 2 * p.bounds[0])
            from_paths(font, digit + ".onum", locs, paths, advance)
            oldstyle.append(digit + ".onum")
    vulgar = {
        0xBC: ("1", "4"),
        0xBD: ("1", "2"),
        0xBE: ("3", "4"),
        0x2150: ("1", "7"),
        0x2151: ("1", "9"),
        0x2152: ("1", "10"),
        0x2153: ("1", "3"),
        0x2154: ("2", "3"),
        0x2155: ("1", "5"),
        0x2156: ("2", "5"),
        0x2157: ("3", "5"),
        0x2158: ("4", "5"),
        0x2159: ("1", "6"),
        0x215A: ("5", "6"),
        0x215B: ("1", "8"),
        0x215C: ("3", "8"),
        0x215D: ("5", "8"),
        0x215E: ("7", "8"),
    }
    for cp, (numerator, denominator) in vulgar.items():
        names = (
            [DIGITS[int(c)] + ".numr" for c in numerator]
            + ["fraction"]
            + [DIGITS[int(c)] + ".dnom" for c in denominator]
        )
        x = 0
        parts = []
        for n in names:
            parts.append((n, 1, 1, x, 0))
            x += font["hmtx"][n][0]
        name = f"uni{cp:04X}"
        compose(font, name, parts, x, sum_metrics=True)
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[cp] = name
    font["OS/2"].recalcUnicodeRanges(font)
    inputs = (
        DIGITS + oldstyle + ([d + ".tnum" for d in DIGITS] if key == "system" else [])
    )
    repeats = len(inputs) // 10
    rules = [
        "languagesystem DFLT dflt;",
        "languagesystem latn dflt;",
        "@FracInput=[" + " ".join(inputs) + "];",
        "@Numerators=[" + " ".join(d + ".numr" for d in DIGITS) + "];",
        "@Denominators=[" + " ".join(d + ".dnom" for d in DIGITS) + "];",
        "@NumrOutput=[" + " ".join([d + ".numr" for d in DIGITS] * repeats) + "];",
        "@DnomOutput=[" + " ".join([d + ".dnom" for d in DIGITS] * repeats) + "];",
        "feature numr { sub @FracInput by @NumrOutput; } numr;",
        "feature dnom { sub @FracInput by @DnomOutput; } dnom;",
        "feature frac { sub @FracInput slash' @FracInput by fraction;",
        "rsub @FracInput' [fraction @Numerators] by @NumrOutput;",
        "sub [fraction @Denominators] @FracInput' by @DnomOutput; } frac;",
    ]
    if oldstyle:
        rules += [
            "@Lining=[" + " ".join(DIGITS) + "];",
            "@Oldstyle=[" + " ".join(oldstyle) + "];",
            "feature onum { sub @Lining by @Oldstyle; } onum;",
            "feature lnum { sub @Oldstyle by @Lining; } lnum;",
        ]
    add_features(font, "\n".join(rules))
    return {
        "unicode_fractions": len(vulgar),
        "fractions": "frac, numr, dnom; reuses source-designed super/sub digits; new variable fraction slash; multi-digit numeric sequences",
        "oldstyle": bool(oldstyle),
        "oldstyle_note": "0/1/2 at x-height,3/4/5/7/9 descend,6/8 retain ascenders; uniform sizing with stroke compensation; review trial",
        "counter_backoffs": backoffs,
    }


def main(families=("code", "sans", "system")):
    OUT.mkdir(exist_ok=True)
    cfg = specimen_families()
    reports = (
        json.loads((OUT / "recipe-report.json").read_text())
        if (OUT / "recipe-report.json").exists()
        else {}
    )
    paths = (
        json.loads((OUT / "fonts.json").read_text())
        if (OUT / "fonts.json").exists()
        else {}
    )
    for key in families:
        source = ROOT / RECIPE["inputs"][key]["font"]
        import hashlib

        assert (
            hashlib.sha256(source.read_bytes()).hexdigest()
            == RECIPE["inputs"][key]["sha256"]
        )
        palette = json.loads(
            (ROOT / "trials/2026-11-17-dot-palette/fonts.json").read_text()
        )
        font = TTFont(ROOT / palette[key])
        font.recalcTimestamp = False
        report = code(font) if key == "code" else numerals(font, key)
        family = cfg[key]["name"] + " Syntax Study"
        old = font["name"].getDebugName(16)
        for record in font["name"].names:
            text = (
                record.toUnicode()
                .replace(old, family)
                .replace(old.replace(" ", ""), family.replace(" ", ""))
            )
            if record.nameID == 5:
                text = "Version 0.001; syntax and numeral review trial"
            elif record.nameID == 3:
                text = family.replace(" ", "") + "-VF 0.001"
            record.string = text.encode(record.getEncoding())
        font["head"].fontRevision = 0.001
        folder = OUT / key
        folder.mkdir(exist_ok=True)
        path = folder / (family.replace(" ", "") + "-VF.ttf")
        font.save(path)
        paths[key] = str(path.relative_to(ROOT))
        reports[key] = {
            "source": str(source.relative_to(ROOT)),
            "dot_palette": palette[key],
            **report,
        }
        print(key, "built", flush=True)
    (OUT / "fonts.json").write_text(json.dumps(paths, indent=2) + "\n")
    (OUT / "recipe-report.json").write_text(json.dumps(reports, indent=2) + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=["code", "sans", "system"], action="append")
    args = parser.parse_args()
    main(args.family or ("code", "sans", "system"))
