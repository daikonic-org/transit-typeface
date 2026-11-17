"""Compare Code i/c with real reference fonts and an optical i construction."""

from copy import deepcopy
from io import BytesIO
from pathlib import Path
import argparse
import base64
import csv
import hashlib
import json
import html

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import pathops
import uharfbuzz as hb
from fontTools.designspaceLib import (
    DesignSpaceDocument,
    AxisDescriptor,
    SourceDescriptor,
)
from fontTools.varLib import build
import ots
import subprocess
import tempfile

from adopt_weighting import ROOT, instance
from audit import Samples, shape, spans
from derive_weights import install
from compatibility import compatible_masters
from hook_ligature_study import rect, op
from specimens import DATA, Panel

OUT = ROOT / ".build/code-balance"
CONSTRUCTION = "flat"
EXTENSION = 40
SHAFT_SHIFT = 0
REFERENCES = {
    "JetBrains Mono 400": Path(
        "/Users/pmouli/GitHub.nosync/daikonic-transit-code/comparisons/glyph-dimensions/references/JetBrainsMono-wght.ttf"
    ),
    "Source Code Pro 400": Path(
        "/Users/pmouli/Library/Fonts/SourceCodePro-VariableFont_wght.ttf"
    ),
    "Menlo Regular": Path("/System/Library/Fonts/Menlo.ttc"),
}


def load(path, weight=400):
    font = TTFont(path, fontNumber=0)
    if "fvar" in font:
        font = instantiateVariableFont(font, {"wght": weight}, inplace=False)
    return font


def proposed_i(font, shift=24, shaft_shift=None):
    if CONSTRUCTION == "right-base":
        glyph = font["glyf"]["i"]
        before = list(glyph.coordinates)
        right = glyph.xMax
        body = sorted(shape(font, "i").contours, key=lambda c: c.bounds[1])[0]
        left = body.bounds[0]
        stem = spans(body, 200, 1)[0]
        bar = spans(body, (left + stem[0]) / 2, 0)[0][1]
        indices = [
            j for j, (x, y) in enumerate(glyph.coordinates) if x == right and y <= bar
        ]
        assert len(indices) >= 2
        for j in indices:
            x, y = glyph.coordinates[j]
            glyph.coordinates[j] = (x + EXTENSION, y)
        movement = SHAFT_SHIFT if shaft_shift is None else shaft_shift
        if movement:
            edge = right + EXTENSION
            for j, (x, y) in enumerate(glyph.coordinates):
                if y > bar:
                    delta = movement
                elif y == bar:
                    ratio = (
                        (x - left) / (stem[0] - left)
                        if x < stem[0]
                        else (edge - x) / (edge - stem[1]) if x > stem[1] else 1
                    )
                    delta = round(movement * ratio)
                else:
                    continue
                glyph.coordinates[j] = (x + delta, y)
        glyph.recalcBounds(font["glyf"])
        return {
            "right_base_extension": EXTENSION,
            "changed_point_indices": indices,
            "shaft_shift": movement,
            "point_shifts": {
                j: p[0] - q[0]
                for j, (p, q) in enumerate(zip(glyph.coordinates, before))
                if p != q
            },
            "bar_thickness": bar,
            "top_and_dot": (
                "translated with shaft; shape retained"
                if movement
                else "exactly retained"
            ),
        }
    return flat_i(font, shift)


def flat_i(font, shift=24):
    old = shape(font, "i")
    contours = sorted(old.contours, key=lambda c: c.bounds[1])
    body, dot = contours
    left, bottom, right, top = body.bounds
    stem = spans(body, 200, 1)[0]
    bar = spans(body, (left + stem[0]) / 2, 0)[0][1]
    revised = op(
        op(
            rect(left, bottom, right, bar),
            rect(stem[0] + shift, bar, stem[1] + shift, top),
        ),
        rect(left, top - bar, stem[1] + shift, top),
    )
    revised = op(revised, dot.transform(1, 0, 0, 1, shift, 0))
    install(font, "i", revised)
    return {
        "shaft_shift": shift,
        "stem_width": stem[1] - stem[0],
        "bar_thickness": bar,
        "body_top": top,
    }


