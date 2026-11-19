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
import uharfbuzz as hb
from fontTools.ttLib import TTFont, TTCollection
from adopt_weighting import instance
from export_otf import STYLES, convert
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
        "from pathlib import Path\nimport gzip\nfrom fontTools.ttLib import TTFont\n"
        "for path in sorted(Path(__file__).resolve().parent.glob('*.ttx.gz')):\n"
        "    font = TTFont(recalcTimestamp=False)\n"
        "    with gzip.open(path, 'rb') as source:\n"
        "        font.importXML(source)\n"
        "    font.save(path.with_name(path.name.removesuffix('.ttx.gz') + '-VF.ttf'))\n"
    )


def generate_instances(vf, font, directory, config):
    italic = bool(font["OS/2"].fsSelection & 1)
    for item in font["fvar"].instances:
        weight = item.coordinates["wght"]
        optical = item.coordinates.get("opsz")
        style = STYLES[weight]
        if optical is not None:
            style += " " + {10: "Caption", 14: "Text", 36: "Display"}[optical]
        font_style = style + (" Italic" if italic else "")
        stem = config["stem"] + "-" + font_style.replace(" ", "")
        family = config["name"]
        static = instance(vf, weight, optical)
        static.recalcTimestamp = False
        names = {
            1: family if family.endswith("Code") and weight == 400 else family + " " + style,
            2: "Italic" if italic else "Regular",
            3: stem + " " + config["version"],
            4: family + " " + font_style,
            6: stem,
            16: family,
            17: font_style,
        }
        for record in static["name"].names:
            if record.nameID in names:
                record.string = names[record.nameID].encode(record.getEncoding())
        static.save(directory / "TTF" / (stem + ".ttf"))
        convert(static, directory / "OTF" / (stem + ".otf"))


def generate_formats(vf, directory, config):
    font = TTFont(vf, recalcTimestamp=False)
    sanitize(deepcopy(font))
    generate_instances(vf, font, directory, config)
    font.flavor = "woff2"
    font.save(directory / "WOFF2" / vf.with_suffix(".woff2").name)
    font.flavor = None
    xml = directory / "SOURCE" / (vf.stem.removesuffix("-VF") + ".ttx")
    font.saveXML(xml)
    rebuilt = TTFont(recalcTimestamp=False)
    rebuilt.importXML(xml)
    for tag in TABLES + ["gvar", "fvar", "HVAR"]:
        if tag in font:
            assert font.getTableData(tag) == rebuilt.getTableData(tag), (vf.name, tag)
    sanitize(rebuilt)


