"""Measure current typefaces; do not change their drawings or metadata."""

from io import BytesIO
from pathlib import Path
import json
import math
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import pathops
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "family.json").read_text())


class Samples(BasePen):
    def __init__(self):
        super().__init__(None)
        self.lines = []
        self.last = self.start = None

    def _moveTo(self, point):
        self.last = self.start = point

    def _lineTo(self, point):
        self.lines.append((self.last, point))
        self.last = point

    def _qCurveToOne(self, control, end):
        start = self.last
        for step in range(1, 65):
            t = step / 64
            q = 1 - t
            self._lineTo(
                tuple(
                    q * q * start[i] + 2 * q * t * control[i] + t * t * end[i]
                    for i in [0, 1]
                )
            )

    def _curveToOne(self, first, second, end):
        start = self.last
        for step in range(1, 65):
            t = step / 64
            q = 1 - t
            self._lineTo(
                tuple(
                    q**3 * start[i]
                    + 3 * q * q * t * first[i]
                    + 3 * q * t * t * second[i]
                    + t**3 * end[i]
                    for i in [0, 1]
                )
            )

    def _closePath(self):
        if self.last != self.start:
            self._lineTo(self.start)


def shape(font, name):
    p = pathops.Path()
    glyphs = font.getGlyphSet()
    glyphs[name].draw(p.getPen(glyphs))
    return pathops.simplify(p, fix_winding=True, clockwise=True)


def spans(p, value, axis):
    pen = Samples()
    p.draw(pen)
    crossings = []
    for a, b in pen.lines:
        if (a[axis] <= value < b[axis]) or (b[axis] <= value < a[axis]):
            crossings.append(
                a[1 - axis]
                + (value - a[axis]) * (b[1 - axis] - a[1 - axis]) / (b[axis] - a[axis])
            )
    crossings.sort()
    return list(zip(crossings[::2], crossings[1::2]))


def run(font, text):
    stream = BytesIO()
    font.save(stream)
    f = hb.Font(hb.Face(stream.getvalue()))
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(f, buf)
    return [
        {
            "glyph": font.getGlyphName(g.codepoint),
            "advance": p.x_advance,
            "offset": [p.x_offset, p.y_offset],
        }
        for g, p in zip(buf.glyph_infos, buf.glyph_positions)
    ]


def main():
    report = {}
    for key, cfg in DATA["families"].items():
        original = TTFont(ROOT / cfg["font"])
        records = []
        for weight in [300, 350, 400] if key == "code" else [300, 350, 400, 500, 600]:
            font = instantiateVariableFont(
                TTFont(ROOT / cfg["font"]),
                {"wght": weight, **({"opsz": 14} if key == "system" else {})},
                inplace=False,
            )
            h = shape(font, "H")
            x0, y0, x1, y1 = h.bounds
            stems = spans(h, y0 + (y1 - y0) * 0.25, 1)
            crossbars = spans(h, (x0 + x1) / 2, 0)
            records.append(
                {
                    "weight": weight,
                    "H_vertical_stem_mean": round(
                        sum(b - a for a, b in stems) / len(stems), 3
                    ),
                    "H_horizontal_bar_mean": round(
                        sum(b - a for a, b in crossbars) / len(crossbars), 3
                    ),
                    "counters": {
                        name: {
                            "count": sum(
                                not c.clockwise for c in shape(font, name).contours
                            ),
                            "area": round(
                                sum(
                                    c.area
                                    for c in shape(font, name).contours
                                    if not c.clockwise
                                ),
                                2,
                            ),
                        }
                        for name in ["a", "e", "o"]
                    },
                }
            )
        gdef = original["GDEF"].table if "GDEF" in original else None
        caret = getattr(gdef, "LigCaretList", None)
        report[key] = {
            "version": cfg["version"],
            "upm": original["head"].unitsPerEm,
            "axes": {
                a.axisTag: [a.minValue, a.defaultValue, a.maxValue]
                for a in original["fvar"].axes
            },
            "isFixedPitch": original["post"].isFixedPitch,
            "panoseFamilyType": original["OS/2"].panose.bFamilyType,
            "panoseProportion": original["OS/2"].panose.bProportion,
            "averageWidth": original["OS/2"].xAvgCharWidth,
            "hasGPOS": "GPOS" in original,
            "GPOSLookupTypes": (
                [l.LookupType for l in original["GPOS"].table.LookupList.Lookup]
                if "GPOS" in original
                else []
            ),
            "caretPositions": (
                {
                    name: [v.Coordinate for v in glyph.CaretValue if v.Format == 1]
                    for name, glyph in zip(caret.Coverage.glyphs, caret.LigGlyph)
                }
                if caret
                else {}
            ),
            "zeroContourCount": original["glyf"]["zero"].numberOfContours,
            "OContourCount": original["glyf"]["O"].numberOfContours,
            "measurements": records,
            "combiningExamples": {
                text: run(
                    instantiateVariableFont(
                        TTFont(ROOT / cfg["font"]),
                        {
                            "wght": cfg["display"],
                            **({"opsz": 14} if key == "system" else {}),
                        },
                    ),
                    text,
                )
                for text in ["a\u0301", "q\u0301"]
            },
        }
    (ROOT / "docs/measurements.json").write_text(json.dumps(report, indent=2) + "\n")
    table = [
        "# Measured stroke and counter checks",
        "",
        "Values are font units on the actual 1000-UPM exports. H stems are sampled at25% of cap height; its crossbar is sampled at the horizontal center. Curved counter areas are geometric font-unit squares. These are measurements, not perceptual readability scores.",
        "",
        "| Family | Weight | H vertical | H crossbar | o counter area |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for key, record in report.items():
        for row in record["measurements"]:
            table.append(
                f"| {key.title()} | {row['weight']} | {row['H_vertical_stem_mean']} | {row['H_horizontal_bar_mean']} | {row['counters']['o']['area']} |"
            )
    (ROOT / "docs/measurements.md").write_text("\n".join(table) + "\n")
    print("\n".join(table))
    print("Code combining examples:", report["code"]["combiningExamples"])


if __name__ == "__main__":
    main()
