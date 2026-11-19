"""Render the real italic companions and Code's opt-in texture healing."""

import argparse
from html import escape
from pathlib import Path
from shutil import copyfile, which
from subprocess import CalledProcessError, run
from tempfile import TemporaryDirectory

from fontTools.pens.svgPathPen import SVGPathPen

from code_receiver_shapes import FORM_SHIFT
from render_svg import render
from specimens import Panel, specimen_families

BG = "#142330"
CREAM = "#eeeddb"
MUTED = "#b9ccd5"
COLS = (47, 630)


def label(value, x, y, size, ink=CREAM, bold=False):
    weight = ' font-weight="700"' if bold else ""
    return (
        f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" font-size="{size}" '
        f'fill="{ink}"{weight}>{escape(value)}</text>'
    )


def rect(x, y, width, height, fill):
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{fill}"/>'


def export(path, body, width, height):
    with TemporaryDirectory(prefix="transit-proof-") as directory:
        staged = Path(directory) / path.name
        staged.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            + "".join(body)
            + "</svg>"
        )
        try:
            render(staged, scale=1)
        except CalledProcessError:
            inkscape = which("inkscape")
            if inkscape is None:
                raise
            for suffix in (".png", ".pdf"):
                run(
                    [
                        inkscape,
                        str(staged),
                        "--export-area-page",
                        f"--export-filename={staged.with_suffix(suffix)}",
                    ],
                    check=True,
                    capture_output=True,
                )
        for suffix in (".svg", ".png", ".pdf"):
            copyfile(staged.with_suffix(suffix), path.with_suffix(suffix))


def italic_proof(directory, families):
    data = {
        "sans": (
            CREAM,
            "#194454",
            [
                ("Finding a quieter rhythm", 35),
                ("A fine grain of light in the café.", 22),
                ("fig   affinity   signal   jigsaw", 25),
                ("Now arriving at King's Cross.", 16),
            ],
        ),
        "system": (
            "#f8ede2",
            "#633214",
            [
                ("Find a location", 34),
                ("Saved filters and recent activity", 20),
                ("Show Café and dining · Sign out", 16),
                ("Pin filter / Edit profile / Account", 13),
            ],
        ),
        "code": (
            "#101821",
            CREAM,
            [
                ("fn find<'a>(file: &'a str) -> Option<&'a str> {", 16),
                ("    if file.len() != 0 { file.get(..1) }", 16),
                ("    else { None }", 16),
                ("}   // a f g i: affinity, file_id, glyph", 16),
            ],
        ),
    }
    body = [
        rect(0, 0, 1200, 1015, BG),
        label("Daikonic Transit · 9° italic companions", 47, 52, 31, bold=True),
        label(
            "Book 350 from the variable font files · System at optical size 14",
            47,
            82,
            15,
            MUTED,
        ),
    ]
    for row, (key, (background, ink, samples)) in enumerate(data.items()):
        y = 112 + row * 285
        cfg = families[key]
        body += [
            rect(23, y, 1154, 263, background),
            label(cfg["name"], COLS[0], y + 36, 19, ink, True),
            label("UPRIGHT", COLS[0], y + 67, 11, ink, True),
            label("ITALIC", COLS[1], y + 67, 11, ink, True),
            f'<path d="M601 {y + 51}V{y + 227}" stroke="{ink}" stroke-opacity=".2"/>',
        ]
        italic = directory / (cfg["stem"] + "-Italic-VF.ttf")
        for col, candidate in enumerate([cfg, {**cfg, "font": str(italic)}]):
            panel = Panel(key, candidate)
            instance, _ = panel.font(350)
            if col:
                assert instance["post"].italicAngle == -9
            panel.key += "-" + str(col)
            for line, (text, size) in enumerate(samples):
                panel.text(
                    text, COLS[col], y + 111 + line * 39, size, 350, ink, max_width=505
                )
            body.append(panel.body())
    body.append(
        label(
            "Upright letter constructions with a 9° lean and the original i diamond",
            47,
            992,
            14,
            MUTED,
        )
    )
    export(directory / "Transit-Italic-Companions.svg", body, 1200, 1015)


