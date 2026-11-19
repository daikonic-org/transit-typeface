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
from export_otf import STYLES, convert, optical_styles
from specimens import ROOT, specimen_families
from font_size_calibration import NEW_POINT_SIZE, recalibrate

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
    optical_names = optical_styles(font)
    for item in font["fvar"].instances:
        weight = item.coordinates["wght"]
        optical = item.coordinates.get("opsz")
        style = " ".join(filter(None, (STYLES[weight], optical_names[optical])))
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
    for tag in TABLES + ["head", "STAT", "gvar", "fvar", "HVAR"]:
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
        settings = RECIPE["typography"][key]
        previous_size = settings.get("previous_point_size", NEW_POINT_SIZE)
        em = round(1000 * NEW_POINT_SIZE / previous_size)
        for filename in record["variable_files"]:
            path = OUT / key / "VF" / filename
            variable = TTFont(path)
            assert variable["name"].getDebugName(16) == record["name"], filename
            assert variable["name"].getDebugName(5) == "Version " + record["version"], filename
            assert variable["head"].unitsPerEm == em, filename
            sanitize(variable)
            check_repeated_stems(variable, path, key)
            if key == "system":
                source = ROOT / settings["italic_font" if "-Italic" in filename else "font"]
                check_system_calibration(TTFont(source), variable, previous_size)
            web = TTFont(OUT / key / "WOFF2" / path.with_suffix(".woff2").name)
            assert variable["head"].unitsPerEm == web["head"].unitsPerEm, filename
            for tag in ("cmap", "GSUB", "GPOS", "GDEF", "fvar", "STAT", "HVAR", "name"):
                assert variable.getTableData(tag) == web.getTableData(tag), (filename, tag)
        path = next((OUT / key / "TTC").glob("*.ttc"))
        collection = TTCollection(path)
        assert len(collection.fonts) == record["ttc_faces"]
        for face, filename in zip(collection.fonts, record["static_files"]):
            original = TTFont(OUT / key / "TTF" / filename)
            otf = TTFont(OUT / key / "OTF" / Path(filename).with_suffix(".otf"))
            assert "fvar" not in face
            assert all(f["head"].unitsPerEm == em for f in (face, original, otf)), filename
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
        ROOT / RECIPE["typography"]["code"]["unhealed_font"],
        OUT / "code" / "VF" / "DaikonicTransitCode-VF.ttf",
        default_on=True,
    )


def check_system_calibration(source, font, previous_size):
    recalibrate(source, previous_size)
    assert source["head"].unitsPerEm == font["head"].unitsPerEm
    for tag in ("glyf", "gvar", "hmtx", "HVAR", "fvar", "STAT", "GSUB", "GPOS"):
        assert source.getTableData(tag) == font.getTableData(tag), ("System calibration", tag)


def check_repeated_stems(font, path, family):
    engine = hb.Font(hb.Face(path.read_bytes()))
    caret_table = font["GDEF"].table.LigCaretList
    carets = dict(zip(caret_table.Coverage.glyphs, caret_table.LigGlyph))
    for instance in font["fvar"].instances:
        engine.set_variations(instance.coordinates)
        glyphs = font.getGlyphSet(location=instance.coordinates)
        for letter in ("ftl" if family == "code" else "ft"):
            ligature = f"{letter}_{letter}"
            for enable, names in ((True, [ligature]), (False, [letter, letter])):
                buffer = hb.Buffer()
                buffer.add_str(letter * 2)
                buffer.guess_segment_properties()
                hb.shape(engine, buffer, {"liga": enable})
                assert [font.getGlyphName(item.codepoint) for item in buffer.glyph_infos] == names
                if family == "code":
                    assert sum(item.x_advance for item in buffer.glyph_positions) == 1200
                    assert [v.Coordinate for v in carets[ligature].CaretValue] == [600]
            assert abs(glyphs[ligature].width - 2 * glyphs[letter].width) < 0.01
        if family == "code":
            assert font["glyf"]["i"].yMin == font["glyf"]["n"].yMin
            accented = hb.Buffer()
            accented.add_str("ll\u0301")
            accented.guess_segment_properties()
            hb.shape(engine, accented)
            assert all(font.getGlyphName(g.codepoint) != "l_l" for g in accented.glyph_infos)


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
        "- **System** recalibrates point sizing in upright and italic. The new 12 pt setting matches the previous 11 pt setting and preserves the taller lowercase proportions. Caption, Text and Display now correspond to about 10.91, 15.27 and 39.27 pt.",
        "- **Code** recalibrates 12 pt to the previous 11.5 pt scale in upright and italic. It aligns the foot of `i` with the lowercase baseline, refits the `ff` and `tt` crossbars, and adds an `ll` ligature. Each pair keeps its grid-aligned stems, two-cell advance and middle caret.",
        "- **Code Upright** applies texture healing by default with `calt`. Wider `m` and `w` fit beside selected punctuation as well as `a`, `i`, `j` and `l`. Enable `ss04` to opt out while keeping other contextual features active.",
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