def metrics(font, char):
    name = font.getBestCmap()[ord(char)]
    p = shape(font, name)
    cell = font["hmtx"][name][0]
    pen = Samples()
    p.draw(pen)
    area = sx = 0
    for (x, y), (xx, yy) in pen.lines:
        cross = x * yy - xx * y
        area += cross
        sx += (x + xx) * cross
    centroid = sx / (3 * area)
    record = {
        "glyph": char,
        "cell": cell,
        "upm": font["head"].unitsPerEm,
        "ink_width_percent": round((p.bounds[2] - p.bounds[0]) / cell * 100, 2),
        "left_margin_percent": round(p.bounds[0] / cell * 100, 2),
        "right_margin_percent": round((cell - p.bounds[2]) / cell * 100, 2),
        "ink_centroid_percent": round(centroid / cell * 100, 2),
        "bounds": p.bounds,
    }
    if char == "i":
        body = sorted(p.contours, key=lambda c: c.bounds[1])[0]
        bottom, top = body.bounds[1], body.bounds[3]
        shaft = spans(body, bottom + (top - bottom) * 0.4, 1)[0]
        base = spans(body, bottom + (top - bottom) * 0.03, 1)[0]
        record["base_geometry"] = {
            "shaft": shaft,
            "base": base,
            "base_center": sum(base) / 2,
            "shaft_center": sum(shaft) / 2,
            "overhang_left": shaft[0] - base[0],
            "overhang_right": base[1] - shaft[1],
        }
    return record


def bind(panel, font):
    stream = BytesIO()
    font.save(stream)
    h = hb.Font(hb.Face(stream.getvalue()))
    h.scale = (font["head"].unitsPerEm,) * 2
    panel.instances[400] = (font, h)


def proof(fonts):
    cfg = DATA["families"]["code"]
    body = []
    labels = Panel("labels", cfg)
    labels.text("TRANSIT CODE / i AND c OPTICAL REVIEW", 25, 35, 23, 400, "#194454")
    labels.text(
        "Equal character-cell size. Actual outlines; Book 350 vs reference Regular 400. References differ in stroke weight.",
        25,
        62,
        12,
        400,
        "#194454",
    )
    body.append(labels.body())
    for row, (name, font) in enumerate(fonts.items()):
        y = 95 + row * 190
        p = Panel(name, cfg)
        bind(p, font)
        cell = font["hmtx"][font.getBestCmap()[ord("i")]][0]
        upm = font["head"].unitsPerEm
        scale = 600 * upm / (1000 * cell)
        p.text(name, 25, y + 12, 14 * scale, 400, "#194454")
        # Faint cell edges and center lines locate optical placement.
        for index in range(8):
            x = 25 + index * 66
            p.elements.append(
                f'<path d="M{x} {y+25}v100 M{x+33} {y+25}v100" stroke="#D8D5C2" stroke-width=".6"/>'
            )
        p.text("i c o n", 25, y + 112, 110 * scale, 400, "#101712")
        p.text(
            "iiii iii  cccc ccc  icici  minimum",
            590,
            y + 50,
            24 * scale,
            400,
            "#101712",
        )
        p.text("const circuit = items[index];", 590, y + 87, 24 * scale, 400, "#101712")
        for size, baseline in ((13, y + 139), (14, y + 165)):
            p.text(
                "civic clinic ionic choice  |  if (isCurrent) { collect(items); }",
                25,
                baseline,
                size * scale,
                400,
                "#101712",
            )
        body.append(p.body())
    height = 105 + len(fonts) * 190
    (OUT / "Comparison.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}"><rect width="1200" height="{height}" fill="#EEECD9"/>'
        + "".join(body)
        + "</svg>"
    )


def browser_proof(
    fonts,
    samples=None,
    title="Code i/c review — actual browser text at 13, 14 and 16px",
):
    samples = samples or [
        (13, "const circuit = items[index]; if (isCurrent) { collect(items); }"),
        (14, "civic clinic ionic choice | minimum iii ccc icici"),
        (16, "if (isCurrent) { collect(items); }"),
    ]
    css = []
    rows = []
    for index, (name, font) in enumerate(fonts.items()):
        copy = deepcopy(font)
        copy.flavor = "woff2"
        stream = BytesIO()
        copy.save(stream)
        encoded = base64.b64encode(stream.getvalue()).decode()
        css.append(
            f'@font-face{{font-family:Review{index};src:url(data:font/woff2;base64,{encoded}) format("woff2");font-weight:400}}'
        )
        rows.append(
            f'<section><h2>{name}</h2><div class="sample" style="font-family:Review{index}">'
            + "".join(
                f'<div style="font-size:{size}px">{html.escape(text)}</div>'
                for size, text in samples
            )
            + "</div></section>"
        )
    (OUT / "Browser.html").write_text(
        '<!doctype html><meta charset="utf-8"><style>'
        + "".join(css)
        + 'body{margin:0;padding:24px;background:#EEECD9;color:#101712;font:14px system-ui;width:1152px}h1{font-size:22px}h2{font-size:15px;color:#194454}section{margin:24px 0;padding-bottom:12px;border-bottom:1px solid #ccc}.sample{font-synthesis:none;font-feature-settings:"calt" 1;line-height:2;white-space:pre}#loaded{font-size:11px}</style>'
        + "<h1>"
        + html.escape(title)
        + "</h1>"
        + "".join(rows)
        + '<p id="loaded">Loading fonts…</p><script>document.fonts.ready.then(()=>{document.getElementById("loaded").textContent="Font loading: "+'
        "JSON.stringify(["
        + ",".join(f'document.fonts.check("14px Review{i}")' for i in range(len(fonts)))
        + "]);document.body.dataset.fontStatus=JSON.stringify(Array.from(document.fonts).map(f=>[f.family,f.status]));});</script>"
    )


