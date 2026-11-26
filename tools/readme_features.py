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
from specimens import ROOT, DATA, Panel, specimen_families, weight_location
from code_balance_study import bind
from code_logic_shortcuts import COMMANDS, glyph_name
from code_glyph_names import sequence_name
from code_compact_build import CONTEXT_PAIRS, DIRECT, LOOSE_NAMES
from code_math import ARROWS, COMPARISONS
from code_compact_operators import CELL, LOOSE_GLYPHS, SAVED_CELL_GLYPHS

OUT = ROOT / "specimens/features"
ON = {"calt": True, "liga": True, "clig": True}
OFF = {"calt": False, "liga": False, "clig": False, "kern": False}
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
        (
            "paired-stems", "Paired stems / liga", "coffee letter bell",
            {"liga": True}, {"liga": False},
        ),
        (
            "texture-healing", "Texture healing", "imi imx xmi xmx .w. IMI IWI",
            {"ss04": False}, {"ss04": True},
        ),
        (
            "hairline-delimiters", "Delimiters", "|w| (x) [x] {x}  a | b",
            {"ss05": True}, {"ss05": False, "ss07": True},
        ),
        (
            "hairline-scope", "Scope and generics", "path::item::<T>",
            {"ss05": True}, {"ss05": False, "ss07": True},
        ),
        (
            "hairline-lifetimes", "Rust lifetime markers", "&'a 'static 'a'",
            {"ss05": True}, {"ss05": False, "ss07": True},
        ),
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
        ("optical", "Contextual optical placement", "string extra text", ON, OFF),
        ("at-repeat", "Repeated at-symbol fitting", "@@ @@@", ON, OFF),
    ],
}


def shaped(font, text, features):
    data = BytesIO()
    font.save(data)
    h = hb.Font(hb.Face(data.getvalue()))
    h.scale = (font["head"].unitsPerEm,) * 2
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


def highlight_code_line(panel, text, features, *, extra_keywords=(), extra_types=(), expected_advance=None):
    """Color the already-shaped glyphs; lexical runs never split font context."""
    assert text.isascii(), "The specimen uses ASCII source offsets."
    colors = ["#eeeddb"] * len(text)
    tokens = re.compile(
        r'"(?:[^"\\]|\\.)*"|\'[A-Za-z_][A-Za-z_0-9]*|\b[0-9]+\b|\b[A-Za-z_][A-Za-z_0-9]*\b'
    )
    keywords = {"const", "struct", "fn", "let", "mut", "pub", "impl", "return", "self", *extra_keywords}
    types = {"usize", "str", "u8", "u64", "bool", *extra_types}
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
    instance, font = panel.font(400)
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.guess_segment_properties()
    hb.shape(font, buffer, {**features, "tnum": False})
    names = [font.get_glyph_name(info.codepoint) for info in buffer.glyph_infos]
    actual = sum(pos.x_advance for pos in buffer.glyph_positions)
    expected = expected_code_advance(instance, text, names) if expected_advance is None else expected_advance
    assert actual == expected, (text, features, actual, expected, names)
    element = ET.fromstring(panel.elements[-1])
    uses = list(element)
    assert len(uses) == len(buffer.glyph_infos)
    for use, info in zip(uses, buffer.glyph_infos):
        use.set("fill", colors[info.cluster])
    panel.elements[-1] = ET.tostring(element, encoding="unicode")
    return names


