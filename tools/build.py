"""Rebuild variable fonts directly from portable compatible masters/metadata."""

from pathlib import Path
import argparse
import json
from fontTools.varLib import build
from fontTools.ttLib import TTFont
from derive_weights import locked
from weighting_support import preserve_layout

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
        if cfg.get("weighting_baseline"):
            baseline = TTFont(ROOT / cfg["weighting_baseline"])
            locks = json.loads((ROOT / "recipes/weights.json").read_text())["defaults"][
                "locks"
            ]
            preserve_layout(
                font,
                baseline,
                locked(baseline, locks),
                **cfg.get("layout_revision", {})
            )
        out = ROOT / ".build" / key
        out.mkdir(parents=True, exist_ok=True)
        dest = out / (cfg["stem"] + "-VF.ttf")
        font.save(dest)
        font.flavor = "woff2"
        font.save(dest.with_suffix(".woff2"))
        print(dest.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    main()
