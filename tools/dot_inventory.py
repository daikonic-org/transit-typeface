"""Read-only inventory of isolated solid dots in Metropolitan Line and Transit Sans."""

from pathlib import Path
from collections import defaultdict
import csv
import hashlib
import json
import math
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.pens.svgPathPen import SVGPathPen
from specimens import ROOT, DATA, Panel
from code_balance_study import bind
from adopt_weighting import instance
from audit import shape_from_glyphs

OUT = ROOT / "trials/2026-11-17-dot-inventory"
UPSTREAM = ROOT / "upstream/MetropolitanLine-Regular.ttf"
SANS = ROOT / "fonts/sans/VF/DaikonicTransitSans-VF.ttf"
CORE = [
    ("i", "i"),
    ("j", "j"),
    ("period", "period"),
    ("question", "?"),
    ("exclam", "!"),
    ("periodcentered", "middle dot"),
    ("divide", "divide"),
    ("ellipsis", "ellipsis"),
    ("uni0307", "dot above"),
    ("uni0308", "diaeresis"),
    ("bullet", "bullet"),
]


class Samples(BasePen):
    def __init__(self):
        super().__init__(None)
        self.points = []

    def _moveTo(self, p):
        self.points.append(p)

    def _lineTo(self, p):
        self.points.append(p)

    def _curveToOne(self, a, b, c):
        old = self._getCurrentPoint()
        for i in range(1, 17):
            t = i / 16
            s = 1 - t
            self.points.append(
                tuple(
                    s**3 * old[k]
                    + 3 * s * s * t * a[k]
                    + 3 * s * t * t * b[k]
                    + t**3 * c[k]
                    for k in [0, 1]
                )
            )

    def _qCurveToOne(self, a, b):
        old = self._getCurrentPoint()
        for i in range(1, 17):
            t = i / 16
            s = 1 - t
            self.points.append(
                tuple(s * s * old[k] + 2 * s * t * a[k] + t * t * b[k] for k in [0, 1])
            )

    def _closePath(self):
        pass


def dots(glyphs, name):
    p = shape_from_glyphs(glyphs, name)
    contours = list(p.contours)
    output = []
    for contour in contours:
        if not contour.clockwise:
            continue
        l, b, r, t = contour.bounds
        w = r - l
        h = t - b
        if not (20 <= w <= 350 and 20 <= h <= 350 and 0.6 <= w / h <= 1.65):
            continue
        if any(
            not c.clockwise
            and l <= c.bounds[0] <= c.bounds[2] <= r
            and b <= c.bounds[1] <= c.bounds[3] <= t
            for c in contours
        ):
            continue
        sample = Samples()
        contour.draw(sample)
        normalized = [
            ((x - (l + r) / 2) / (w / 2), (y - (b + t) / 2) / (h / 2))
            for x, y in sample.points
        ]
        errors = {
            "diamond": sum(abs(abs(x) + abs(y) - 1) for x, y in normalized)
            / len(normalized),
            "square": sum(abs(max(abs(x), abs(y)) - 1) for x, y in normalized)
            / len(normalized),
            "round": sum(abs(math.hypot(x, y) - 1) for x, y in normalized)
            / len(normalized),
        }
        area = abs(contour.area)
        # Corners alone can fit both a diamond and square bounding box: use ink
        # occupancy to disambiguate, including odd-unit asymmetric diamonds.
        occupancy = {"diamond": 0.5, "square": 1, "round": math.pi / 4}
        candidates = {
            form: error
            for form, error in errors.items()
            if abs(area / (w * h) - occupancy[form]) <= 0.06
        }
        if not candidates:
            continue
        form = min(candidates, key=candidates.get)
        if errors[form] > 0.035:
            continue
        output.append(
            (
                contour,
                {
                    "width": w,
                    "height": h,
                    "ink_area": area,
                    "form": form,
                    "bounds": [l, b, r, t],
                    "boundary_fit_error": errors[form],
                },
            )
        )
    return sorted(
        output, key=lambda value: (value[1]["bounds"][1], value[1]["bounds"][0])
    )