def code_comparison(font):
    examples = (
        ("Rust", (
            "struct IoRecord<'a> {",
            "    user_id: usize,",
            "    label: &'a str,",
            "    active: bool,",
            "}",
            "",
            "fn collect_labels<'a>(",
            "    rows: &'a [IoRecord<'a>],",
            ") -> Vec<Vec<&'a str>> {",
            "    // Collect matching labels.",
            "    rows.iter()",
            "        .filter(|row| {",
            "            row.user_id != 0 || !row.active",
            "        })",
            '        .map(|r| vec![r.label, "film@host"])',
            "        .collect::<Vec<_>>()",
            "}",
        )),
        ("TypeScript", (
            "const key = row?.id ?? row!.id;",
            "const all = [...items, ...tail];",
            "const check = (x: number) =>",
            "    x === 0 || x != 1;",
        )),
        ("Logic", (
            r"[]p -> <>q    \forall x    \exists y",
            "<[p]>   [<q>]   [<>]   <[]>",
        )),
    )
    pane_width, padding, size, leading = 525, 20, 18, 25
    width = 2 * pane_width
    height = 52 + sum(50 + leading * len(lines) for _, lines in examples)
    assert max(len(line) for _, lines in examples for line in lines) * CELL * size / font["head"].unitsPerEm <= (
        pane_width - 2 * padding
    )
    body = [
        f'<rect width="{width}" height="{height}" fill="#0d1218"/>',
        f'<path d="M{pane_width} 0V{height}" stroke="#2c3945"/>',
    ]
    panel = Panel("code-example", DATA["families"]["code"])
    bind(panel, font)
    glyphs = {}
    for column, enabled in enumerate((True, False)):
        x = column * pane_width + padding
        features = {
            **(ON if enabled else OFF),
            "kern": enabled,
            "ss03": enabled,
            "ss04": not enabled,
            "ss05": enabled,
            "ss07": not enabled,
        }
        state = "Features on" if enabled else "Features off"
        body.append(
            f'<text x="{x}" y="35" font-family="Arial,sans-serif" font-size="16" '
            f'font-weight="700" fill="#aebbc6">{state}</text>'
        )
        y = 72
        for language, lines in examples:
            language_features = {
                **features,
                "ss02": enabled and language == "Logic",
                "ss06": enabled and language == "TypeScript",
            }
            names = set()
            body.append(
                f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" '
                f'font-size="13" fill="#aebbc6">{language}</text>'
            )
            y += 22
            for line in lines:
                if line:
                    panel.text(line, x, y, size, 400, "#eeeddb", features=language_features)
                    names.update(highlight_code_line(panel, line, language_features))
                y += leading
            y += 28
            glyphs[enabled, language] = names

    required = {
        "Rust": (
            COMPARISONS["!="], "bar.positioned", "slash.positioned",
            DIRECT["::"], "less.generic.hairline", "bar.delimiterOpen.hairline", "l_l",
            "m.texture.",
        ),
        "TypeScript": (
            LOOSE_NAMES["!="], LOOSE_NAMES["==="], "question.positioned",
            "exclam.positioned", ARROWS["=>"], "period.spread",
        ),
        "Logic": (
            glyph_name(r"\forall"), glyph_name(r"\exists"),
            "code.enclosureBox", "code.enclosureDiamond",
            "less.generic.hairline", "bracketleft.hairline",
            "code.logicBoxDiamond", "code.logicDiamondBox",
        ),
    }
    for language, expected in required.items():
        shown = glyphs[True, language] - glyphs[False, language]
        for name in expected:
            if name.endswith(("positioned", ".", "spread")):
                assert any(glyph.startswith(name) for glyph in shown), (language, name)
            else:
                assert current_name(font, name) in shown, (language, name, shown)
    for language in ("Rust", "TypeScript"):
        assert "logicalnot" not in glyphs[True, language]
    assert not any(name.endswith(".loose") for name in glyphs[True, "Rust"])
    assert all(".texture." not in name for name in glyphs[False, "Rust"])
    assert any(name.startswith("quotesingle.lifetime.hairline") for name in glyphs[True, "Rust"])
    body.append(panel.body())
    return svg(
        "".join(body),
        "Rust, TypeScript, and logic in Daikonic Transit Code Book with features on and off",
        width,
        height,
    )


def current_name(font, name):
    return name if name in font.getGlyphOrder() else sequence_name(font.getBestCmap(), name)


