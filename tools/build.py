"""Rebuild variable fonts directly from portable compatible masters/metadata."""

from pathlib import Path
import argparse
import json
from fontTools.varLib import build

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "family", choices=["all", "sans", "system", "code"], default="all", nargs="?"
    )
    args = parser.parse_args()
    families = json.loads((ROOT / "family.json").read_text())["families"]
    for key, cfg in families.items():
        if args.family not in ["all", key]:
            continue
        sources = ROOT / "sources" / key
        design = (
            next(sources.glob("*TTF.designspace"), None)
            or sources / "DaikonicTransitCodeVF.designspace"
        )
        font, _, _ = build(design, optimize=False)
        font.importXML(sources / "VariableMetadata.ttx")
        out = ROOT / ".build" / key
        out.mkdir(parents=True, exist_ok=True)
        dest = out / (cfg["stem"] + "-VF.ttf")
        font.save(dest)
        font.flavor = "woff2"
        font.save(dest.with_suffix(".woff2"))
        print(dest.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
