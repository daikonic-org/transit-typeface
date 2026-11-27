"""Build the released lifetime forms from the current Code strokes and diamond."""

from unicodedata import normalize

import pathops
import uharfbuzz as hb

from audit import shape_from_glyphs, spans
from check_code_rebuild import shape
from check_rust_lifetimes import CASES
from code_hairline_study import BORROW_INSET, HAIRLINE, LEADERS, MARKER, lifetime, lifetime_context
from code_hairline_toggle import FEATURE, OFF_FEATURE, default_hairlining, position_lifetime_ampersand
from code_lifetime_hook import marker
from font_feature_tools import add_features, from_paths, label_stylistic_set, master_locations
from syntax_numeral_study import rust_lifetime_rules


def build_lifetimes(font, cell, settings):
    _, locations = master_locations(font)
    masters = [font.getGlyphSet(location=location) for location in locations]
    from_paths(font, MARKER, locations,
               [marker(gs, bottom=settings["lifetime_hook_bottom"]) for gs in masters], cell)
    if not settings.get("delimiter_revision"):
        for name, height in LEADERS.items():
            from_paths(font, name, locations, [lifetime(gs, height) for gs in masters], cell)
    lines, _ = rust_lifetime_rules(font.getBestCmap(), settings["quoted_identifier_limit"])
    add_features(font, "\n".join(lines))


def activate_lifetime_hairlining(font):
    # Run after angle matching so the delimiter rules see the canonical marker.
    _, locations = master_locations(font)
    lifetime_context(font, [font.getGlyphSet(location=loc) for loc in locations], FEATURE, markers=(MARKER,))
    label_stylistic_set(font, FEATURE, "Hairline delimiters and markers")
    default_hairlining(font)
    position_lifetime_ampersand(font, include_hairlines=True)


def verify_lifetimes(font, path, cell, weights):
    engine = hb.Font(hb.Face(path.read_bytes()))
    cases = CASES | {"&'T": 1, "&'á": 1, "&'a\u0301": 1, "&'î": 1}
    for tag in ("GSUB", "GPOS"):
        assert "ss01" not in {item.FeatureTag for item in font[tag].table.FeatureList.FeatureRecord}

    for weight in weights:
        location = {"wght": weight}
        engine.set_variations(location)
        gs = font.getGlyphSet(location=location)
        stem, = spans(shape_from_glyphs(gs, "l"), 400, 1)
        bar, = spans(shape_from_glyphs(gs, MARKER), 400, 0)
        assert abs((stem[1] - stem[0]) - (bar[1] - bar[0])) <= 1, (weight, stem, bar)
        for name in LEADERS:
            ink = shape_from_glyphs(gs, name)
            line, = spans(ink, cell * 1.75, 0)
            assert abs(line[1] - line[0] - HAIRLINE) <= .5, (weight, name, line)
        for text, expected in cases.items():
            for enabled, plain in ((True, False), (True, True), (False, False)):
                rows = shape(engine, text, {"calt": enabled, OFF_FEATURE: plain})
                positions, cursor = [], 0
                for name, _, advance, _, x, y in rows:
                    positions.append((cursor + x, y))
                    cursor += advance
                assert cursor == cell * len(normalize("NFC", text)), (weight, text, rows)
                marks = [i for i, row in enumerate(rows) if row[0].startswith(MARKER)]
                assert len(marks) == (expected if enabled else 0), (weight, text, rows)
                for i in marks:
                    name, _, advance, *_ = rows[i]
                    assert advance == cell and (name == MARKER if plain else name in LEADERS)
                    if i and rows[i - 1][0] == "ampersand":
                        assert rows[i - 1][4] == BORROW_INSET, (weight, text, rows)
                    marker_ink = shape_from_glyphs(gs, name).transform(translateX=positions[i][0],
                                                                      translateY=positions[i][1])
                    for neighbor in (i - 1, i + 1):
                        if 0 <= neighbor < len(rows):
                            other = shape_from_glyphs(gs, rows[neighbor][0])
                            if len(other):
                                other = other.transform(translateX=positions[neighbor][0],
                                                        translateY=positions[neighbor][1])
                                assert abs(pathops.op(marker_ink, other, pathops.PathOp.INTERSECTION).area) < 1, (
                                    weight, text, name, rows[neighbor][0],
                                )
        assert shape(engine, "a & b", {}) == shape(engine, "a & b", {"calt": False})
        assert shape(engine, "<'a'>", {})[-1][0] == "greater"
        assert shape(engine, "<'a>", {OFF_FEATURE: True})[-1][0] == "greater.generic"
    return {"contexts": len(cases), "weights": weights, "marker_advance": cell,
            "hairline_thickness": HAIRLINE, "hairline_opt_out": OFF_FEATURE, "borrow_offset": BORROW_INSET}
