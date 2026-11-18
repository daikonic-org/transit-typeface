"""Generate real-font feature comparisons and the matching README tables."""

from copy import deepcopy
from io import BytesIO
from pathlib import Path
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import uharfbuzz as hb
from specimens import ROOT, DATA, Panel, specimen_families
from code_balance_study import bind
from code_logic_shortcuts import COMMANDS

OUT = ROOT / "specimens/features"
ON = {"calt": True, "liga": True, "clig": True}
OFF = {"calt": False, "liga": False, "clig": False}
# Each row defines its sample and actual feature switch once for both rendering
# and README generation. Permanent designs use one Book-weight sample.
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
    ],
    "code": [
        ("rust-inference", "Rust inference placeholders", "<'_> <_> <[_]>", ON, OFF),
        ("rust-turbofish", "Rust turbofish", "::<T> ::<_> ::<[_]>", ON, OFF),
        (
            "logic-not",
            "Logical negation / ss02",
            "!p !!p != !== !.",
            {**ON, "ss02": True},
            {**ON, "ss02": False},
        ),
        ("arrows", "Arrows", "-> ->> => <- <<-", ON, OFF),
        ("comparisons", "Comparisons", "== === != !== <= >=", ON, OFF),
        ("scope", "Scope separator", "::", ON, OFF),
        ("access", "Optional / non-null access", "?. !.", ON, OFF),
        ("interpolation", "Interpolation / expansion", "${ $[ $(", ON, OFF),
        ("ranges", "Ranges and dot assignment", ".. .= ..=", ON, OFF),
        ("ellipsis", "Three-character ellipsis", "...", ON, OFF),
        ("assignment", "Assignment / turnstiles", ":= |= |-", ON, OFF),
        ("hashes", "Hash groups", "## ### #### ##### ######", ON, OFF),
        ("lifetimes", "Rust lifetime marker", "&'a <'a> 'static", ON, OFF),
        ("lifetime-literals", "Lifetimes / character literals", "&'a 'a' '_'", ON, OFF),
        (
            "lifetime-placement",
            "Extended lifetime hooks / ss01",
            "&'a <'a> 'static",
            {**ON, "ss01": True},
            {**ON, "ss01": False},
        ),
        ("logic", "Logic / ss02", "<> []", {**ON, "ss02": True}, {**ON, "ss02": False}),
        (
            "logic-order",
            "Empty nested Logic order / ss02",
            "[<>] <[]>",
            {**ON, "ss02": True},
            {**ON, "ss02": False},
        ),
        (
            "pipe-delimiters",
            "Contextual pipe delimiters",
            "|x| map(|x| x) a | b",
            ON,
            OFF,
        ),
        ("generics", "Comparison / generic context", "a<>b Vec<> Vec<Vec<T>>", ON, OFF),
        ("optical", "Contextual optical placement", "ke Ke KE vi il", ON, OFF),
        ("at-repeat", "Repeated at-symbol fitting", "@@ @@@", ON, OFF),
    ],
}


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
    return f'<img src="specimens/features/{name}.svg" width="460" alt="{html.escape(alt,quote=True).replace(chr(124),"&#124;")}">'


def update_table(readme, marker, table):
    pattern = re.compile(r"<!-- " + marker + r" -->.*?<!-- /" + marker + r" -->", re.S)
    replacement = "<!-- " + marker + " -->\n" + table + "\n<!-- /" + marker + " -->"
    assert pattern.search(readme), marker
    return pattern.sub(lambda _: replacement, readme)