def draw_atlas(atlas, columns, title, filename):
    panel = Panel("labels", DATA["families"]["sans"])
    bind(panel, instance(SANS, 400, None))
    panel.text(title, 25, 30, 23, 400, "#194454")
    panel.text(
        "One dot per usage, at the same scale. Measurements are width x height; original inter-dot spacing is not shown.",
        25,
        58,
        16,
        400,
        "#194454",
    )
    for col, (_, label) in enumerate(columns):
        panel.text(label, 250 + 125 * col, 92, 14, 400, "#194454", align="center")
    elements = [panel.body()]
    for row, (title, found) in enumerate(atlas):
        y = 135 + 145 * row
        label = Panel("row" + str(row), DATA["families"]["sans"])
        bind(label, instance(SANS, 400, None))
        label.text(title, 20, y + 35, 15, 400, "#194454", max_width=165)
        for col, (name, usage) in enumerate(columns):
            items = found.get(name, [])
            cx = 250 + 125 * col
            cy = y + 28
            displayed = items[:1]
            for i, (contour, data) in enumerate(displayed):
                l, b, r, t = data["bounds"]
                pen = SVGPathPen(None)
                contour.draw(pen)
                x = cx + ((i - 0.5) * 50 if len(displayed) == 2 else 0)
                scale = 0.38
                elements.append(
                    f'<path d="{pen.getCommands()}" fill="#101712" transform="translate({x} {cy}) scale({scale} {-scale}) translate({-(l+r)/2} {-(b+t)/2})"/>'
                )
            if items:
                widths = [d["width"] for _, d in items]
                heights = [d["height"] for _, d in items]

                def fmt(v):
                    return str(round(v, 1)).removesuffix(".0")

                text = (
                    fmt(min(widths))
                    + (
                        "–" + fmt(max(widths))
                        if max(widths) - min(widths) > 0.1
                        else ""
                    )
                    + " x "
                    + fmt(max(heights))
                )
                label.text(
                    text, cx, y + 90, 12, 400, "#101712", align="center", max_width=118
                )
                label.text(
                    items[0][1]["form"], cx, y + 113, 11, 400, "#194454", align="center"
                )
        elements.append(label.body())
    width = 260 + 125 * len(columns)
    (OUT / (filename + ".svg")).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="1030"><rect width="{width}" height="1030" fill="#EEECD9"/>'
        + "".join(elements)
        + "</svg>"
    )


