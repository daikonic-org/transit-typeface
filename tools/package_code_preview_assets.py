"""Format-separated preview archives and a portable editable TTX source snapshot."""

from pathlib import Path
import hashlib
import json
import subprocess
import zipfile
from fontTools.ttLib import TTFont
import ots
from adopt_weighting import ROOT
from package_code_preview import PREVIEWS, check_preview


def main():
    version = PREVIEWS["latest"]
    preview = ROOT / "previews" / f"code-{version}"
    check_preview(preview)
    out = ROOT / ".dist/code-preview" / version
    out.mkdir(parents=True, exist_ok=True)
    work = ROOT / ".build/code-preview-source" / version
    work.mkdir(parents=True, exist_ok=True)
    vf = preview / "VF/DaikonicTransitCode-VF.ttf"
    font = TTFont(vf)
    font.recalcTimestamp = False
    xml = work / "DaikonicTransitCode.ttx"
    font.saveXML(xml)
    rebuilt = TTFont(recalcTimestamp=False)
    rebuilt.importXML(xml)
    rebuilt_path = work / "Rebuilt-VF.ttf"
    rebuilt.save(rebuilt_path)
    actual = TTFont(rebuilt_path)
    for tag in ["glyf", "gvar", "hmtx", "GSUB", "GPOS", "GDEF", "cmap", "fvar", "HVAR"]:
        assert font.getTableData(tag) == actual.getTableData(tag), tag
    subprocess.run(
        [ots.OTS_SANITIZE, str(rebuilt_path), str(work / "checked.ttf")],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    woff = work / "DaikonicTransitCode-VF.woff2"
    font.flavor = "woff2"
    font.save(woff)
    (work / "rebuild.py").write_text(
        "from pathlib import Path\nfrom fontTools.ttLib import TTFont\nr=Path(__file__).resolve().parent\nf=TTFont(recalcTimestamp=False)\nf.importXML(r/'DaikonicTransitCode.ttx')\nf.save(r/'DaikonicTransitCode-VF.ttf')\n"
    )
    (work / "SOURCE.md").write_text(
        "Editable full-font TTX snapshot for Code "
        + version
        + ". Rebuild with `python rebuild.py` after installing fonttools. Outline, variation, layout and metrics tables were verified against the packaged VF after XML roundtrip. The scripted design recipe and earlier trials remain in the repository tools/ and trials/ folders. Released native Glyphs/UFO sources remain at their separately documented version.\n"
    )
    (work / "font.css").write_text(
        "@font-face { font-family: 'Daikonic Transit Code'; src: url('./DaikonicTransitCode-VF.woff2') format('woff2'); font-weight: 300 400; font-style: normal; font-display: swap; }\n"
    )
    groups = {
        "VF": list((preview / "VF").glob("*.ttf")),
        "TTF": list((preview / "TTF").glob("*.ttf")),
        "WOFF2": [woff, work / "font.css"],
        "SOURCE": [
            xml,
            work / "rebuild.py",
            work / "SOURCE.md",
            ROOT / "requirements.lock",
        ],
        "SPECIMEN": list((preview / "specimens").glob("*"))
        + [
            ROOT / "specimens" / ("Transit-Family" + ext)
            for ext in [".png", ".pdf", ".svg"]
        ],
    }
    assets = []
    for kind, files in groups.items():
        slug = f"{kind}-daikonic-transit-code-{version}-preview"
        archive = out / (slug + ".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for p in files + [
                preview / "README.md",
                preview / "selection.json",
                ROOT / "OFL.txt",
                ROOT / "NOTICE.txt",
            ]:
                z.write(p, Path(slug) / p.name)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
        assets.append(archive)
    (out / "SHA256SUMS.txt").write_text(
        "".join(
            hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
            for p in assets
        )
    )
    (out / "Release.md").write_text(
        "Daikonic Transit Code "
        + version
        + " working preview adopts the original two-storey `a` inside an open, rounded `c` wrap. The stroke gradually tapers into the upper arch. The lower terminal turns gently upward with a vertical cut perpendicular to the baseline.\n\nIncludes all prior Code character, delimiter, underscore, hyphen, spacing and operator-ligature refinements. Family name remains **Daikonic Transit Code**; Book350 remains the default. Variable range300–400, plus Light/Book/Regular snapshots.\n\nChoose **VF** or **TTF** for installation; **WOFF2** is for web use. **SOURCE** contains an editable full-font TTX snapshot with a verified portable rebuild. **SPECIMEN** includes matched PNG/PDF and editable SVG panels. Earlier cuts and stable releases are preserved; Sans and System fonts are unchanged. Released native Glyphs/UFO sources remain at their separately documented versions.\n\nValidation: four sanitized preview fonts, source/table fidelity, named snapshots, 11 interpolation/shaping weights, retained operators and repeated-@ fitting. TTX source roundtrip matches outline, variation, layout and metric tables and passes OTS.\n"
    )
    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
