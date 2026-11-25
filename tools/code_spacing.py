"""Keep the established Code optical spacing and contextual at-sign fitting."""

import uharfbuzz as hb

from check_code_rebuild import shape
from code_at_uniform_study import SCALE
from font_feature_tools import add_features
from italic_returns import raw_outline
from specimens import ROOT


PLACEMENT = ROOT / "trials/2026-11-16-code-hyphen-k/Positioning.fea"


def add_code_spacing(font, cell, install, *, triplet_offsets=None):
    placement = PLACEMENT.read_text()
    if triplet_offsets:
        cmap = font.getBestCmap()
        rules = []
        for text, offset in sorted(triplet_offsets.items()):
            left, middle, right = (cmap[ord(char)] for char in text)
            rules.append(f"pos {left} {middle}' <{offset:d} 0 0 0> {right};")
        placement += "\nfeature calt {\n" + "\n".join(rules) + "\n} calt;\n"
    add_features(font, placement)
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
        for sample in ("ke", "Ke", "KE", "vi", "iv"):
            rows = shape(engine, sample, {})
            assert [row[4] for row in rows] == [18, -18], (sample, rows)
            assert [row[2] for row in rows] == [cell, cell], (sample, rows)
            assert all(row[4] == 0 for row in shape(engine, sample, {"calt": False}))
        for sample in ("@@", "@@@"):
            rows = shape(engine, sample, {})
            assert [(row[0], row[2]) for row in rows] == [("at.compact", cell)] * len(sample)
        assert shape(engine, "x@y", {})[1][0] == "at"
        for sample in ("ff", "tt", "ll"):
            assert shape(engine, sample, {})[0][:3] == ["_".join(sample), 0, 2 * cell]
    return {"optical_placement": True, "repeated_at": True, "paired_stems": True}