def build(only=None):
    families = specimen_families()
    report = {"version": RECIPE["version"], "tag": RECIPE["tag"], "families": {}}
    if only:
        report = json.loads((OUT / "manifest.json").read_text())
        report.update(version=RECIPE["version"], tag=RECIPE["tag"])
    assert set(families) == set(RECIPE["families"])
    for key, cfg in families.items():
        if only and key not in only:
            continue
        directory = OUT / key
        for fmt in ["VF", "TTF", "TTC", "OTF", "WOFF2", "SOURCE"]:
            (directory / fmt).mkdir(parents=True, exist_ok=True)
        source = ROOT / cfg["font"]
        vf = directory / "VF" / (cfg["stem"] + "-VF.ttf")
        if source.resolve() != vf.resolve():
            shutil.copy2(source, vf)
        italic = directory / "VF" / (cfg["stem"] + "-Italic-VF.ttf")
        variables = [vf, italic]
        for variant in variables:
            generate_formats(variant, directory, cfg)
        paths = sorted((directory / "TTF").glob("*.ttf"))
        collection = TTCollection()
        collection.fonts = [TTFont(p, recalcTimestamp=False) for p in paths]
        collection.save(directory / "TTC" / (cfg["stem"] + ".ttc"), shareTables=True)
        compress_source(directory / "SOURCE")
        report["families"][key] = {
            "name": cfg["name"],
            "version": cfg["version"],
            "source": str(source.relative_to(ROOT)),
            "source_sha256": digest(source),
            "static_files": [p.name for p in paths],
            "variable_files": [p.name for p in variables],
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
    report["proofs"] = {
        path.name: digest(path) for path in sorted((OUT / "specimens").glob("*"))
    }
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    check()


def check():
    report = json.loads((OUT / "manifest.json").read_text())
    assert report["version"] == RECIPE["version"] and report["tag"] == RECIPE["tag"]
    assert set(report["families"]) == set(RECIPE["families"])
    for rel, expected in report["files"].items():
        assert digest(OUT / rel) == expected, rel
    for name, expected in report["proofs"].items():
        assert digest(OUT / "specimens" / name) == expected, name
    for key, record in report["families"].items():
        assert digest(ROOT / record["source"]) == record["source_sha256"]
        for filename in record["variable_files"]:
            path = OUT / key / "VF" / filename
            variable = TTFont(path)
            sanitize(variable)
            check_repeated_stems(variable, path, key)
            web = TTFont(OUT / key / "WOFF2" / path.with_suffix(".woff2").name)
            for tag in ("cmap", "GSUB", "GPOS", "GDEF", "fvar", "HVAR", "name"):
                assert variable.getTableData(tag) == web.getTableData(tag), (filename, tag)
        path = next((OUT / key / "TTC").glob("*.ttc"))
        collection = TTCollection(path)
        assert len(collection.fonts) == record["ttc_faces"]
        for face, filename in zip(collection.fonts, record["static_files"]):
            original = TTFont(OUT / key / "TTF" / filename)
            otf = TTFont(OUT / key / "OTF" / Path(filename).with_suffix(".otf"))
            assert "fvar" not in face
            for tag in TABLES:
                if tag in original:
                    assert original.getTableData(tag) == face.getTableData(tag), (
                        key,
                        filename,
                        tag,
                    )
            for tag in ("cmap", "hmtx", "GSUB", "GPOS", "GDEF"):
                assert original.getTableData(tag) == otf.getTableData(tag), (filename, tag)
            assert original["post"].italicAngle == otf["CFF "].cff.topDictIndex[0].ItalicAngle
            sanitize(face)
        print(
            key, "TTC faces verified against individual TTFs and sanitized", flush=True
        )
    from code_texture_healing import verify as verify_texture_healing

    verify_texture_healing(
        ROOT / RECIPE["typography"]["code"]["font"],
        OUT / "code" / "VF" / "DaikonicTransitCode-VF.ttf",
    )


def check_repeated_stems(font, path, family):
    engine = hb.Font(hb.Face(path.read_bytes()))
    for instance in font["fvar"].instances:
        engine.set_variations(instance.coordinates)
        glyphs = font.getGlyphSet(location=instance.coordinates)
        for letter in "ft":
            ligature = f"{letter}_{letter}"
            for enable, names in ((True, [ligature]), (False, [letter, letter])):
                buffer = hb.Buffer()
                buffer.add_str(letter * 2)
                buffer.guess_segment_properties()
                hb.shape(engine, buffer, {"liga": enable})
                assert [font.getGlyphName(item.codepoint) for item in buffer.glyph_infos] == names
                if family == "code":
                    assert sum(item.x_advance for item in buffer.glyph_positions) == 1200
            assert abs(glyphs[ligature].width - 2 * glyphs[letter].width) < 0.01


def package():
    check()
    destination = ROOT / ".dist/bundle" / RECIPE["version"]
    destination.mkdir(parents=True, exist_ok=True)
    families = specimen_families()
    archives = []
    for fmt in ["VF", "TTF", "TTC", "OTF", "WOFF2", "SOURCE", "SPECIMEN"]:
        stem = fmt + "-daikonic-transit-" + RECIPE["version"]
        path = destination / (stem + ".zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for key, cfg in families.items():
                if fmt == "SPECIMEN":
                    files = []
                else:
                    files = [
                        (p, Path(key) / p.relative_to(OUT / key / fmt))
                        for p in (OUT / key / fmt).rglob("*")
                        if p.is_file()
                    ]
                for source, member in files:
                    z.write(source, Path(stem) / member)
                if fmt == "WOFF2":
                    z.writestr(
                        str(Path(stem) / key / "font.css"),
                        "".join(
                            "@font-face { "
                            f"font-family: '{cfg['name']}'; "
                            f"src: url('./{cfg['stem']}{suffix}-VF.woff2') format('woff2'); "
                            f"font-weight: {cfg['light']} {cfg['heavy']}; font-style: {style}; "
                            "font-display: swap; }\n"
                            for suffix, style in (("", "normal"), ("-Italic", "italic"))
                        ),
                    )
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
                for source in sorted((OUT / "specimens").glob("*")):
                    z.write(source, Path(stem) / "specimens" / source.name)
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
    notes = [
        "Daikonic Transit — coordinated release " + RECIPE["version"] + ".",
        versions + ". All three families ship together as a normal release.",
        "All three families add 9° italics with a single-storey `a`, a descending `f` and an open, single-storey `g`. Code’s italic `i` has a rightward foot. System Italic carries the Caption, Text and Display optical-size presets.",
        "The `liga` feature adds optically fitted `ff` and `tt` pairs in upright and italic. Code’s pairs occupy exactly two cells. Its upright also adds optional texture healing (`ss03`) for `m` and `w` near `a`, `i`, `j` and `l`.",
        "The **VF** and **WOFF2** packages include upright and italic variable fonts. **TTF** and **OTF** contain named styles, and **TTC** includes one collection per family. **SOURCE** contains editable TTX and a verified rebuild script. **SPECIMEN** includes PNG, PDF and outlined SVG proofs. `SHA256SUMS.txt` covers all seven archives.",
        "Native Code Glyphs/UFO sources remain at 1.017; the full current drawings and layout are editable through the TTX source package.",
    ]
    (destination / "Release.md").write_text("\n\n".join(notes) + "\n")
    print(destination.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "check", "package"])
    args = parser.parse_args()
    {"build": build, "check": check, "package": package}[args.action]()
