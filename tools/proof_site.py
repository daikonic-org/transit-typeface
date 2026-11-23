"""Generate the public proof site from the coordinated release fonts."""

from argparse import ArgumentParser
from html import escape
from pathlib import Path
from shutil import copyfile
from string import Template

from fontTools.ttLib import TTFont

from bundle_release import OUT, RECIPE, ROOT, release_families
from glyph_proof import build_proof


TOOLS = Path(__file__).resolve().parent
EXAMPLES = {"sans": ("Wayfinding", "Text and signage"),
            "system": ("Legend", "Controls, labels and dashboards")}


def build_site(output):
    assets = output / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    copyfile(TOOLS / "proof_site.css", assets / "proof-site.css")
    for name in ("OFL.txt", "NOTICE.txt"):
        copyfile(ROOT / name, output / name)
    cards = []
    for key, config in release_families().items():
        sample, role = EXAMPLES[key]
        for variant, suffix in (("upright", "-VF"), ("italic", "-Italic-VF")):
            stem = config["stem"] + suffix
            source = OUT / key / "VF" / (stem + ".ttf")
            build_proof(source, output / key / variant, svg_only=True, interactive_axes=True,
                        site_prefix="../../")
            if variant == "upright":
                with TTFont(source, recalcTimestamp=False) as font:
                    font.flavor = "woff2"
                    font.save(assets / (stem + ".woff2"))
        cards.append(f'<section class="family-card {key}">'
                     f'<h2>{escape(key.title())}</h2><p class="role">{escape(role)}</p>'
                     f'<p class="family-sample">{escape(sample)}</p>'
                     f'<div class="proof-links">'
                     f'<a href="{key}/upright/?view=text">Upright <span aria-hidden="true">→</span></a>'
                     f'<a href="{key}/italic/?view=text">Italic <span aria-hidden="true">→</span></a>'
                     '</div></section>')
    template = Template((TOOLS / "proof_site.html").read_text())
    (output / "index.html").write_text(template.substitute(
        cards="\n".join(cards), version=escape(RECIPE["version"]), tag=escape(RECIPE["tag"]),
    ))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    build_site(parser.parse_args().output)
