"""Attach the existing Hairlining treatment to the current delimiter outlines."""

from string import ascii_letters

from fontTools.pens.ttGlyphPen import TTGlyphPen
import uharfbuzz as hb

from check_code_rebuild import shape
from code_bar_delimiters import add_bar_delimiters
from code_compact_build import SCOPE
from code_hairline_study import HAIRLINE, PAIRS, delimiter_rail, polygon
from code_hairline_toggle import (
    BAR_CLOSE, BAR_OPEN, FEATURE, OFF_FEATURE, PAIRS as MIXED,
    default_hairlining, position_lifetime_ampersand,
)
from code_lifetimes import activate_lifetime_hairlining
from code_syntax_build import syntax_names
from font_feature_tools import add_features, append_glyph, from_paths, master_locations
from italic_returns import raw_outline


def build_hairlining(font, cell, settings, *, delimited_rails=True):
    tokens = syntax_names(font)
    add_bar_delimiters(font, settings["bar_delimiters"], tokens, cell, scope=SCOPE)
    if delimited_rails:
        build_delimiter_rails(font, settings, tokens)
        if settings.get("delimiter_revision"):
            from font_feature_tools import label_stylistic_set

            label_stylistic_set(font, FEATURE, "Hairline delimiters")
            default_hairlining(font)
            position_lifetime_ampersand(font)
        else:
            activate_lifetime_hairlining(font)


def build_delimiter_rails(font, settings, tokens):
    _, locations = master_locations(font)
    masters = [font.getGlyphSet(location=location) for location in locations]
    glyf = font["glyf"]
    metrics = font["hmtx"]
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    aliases = {}

    def register(base, parts):
        alternate = base + ".hairline"
        pen = TTGlyphPen(font.getGlyphSet())
        for name, matrix in parts:
            pen.addComponent(name, matrix)
        append_glyph(font, alternate, pen.glyph(), [], metrics[base][0], metric_source=base)
        classes[alternate] = classes.get(base, 1)
        aliases[base] = alternate

    for pair in (*PAIRS, ("less.generic", "greater.generic")):
        for index, base in enumerate(pair):
            stroke = base + ".rail"
            forms = [polygon(delimiter_rail(gs, base, opening=index == 0, shifted=True)[0])
                     for gs in masters]
            from_paths(font, stroke, locations, forms, 0)
            register(base, [(name, (1, 0, 0, 1, 0, 0)) for name in (base, stroke)])

    derived = [tokens[token] for token in ("${", "$[", "$(") if tokens[token] in glyf]
    derived.extend(name for name in font.getGlyphOrder() if name.startswith("code.genericClose"))
    for base in derived:
        parts = [part.getComponentInfo() for part in glyf[base].components]
        register(base, [(aliases.get(name, name), matrix) for name, matrix in parts])

    cmap = font.getBestCmap()
    parameters = " ".join(cmap[ord(char)] for char in ascii_letters + "_")
    lines = [
        "languagesystem DFLT dflt;", "languagesystem latn dflt;",
        f"@EchoParameter = [{parameters}];",
        f"feature {FEATURE} {{",
        "lookup RecoverBarOpen {",
        f"sub {BAR_CLOSE} space bar' @EchoParameter bar by {BAR_OPEN};",
        f"sub {BAR_CLOSE} space space bar' @EchoParameter bar by {BAR_OPEN};",
        "} RecoverBarOpen;",
        f"sub {BAR_OPEN} @EchoParameter bar' by {BAR_CLOSE};",
        *(f"sub {base} by {alternate};" for base, alternate in aliases.items()),
        f"}} {FEATURE};",
        f"feature {FEATURE} {{",
    ]
    shift = settings["mixed_angle_shift"]
    if not settings.get("delimiter_revision"):
        for left, right in MIXED:
            lines.append(f"pos {aliases[left]}' <{shift} 0 0 0> {aliases[right]}' <-{shift} 0 0 0>;")
    inset = settings["turbofish_inset"]
    lines.append(f"pos {SCOPE}' <{inset} 0 0 0> {aliases['less.generic']}' <-{inset} 0 0 0>;")
    lines.extend((f"}} {FEATURE};", "table GDEF {"))
    carets = font["GDEF"].table.LigCaretList
    for name, record in zip(carets.Coverage.glyphs, carets.LigGlyph, strict=True):
        if name in aliases:
            coordinates = " ".join(str(value.Coordinate) for value in record.CaretValue)
            lines.append(f"LigatureCaretByPos {aliases[name]} {coordinates};")
    lines.append("} GDEF;")
    add_features(font, "\n".join(lines))


def verify_hairlining(font, path, weights):
    engine = hb.Font(hb.Face(path.read_bytes()))
    cases = ("(a) [b] {c}", "Vec<[T]> [<T>]", ":: <T> ::<Vec<T>>", "${x} $[y] $(z)",
             "map(|| f(x))", "let f = || 1", "|x|  |w|  a | b", "f(x, ...rest)")
    for weight in weights:
        engine.set_variations({"wght": weight})
        for sample in cases:
            active = shape(engine, sample, {})
            plain = shape(engine, sample, {OFF_FEATURE: True})
            assert any(row[0].endswith(".hairline") for row in active), (weight, sample, active)
            assert all(not row[0].endswith(".hairline") for row in plain), (weight, sample, plain)
            if sample != "|x|  |w|  a | b":
                assert [[name.removesuffix(".hairline"), *rest] for name, *rest in active] == plain, (
                    weight, sample, active, plain)
        pipes = [row[0] for row in shape(engine, "|x|  |w|  a | b", {}) if row[0].startswith("bar")]
        assert pipes == [BAR_OPEN + ".hairline", BAR_CLOSE + ".hairline"] * 2 + ["bar"], pipes
        gs = font.getGlyphSet(location={"wght": weight})
        for name in ("bracketleft", "bracketright", BAR_OPEN, BAR_CLOSE):
            left, bottom, right, top = raw_outline(gs, name + ".rail").bounds
            assert abs(right - left - HAIRLINE) <= 1 and bottom < top, (weight, name)
        assert SCOPE + ".hairline" not in gs
    return {"default": True, "opt_out": OFF_FEATURE, "stroke": HAIRLINE, "weights": weights}
