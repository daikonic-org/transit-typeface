"""Build Transit Code with sequence-based ligature names and Unicode comparisons."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from fontTools.ttLib import TTFont
import uharfbuzz as hb

from audit import shape_from_glyphs
from code_compact_operators import ARROWS, CELL, COMPARISONS, PAIRS, compact_operator
from code_logic_shortcuts import COMMANDS, glyph_name
from code_weight_width_trial import SOURCES, WEIGHTS, build_static, recalibrate, sanitize
from font_feature_tools import compose, from_paths, master_locations
from syntax_numeral_study import TOKENS

FAMILY = "Daikonic Transit Code Glyph Names Trial"
UNICODE_SYMBOLS = {0x2260: "notequal", 0x2264: "lessequal", 0x2265: "greaterequal"}
SEQUENCES = (
    {name: token for token, name in (ARROWS | COMPARISONS).items()}
    | {name: token for token, (_, name, _) in PAIRS.items()}
    | {f"code.syntax{index:02d}": token for index, token in enumerate(TOKENS)}
    | {glyph_name(command): command for command in COMMANDS}
    | {"code.scope": "::", "code.enclosureBox": "[]", "code.enclosureDiamond": "<>"}
)


def sequence_name(cmap, name):
    for base, token in SEQUENCES.items():
        if name == base or name.startswith(base + "."):
            sequence = "_".join(cmap[ord(char)] for char in token)
            suffix = ".liga" + name[len(base):]
            if len(sequence + suffix) > 63:
                sequence = "uni" + "".join(f"{ord(char):04X}" for char in token)
            return sequence + suffix
    return name


def glyph_names(font):
    cmap = font.getBestCmap()
    order = font.getGlyphOrder()
    names = {name: renamed for name in order if (renamed := sequence_name(cmap, name)) != name}
    new_order = [names.get(name, name) for name in order]
    assert len(set(new_order)) == len(order)
    assert all(len(name) <= 63 for name in names.values())
    return names


def add_unicode_symbols(font):
    for token, symbol in (("<=", "lessequal"), (">=", "greaterequal")):
        glyph = COMPARISONS[token]
        advance = font["hmtx"][glyph][0]
        compose(font, symbol, [(glyph, 1, 1, (CELL - advance) / 2, 0)], CELL)
    _, locations = master_locations(font)
    outlines = []
    for location in locations:
        glyphs = font.getGlyphSet(location=location)
        equal = shape_from_glyphs(glyphs, "equal")
        unequal = shape_from_glyphs(glyphs, COMPARISONS["!="])
        outlines.append(compact_operator(unequal, "!=", loose=True,
                                         width=equal.bounds[2] - equal.bounds[0]))
    from_paths(font, "notequal", locations, outlines, CELL)
    for table in font["cmap"].tables:
        if table.isUnicode() and table.format in (4, 12):
            table.cmap.update(UNICODE_SYMBOLS)
    font["OS/2"].recalcUnicodeRanges(font)


def shape(font, text, features):
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer, features)
    return [(info.codepoint, info.cluster, pos.x_advance, pos.x_offset, pos.y_offset)
            for info, pos in zip(buffer.glyph_infos, buffer.glyph_positions)]


def verify(reference, candidate, rename):
    old, new = map(TTFont, (reference, candidate))
    expected = [rename.get(name, name) for name in old.getGlyphOrder()]
    assert new.getGlyphOrder()[:len(expected)] == expected
    assert all(new.getBestCmap()[cp] == name for cp, name in UNICODE_SYMBOLS.items())
    for table in ("GSUB", "GPOS"):
        assert old.getTableData(table) == new.getTableData(table), table
    old_hb, new_hb = [hb.Font(hb.Face(path.read_bytes())) for path in (reference, candidate)]
    sample = " -> ->> <- <<- => :: == === != !== <= >= || ?. !. .. // ## !p <> [] "
    sample += " parse::<Vec<T>>() &'a " + " ".join(COMMANDS)
    for weight in WEIGHTS:
        for width in (94, 100, 108):
            for engine in (old_hb, new_hb):
                engine.set_variations({"wght": weight, "wdth": width})
            symbols = "≠≤≥"
            run = shape(new_hb, symbols, {})
            assert [new.getGlyphName(gid) for gid, *_ in run] == [
                UNICODE_SYMBOLS[ord(char)] for char in symbols
            ]
            assert all(item[2] == width * 6 for item in run)
            for features in ({}, {"ss02": True, "ss06": True}, {"calt": False, "liga": False}):
                assert shape(old_hb, sample, features) == shape(new_hb, sample, features)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    for directory in ("VF", "TTF", "TTC", "WOFF2"):
        (args.output / directory).mkdir(parents=True, exist_ok=True)
    folder, stem = SOURCES["code"]
    paths = []
    for suffix in ("-VF.ttf", "-Italic-VF.ttf"):
        source = folder / (stem + suffix)
        old = TTFont(source, recalcTimestamp=False)
        recalibrate(old, FAMILY)
        font = TTFont(source, recalcTimestamp=False)
        rename = glyph_names(font)
        add_unicode_symbols(font)
        postscript_name = recalibrate(font, FAMILY)
        # Glyph IDs and layout references stay intact. New names take effect when reopened.
        font["post"].mapping.update(rename)
        path = args.output / "VF" / (postscript_name + ".ttf")
        font.save(path)
        with TemporaryDirectory() as tmp:
            reference = Path(tmp) / source.name
            old.save(reference)
            verify(reference, path, rename)
        sanitize(path)
        paths.append(path)
        stored = TTFont(path, recalcTimestamp=False)
        stored.flavor = "woff2"
        web = args.output / "WOFF2" / (postscript_name + ".woff2")
        stored.save(web)
        sanitize(web)
        print(path, flush=True)
    build_static(paths, args.output, FAMILY.replace(" Trial", " Presets"), WEIGHTS)


if __name__ == "__main__":
    main()
