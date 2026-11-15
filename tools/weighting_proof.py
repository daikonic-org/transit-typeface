"""Compare every named weight/profile with the corrected weighting recommendation."""

from io import BytesIO
from pathlib import Path
import html
import json
import shutil

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import uharfbuzz as hb

from audit import shape, spans
from specimens import DATA, Panel, ROOT

OUT = ROOT / ".build/weighting-review"
STUDIES = ROOT / ".build/weight-studies"
VARIANTS = [
    ("current", "CURRENT"),
    ("1", "REGULAR-BASED / 100%"),
    ("0.72", "REGULAR-BASED / 72%"),
]
STYLES = {300: "Light", 350: "Book", 400: "Regular", 500: "Medium", 600: "SemiBold"}


def load(key, weight, optical, variant):
    if variant == "current":
        return instantiateVariableFont(
            TTFont(
                ROOT
                / DATA["families"][key].get(
                    "weighting_baseline", DATA["families"][key]["font"]
                )
            ),
            {"wght": weight, **({"opsz": optical} if optical else {})},
            inplace=False,
        )
    filename = f"{key}-{weight}" + (f"-opsz{optical}" if optical else "") + ".ttf"
    return TTFont(STUDIES / f"approved-regular-ratio-{variant}" / filename)


def bind(panel, font, weight):
    stream = BytesIO()
    font.save(stream)
    shaped = hb.Font(hb.Face(stream.getvalue()))
    shaped.scale = (font["head"].unitsPerEm,) * 2
    panel.instances[weight] = font, shaped


def measure(font):
    h = shape(font, "H")
    x0, y0, x1, y1 = h.bounds
    vertical = spans(h, y0 + (y1 - y0) * 0.25, 1)
    horizontal = spans(h, (x0 + x1) / 2, 0)
    return {
        "H_stem": sum(b - a for a, b in vertical) / len(vertical),
        "H_bar": sum(b - a for a, b in horizontal),
        "o_counter_area": sum(
            c.area for c in shape(font, "o").contours if not c.clockwise
        ),
    }


