"""Build Code class spacing and contextual at-sign fitting."""

import uharfbuzz as hb

from check_code_rebuild import shape
from code_at_uniform_study import SCALE
from font_feature_tools import add_features
from italic_returns import raw_outline


def add_code_spacing(font, cell, install, *, triplet_offsets=None, edge_spacing=None):
    locked = triplet_offsets or {}
    if locked or edge_spacing:
        cmap = font.getBestCmap()
        placement = ["languagesystem DFLT dflt;", "languagesystem latn dflt;"]

        def names(text):
            return [cmap[ord(char)] for char in text]

        rules = []
        for text, offset in sorted(locked.items()):
            left, middle, right = names(text)
            rules.append(f"pos {left} {middle}' <{offset:d} 0 0 0> {right};")
        if edge_spacing:
            glyph_order = set(font.getGlyphOrder())
            for label, members in edge_spacing["classes"].items():
                if isinstance(members, str):
                    glyphs = names(members)
                else:
                    bases = names(members["characters"])
                    variants = [base + suffix for base in bases for suffix in members["suffixes"]]
                    glyphs = bases + [variant for variant in variants if variant in glyph_order]
                placement.append(f"@{label} = [{' '.join(glyphs)}];")
            rules.append("lookup EdgeClassSpacing {")
            # Preserve the facing edges of the explicitly approved triplets.
            for text in sorted(locked):
                glyphs = names(text)
                for index in range(len(glyphs)):
                    marked = [name + "'" if i == index else name for i, name in enumerate(glyphs)]
                    rules.append("ignore pos " + " ".join(marked) + ";")
            for left, middle, right, offset in edge_spacing["rules"]:
                rules.append(f"pos @{left} @{middle}' <{offset:d} 0 0 0> @{right};")
            rules.append("} EdgeClassSpacing;")
        placement.extend(["feature calt {", *rules, "} calt;"])
        add_features(font, "\n".join(placement))
    ratio = 1 / SCALE
    _, low, _, high = raw_outline(font.getGlyphSet(), "at").bounds
    install("at.compact", [("at", ratio, ratio, (1 - ratio) * cell / 2,
                            (1 - ratio) * (low + high) / 2)], cell)
    add_features(font, """
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        @AtNeighbor = [at at.compact];
        feature calt {
            sub at' @AtNeighbor by at.compact;
            sub @AtNeighbor at' by at.compact;
        } calt;
    """)


def verify_code_spacing(path, cell):
    engine = hb.Font(hb.Face(path.read_bytes()))
    for weight in range(350, 501, 25):
        engine.set_variations({"wght": weight})
        for sample in ("ke", "Ke", "KE", "vi", "lv", "yi", "ly", "ki", "lk", "Kl", "iK", "/i", "l/"):
            rows = shape(engine, sample, {})
            assert [row[4] for row in rows] == [0, 0], (sample, rows)
            assert [row[2] for row in rows] == [cell, cell], (sample, rows)
        for sample in ("@@", "@@@"):
            rows = shape(engine, sample, {})
            assert [(row[0], row[2]) for row in rows] == [("at.compact", cell)] * len(sample)
        assert shape(engine, "x@y", {})[1][0] == "at"
        for sample in ("ff", "tt", "ll"):
            assert shape(engine, sample, {})[0][:3] == ["_".join(sample), 0, 2 * cell]
    return {"legacy_pair_overrides_removed": True, "repeated_at": True, "paired_stems": True}
