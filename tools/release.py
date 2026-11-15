"""Create format-separated release assets and notes; never publish implicitly."""

from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    families = json.loads((ROOT / "family.json").read_text())["families"]
    for key, cfg in families.items():
        version = cfg["version"] + "R"
        slug = f"transit-{key}-{version}"
        out = ROOT / ".dist" / key
        out.mkdir(parents=True, exist_ok=True)
        groups = {
            "TTF": list((ROOT / "fonts" / key / "TTF").glob("*.ttf")),
            "VF": list((ROOT / "fonts" / key / "VF").glob("*.ttf")),
            "WOFF2": list((ROOT / "fonts" / key / "WOFF2").glob("*.woff2")),
            "SOURCE": [p for p in (ROOT / "sources" / key).rglob("*") if p.is_file()],
            "SPECIMEN": [
                ROOT / "specimens" / ("Transit" + key.title() + suffix)
                for suffix in [".png", ".pdf", ".svg"]
            ],
        }
        for fmt, files in groups.items():
            archive = out / f"{fmt}-{slug}.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                prefix = Path(f"{fmt}-{slug}")
                for p in sorted(files):
                    name = (
                        p.relative_to(ROOT / "sources" / key)
                        if fmt == "SOURCE"
                        else Path(p.name)
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
                    z.writestr(
                        str(prefix / "rebuild.py"),
                        "from pathlib import Path\nfrom fontTools.varLib import build\nr=Path(__file__).resolve().parent\nd=next(r.glob('*TTF.designspace'),None) or r/'DaikonicTransitCodeVF.designspace'\nf,_,_=build(d,optimize=False)\nf.importXML(r/'VariableMetadata.ttx')\nf.save(r/'Rebuilt-VF.ttf')\n",
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

Initial public release of the current reviewed upright family. Format-separated downloads follow Adobe Source Sans's release layout. All named static weights are snapshots of the variable font.

- **TTF**: named static weights ({len(groups['TTF'])} files).
- **VF**: installable variable TrueType font, weight{cfg['light']}–{cfg['heavy']}, default{cfg['display']}.
- **WOFF2**: variable webfont and CSS.
- **SOURCE**: editable Glyphs/UFO/designspace plus compatible TTF masters/metadata.
- **SPECIMEN**: PNG, vector PDF and outlined SVG panel.
- **SHA256SUMS**: archive checksums.

Concave acute arrows with extended wings and matching double-rail clearance are included. {'Code preserves600-unit cells and twelve operator ligatures with caret positions.' if key=='code'else 'The proportional family and its reviewed letter/numeral choices are retained.'}
{'System also has opsz10–36, separate ai/li letters, optional tabular figures and the selected clean y.'if key=='system'else ''}

No italic,700-weight,OTF or legacy WOFF files are claimed. Install VF or static TTFs as alternatives. See the repository's generation audit for measured counter/weight behavior and current Code mark-positioning limitations.

Validation: OpenType Sanitizer, static/VF parity, source rebuilds and HarfBuzz shaping. Earlier native Core Text/Glyphs checks are recorded in qa/. Font files retain OFL1.1 and original notices.
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
