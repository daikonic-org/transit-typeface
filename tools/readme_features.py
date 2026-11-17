"""Generate real-font feature comparisons and the matching README tables."""

from copy import deepcopy
from io import BytesIO
from pathlib import Path
import hashlib
import html
import json
import re
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import uharfbuzz as hb
from specimens import ROOT, DATA, Panel, specimen_families
from code_balance_study import bind

OUT = ROOT / "specimens/features"
ON = {"calt": True, "liga": True, "clig": True}
OFF = {"calt": False, "liga": False, "clig": False}
# Each row defines its sample and actual feature switch once for both rendering
# and README generation. Permanent designs use an explicit source reference.
FEATURES = {
    "sans": [
        ("standard", "Standard ligatures", "fi fl", {"liga": True}, {"liga": False}),
        ("hooks", "Hooked combinations", "ai li", ON, OFF),
    ],
    "system": [
        ("standard", "Standard ligatures", "fi fl", {"liga": True}, {"liga": False}),
        (
            "tabular",
            "Tabular figures",
            "111  248  000",
            {"tnum": True},
            {"tnum": False},
        ),
        ("one", "Tabular 1 / default 1", "1", {"tnum": True}, {"tnum": False}),
    ],
    "code": [
        ("arrows", "Arrows", "-> ->> => <- <<-", ON, OFF),
        ("comparisons", "Comparisons", "== === != !== <= >=", ON, OFF),
        ("scope", "Scope separator", "::", ON, OFF),
        ("access", "Optional / non-null access", "?. !.", ON, OFF),
        ("interpolation", "Interpolation / expansion", "${ $[ $(", ON, OFF),
        ("ranges", "Ranges and dot assignment", ".. .= ..=", ON, OFF),
        ("ellipsis", "Three-character ellipsis", "...", ON, OFF),
        ("assignment", "Assignment / turnstiles", ":= |= |-", ON, OFF),
        ("hashes", "Hash groups", "## ### ####", ON, OFF),
        ("lifetimes", "Rust lifetime marker", "&'a <'a> 'static", ON, OFF),
        ("lifetime-literals", "Lifetimes / character literals", "&'a 'a' '_'", ON, OFF),
        ("generics", "Comparison / generic context", "a<b x<2 Vec<T> Vec<u8>", ON, OFF),
        ("optical", "Contextual optical placement", "ke Ke KE vi il", ON, OFF),
        ("at-repeat", "Repeated at-symbol fitting", "@@ @@@", ON, OFF),
    ],
}
DISTINCT = [
    ("identity", "Distinct letters and figures", "I l 1 0 O"),
    ("delimiters", "Stronger, inward-set delimiters", "() [] {}"),
    ("underscore", "Inline, gapless underscore", "snake_case __init__"),
    ("at", "Redrawn two-storey at symbol", "o@o user@host"),
    ("diamonds", "Shared prominent diamond dots", "i j . : ; ! ?"),
    ("bars", "Equals and hyphen", "= + -"),
]


def shaped(font, text, features):
    data = BytesIO()
    font.save(data)
    h = hb.Font(hb.Face(data.getvalue()))
    h.scale = (1000, 1000)
    b = hb.Buffer()
    b.add_str(text)
    b.guess_segment_properties()
    hb.shape(h, b, features)
    return [
        (font.getGlyphName(g.codepoint), p.x_advance, p.x_offset, p.y_offset)
        for g, p in zip(b.glyph_infos, b.glyph_positions)
    ]


def cell(key, font, text, features):
    p = Panel(key, DATA["families"]["code"])
    bind(p, font)
    p.text(text, 14, 37, 31, 400, "#101712", features=features, max_width=430)
    return p.body()


def svg(body, title, width=460, height=58):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img"><title>{html.escape(title)}</title><rect width="100%" height="100%" fill="#EEECD9"/>{body}</svg>'


def image(name, alt):
    return f'<img src="specimens/features/{name}.svg" width="300" alt="{html.escape(alt,quote=True).replace(chr(124),"&#124;")}">'


def update_table(readme, marker, table):
    pattern = re.compile(r"<!-- " + marker + r" -->.*?<!-- /" + marker + r" -->", re.S)
    replacement = "<!-- " + marker + " -->\n" + table + "\n<!-- /" + marker + " -->"
    assert pattern.search(readme), marker
    return pattern.sub(lambda _: replacement, readme)


