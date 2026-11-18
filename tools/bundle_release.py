"""Build and verify one coordinated release containing all three Transit families."""

from pathlib import Path
import argparse
from copy import deepcopy
import hashlib
import gzip
import json
import shutil
import subprocess
import tempfile
import zipfile
import ots
from fontTools.ttLib import TTFont, TTCollection
from adopt_weighting import instance
from export_otf import STYLES
from specimens import ROOT, specimen_families

RECIPE = json.loads((ROOT / "recipes/bundle-release.json").read_text())
OUT = ROOT / "releases" / RECIPE["version"]
TABLES = ["glyf", "hmtx", "cmap", "GSUB", "GPOS", "GDEF", "name", "OS/2"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sanitize(font):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        font.recalcTimestamp = False
        font.save(root / "input.ttf")
        result = subprocess.run(
            [ots.OTS_SANITIZE, str(root / "input.ttf"), str(root / "checked.ttf")],
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr.decode()


def compress_source(directory):
    """Keep large editable XML snapshots portable and below repository file limits."""
    for xml in directory.glob("*.ttx"):
        compressed = xml.with_suffix(".ttx.gz")
        with xml.open("rb") as source, compressed.open("wb") as target:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=target, mtime=0
            ) as stream:
                shutil.copyfileobj(source, stream)
        with gzip.open(compressed, "rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == digest(xml)
        xml.unlink()
    (directory / "rebuild.py").write_text(
        "from pathlib import Path\nimport gzip\nfrom fontTools.ttLib import TTFont\nr=Path(__file__).resolve().parent\nf=TTFont(recalcTimestamp=False)\nwith gzip.open(next(r.glob('*.ttx.gz')), 'rb') as source:\n    f.importXML(source)\nf.save(r/'Rebuilt-VF.ttf')\n"
    )


def build():
    families = specimen_families()
    report = {"version": RECIPE["version"], "tag": RECIPE["tag"], "families": {}}
    assert set(families) == set(RECIPE["families"])
    for key, cfg in families.items():
        directory = OUT / key
        for fmt in ["VF", "TTF", "TTC", "WOFF2", "SOURCE"]:
            (directory / fmt).mkdir(parents=True, exist_ok=True)
        source = ROOT / cfg["font"]
        vf = directory / "VF" / (cfg["stem"] + "-VF.ttf")
        if source.resolve() != vf.resolve():
            shutil.copy2(source, vf)
        font = TTFont(vf, recalcTimestamp=False)
        sanitize(deepcopy(font))
        if key == "code":
            for weight, style in STYLES.items():
                if weight > cfg["heavy"]:
                    continue
                f = instance(vf, weight, None)
                f.recalcTimestamp = False
                names = {
                    1: cfg["name"] if weight == 400 else cfg["name"] + " " + style,
                    2: "Regular",
                    3: cfg["stem"] + "-" + style + " " + cfg["version"],
                    4: cfg["name"] + " " + style,
                    6: cfg["stem"] + "-" + style,
                    16: cfg["name"],
                    17: style,
                }
                for record in f["name"].names:
                    if record.nameID in names:
                        record.string = names[record.nameID].encode(
                            record.getEncoding()
                        )
                f.save(directory / "TTF" / (cfg["stem"] + "-" + style + ".ttf"))
        else:
            for path in (ROOT / "fonts" / key / "TTF").glob("*.ttf"):
                shutil.copy2(path, directory / "TTF" / path.name)
        paths = sorted((directory / "TTF").glob("*.ttf"))
        collection = TTCollection()
        collection.fonts = [TTFont(p, recalcTimestamp=False) for p in paths]
        collection.save(directory / "TTC" / (cfg["stem"] + ".ttc"), shareTables=True)
        font.flavor = "woff2"
        font.save(directory / "WOFF2" / (cfg["stem"] + "-VF.woff2"))
        font.flavor = None
        xml = directory / "SOURCE" / (cfg["stem"] + ".ttx")
        font.saveXML(xml)
        rebuilt = TTFont(recalcTimestamp=False)
        rebuilt.importXML(xml)
        for tag in TABLES + ["gvar", "fvar", "HVAR"]:
            if tag in font:
                assert font.getTableData(tag) == rebuilt.getTableData(tag), (key, tag)
        sanitize(rebuilt)
        compress_source(directory / "SOURCE")
        report["families"][key] = {
            "name": cfg["name"],
            "version": cfg["version"],
            "source": str(source.relative_to(ROOT)),
            "source_sha256": digest(source),
            "static_files": [p.name for p in paths],
            "ttc_faces": len(paths),
            "source_format": "Complete editable TTX with verified rebuild; historical native sources retained in repository.",
        }
        print(
            key,
            len(paths),
            "static styles and one TTC built; editable TTX roundtrip verified",
            flush=True,
        )
    report["files"] = {
        str(p.relative_to(OUT)): digest(p)
        for key in families
        for p in sorted((OUT / key).rglob("*"))
        if p.is_file() and p.name != "selection.json"
    }
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    check()


def check():
    report = json.loads((OUT / "manifest.json").read_text())
    assert set(report["families"]) == set(RECIPE["families"])
    for rel, expected in report["files"].items():
        assert digest(OUT / rel) == expected, rel
    for key, record in report["families"].items():
        assert digest(ROOT / record["source"]) == record["source_sha256"]
        path = next((OUT / key / "TTC").glob("*.ttc"))
        collection = TTCollection(path)
        assert len(collection.fonts) == record["ttc_faces"]
        for face, filename in zip(collection.fonts, record["static_files"]):
            original = TTFont(OUT / key / "TTF" / filename)
            assert "fvar" not in face
            for tag in TABLES:
                if tag in original:
                    assert original.getTableData(tag) == face.getTableData(tag), (
                        key,
                        filename,
                        tag,
                    )
            sanitize(face)
        print(
            key, "TTC faces verified against individual TTFs and sanitized", flush=True
        )


def package():
    check()
    destination = ROOT / ".dist/bundle" / RECIPE["version"]
    destination.mkdir(parents=True, exist_ok=True)
    families = specimen_families()
    otf = json.loads((ROOT / "exports/otf/current/manifest.json").read_text())
    archives = []
    for fmt in ["VF", "TTF", "TTC", "OTF", "WOFF2", "SOURCE", "SPECIMEN"]:
        stem = fmt + "-daikonic-transit-" + RECIPE["version"]
        path = destination / (stem + ".zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for key, cfg in families.items():
                if fmt == "OTF":
                    assert otf[key]["source_sha256"] == digest(ROOT / cfg["font"])
                    files = [
                        (ROOT / item["file"], Path(key) / Path(item["file"]).name)
                        for item in otf[key]["exports"]
                    ]
                    for item in otf[key]["exports"]:
                        assert digest(ROOT / item["file"]) == item["sha256"]
                elif fmt == "SPECIMEN":
                    files = []
                else:
                    files = [
                        (p, Path(key) / p.relative_to(OUT / key / fmt))
                        for p in (OUT / key / fmt).rglob("*")
                        if p.is_file()
                    ]
                for source, member in files:
                    z.write(source, Path(stem) / member)
            if fmt == "SPECIMEN":
                # Manifests select current proofs; historical study images stay in Git.
                paths = {
                    ROOT / "specimens" / name
                    for name in json.loads(
                        (ROOT / "qa/specimen-rendering.json").read_text()
                    )["files"]
                }
                paths.update(
                    ROOT / "specimens/features" / name
                    for name in json.loads(
                        (ROOT / "specimens/features/manifest.json").read_text()
                    )["files"]
                )
                paths.update(
                    ROOT / name
                    for name in json.loads(
                        (ROOT / "qa/readme-feature-rendering.json").read_text()
                    )["files"]
                )
                paths.update(
                    ROOT / "specimens" / name
                    for name in [
                        "README.md",
                        "content.json",
                        "manifest.json",
                        "font-selections.json",
                        "features/manifest.json",
                        "features/Rust-Lifetimes.svg",
                    ]
                )
                for source in sorted(paths):
                    z.write(
                        source,
                        Path(stem)
                        / "specimens"
                        / source.relative_to(ROOT / "specimens"),
                    )
            for name in ["OFL.txt", "NOTICE.txt", "README.md", "requirements.lock"]:
                z.write(ROOT / name, Path(stem) / name)
            z.write(OUT / "manifest.json", Path(stem) / "manifest.json")
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            assert len(z.namelist()) == len(set(z.namelist()))
        archives.append(path)
    (destination / "SHA256SUMS.txt").write_text(
        "".join(digest(p) + "  " + p.name + "\n" for p in archives)
    )
    versions = ", ".join(
        cfg["name"] + " " + cfg["version"] for cfg in families.values()
    )
    (destination / "Release.md").write_text(
        "Daikonic Transit — coordinated release "
        + RECIPE["version"]
        + ".\n\n"
        + versions
        + ".\n\nAll three families are published together. Choose VF for adjustable weights, TTF or OTF for individual styles, or TTC for one collection per family. The System TTC contains all 15 named weight/optical-size combinations; Sans contains five weights and Code three. WOFF2 is for web use. SOURCE provides complete editable TTX snapshots and verified rebuild scripts. SPECIMEN includes matching PNG/PDF and outlined SVG samples.\n\nCode retains the joined Logic enclosures and heavier delimiters. With Logic off, adjacent <> uses ordinary angles whenever only one character qualifies as a delimiter. Both independently qualifying angles stay tall. Logic (ss02) and boundary-centered Rust lifetimes (ss01) remain independently optional and off by default. Book 350 remains the default. Sans and System drawings are unchanged.\n\nValidation includes TTC/TTF table parity and sanitizer checks for every collection face, source roundtrip fidelity, variable shaping and current-font specimens. Native Code Glyphs/UFO sources remain at 1.017; the complete current font is editable through the TTX source package.\n"
    )
    print(destination.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "check", "package"])
    args = parser.parse_args()
    {"build": build, "check": check, "package": package}[args.action]()