def proof(name, rows):
    fragments = []
    labels = Panel(name + "-labels", DATA["families"]["sans"])
    labels.text("DAIKONIC TRANSIT / WEIGHTING TRIAL", 26, 33, 23, 400, "#194454")
    labels.text(
        "Same sizes and spacing. Selected glyphs retained. Regular is the unchanged source anchor.",
        26,
        59,
        14,
        400,
        "#194454",
    )
    for column, (_, title) in enumerate(VARIANTS):
        labels.text(title, 26 + 530 * column, 91, 14, 400, "#194454")
    for row, (key, weight, optical) in enumerate(rows):
        top = 116 + row * 174
        cfg = DATA["families"][key]
        label = f'{cfg["title"]} / {STYLES[weight]} {weight}' + (
            f" / opsz {optical}" if optical else ""
        )
        labels.text(label, 26, top, 13, 400, "#194454")
        for column, (variant, _) in enumerate(VARIANTS):
            x = 26 + 530 * column
            font = load(key, weight, optical, variant)
            p = Panel(f"{name}-{row}-{column}", cfg)
            bind(p, font, weight)
            # No width fitting: every column uses exactly the stated sizes.
            p.text("Hno aeo affix", x, top + 49, 43, weight, "#101712")
            p.text(
                "minimum, banana, source -> result", x, top + 77, 14, weight, "#101712"
            )
            p.text(
                "a e s f t 0123456789 :; != <= ===", x, top + 100, 18, weight, "#101712"
            )
            p.elements.append(
                f'<rect x="{x-5}" y="{top+113}" width="510" height="39" fill="#11191D"/>'
            )
            p.text(
                "office, café; 1ilj ->> => ==", x + 5, top + 138, 16, weight, "#EEECD9"
            )
            fragments.append(p.body())
    fragments.insert(0, labels.body())
    height = 128 + 174 * len(rows)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" viewBox="0 0 1600 {height}"><rect width="1600" height="{height}" fill="#EEECD9"/>'
        + "".join(fragments)
        + "</svg>"
    )
    (OUT / f"{name}.svg").write_text(svg)
    return {"name": name, "width": 1600, "height": height}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    recipes = json.loads((ROOT / "recipes/weights.json").read_text())
    measurements, checks = [], []
    pages = [
        proof(
            "Overview",
            [
                ("sans", 350, None),
                ("sans", 600, None),
                ("system", 350, 14),
                ("system", 600, 14),
                ("code", 300, None),
                ("code", 350, None),
            ],
        )
    ]
    for key, recipe in recipes["families"].items():
        for optical in recipe["optical_sizes"]:
            rows = [(key, int(w), optical) for w in recipe["target_H_stems"]]
            name = key.title() + (f"-opsz{optical}" if optical else "")
            pages.append(proof(name, rows))
            for _, weight, _ in rows:
                current = load(key, weight, optical, "current")
                metrics = {}
                for variant, _ in VARIANTS:
                    font = load(key, weight, optical, variant)
                    metrics[variant] = measure(font)
                    assert font["hmtx"].metrics == current["hmtx"].metrics or all(
                        font["hmtx"][n][0] == current["hmtx"][n][0]
                        for n in current.getGlyphOrder()
                    )
                    for table in ("GSUB", "GPOS", "GDEF"):
                        if table in current:
                            assert font[table].compile(font) == current[table].compile(
                                current
                            ), (key, weight, table)
                    if key == "code":
                        for text in (
                            "->",
                            "->>",
                            "=>",
                            "<-",
                            "<<-",
                            "==",
                            "===",
                            "!=",
                            "!==",
                            "<=",
                            ">=",
                            "::",
                        ):
                            stream = BytesIO()
                            font.save(stream)
                            hbfont = hb.Font(hb.Face(stream.getvalue()))
                            buf = hb.Buffer()
                            buf.add_str(text)
                            buf.guess_segment_properties()
                            hb.shape(hbfont, buf, {"calt": True})
                            assert len(buf.glyph_infos) == 1, text
                            assert sum(
                                p.x_advance for p in buf.glyph_positions
                            ) == 600 * len(text), text
                measurements.append(
                    {
                        "family": key,
                        "weight": weight,
                        "opsz": optical,
                        "variants": metrics,
                    }
                )
                checks.append(
                    {
                        "family": key,
                        "weight": weight,
                        "opsz": optical,
                        "metrics_and_layout": "passed",
                    }
                )
    for variant, _ in VARIANTS[1:]:
        dest = OUT / "fonts" / variant
        dest.mkdir(parents=True, exist_ok=True)
        for path in (STUDIES / f"approved-regular-ratio-{variant}").glob("*.ttf"):
            shutil.copy2(path, dest / path.name)
        shutil.copy2(
            STUDIES / f"approved-regular-ratio-{variant}" / "report.json",
            dest / "report.json",
        )
    (OUT / "measurements.json").write_text(json.dumps(measurements, indent=2) + "\n")
    (OUT / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    (OUT / "pages.json").write_text(json.dumps(pages, indent=2) + "\n")
    for filename in (
        "OFL.txt",
        "NOTICE.txt",
        "recipes/weights.json",
        "tools/derive_weights.py",
        "tools/weighting_proof.py",
    ):
        dest = OUT / "recipe" / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / filename, dest)
    (OUT / "README.md").write_text(
        "# Weighting recommendation trial\n\n"
        "Corrected implementation of the supplied PathOps weighting approach. Compare Current, Regular-based100%, and Regular-based72%. "
        "All 23 named weight/optical-size combinations are included per study. Regular400 remains unchanged; the other weights are derived directly from it. "
        "Selected glyphs retain their approved target-weight drawings. Trials have distinct installable Study family names; production fonts were not replaced.\n\n"
        "No extra width stretch or tracking was applied. Counter topology is checked with reduced-offset backoffs; counter area is measured, not held constant. "
        "72% is the pre-height-refit offset ratio, not a guaranteed final crossbar-growth ratio. Fonts passed OTS; fixed cells and retained layout were checked. "
        "These are static trials, not an interpolating VF. The full source inputs and dependencies remain in the transit-typeface repository.\n\n"
        "Use Overview.png/PDF for a quick comparison; individual family/profile sheets cover every named weight.\n"
    )
    links = "".join(
        f'<li><a href="{p["name"]}.svg">{html.escape(p["name"])}</a></li>'
        for p in pages
    )
    (OUT / "index.html").write_text(
        "<!doctype html><title>Transit weighting trial</title><h1>Transit weighting trial</h1><ul>"
        + links
        + "</ul>"
    )
    print(
        f"Generated {len(pages)} proof sheets; {len(checks)} weight/profile combinations checked."
    )


if __name__ == "__main__":
    main()
