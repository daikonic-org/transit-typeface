"""Package additive OTF exports and clearly separated optical review fonts."""

from pathlib import Path
import hashlib
import json
import zipfile
from fontTools.ttLib import TTFont
from specimens import ROOT

OUT = ROOT / ".dist/layout-optical/2026-11-17"
TRIAL = ROOT / "trials/2026-11-17-layout-optical"


def archive(name, files, notes):
    path = OUT / (name + ".zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for p, relative in files:
            z.write(p, Path(name) / relative)
        for n in ["OFL.txt", "NOTICE.txt"]:
            z.write(ROOT / n, Path(name) / n)
        z.writestr(str(Path(name) / "README.md"), notes)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
    return path


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assets = []
    current = json.loads((ROOT / "exports/otf/current/manifest.json").read_text())
    for key, version in [
        ("sans", "0.109R"),
        ("system", "0.117R"),
        ("code", "1.023-preview"),
    ]:
        files = [
            (ROOT / r["file"], Path(r["file"]).name) for r in current[key]["exports"]
        ]
        files.append((ROOT / "exports/otf/current/manifest.json", "manifest.json"))
        assets.append(
            archive(
                f"OTF-daikonic-transit-{key}-{version}",
                files,
                "Static CFF OpenType exports of the same named TTF instances. Layout/metrics match; every font passes OTS and every glyph bound agrees within0.05units. Install either OTF or TTF snapshots, or the variableTTF.\n",
            )
        )
    optical = json.loads((TRIAL / "optical-fonts.json").read_text())
    assets.append(
        archive(
            "VF-daikonic-transit-optical-trials-2026-11-17",
            [(ROOT / p, Path(p).name) for p in optical.values()]
            + [(ROOT / "docs/layout-optical.md", "Design.md")],
            "Separate Sans/Code Optical Study families: wght and opsz10–36(default14). Default drawings match existing fonts. Review endpoints before adopting; installed Code1.023 remains weight-only.\n",
        )
    )
    data = json.loads((ROOT / "exports/otf/optical-trial/manifest.json").read_text())
    files = [
        (ROOT / r["file"], Path(r["file"]).name)
        for key in ("sans", "code")
        for r in data[key]["exports"]
    ]
    assets.append(
        archive(
            "OTF-daikonic-transit-optical-trials-2026-11-17",
            files,
            "Static CFF snapshots of the Sans/Code Optical Study families at all named weights and opsz10/14/36. Review fonts, separate from approved releases.\n",
        )
    )
    source = ROOT / ".build/optical-source"
    source.mkdir(parents=True, exist_ok=True)
    files = []
    for rel in optical.values():
        p = ROOT / rel
        xml = source / (p.stem + ".ttx")
        f = TTFont(p)
        f.saveXML(xml)
        # Standalone source roundtrip preserves complete binary table functions.
        g = TTFont(recalcTimestamp=False)
        g.importXML(xml)
        target = source / p.name
        g.save(target)
        h = TTFont(target)
        for tag in ["glyf", "gvar", "GPOS", "GSUB", "GDEF", "HVAR", "hmtx", "cmap"]:
            assert f.getTableData(tag) == h.getTableData(tag), (p.name, tag)
        files.append((xml, xml.name))
    rebuild = source / "rebuild.py"
    rebuild.write_text(
        "from pathlib import Path\nfrom fontTools.ttLib import TTFont\nfor p in Path(__file__).resolve().parent.glob('*.ttx'):\n f=TTFont(recalcTimestamp=False)\n f.importXML(p)\n f.save(p.with_suffix('.ttf'))\n"
    )
    files += [
        (rebuild, "rebuild.py"),
        (ROOT / "recipes/optical-trial.json", "optical-trial.json"),
        (ROOT / "docs/layout-optical.md", "Design.md"),
    ]
    assets.append(
        archive(
            "SOURCE-daikonic-transit-optical-trials-2026-11-17",
            files,
            "Editable complete TTX review fonts. Install fonttools and run python rebuild.py. Outline/variation/layout/metric tables verified after roundtrip. Design scripts and pinned input provenance are in the transit-typeface repository.\n",
        )
    )
    files = [
        (TRIAL / (name + ext), name + ext)
        for name in ["Positioning", "Optical-Sans", "Optical-Code"]
        for ext in [".png", ".pdf", ".svg"]
    ] + [
        (TRIAL / "Browser.html", "Browser.html"),
        (TRIAL / "Browser.png", "Browser.png"),
        (TRIAL / "Interactive.html", "Interactive.html"),
        (TRIAL / "Interactive.png", "Interactive.png"),
        (TRIAL / "validation.json", "validation.json"),
    ]
    assets.append(
        archive(
            "SPECIMEN-daikonic-transit-layout-optical-2026-11-17",
            files,
            "Matched PNG/PDF/SVG proofs for Code accent attachment and Sans/Code optical endpoints. Browser proof embeds real font snapshots.\n",
        )
    )
    (OUT / "SHA256SUMS.txt").write_text(
        "".join(
            hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
            for p in assets
        )
    )
    print(OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