def highlight_rust_line(panel, text):
    """Color the already-shaped glyphs; lexical runs never split font context."""
    assert text.isascii(), "The specimen uses ASCII source offsets."
    colors = ["#eeeddb"] * len(text)
    tokens = re.compile(
        r'"(?:[^"\\]|\\.)*"|\'[A-Za-z_][A-Za-z_0-9]*|\b[0-9]+\b|\b[A-Za-z_][A-Za-z_0-9]*\b'
    )
    keywords = {"struct", "fn", "let", "mut", "pub", "impl", "return", "self"}
    types = {"usize", "str", "u8", "u64", "bool"}
    for match in tokens.finditer(text):
        token = match.group()
        color = None
        if token.startswith('"'):
            color = "#c3e88d"
        elif token.startswith("'"):
            colors[match.start() + 1 : match.end()] = ["#c3a6ff"] * (len(token) - 1)
            continue
        elif token in keywords:
            color = "#c792ea"
        elif token[0].isdigit():
            color = "#f78c6c"
        elif token in types or token[0].isupper():
            color = "#ffcb6b"
        elif re.match(r"\s*(?:\(|!(?!=))", text[match.end() :]) or text[
            : match.start()
        ].rstrip().endswith("fn"):
            color = "#82aaff"
        if color:
            colors[match.start() : match.end()] = [color] * len(token)
    _, font = panel.font(400)
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer, {**ON, "tnum": False})
    element = ET.fromstring(panel.elements[-1])
    uses = list(element)
    assert len(uses) == len(buffer.glyph_infos)
    for use, info in zip(uses, buffer.glyph_infos):
        use.set("fill", colors[info.cluster])
    panel.elements[-1] = ET.tostring(element, encoding="unicode")


def main(check=False):
    OUT.mkdir(exist_ok=True)
    prior_files = (
        set(json.loads((OUT / "manifest.json").read_text()).get("files", {}))
        if (OUT / "manifest.json").exists()
        else set()
    )
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
    manifest["shortcuts"] = {}
    shortcuts = ["| Input | Rendered form |", "| --- | --- |"]
    for command in COMMANDS:
        rendered = shaped(fonts["code"], command, ON)
        assert len(rendered) == 1 and rendered[0][0] == "code.command." + command[1:]
        manifest["shortcuts"][command] = {"shaping": rendered, "features": ON}
        slug = "code-command-" + command[1:]
        body = cell(slug, fonts["code"], command, ON)
        emit(OUT / (slug + ".svg"), svg(body, "Code shortcut " + command))
        shortcuts.append(
            f"| <code>{html.escape(command)}</code> | {image(slug,command)} |"
        )
    readme = update_table(readme, "code-shortcuts", "\n".join(shortcuts))
    example = [
        "struct IoRecord<'a> {",
        "    user_id: usize,",
        "    label: &'a str,",
        "}",
        "",
        "fn labels<'a>(rows: &'a [IoRecord<'a>]) -> Vec<Vec<&'a str>> {",
        "    rows.iter()",
        "        .filter(|row| row.user_id != 0)",
        "        .take(1)",
        '        .map(|row| vec![row.label, "user@host"])',
        "        .collect()",
        "}",
    ]
    p = Panel("code-example", DATA["families"]["code"])
    bind(p, fonts["code"])
    for line, text in enumerate(example):
        if text:
            p.text(
                text,
                30,
                84 + 34 * line,
                24,
                400,
                "#eeeddb",
                features=ON,
                max_width=1040,
            )
            highlight_rust_line(p, text)
    height = 112 + 34 * len(example)
    body = '<rect width="1100" height="' + str(height) + '" fill="#0d1218"/>'
    body += '<text x="30" y="32" font-family="Arial" font-size="14" fill="#aebbc6">Daikonic Transit Code · Book 350</text>'
    body += p.body()
    emit(
        OUT / "Code-Characters.svg",
        svg(
            body, "Syntax-highlighted Rust in Daikonic Transit Code Book", 1100, height
        ),
    )
    readme = update_table(
        readme,
        "code-characters",
        '<img src="specimens/features/Code-Characters.svg" width="1100" alt="Syntax-highlighted Rust rendered in Daikonic Transit Code Book">',
    )
    emit(ROOT / "README.md", readme)
    manifest["files"] = {
        p.name: hashlib.sha256(content.encode()).hexdigest()
        for p, content in sorted(documents.items())
        if p.suffix == ".svg"
    }
    if not check:
        for stale in prior_files - set(manifest["files"]):
            for suffix in (".svg", ".png", ".pdf"):
                path = (OUT / stale).with_suffix(suffix)
                if path.exists():
                    path.unlink()
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
