"""Create format-separated release assets and notes; never publish implicitly."""

from pathlib import Path
import hashlib
import json
import zipfile
import argparse
from fontTools.ttLib import TTFont
from derive_weights import locked

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--family", choices=["all", "sans", "system", "code"], default="all"
    )
    args = parser.parse_args()
    families = json.loads((ROOT / "family.json").read_text())["families"]
    for key, cfg in families.items():
        if args.family not in ("all", key):
            continue
        version = cfg["version"] + "R"
        slug = f"daikonic-transit-{key}-{version}"
        out = ROOT / ".dist" / key / cfg["version"]
        out.mkdir(parents=True, exist_ok=True)
        groups = {
            "TTF": list((ROOT / "fonts" / key / "TTF").glob("*.ttf")),
            "VF": list((ROOT / "fonts" / key / "VF").glob("*.ttf")),
            "WOFF2": list((ROOT / "fonts" / key / "WOFF2").glob("*.woff2")),
            "SOURCE": [p for p in (ROOT / "sources" / key).rglob("*") if p.is_file()],
            "SPECIMEN": [
                ROOT / "specimens" / ("Transit" + key.title() + suffix)
                for suffix in [".png", ".pdf", ".svg"]
            ]
            + [ROOT / p for p in cfg.get("specimen_extras", [])],
        }
        for fmt, files in groups.items():
            archive = out / f"{fmt}-{slug}.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                prefix = Path(f"{fmt}-{slug}")
                for p in sorted(files):
                    name = (
                        p.relative_to(ROOT / "sources" / key)
                        if fmt == "SOURCE"
                        else (
                            Path(
                                (
                                    cfg["stem"]
                                    if p.stem.startswith("Transit")
                                    else p.parent.name
                                )
                                + p.suffix
                            )
                            if fmt == "SPECIMEN"
                            else Path(p.name)
                        )
                    )
                    z.write(p, prefix / name)
                for notice in ["OFL.txt", "NOTICE.txt"]:
                    z.write(ROOT / notice, prefix / notice)
                z.writestr(
                    str(prefix / "README.txt"),
                    f"{cfg['title']} {cfg['version']} - {fmt}\nVariable range {cfg['light']}-{cfg['heavy']}; default {cfg['display']}.\nSee https://github.com/daikonic-org/transit-typeface for source, audit and build notes.\n",
                )
                if fmt == "SOURCE":
                    z.write(ROOT / "requirements.lock", prefix / "requirements.lock")
                    z.write(ROOT / "docs/build.md", prefix / "BUILD.md")
                    extra = ""
                    if cfg.get("weighting_baseline"):
                        z.write(
                            ROOT / cfg["weighting_baseline"],
                            prefix / "WeightingBaseline.ttf",
                        )
                        z.write(
                            ROOT / "tools/weighting_support.py",
                            prefix / "weighting_support.py",
                        )
                        config = json.loads((ROOT / "recipes/weights.json").read_text())
                        protected = sorted(
                            locked(
                                TTFont(ROOT / cfg["weighting_baseline"]),
                                config["defaults"]["locks"],
                            )
                        )
                        z.writestr(
                            str(prefix / "SelectedGlyphs.json"), json.dumps(protected)
                        )
                        z.writestr(
                            str(prefix / "LayoutRevision.json"),
                            json.dumps(cfg.get("layout_revision", {})),
                        )
                        extra = "from fontTools.ttLib import TTFont\nimport json\nfrom weighting_support import preserve_layout\npreserve_layout(f,TTFont(r/'WeightingBaseline.ttf'),set(json.loads((r/'SelectedGlyphs.json').read_text())),**json.loads((r/'LayoutRevision.json').read_text()))\n"
                    z.writestr(
                        str(prefix / "rebuild.py"),
                        "from pathlib import Path\nfrom fontTools.varLib import build\nr=Path(__file__).resolve().parent\nd=next(r.glob('*TTF.designspace'),None) or r/'DaikonicTransitCodeVF.designspace'\nf,_,_=build(d,optimize=False)\nf.importXML(r/'VariableMetadata.ttx')\n"
                        + extra
                        + "f.save(r/'Rebuilt-VF.ttf')\n",
                    )
                if fmt == "WOFF2":
                    z.writestr(
                        str(prefix / "font.css"),
                        f"@font-face {{\n  font-family: '{cfg['name']}';\n  src: url('./{cfg['stem']}-VF.woff2') format('woff2');\n  font-weight: {cfg['light']} {cfg['heavy']};\n  font-style: normal;\n  font-display: swap;\n}}\n",
                    )
            with zipfile.ZipFile(archive) as z:
                assert z.testzip() is None
        sums = "".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
            for p in sorted(out.glob("*.zip"))
        )
        (out / f"SHA256SUMS-{slug}.txt").write_text(sums)
        title = f"Fonts version {cfg['version']} — {cfg['title']} (TTF, VF, WOFF2)"
        notes = f"""{cfg['title']}, version {cfg['version']}.

{cfg.get('release_summary', 'This release standardizes the public names and download packages as Daikonic Transit Sans, Daikonic Transit System and Daikonic Transit Code. Code no longer includes a cell-width suffix in font menus or filenames. Letterforms, weights, spacing and ligatures are unchanged from the preceding releases.')}

- **TTF**: named static weights ({len(groups['TTF'])} files).
- **VF**: installable variable TrueType font, weight{cfg['light']}–{cfg['heavy']}, default{cfg['display']}.
- **WOFF2**: variable webfont and CSS.
- **SOURCE**: editable Glyphs/UFO/designspace plus compatible TTF masters/metadata.
- **SPECIMEN**: PNG, vector PDF and outlined SVG panel{', plus named and intermediate hook comparisons' if cfg.get('specimen_extras') else ''}.
- **SHA256SUMS**: archive checksums.

{'A monospaced companion for code and terminals, with Light, Book and Regular weights, twelve coding ligatures and ligature caret positions.' if key=='code'else 'A proportional typeface with Light, Book, Regular, Medium and SemiBold weights.'}
{'System includes an optical-size range of 10–36 and optional tabular figures.'if key=='system'else ''}

Install either the variable font or the static styles. These releases contain upright styles. See the [README](https://github.com/daikonic-org/transit-typeface#readme) for family descriptions, features and credits.

Validation: OpenType Sanitizer, static/VF parity, source rebuilds and HarfBuzz shaping. Weighting validation covers intermediate positions and independent editable-source rebuilds. Earlier native Core Text checks describe prior releases; they were not repeated for this update. Font files retain OFL1.1 and original notices.
"""
        (out / "Release.md").write_text(notes)
        (out / "release.json").write_text(
            json.dumps(
                {
                    "tag": cfg["tag"],
                    "title": title,
                    "family": key,
                    "version": cfg["version"],
                    "assets": [
                        p.name
                        for p in sorted(out.iterdir())
                        if p.suffix == ".zip" or p.name.startswith("SHA256SUMS")
                    ],
                },
                indent=2,
            )
            + "\n"
        )
        print(
            key,
            cfg["tag"],
            len(groups["TTF"]),
            "static TTFs; five verified archives",
            flush=True,
        )


if __name__ == "__main__":
    main()