def study_identity():
    if CONSTRUCTION == "right-base":
        return (
            (
                "DaikonicTransitCodeRightBaseShaftStudy",
                "Daikonic Transit Code Right Base Shaft Study",
            )
            if SHAFT_SHIFT
            else (
                "DaikonicTransitCodeRightBaseStudy",
                "Daikonic Transit Code Right Base Study",
            )
        )
    return "DaikonicTransitCodeBalanceStudy", "Daikonic Transit Code Balance Study"


def trial_fonts():
    cfg = DATA["families"]["code"]
    baseline = TTFont(ROOT / cfg["font"])
    if CONSTRUCTION == "right-base":
        # Fully explicit original deltas remain valid: only default right-edge
        # points move by a constant amount, with no contour reconstruction.
        assert all(
            all(p is not None for p in v.coordinates)
            for v in baseline["gvar"].variations["i"]
        )
        details = proposed_i(baseline)
        changed = details["point_shifts"]
    else:
        compatible_flat_i(baseline)
        changed = None
    stem, family = study_identity()
    for record in baseline["name"].names:
        record.string = (
            record.toUnicode()
            .replace("Daikonic Transit Code", family)
            .replace("DaikonicTransitCode", stem)
            .encode(record.getEncoding())
        )
    baseline["head"].fontRevision = 0.001
    for record in baseline["name"].names:
        if record.nameID == 5:
            record.string = "Version 0.001; i optical study".encode(
                record.getEncoding()
            )
    paths = [OUT / (stem + "-VF.ttf")]
    baseline.save(paths[0])
    for w in (300, 350, 400):
        f = instance(paths[0], w, None)
        style = {300: "Light", 350: "Book", 400: "Regular"}[w]
        names = {
            1: family if w == 400 else family + " " + style,
            2: "Regular",
            3: "0.001;" + stem + "-" + style,
            4: family + " " + style,
            6: stem + "-" + style,
            16: family,
            17: style,
        }
        for record in f["name"].names:
            if record.nameID in names:
                record.string = names[record.nameID].encode(record.getEncoding())
        path = OUT / (stem + "-" + style + ".ttf")
        f.save(path)
        paths.append(path)
    for path in paths:
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [ots.OTS_SANITIZE, str(path), str(Path(temporary) / "checked.ttf")],
                capture_output=True,
            )
            assert result.returncode == 0, result.stderr.decode()
    for weight in range(300, 401, 10):
        f = instance(paths[0], weight, None)
        assert f["hmtx"]["i"][0] == 600
        assert len(list(shape(f, "i").contours)) == 2
        if changed:
            old = instance(ROOT / cfg["font"], weight, None)
            for j, (p, q) in enumerate(
                zip(old["glyf"]["i"].coordinates, f["glyf"]["i"].coordinates)
            ):
                assert q == (p[0] + changed.get(j, 0), p[1]), (
                    weight,
                    j,
                    p,
                    q,
                )
    print(
        "Sanitized study VF and three static fonts; checked 11 interpolation positions"
    )


def compatible_flat_i(baseline):
    cfg = DATA["families"]["code"]
    masters = OUT / "masters"
    masters.mkdir(exist_ok=True)
    fonts = [instance(ROOT / cfg["font"], w, None) for w in (300, 350, 400)]
    for f in fonts:
        proposed_i(f)
    glyphs, missing = compatible_masters([shape(f, "i") for f in fonts])
    assert missing == 0
    design = DesignSpaceDocument()
    axis = AxisDescriptor()
    axis.name = "Weight"
    axis.tag = "wght"
    axis.minimum = 300
    axis.default = 350
    axis.maximum = 400
    design.addAxis(axis)
    for w, f, g in zip((300, 350, 400), fonts, glyphs):
        f["glyf"]["i"] = g
        g.recalcBounds(f["glyf"])
        f["hmtx"]["i"] = (600, g.xMin)
        path = masters / f"Master-{w}.ttf"
        f.save(path)
        source = SourceDescriptor()
        source.path = str(path)
        source.name = str(w)
        source.location = {"Weight": w}
        design.addSource(source)
    design.write(masters / "CodeBalance.designspace")
    candidate, _, _ = build(masters / "CodeBalance.designspace", optimize=False)
    baseline["glyf"]["i"] = deepcopy(candidate["glyf"]["i"])
    baseline["gvar"].variations["i"] = deepcopy(candidate["gvar"].variations["i"])


