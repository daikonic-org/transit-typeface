"""Outlined specimen panels drawn from the distributed variable fonts."""

from io import BytesIO
from pathlib import Path
import hashlib
import html
import json
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "family.json").read_text())


class Panel:
    def __init__(self, key, config):
        self.key, self.config = key, config
        self.instances, self.defs, self.elements = {}, {}, []

    def font(self, weight, tabular=False):
        if weight not in self.instances:
            f = instantiateVariableFont(
                TTFont(ROOT / self.config["font"]),
                {"wght": weight, **({"opsz": 14} if self.key == "system" else {})},
                inplace=False,
            )
            out = BytesIO()
            f.save(out)
            h = hb.Font(hb.Face(out.getvalue()))
            h.scale = (f["head"].unitsPerEm,) * 2
            self.instances[weight] = f, h
        return self.instances[weight]

    def text(
        self,
        value,
        x,
        y,
        size,
        weight,
        fill,
        align="left",
        tabular=False,
        max_width=None,
    ):
        f, hbfont = self.font(weight)
        assert all(ord(c) in f.getBestCmap() for c in value), value
        buffer = hb.Buffer()
        buffer.add_str(value)
        buffer.guess_segment_properties()
        hb.shape(hbfont, buffer, {"calt": True, "liga": True, "tnum": tabular})
        upm = f["head"].unitsPerEm
        width = sum(p.x_advance for p in buffer.glyph_positions) * size / upm
        if max_width and width > max_width:
            size *= max_width / width
            width = max_width
        scale = size / upm
        left = x - (
            width / 2 if align == "center" else width if align == "right" else 0
        )
        uses, cursor = [], 0
        for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
            name = f.getGlyphName(info.codepoint)
            identity = f"{self.key}-{weight}-{info.codepoint}"
            if identity not in self.defs:
                pen = SVGPathPen(f.getGlyphSet())
                f.getGlyphSet()[name].draw(pen)
                self.defs[identity] = f'<path id="{identity}" d="{pen.getCommands()}"/>'
            tx = left + (cursor + position.x_offset) * scale
            ty = y - position.y_offset * scale
            uses.append(
                f'<use href="#{identity}" transform="translate({tx:.5f} {ty:.5f}) scale({scale:.7f} {-scale:.7f})"/>'
            )
            cursor += position.x_advance
        self.elements.append(
            f'<g fill="{fill}" aria-label="{html.escape(value, quote=True)}">'
            + "".join(uses)
            + "</g>"
        )

    def draw(self):
        c = self.config
        ink = "#101712"
        cream = DATA["palette"]["cream"]
        bottom_ink = cream if self.key == "sans" else ink
        digits = "#FFFFFF" if self.key != "system" else "#142C35"
        self.elements += [
            f'<rect width="500" height="370" fill="{cream}"/>',
            f'<rect y="370" width="500" height="250" fill="{c["color"]}"/>',
        ]
        self.text("DAIKONIC", 25, 22, 11, c["display"], ink)
        self.text(c["title"], 24, 74, 44, c["heavy"], ink, max_width=452)
        self.text("Aa  Ee  Qq", 24, 151, 58, c["light"], ink, max_width=293)
        self.text("Aa  Ee  Qq", 24, 229, 58, c["heavy"], ink, max_width=293)
        # Uniform type scaling only: a decorative large glyph, not a stretched outline.
        self.text(
            "a", 487, 254, 300, c["display"], "#FFFFFF", align="right", max_width=166
        )
        self.text(
            "Starship", 250, 339, 67, c["display"], ink, align="center", max_width=452
        )
        self.text(
            "abcdefghijklm",
            250,
            420,
            51,
            c["display"],
            bottom_ink,
            align="center",
            max_width=452,
        )
        self.text(
            "nopqrstuvwxyz",
            250,
            467,
            51,
            c["display"],
            bottom_ink,
            align="center",
            max_width=452,
        )
        self.text(
            "0123456789", 464, 523, 47, c["light"], digits, align="right", max_width=430
        )
        self.text(
            "0123456789",
            464,
            577,
            47,
            c["heavy"],
            digits,
            align="right",
            max_width=430,
            tabular=self.key == "system",
        )
        note = f'LIGHT 300 / {"REGULAR 400" if self.key == "code" else "SEMIBOLD 600"} - V{c["version"]}'
        self.text(note, 250, 606, 9.2, c["display"], bottom_ink, align="center")
        return self

    def body(self):
        return (
            "<defs>" + "".join(self.defs.values()) + "</defs>" + "".join(self.elements)
        )

    def svg(self):
        title = self.config["title"] + " typography panel"
        desc = f'Actual distributed variable font, version {self.config["version"]}. Text converted to editable vector paths. Cream upper panel; brand-color lower panel. System second figure row uses tabular figures.'
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="500" height="620" viewBox="0 0 500 620" role="img"><title>{title}</title><desc>{desc}</desc>{self.body()}</svg>'


def main():
    panels, audit = [], {}
    for key, c in DATA["families"].items():
        panel = Panel(key, c).draw()
        name = "Transit" + key.title()
        (ROOT / "specimens" / (name + ".svg")).write_text(panel.svg())
        panels.append(panel)
        audit[key] = {
            "font": c["font"],
            "sha256": hashlib.sha256((ROOT / c["font"]).read_bytes()).hexdigest(),
            "version": c["version"],
            "weights": [c["light"], c["display"], c["heavy"]],
            "outline_source": "exported variable TTF; HarfBuzz shaping; SVG paths",
            "synthetic_styles": False,
            "background": c["color"],
        }
    board = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="620" viewBox="0 0 1500 620">'
        + "".join(
            f'<g transform="translate({i*500} 0)">{p.body()}</g>'
            for i, p in enumerate(panels)
        )
        + "</svg>"
    )
    (ROOT / "specimens/Transit-Family.svg").write_text(board)
    (ROOT / "specimens/manifest.json").write_text(json.dumps(audit, indent=2) + "\n")
    (ROOT / "specimens/index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Daikonic Transit specimens</title><style>body{margin:0;background:#EEECD9}main{width:1500px;height:620px;display:flex}object{width:500px;height:620px;border:0}</style><main>'
        + "".join(
            f'<object type="image/svg+xml" data="Transit{k.title()}.svg" aria-label="Transit {k}"></object>'
            for k in DATA["families"]
        )
        + "</main>"
    )
    print("Generated three SVG panels and family board")


if __name__ == "__main__":
    main()
