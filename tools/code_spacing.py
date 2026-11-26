"""Keep the established Code optical spacing and contextual at-sign fitting."""

from copy import copy
from io import StringIO
from itertools import product

from fontTools.feaLib import ast
from fontTools.feaLib.parser import Parser
import uharfbuzz as hb

from check_code_rebuild import shape
from code_at_uniform_study import SCALE
from font_feature_tools import add_features
from italic_returns import raw_outline
from specimens import ROOT


PLACEMENT = ROOT / "trials/2026-11-16-code-hyphen-k/Positioning.fea"


def anchor_pair_positions(placement, glyph_order, anchored):
    """Keep the other side of a legacy pair adjustment when one glyph is fixed."""
    document = Parser(StringIO(placement), glyph_order).parse()

    def options(expression, value):
        members = expression.glyphSet()
        fixed = [name for name in members if name in anchored]
        if not fixed or value is None:
            return [(expression, value)]
        remaining = [name for name in members if name not in anchored]
        stationary = copy(value)
        stationary.xPlacement = stationary.yPlacement = 0
        stationary.xPlaDevice = stationary.yPlaDevice = None
        result = [(ast.GlyphClass(fixed), stationary)]
        if remaining:
            result.append((ast.GlyphClass(remaining), value))
        return result

    def visit(block):
        statements = []
        for statement in block.statements:
            if isinstance(statement, ast.PairPosStatement):
                left = options(statement.glyphs1, statement.valuerecord1)
                right = options(statement.glyphs2, statement.valuerecord2)
                statements.extend(ast.PairPosStatement(a, av, b, bv, statement.enumerated)
                                  for (a, av), (b, bv) in product(left, right))
            else:
                if isinstance(statement, ast.Block):
                    visit(statement)
                statements.append(statement)
        block.statements = statements

    visit(document)
    return document.asFea()


def add_code_spacing(font, cell, install, *, triplet_offsets=None, edge_spacing=None, anchors=""):
    placement = PLACEMENT.read_text()
    cmap = font.getBestCmap()
    if anchors:
        placement = anchor_pair_positions(placement, font.getGlyphOrder(),
                                          {cmap[ord(char)] for char in anchors})
    locked = triplet_offsets or {}
    if locked or edge_spacing:
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
                placement += f"\n@{label} = [{' '.join(glyphs)}];"
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


def verify_code_spacing(path, cell, *, anchors=""):
    engine = hb.Font(hb.Face(path.read_bytes()))
    for weight in range(350, 501, 25):
        engine.set_variations({"wght": weight})
        for sample in ("ke", "Ke", "KE", "vi", "iv"):
            rows = shape(engine, sample, {})
            expected = [0 if sample == "ke" or char in anchors else offset
                        for char, offset in zip(sample, (18, -18), strict=True)]
            assert [row[4] for row in rows] == expected, (sample, rows)
            assert [row[2] for row in rows] == [cell, cell], (sample, rows)
            assert all(row[4] == 0 for row in shape(engine, sample, {"calt": False}))
        for sample in ("@@", "@@@"):
            rows = shape(engine, sample, {})
            assert [(row[0], row[2]) for row in rows] == [("at.compact", cell)] * len(sample)
        assert shape(engine, "x@y", {})[1][0] == "at"
        for sample in ("ff", "tt", "ll"):
            assert shape(engine, sample, {})[0][:3] == ["_".join(sample), 0, 2 * cell]
    return {"optical_placement": True, "repeated_at": True, "paired_stems": True}