def weight_proof():
    cfg = DATA["families"]["code"]
    parts = []
    labels = Panel("weight-labels", cfg)
    labels.text(
        (
            f"CODE / BASE +{EXTENSION} / SHAFT +{SHAFT_SHIFT} ACROSS WEIGHTS"
            if CONSTRUCTION == "right-base"
            else "CODE / CURRENT AND PROPOSED i ACROSS WEIGHTS"
        ),
        25,
        35,
        20,
        400,
        "#194454",
    )
    labels.text("CURRENT 1.017", 25, 70, 13, 400, "#194454")
    labels.text("PROPOSED i / c UNCHANGED", 625, 70, 13, 400, "#194454")
    parts.append(labels.body())
    for row, w in enumerate((300, 350, 400)):
        y = 100 + row * 220
        for col, path in enumerate(
            (
                ROOT / cfg["font"],
                OUT / ((study_identity()[0]) + "-VF.ttf"),
            )
        ):
            p = Panel(f"weight-{w}-{col}", cfg)
            bind(p, instance(path, w, None))
            x = 25 + 600 * col
            p.text(str(w), x, y + 12, 12, 400, "#194454")
            p.text("i l I 1 | ! j c e o", x, y + 65, 42, 400, "#101712")
            p.text("civic clinic ionic choice minimum", x, y + 100, 14, 400, "#101712")
            p.elements.append(
                f'<rect x="{600*col}" y="{y+118}" width="600" height="78" fill="#101712"/>'
            )
            p.text("if (isCurrent) { collect(items); }", x, y + 145, 14, 400, "#EEECD9")
            p.text("civic clinic ionic choice minimum", x, y + 177, 13, 400, "#EEECD9")
            parts.append(p.body())
    (OUT / "Weights.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="760" viewBox="0 0 1200 760"><rect width="1200" height="760" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )


def main():
    global OUT, CONSTRUCTION, EXTENSION, SHAFT_SHIFT
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--construction", choices=("flat", "right-base"), default="flat"
    )
    parser.add_argument("--extension", type=int, default=40)
    parser.add_argument("--shaft-shift", type=int, default=0)
    for key in ("jetbrains", "source-code", "menlo"):
        parser.add_argument("--" + key, type=Path)
    args = parser.parse_args()
    CONSTRUCTION, EXTENSION = args.construction, args.extension
    SHAFT_SHIFT = args.shaft_shift
    if CONSTRUCTION == "right-base":
        OUT = ROOT / (
            ".build/code-right-base-shaft" if SHAFT_SHIFT else ".build/code-right-base"
        )
    for key, label in [
        ("jetbrains", "JetBrains Mono 400"),
        ("source_code", "Source Code Pro 400"),
        ("menlo", "Menlo Regular"),
    ]:
        if getattr(args, key):
            REFERENCES[label] = getattr(args, key)
    OUT.mkdir(exist_ok=True)
    cfg = DATA["families"]["code"]
    current = instance(ROOT / cfg["font"], 350, None)
    candidate = deepcopy(current)
    details = proposed_i(candidate)
    fonts = {
        "Transit Code / current Book": current,
    }
    if CONSTRUCTION == "right-base":
        previous = deepcopy(current)
        if SHAFT_SHIFT:
            proposed_i(previous, shaft_shift=0)
            fonts["Right base +40 / shaft unchanged"] = previous
        else:
            flat_i(previous)
            fonts["Previous flat-top trial"] = previous
    fonts[
        (
            f"Transit Code / base +{EXTENSION} / shaft +{SHAFT_SHIFT}"
            if CONSTRUCTION == "right-base"
            else "Transit Code / proposed i"
        )
    ] = candidate
    provenance = []
    for name, path in REFERENCES.items():
        if CONSTRUCTION == "right-base" and name != "JetBrains Mono 400":
            continue
        f = load(path)
        fonts[name] = f
        provenance.append(
            {
                "label": name,
                "path": str(path),
                "version": f["name"].getDebugName(5),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    rows = [
        {"font": label, **metrics(font, char)}
        for label, font in fonts.items()
        for char in "icon"
    ]
    with (OUT / "metrics.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (OUT / "report.json").write_text(
        json.dumps(
            {"references": provenance, "i_construction": details, "metrics": rows},
            indent=2,
        )
        + "\n"
    )
    proof(fonts)
    browser_proof(fonts)
    trial_fonts()
    weight_proof()
    print("Generated actual-font comparison and measured i/c controls")


if __name__ == "__main__":
    main()