def texture_proof(directory, families):
    path = directory / "DaikonicTransitCode-TextureTrial-VF.ttf"
    config = {**families["code"], "font": str(path)}
    panel = Panel("texture", config)
    body = [
        rect(0, 0, 1200, 1220, BG),
        label("Transit Code · texture healing", 47, 54, 31, bold=True),
        label(
            "Book 350 · three receiver widths, drawn from Transit Sans",
            47,
            83,
            15,
            MUTED,
        ),
        rect(23, 112, 1154, 510, "#101821"),
        label("STANDARD", COLS[0], 150, 13, MUTED, True),
        label("TEXTURE HEALING · SS03", COLS[1], 150, 13, MUTED, True),
        f'<path d="M601 131V594" stroke="{MUTED}" stroke-opacity=".25"/>',
    ]
    rows = [
        ("xmx  lmx  xml  imi  im  mi", 31, 215),
        ("xwx  iwx  xwi  iwi", 36, 283),
        ("am  ma  mam  mim  mjm  mlm", 30, 350),
        ("minimum    film    always", 23, 421),
        ("let minimum_width = film.width();", 16, 477),
        ("let always_wait = max(1, width);", 16, 516),
        ("// manual, railway, new_job", 14, 556),
    ]
    for column, x in enumerate(COLS):
        for value, size, baseline in rows:
            panel.text(
                value,
                x,
                baseline,
                size,
                350,
                CREAM,
                features={"ss03": bool(column)},
                max_width=505,
            )
    body.append(panel.body())
    body.append(rect(23, 638, 1154, 295, "#101821"))
    body.append(label("RECEIVER OUTLINES", 47, 673, 13, MUTED, True))
    font, _ = panel.font(350)
    glyphs = font.getGlyphSet()
    for column, (heading, suffix) in enumerate(
        [("NORMAL", ""), ("INTERMEDIATE", ".heal.left"), ("WIDE", ".heal.both")]
    ):
        x = 125 + 383 * column
        body.append(label(heading, x, 714, 12, MUTED, True))
        for index, letter in enumerate("mw"):
            pen = SVGPathPen(glyphs)
            glyphs[letter + suffix].draw(pen)
            correction = FORM_SHIFT[letter] if suffix == ".heal.left" else 0
            origin = x + 143 * index + correction * 0.18
            body.append(
                f'<path d="{pen.getCommands()}" fill="{CREAM}" '
                f'transform="translate({origin} 840) scale(.18 -.18)"/>'
            )
        if column == 1:
            body.append(label("Same drawing shifted left or right", x, 885, 13, MUTED))
    body.append(rect(23, 949, 1154, 249, "#101821"))
    body.append(label("DONOR OUTLINES", 47, 983, 13, MUTED, True))
    body.append(label("Default and narrow forms", 47, 1010, 13, MUTED))
    for column, letter in enumerate("aijl"):
        x = 88 + 274 * column
        for position, suffix in enumerate(("", ".heal.center")):
            pen = SVGPathPen(glyphs)
            glyphs[letter + suffix].draw(pen)
            origin = x + 102 * position
            body.append(
                f'<path d="{pen.getCommands()}" fill="{CREAM}" '
                f'transform="translate({origin} 1115) scale(.105 -.105)"/>'
            )
        body.append(label("DEFAULT", x + 8, 1173, 11, MUTED, True))
        body.append(label("NARROW", x + 110, 1173, 11, MUTED, True))
    export(directory / "Transit-Texture-Healing.svg", body, 1200, 1220)