def main(check=False):
    OUT.mkdir(exist_ok=True)
    documents = {}

    def emit(path, content):
        documents[path] = content
        if check:
            assert path.read_text() == content, str(path.relative_to(ROOT))
        else:
            path.write_text(content)

    cfg = specimen_families()
    fonts = {}
    manifest = {"sources": {}, "rows": {}}
    readme = (ROOT / "README.md").read_text()
    for key, c in cfg.items():
        source = ROOT / c["font"]
        f = TTFont(source)
        loc = {"wght": 350, **({"opsz": 14} if key == "system" else {})}
        fonts[key] = instantiateVariableFont(f, loc, inplace=True)
        manifest["sources"][key] = {
            "font": c["font"],
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "location": loc,
        }
    reference = TTFont(ROOT / "upstream/MetropolitanLine-Regular.ttf")
    manifest["sources"]["metropolitan"] = {
        "font": "upstream/MetropolitanLine-Regular.ttf",
        "sha256": hashlib.sha256(
            (ROOT / "upstream/MetropolitanLine-Regular.ttf").read_bytes()
        ).hexdigest(),
    }
    for key, rows in FEATURES.items():
        table = ["| Feature / input | On | Off |", "| --- | --- | --- |"]
        board = []
        for row, (slug, label, text, on, off) in enumerate(rows):
            samples = []
            for col, (state, settings) in enumerate([("on", on), ("off", off)]):
                name = key + "-" + slug + "-" + state
                body = cell(name, fonts[key], text, settings)
                emit(
                    OUT / (name + ".svg"),
                    svg(body, f'{cfg[key]["name"]}: {label}, {state}; input {text}'),
                )
                board.append(
                    f'<g transform="translate({310+460*col} {58+72*row})">{body}</g>'
                )
                samples.append(image(name, label + " " + state + ": " + text))
            on_shape = shaped(fonts[key], text, on)
            off_shape = shaped(fonts[key], text, off)
            assert on_shape != off_shape, (
                key,
                slug,
                "feature has no visible shaping change",
            )
            if key == "code":
                assert (
                    sum(v[1] for v in on_shape)
                    == sum(v[1] for v in off_shape)
                    == 600 * len(text)
                )
            manifest["rows"][key + "-" + slug] = {
                "text": text,
                "on_features": on,
                "off_features": off,
                "on_shaping": on_shape,
                "off_shaping": off_shape,
            }
            escaped = html.escape(text).replace("|", "&#124;")
            table.append(
                f"| {label}<br><code>{escaped}</code> | {samples[0]} | {samples[1]} |"
            )
            p = Panel("label-" + key + slug, DATA["families"][key])
            bind(p, fonts[key])
            p.text(label, 14, 100 + 72 * row, 17, 400, "#194454", max_width=285)
            board.append(p.body())
        p = Panel("head-" + key, DATA["families"][key])
        bind(p, fonts[key])
        p.text(cfg[key]["name"] + " / Book", 14, 29, 23, 400, "#194454")
        p.text("On", 325, 55, 17, 400, "#194454")
        p.text("Off", 785, 55, 17, 400, "#194454")
        board.append(p.body())
        emit(
            OUT / (key + "-Features.svg"),
            svg(
                "".join(board),
                cfg[key]["name"] + " feature on/off comparison",
                1230,
                85 + 72 * len(rows),
            ),
        )
        readme = update_table(readme, key + "-features", "\n".join(table))
    table = [
        "| Permanent design | Transit Code | Metropolitan Line reference |",
        "| --- | --- | --- |",
    ]
    board = []
    for row, (slug, label, text) in enumerate(DISTINCT):
        samples = []
        for col, (which, f) in enumerate(
            [("code", fonts["code"]), ("base", reference)]
        ):
            name = "distinct-" + slug + "-" + which
            body = cell(name, f, text, OFF)
            emit(OUT / (name + ".svg"), svg(body, label + " / " + which))
            samples.append(image(name, label + " / " + which))
            board.append(
                f'<g transform="translate({310+460*col} {58+72*row})">{body}</g>'
            )
        table.append(f"| {label} | {samples[0]} | {samples[1]} |")
        p = Panel("distinct-label" + slug, DATA["families"]["code"])
        bind(p, fonts["code"])
        p.text(label, 14, 100 + 72 * row, 17, 400, "#194454", max_width=285)
        board.append(p.body())
    p = Panel("distinct-head", DATA["families"]["code"])
    bind(p, fonts["code"])
    p.text("Permanent Code designs / base reference", 14, 29, 23, 400, "#194454")
    p.text("Transit Code Book", 325, 55, 17, 400, "#194454")
    p.text("Metropolitan Line Regular", 785, 55, 17, 400, "#194454")
    board.append(p.body())
    emit(
        OUT / "Code-Characters.svg",
        svg(
            "".join(board),
            "Distinct Code designs and original Metropolitan Line",
            1230,
            85 + 72 * len(DISTINCT),
        ),
    )
    readme = update_table(readme, "code-characters", "\n".join(table))
    # Compare matching Code weights to isolate the permanent horizontal change.
    previous_path = ROOT / "previews/code-1.023/VF/DaikonicTransitCode-VF.ttf"
    manifest["sources"]["code-previous"] = {
        "font": str(previous_path.relative_to(ROOT)),
        "sha256": hashlib.sha256(previous_path.read_bytes()).hexdigest(),
    }
    table = [
        f"| Matching Code weight | Current Code {cfg['code']['version']} | Previous Code 1.023 |",
        "| --- | --- | --- |",
    ]
    board = []
    metrics = {}
    from audit import shape_from_glyphs
    from fontTools.pens.svgPathPen import SVGPathPen

    for row, (weight, label) in enumerate([(350, "Book"), (400, "Regular")]):
        metrics[label] = {}
        pictures = []
        for col, (which, path) in enumerate(
            [("current", ROOT / cfg["code"]["font"]), ("previous", previous_path)]
        ):
            f = instantiateVariableFont(TTFont(path), {"wght": weight}, inplace=True)
            key = "equal-" + str(weight) + "-" + which
            p = Panel(key, DATA["families"]["code"])
            bind(p, f)
            p.text("=", 230, 120, 160, 400, "#101712", align="center", features=OFF)
            emit(
                OUT / (key + ".svg"),
                svg(p.body(), label + " equals / " + which, 460, 150),
            )
            pictures.append(image(key, label + " equals / " + which))
            gs = f.getGlyphSet()
            bounds = shape_from_glyphs(gs, "equal").bounds
            bars = list(shape_from_glyphs(gs, "equal").contours)
            metrics[label][which] = {
                "width": bounds[2] - bounds[0],
                "bar_thickness": bars[0].bounds[3] - bars[0].bounds[1],
            }
            x = 100 + 600 * col
            base = 300 + 330 * row
            pen = SVGPathPen(gs)
            gs["equal"].draw(pen)
            board.append(
                f'<path d="{pen.getCommands()}" transform="translate({x} {base}) scale(.5 -.5)" fill="#101712"/>'
            )
            board.append(
                f'<path d="M{x},{base-240} v190 M{x+300},{base-240} v190" stroke="#C06D3E" fill="none"/>'
            )
            heading = Panel(key + "-label", DATA["families"]["code"])
            bind(heading, f)
            heading.text(
                label + " " + str(weight) + " / " + which,
                x - 50,
                35 + 330 * row,
                21,
                400,
                "#194454",
            )
            m = metrics[label][which]
            heading.text(
                "Width "
                + str(round(m["width"]))
                + " / stroke "
                + str(round(m["bar_thickness"])),
                x - 50,
                275 + 330 * row,
                17,
                400,
                "#194454",
            )
            board.append(heading.body())
        table.append(
            "| "
            + label
            + " "
            + str(weight)
            + " | "
            + pictures[0]
            + " | "
            + pictures[1]
            + " |"
        )
    emit(
        OUT / "Equals-Comparison.svg",
        svg(
            "".join(board),
            "Matching-weight Code equals comparison; identical scale",
            1200,
            660,
        ),
    )
    manifest["equals_metrics"] = metrics
    readme = update_table(readme, "code-equals", "\n".join(table))
    emit(ROOT / "README.md", readme)
    manifest["files"] = {
        p.name: hashlib.sha256(content.encode()).hexdigest()
        for p, content in sorted(documents.items())
        if p.suffix == ".svg"
    }
    emit(OUT / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    if check:
        rendered = json.loads((ROOT / "qa/readme-feature-rendering.json").read_text())
        for rel, expected in rendered["files"].items():
            assert (
                hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == expected
            ), rel
    print(
        "Generated font-rendered README tables: all on/off rows shape differently; Code advances unchanged"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    main(check=args.check)