def expected_code_advance(font, text, names):
    loose_savings = {current_name(font, name): len(token) - 1
                     for token, name in LOOSE_GLYPHS.items()}
    for token, name in LOOSE_NAMES.items():
        loose_savings[current_name(font, name)] = len(token) - 1
    saved_glyphs = {current_name(font, name) for name in SAVED_CELL_GLYPHS}
    saved_glyphs.update((COMPARISONS[t] for t in ("<=", ">=", "===", "!==")))
    saved_glyphs.update((ARROWS[t] for t in ("->>", "<<-")))
    saved_glyphs.update(CONTEXT_PAIRS.values())
    saved_glyphs.add("period_period_period.liga.spread")
    # A compact pair remains two glyphs, each with a half-cell advance.
    # A contextual spread remains three glyphs, together saving one cell.
    half_cells = ("colon.positioned", "question.positioned", "exclam.positioned",
                  "slash.positioned", "bar.positioned")
    saved = 0
    previous = ""
    for name in names:
        if name.startswith(half_cells) or name == DIRECT["::"]:
            saved += CELL // 2
        elif name.startswith("period.spread"):
            saved += CELL // 3
        elif name.startswith("period.positioned"):
            # Access periods use the same adjustment as their preceding mark.
            if previous.startswith(("question.positioned", "exclam.positioned")):
                saved += CELL // 2
        else:
            saved += CELL * loose_savings.get(name, int(name in saved_glyphs))
        previous = name
    return CELL * len(text) - saved


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
        loc = weight_location(f, 350)
        fonts[key] = instantiateVariableFont(f, loc, inplace=True)
        manifest["sources"][key] = {
            "font": c["font"],
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "location": loc,
        }
    for key, rows in FEATURES.items():
        header = ["| Feature / input | On | Off |", "| --- | --- | --- |"]
        table, hairlining, healing = header.copy(), header.copy(), header.copy()
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
                for result in (on_shape, off_shape):
                    assert sum(advance for _, advance, *_ in result) == expected_code_advance(
                        fonts[key], text, (name for name, *_ in result)
                    ), (slug, result)
            manifest["rows"][key + "-" + slug] = {
                "text": text,
                "on_features": on,
                "off_features": off,
                "on_shaping": on_shape,
                "off_shaping": off_shape,
            }
            escaped = html.escape(text).replace("|", "&#124;")
            section = hairlining if slug.startswith("hairline-") else (
                healing if slug == "texture-healing" else table
            )
            section.append(
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
        if key == "code":
            readme = update_table(readme, "code-hairlining", "\n".join(hairlining))
            readme = update_table(readme, "code-texture-healing", "\n".join(healing))
    manifest["shortcuts"] = {}
    shortcuts = ["| Input | Rendered form |", "| --- | --- |"]
    for command in COMMANDS:
        rendered = shaped(fonts["code"], command, ON)
        assert len(rendered) == 1 and rendered[0][0] == current_name(fonts["code"], glyph_name(command))
        manifest["shortcuts"][command] = {"shaping": rendered, "features": ON}
        slug = "code-command-" + command[1:]
        body = cell(slug, fonts["code"], command, ON)
        emit(OUT / (slug + ".svg"), svg(body, "Code shortcut " + command))
        shortcuts.append(
            f"| <code>{html.escape(command)}</code> | {image(slug,command)} |"
        )
    readme = update_table(readme, "code-shortcuts", "\n".join(shortcuts))
    emit(OUT / "Code-Characters.svg", code_comparison(fonts["code"]))
    readme = update_table(
        readme,
        "code-characters",
        "[![Rust, TypeScript, and logic in Code Book with features on and off]"
        "(specimens/features/Code-Characters.svg)](specimens/features/Code-Characters.svg)",
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
        "Generated font-rendered README tables: all on/off rows shape differently; Code advances verified"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    main(check=args.check)
