"""Render outlined SVG specimens to matched PNG and vector PDF using Chrome."""

import argparse
from html import escape
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET


CHROME = os.environ.get(
    "TRANSIT_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)


def dimensions(source):
    root = ET.parse(source).getroot()
    return tuple(int(float(root.attrib[key])) for key in ("width", "height"))


def chrome(profile, args):
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", f"--user-data-dir={profile}",
         "--hide-scrollbars", "--no-pdf-header-footer", *args],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def render_pdf(sources, output, *, title=None):
    width, height = dimensions(sources[0])
    if any(dimensions(source) != (width, height) for source in sources):
        raise ValueError("Proof pages must all be the same size")
    pages = "".join(f"<section>{source.read_text()}</section>" for source in sources)
    with tempfile.TemporaryDirectory(prefix="transit-render-") as temporary:
        temp = Path(temporary)
        page = temp / "print.html"
        title = title or output.stem
        page.write_text(
            f"<!doctype html><meta charset=utf-8><title>{escape(title)}</title>"
            f"<style>@page{{size:{width}px {height}px;margin:0}}"
            "body{margin:0}svg{display:block}section:not(:last-child){break-after:page}</style>" + pages
        )
        chrome(temp / "profile", [f"--print-to-pdf={output.resolve()}", page.as_uri()])


def render(source, scale=3, *, pdf=True):
    source = Path(source).resolve()
    width, height = dimensions(source)
    with tempfile.TemporaryDirectory(prefix="transit-render-") as temporary:
        chrome(
            Path(temporary) / "profile",
            [f"--force-device-scale-factor={scale}", f"--window-size={width},{height}",
             f"--screenshot={source.with_suffix('.png')}", source.as_uri()],
        )
    if pdf:
        render_pdf([source], source.with_suffix(".pdf"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--scale", type=int, default=3)
    args = parser.parse_args()
    for source in args.sources:
        render(source, args.scale)
        print(source, flush=True)
