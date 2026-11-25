"""Proof the reconstructed Transit Code at all named weights and widths."""

from argparse import ArgumentParser
from pathlib import Path

from code_weight_width_trial import WEIGHTS, WIDTH_PRESETS
from glyph_proof import build_proof
from italic_texture_proofs import BG, CREAM, MUTED, export, label, rect
from readme_features import highlight_code_line
from specimens import Panel


WIDEST = "Il10O  flying  offset  tally  ke vi  @@"
PUNCTUATION = "! ? % *. , ; : ...  a <= b  p == q  a ->> b"
RUST = (
    "fn render<'a>(items: &'a [Item]) -> Vec<&'a Item> {",
    "    items.iter().collect::<Vec<_>>()",
    "}",
)
TYPESCRIPT = (
    "function copy<T>(...items: T[]): T[] {",
    "    return items.length !== 0 ? [...items] : [];",
    "}",
)


def proof(upright, italic, output):
    width, height = 1240, 1008
    body = [
        rect(0, 0, width, height, BG),
        label("Daikonic Transit Code", 38, 48, 32, bold=True),
        label("Upright and 9° italic  ·  Book, Regular and Medium", 39, 78, 15, MUTED),
    ]
    panels = []
    for column, (width_axis, title) in enumerate(WIDTH_PRESETS.items()):
        x = 38 + column * 388
        body.append(label(f"{title or 'Normal'}   ·   {6 * width_axis} units", x, 130, 16, CREAM, True))
        body.append(rect(x, 146, 364, 388, "#101821"))
        for face, path in (("Upright", upright), ("Italic", italic)):
            panel = Panel(f"{face.lower()}-{width_axis}", {
                "font": str(path.resolve()), "axes": {"wdth": width_axis},
            })
            for row, (weight, weight_name) in enumerate(WEIGHTS.items()):
                y = 174 + row * 123
                if face == "Upright":
                    body.append(label(f"{weight_name} {weight}", x + 13, y, 12, MUTED))
                    panel.text(WIDEST, x + 13, y + 26, 14, weight, CREAM)
                    panel.text(PUNCTUATION, x + 13, y + 92, 12, weight, CREAM)
                else:
                    panel.text(WIDEST, x + 13, y + 58, 14, weight, CREAM)
            panels.append(panel)

    for column, (title, lines, flags) in enumerate((
        ("Rust · default settings", RUST, {}),
        ("TypeScript · Loose Equality enabled", TYPESCRIPT, {"ss06": True}),
    )):
        x = 38 + column * 588
        for offset, description, features in (
            (0, title, flags),
            (158, "Ligatures and contextual features off", {"calt": False, "liga": False}),
        ):
            y = 556 + offset
            body.append(rect(x, y, 564, 143, "#101821"))
            body.append(label(description, x + 14, y + 28, 14, MUTED, True))
            panel = Panel(f"code-{column}-{offset}", {"font": str(upright.resolve())})
            for row, line in enumerate(lines):
                panel.text(line, x + 14, y + 58 + row * 22, 16, 400, CREAM, features=features)
                highlight_code_line(panel, line, features, extra_keywords=("function", "return"))
            panels.append(panel)

    body.append(rect(38, 872, 1152, 96, "#101821"))
    body.append(label("Logic enclosures", 52, 905, 15, MUTED, True))
    example = "[<>]  <[]>  <[T]>  [<T>]"
    panel = Panel("logic", {"font": str(upright.resolve())})
    for x, enabled, title in ((374, False, "Off"), (822, True, "On")):
        body.append(label(title, x, 905, 12, MUTED))
        panel.text(example, x, 940, 21, 400, CREAM, features={"ss02": enabled})
    panels.append(panel)
    export(output / "Code-Specimen.svg",
           body + [panel.body() for panel in panels], width, height)


def glyph_details(upright, output):
    width, height = 1016, 508
    panel = Panel("glyph-details", {"font": str(upright.resolve())})
    body = [
        rect(0, 0, width, height, BG),
        label("Daikonic Transit Code", 30, 47, 29, bold=True),
        label("Hook, bowl and punctuation · Upright at Normal width", 30, 74, 15, MUTED),
    ]
    for column, (weight, name) in enumerate(WEIGHTS.items()):
        x = 30 + column * 322
        body.append(rect(x, 104, 310, 294, "#101821"))
        body.append(label(f"{name} {weight}", x + 17, 132, 14, MUTED, True))
        for sample, baseline in (("l i j", 206), ("g a o", 290), ("* . + %", 374)):
            panel.text(sample, x + 17, baseline, 63, weight, CREAM)
        panel.text("let area = w * h;", x + 17, 439, 17, weight, CREAM)
        panel.text("/* glyph detail */", x + 17, 467, 17, weight, MUTED)
    export(output / "Code-Glyph-Details.svg", body + [panel.body()], width, height)


def build_package_proofs(package):
    out = package / "proofs"
    out.mkdir(parents=True, exist_ok=True)
    upright = package / "VF/DaikonicTransitCode-VF.ttf"
    italic = package / "VF/DaikonicTransitCode-Italic-VF.ttf"
    proof(upright, italic, out)
    glyph_details(upright, out)
    for label, variant in (("upright", upright), ("italic", italic)):
        build_proof(variant, out / label, svg_only=True, interactive_axes=True)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    build_package_proofs(parser.parse_args().package)


if __name__ == "__main__":
    main()
