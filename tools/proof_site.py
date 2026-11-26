"""Generate the public proof site from the coordinated release fonts."""

from argparse import ArgumentParser
from html import escape
import json
from pathlib import Path
from shutil import copyfile
from string import Template

from fontTools.ttLib import TTFont

from bundle_release import LICENSE_FILES, RECIPE, ROOT, release_families, specimen_families
from glyph_proof import collect_inline_proof, viewer_sections


TOOLS = Path(__file__).resolve().parent
EXAMPLES = {
    "sans": "Wayfinding",
    "system": "Legend",
    "code": "fn trim_width<'a>(input: &'a str) -> Vec<&'a str> {\n"
            "    input.split_whitespace().collect::<Vec<_>>()\n}"
            "\n\nimi  imx  xmi  xmx  iwi  .w.  minimum",
}


def build_site(output, *, include_current_code=False):
    assets = output / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    copyfile(TOOLS / "proof_site.css", assets / "proof-site.css")
    copyfile(TOOLS / "proof_site.js", assets / "proof-site.js")
    copyfile(TOOLS / "glyph_proof_compare.js", assets / "glyph-proof-compare.js")
    for name in LICENSE_FILES:
        license_file = output / name
        license_file.parent.mkdir(parents=True, exist_ok=True)
        copyfile(ROOT / name, license_file)
    families = release_families()
    if include_current_code:
        families["code"] = specimen_families()["code"]
    for key, config in families.items():
        upright = ROOT / config["font"]
        italic = upright.with_name(config["stem"] + "-Italic-VF.ttf")
        for variant, source in (("upright", upright), ("italic", italic)):
            directory = output / key / variant
            directory.mkdir(parents=True, exist_ok=True)
            groups, comparison = collect_inline_proof(source)
            (directory / "proof.json").write_text(json.dumps({
                "groups": groups,
                "comparison": comparison,
                "example": EXAMPLES[key],
            }, separators=(",", ":")) + "\n")
            if key == "system" and variant == "upright":
                with TTFont(source, recalcTimestamp=False) as font:
                    font.flavor = "woff2"
                    font.save(assets / (source.stem + ".woff2"))
    choices = []
    for key, config in families.items():
        label = key.title()
        if key == "code" and include_current_code:
            label += " " + config["version"]
        selected = " selected" if key == "system" else ""
        choices.append(f'<option value="{key}"{selected}>{escape(label)}</option>')
    (output / "README.txt").write_text(
        "Daikonic Transit interactive proof\n\n"
        "To open the downloaded proof, run python3 -m http.server 8000 from "
        "this folder, then open http://localhost:8000 in your browser.\n"
    )
    template = Template((TOOLS / "proof_site.html").read_text())
    (output / "index.html").write_text(template.substitute(
        choices="".join(choices), version=escape(RECIPE["version"]), tag=escape(RECIPE["tag"]),
        **viewer_sections(),
    ))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--include-current-code", action="store_true",
                        help="also include the current Code release in a local review")
    args = parser.parse_args()
    build_site(args.output, include_current_code=args.include_current_code)
