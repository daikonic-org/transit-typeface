"""Generate the public proof site from the coordinated release fonts."""

from argparse import ArgumentParser
from html import escape
import json
from pathlib import Path
from shutil import copyfile
from string import Template

from fontTools.ttLib import TTFont

from bundle_release import RECIPE, ROOT, release_families, specimen_families
from glyph_proof import collect_proof, write_viewer


TOOLS = Path(__file__).resolve().parent
EXAMPLES = {
    "sans": "Wayfinding",
    "system": "Legend",
    "code": "let result = parse::<Vec<T>>(&'a input);",
}


def build_site(output, *, include_current_code=False):
    assets = output / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    copyfile(TOOLS / "proof_site.css", assets / "proof-site.css")
    copyfile(TOOLS / "proof_site.js", assets / "proof-site.js")
    for name in ("OFL.txt", "NOTICE.txt"):
        copyfile(ROOT / name, output / name)
    families = release_families()
    if include_current_code:
        families["code"] = specimen_families()["code"]
    for key, config in families.items():
        upright = ROOT / config["font"]
        italic = upright.with_name(config["stem"] + "-Italic-VF.ttf")
        for variant, source in (("upright", upright), ("italic", italic)):
            directory = output / key / variant
            _, _, pages, _, rows, comparison = collect_proof(source, directory, interactive_axes=True)
            (directory / "proof.json").write_text(json.dumps({
                "prefix": f"{key}/{variant}/",
                "pages": [(path.name, label) for path, label in pages],
                "rows": rows,
                "comparison": comparison,
                "example": EXAMPLES[key],
            }, separators=(",", ":")) + "\n")
            if key == "system" and variant == "upright":
                first_pages = pages
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
    template = Template((TOOLS / "proof_site.html").read_text())
    controls = template.substitute(choices="".join(choices)).rstrip()
    version, tag = escape(RECIPE["version"]), escape(RECIPE["tag"])
    write_viewer(output, "Try Daikonic Transit", first_pages, [], rows={}, comparison=None, site={
        "prefix": "system/upright/",
        "controls": controls,
        "status": '<p id="face-status" role="status"></p>',
        "navigation": '<div class="masthead">'
                      '<span>Daikonic Transit</span> '
                      f'<a href="https://github.com/daikonic-org/transit-typeface/releases/tag/{tag}">'
                      f'Download {version} <span aria-hidden="true">↗</span></a></div>',
        "footer": '<footer><a href="OFL.txt">Font license</a> '
                  '<a href="https://github.com/daikonic-org/transit-typeface">Source ↗</a></footer>',
        "script": '<script src="assets/proof-site.js"></script>',
    })


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--include-current-code", action="store_true",
                        help="also include the current Code release in a local review")
    args = parser.parse_args()
    build_site(args.output, include_current_code=args.include_current_code)