def italic_letterform_proof(directory, families, *, refined=False, focus=None):
    height = 130 + 282 * len(families)
    title = {"f": "Descending f", "g": "Cursive g", "ft": "Paired f and t"}.get(
        focus, "Italic letterforms"
    )
    subtitle = (
        "9° italic · System at optical size 14"
        if refined
        else "Book 350 · 9° lean · same a, f and i in both columns"
    )
    body = [
        rect(0, 0, 1200, height, BG),
        label(f"Daikonic Transit · {title}", 47, 52, 31, bold=True),
        label(subtitle, 47, 81, 15, MUTED),
    ]
    for row, (key, cfg) in enumerate(families.items()):
        y = 108 + row * 282
        background, ink = ("#101821", CREAM) if key == "code" else (CREAM, "#194454")
        body += [
            rect(23, y, 1154, 267, background),
            label(cfg["name"], 47, y + 34, 19, ink, True),
            f'<path d="M601 {y + 48}V{y + 243}" stroke="{ink}" stroke-opacity=".2"/>',
        ]
        for column, construction in enumerate(("a", "q")):
            x = COLS[column]
            if refined:
                weight = (350, 400)[column]
                title = ("BOOK 350", "REGULAR 400")[column]
                font_directory = directory
            else:
                weight = 350
                title = f"g FROM THE {construction} BOWL"
                font_directory = directory / (construction + "-return")
            body.append(label(title, x, y + 64, 12, ink, True))
            font = font_directory / (cfg["stem"] + "-Italic-VF.ttf")
            panel = Panel(key, {**cfg, "font": str(font)})
            panel.font(weight)
            panel.key += "-" + construction
            default_headline = "a g q p f" if refined else "a g q f i"
            headline = {"f": "f   fi   fl", "g": "a g q p f", "ft": "ff   tt"}.get(
                focus, default_headline
            )
            samples = [
                (headline, 72, 139),
                ("a fine figure, a quiet place", 25, 190),
                ("fig   gift   affinity   agate   café", 19, 221),
                ("aqua, paper, graph, office, café", 14, 246),
            ]
            if focus == "f":
                samples[1:] = [
                    ("fine figures and flowing forms", 25, 190),
                    ("affinity   office   flag   flow", 19, 221),
                    ("profile, filter, offset, field", 14, 246),
                ]
            if key == "code":
                samples[2] = (
                    "fn find<'a>(file: &'a str) -> Option<&'a str> {",
                    16,
                    223,
                )
                samples[3] = ("// find_file, align, quiet, i j l 1", 14, 250)
            if focus == "g":
                samples[1:] = [
                    ("A figure in the quiet gallery", 25, 190),
                    ("glyph   gauge   graph   signal   gigue", 19, 221),
                    ("fig, jigsaw, cycling, query, alignment", 14, 246),
                ]
                if key == "code":
                    samples[2] = ("fn get_graph(query: &str) -> Graph {", 16, 223)
                    samples[3] = ("// git grep -n 'glyph'", 14, 250)
            if focus == "ft":
                samples[1:] = [
                    ("Effort and attention", 25, 190),
                    ("afford   letter   offset   motto", 19, 221),
                    ("coffee, little, office, kettle, waffle", 14, 246),
                ]
                if key == "code":
                    samples[2] = ("let offset = pattern.offset();", 16, 223)
                    samples[3] = ("// buffer, layout_settings", 14, 250)
            for text, size, baseline in samples:
                panel.text(text, x, y + baseline, size, weight, ink, max_width=506)
            body.append(panel.body())
    export(directory / "Transit-Italic-Letterforms.svg", body, 1200, height)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("italic_directory", type=Path)
    parser.add_argument("texture_directory", type=Path, nargs="?")
    italic_mode = parser.add_mutually_exclusive_group()
    italic_mode.add_argument("--compare-letterforms", action="store_true")
    italic_mode.add_argument("--refined-letterforms", action="store_true")
    italic_mode.add_argument("--descending-f", action="store_true")
    italic_mode.add_argument("--cursive-g", action="store_true")
    italic_mode.add_argument("--paired-stems", action="store_true")
    args = parser.parse_args()
    families = specimen_families()
    focus = next(
        (key for key, on in (("f", args.descending_f), ("g", args.cursive_g), ("ft", args.paired_stems)) if on),
        None,
    )
    if args.compare_letterforms or args.refined_letterforms or focus:
        italic_letterform_proof(
            args.italic_directory.resolve(), families,
            refined=args.refined_letterforms or focus is not None,
            focus=focus,
        )
    else:
        italic_proof(args.italic_directory.resolve(), families)
    if args.texture_directory:
        texture_proof(args.texture_directory.resolve(), families)
