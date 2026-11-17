"""Render outlined SVG specimens to matched PNG and vector PDF using Chrome."""

import argparse
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET


def render(source, scale=3):
    source = Path(source).resolve()
    root = ET.parse(source).getroot()
    width, height = (int(float(root.attrib[k])) for k in ("width", "height"))
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    with tempfile.TemporaryDirectory(prefix="transit-render-") as temporary:
        temp = Path(temporary)
        common = [
            chrome,
            "--headless",
            "--disable-gpu",
            f"--user-data-dir={temp / 'profile'}",
            "--hide-scrollbars",
            "--no-pdf-header-footer",
        ]
        subprocess.run(
            common
            + [
                f"--force-device-scale-factor={scale}",
                f"--window-size={width},{height}",
                f"--screenshot={source.with_suffix('.png')}",
                source.as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        page = temp / "print.html"
        page.write_text(
            f"<!doctype html><style>@page{{size:{width}px {height}px;margin:0}}"
            "body{margin:0}svg{display:block}</style>" + source.read_text()
        )
        subprocess.run(
            common + [f"--print-to-pdf={source.with_suffix('.pdf')}", page.as_uri()],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--scale", type=int, default=3)
    args = parser.parse_args()
    for source in args.sources:
        render(source, args.scale)
        print(source, flush=True)