def main():
    OUT.mkdir(exist_ok=True)
    sources = [("Metropolitan Line Regular", UPSTREAM, 400, None)] + [
        (f"Transit Sans {label}", SANS, w, {"wght": w})
        for w, label in [
            (300, "Light"),
            (350, "Book"),
            (400, "Regular"),
            (500, "Medium"),
            (600, "SemiBold"),
        ]
    ]
    records = []
    atlas = []
    font_data = []
    for title, path, weight, location in sources:
        font = TTFont(path)
        glyphs = font.getGlyphSet(location=location)
        reverse = defaultdict(list)
        for cp, name in font.getBestCmap().items():
            reverse[name].append(f"U+{cp:04X}")
        found = {}
        for name in font.getGlyphOrder():
            result = dots(glyphs, name)
            if not result:
                continue
            found[name] = result
            for index, (contour, measure) in enumerate(result):
                records.append(
                    {
                        "source": title,
                        "weight": weight,
                        "glyph": name,
                        "dot_index": index,
                        "unicode": " ".join(reverse[name]),
                        **measure,
                    }
                )
        assert all(
            n in found
            for n in [
                "i",
                "j",
                "period",
                "question",
                "exclam",
                "uni0307",
                "uni0308",
                "bullet",
            ]
        ), (title, "missing core dot")
        atlas.append((title, found))
        font_data.append(
            {
                "label": title,
                "file": str(path.relative_to(ROOT)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "upm": font["head"].unitsPerEm,
                "weight": weight,
            }
        )
    assert all(
        n in found
        for n in [
            "i",
            "j",
            "period",
            "question",
            "exclam",
            "uni0307",
            "uni0308",
            "bullet",
        ]
    )
    (OUT / "inventory.json").write_text(
        json.dumps(
            {
                "scope": "isolated solid dots only; attached comma/quote tails, rings and non-dot diamond motifs excluded",
                "units": "font units at1000UPM; ink_area in squaredfontunits",
                "sources": font_data,
                "dots": records,
            },
            indent=2,
        )
        + "\n"
    )
    fields = [
        "source",
        "weight",
        "glyph",
        "dot_index",
        "unicode",
        "form",
        "width",
        "height",
        "ink_area",
    ]
    with (OUT / "All-Dot-Usages.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    core = []
    for title, found in atlas:
        for name, label in CORE + [
            (n, n)
            for n in [
                "colon",
                "semicolon",
                "exclamdown",
                "questiondown",
                "dotaccent",
                "dieresis",
                "uni0307.case",
                "uni0308.case",
            ]
        ]:
            for index, (_, data) in enumerate(found.get(name, [])):
                core.append(
                    {
                        "source": title,
                        "usage": label,
                        "dot_index": index,
                        **{k: data[k] for k in ["form", "width", "height", "ink_area"]},
                    }
                )
    with (OUT / "Core-Dot-Metrics.csv").open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "source",
                "usage",
                "dot_index",
                "form",
                "width",
                "height",
                "ink_area",
            ],
        )
        writer.writeheader()
        writer.writerows(core)
    draw_atlas(
        atlas,
        CORE,
        "DOT INVENTORY / METROPOLITAN LINE AND TRANSIT SANS",
        "Dot-Inventory",
    )
    accents = [
        ("dotaccent", "spacing dot"),
        ("uni0307", "combining dot"),
        ("uni0307.case", "capital dot"),
        ("dieresis", "spacing diaeresis"),
        ("uni0308", "comb. diaeresis"),
        ("uni0308.case", "capital diaeresis"),
        ("idieresis", "i diaeresis"),
        ("Adieresis", "A diaeresis"),
    ]
    draw_atlas(
        atlas, accents, "ACCENT DOTS / SAME SCALE AND WEIGHT COMPARISON", "Accent-Dots"
    )
    codepath = ROOT / "previews/code-1.023/VF/DaikonicTransitCode-VF.ttf"
    codefont = TTFont(codepath)
    code_rows = []
    for weight in [300, 350, 400]:
        glyphs = codefont.getGlyphSet(location={"wght": weight})
        for name, usage in CORE + [("colon", "colon"), ("semicolon", "semicolon")]:
            for index, (_, measure) in enumerate(dots(glyphs, name)):
                code_rows.append(
                    {
                        "source": "Transit Code1.023",
                        "weight": weight,
                        "usage": usage,
                        "dot_index": index,
                        **{
                            k: measure[k]
                            for k in ["form", "width", "height", "ink_area"]
                        },
                    }
                )
    with (OUT / "Code-Crosscheck.csv").open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "source",
                "weight",
                "usage",
                "dot_index",
                "form",
                "width",
                "height",
                "ink_area",
            ],
        )
        writer.writeheader()
        writer.writerows(code_rows)
    summary = [
        "# Solid-dot inventory",
        "",
        "Read-only measurements of the preserved Metropolitan Line Regular and Transit Sans0.109 at Light300, Book350, Regular400, Medium500 and SemiBold600. All figures use1000units per em. No inspected or installed fonts were modified by this inventory.",
        "",
        "Only isolated solid dots are counted: i/j tittles, punctuation dots, bullets, division dots, spacing/combining accent dots, precomposed accented letters and relevant ligatures/localized variants. Comma/quote tails, rings and other diamond motifs are excluded.",
        "",
        "## What the measurements show",
        "",
        "- Metropolitan Line uses a100×97 square for the period, colon, semicolon, middle dot and ellipsis. Its black area is9700squareunits.",
        "- Its i/j and accent diamonds are140×141, about9870squareunits. Question/exclamation dots are141–142units wide, with about10000squareunits of ink. These are nearly the same ink weight despite different bounding boxes.",
        "- Transit Sans Regular turns the period group into140×139 diamonds with9684squareunits of ink: essentially an ink-preserving square-to-diamond conversion. It is not a40% emboldening.",
        "- Transit Sans weights diverge: at SemiBold the i/j dot is180×180, the period172×171, combining dot190×140 and combining diaeresis164×141. The accent glyphs are not all following the same shape/weight function.",
        "- The earlier shared punctuation script preserves area with sqrt(2*area) when converting squares. It explicitly shrinks one-cell Code ellipsis dots to93% of the period diameter; question/exclamation dots are not part of that conversion list.",
        "- Code1.023 Book shows the selective punctuation pattern: period/colon are156×157, while question/exclamation dots are roughly133×130. See the Code crosscheck for exact areas.",
        "",
        "## Palette proposal for discussion",
        "",
        "Use one shared standard-dot master per weight for i/j, punctuation, spacing/combining accents and precomposed dotted forms. Anchor the Regular standard to the original approximately140×141 diamond; keep the bullet as a separate larger role (198×198 at Regular, approximately twice the ink area). Preserve intentional optical placement differences. Decide the weight progression and whether tiny original1–2unit differences should survive before changing fonts.",
        "",
        "Dot-Inventory and Accent-Dots are same-scale PNG/PDF/SVG specimens. All-Dot-Usages.csv and inventory.json contain the full contour-level inventory; Core-Dot-Metrics.csv and Code-Crosscheck.csv summarize common usages.",
    ]
    (OUT / "README.md").write_text("\n".join(summary) + "\n")
    print(
        len(records),
        "dot occurrences inventoried across",
        len(sources),
        "font/weight samples",
    )
    print("Unique glyph usages", len({r["glyph"] for r in records}))


if __name__ == "__main__":
    main()
