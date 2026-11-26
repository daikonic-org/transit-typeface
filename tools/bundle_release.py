"""Build and verify the selected Transit families for a release."""

from pathlib import Path
from collections import Counter
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

RECIPE = json.loads((ROOT / "recipes/bundle-release.json").read_text())
OUT = ROOT / "releases" / RECIPE["version"]
TABLES = ["glyf", "hmtx", "cmap", "GSUB", "GPOS", "GDEF", "name", "OS/2"]
LICENSE_FILES = ("OFL.txt", "NOTICE.txt", "upstream/AUTHORS.txt", "upstream/OFL.txt", "upstream/PROVENANCE.json")


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
    if any(axis.axisTag == "wdth" for axis in font["fvar"].axes):
        from code_weight_width_trial import WIDTH_PRESETS, name_trial
        from fontTools.varLib.instancer import instantiateVariableFont

        axis = next(axis for axis in font["fvar"].axes if axis.axisTag == "wdth")
        coords = sorted({tuple(sorted((tag, value) for tag, value in item.coordinates.items() if tag != "wdth"))
                         for item in font["fvar"].instances})
        for pairs in coords:
            location = dict(pairs)
            labels = STYLES[location["wght"]], optical_names[location.get("opsz")]
            style = " ".join(filter(None, labels))
            for width in (width for width in WIDTH_PRESETS if axis.minValue <= width <= axis.maxValue):
                static = instantiateVariableFont(font, location | {"wdth": width})
                stem = name_trial(static, config["name"], style, width)
                snapshot = directory / "TTF" / (stem + ".ttf")
                static.save(snapshot)
                with TTFont(snapshot) as compiled:
                    convert(compiled, directory / "OTF" / (stem + ".otf"))
        return
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


def release_families():
    selections = specimen_families()
    assert set(RECIPE["families"]) <= set(RECIPE["typography"])
    return {key: selections[key] for key in RECIPE["families"]}


def build(only=None):
    families = release_families()
    report = {"version": RECIPE["version"], "tag": RECIPE["tag"], "families": {}}
    if only:
        report = json.loads((OUT / "manifest.json").read_text())
        report.update(version=RECIPE["version"], tag=RECIPE["tag"])
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
        paths = sorted((directory / "TTF").glob("*.ttf"))
        if not RECIPE["typography"][key].get("reuse"):
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
        print(key, len(paths), "static styles and one TTC staged", flush=True)
    report["files"] = {
        str(p.relative_to(OUT)): digest(p)
        for key in families
        for p in sorted((OUT / key).rglob("*"))
        if p.is_file() and p.name != "selection.json"
    }
    report["proofs"] = {
        str(path.relative_to(OUT / "specimens")): digest(path)
        for path in sorted((OUT / "specimens").rglob("*")) if path.is_file()
    }
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    check()


def check_sans_coverage(prior_path, current):
    """Check the rebuilt Sans against its previously released counterpart."""
    with TTFont(prior_path) as prior:
        names = prior.getGlyphOrder()
        assert current.getGlyphOrder()[:len(names)] == names
        for tag in ("cmap", "GSUB", "GDEF"):
            assert current.getTableData(tag) == prior.getTableData(tag), (prior_path, tag)
        assert all(current["glyf"][name].numberOfContours != 0
                   for name in names if prior["glyf"][name].numberOfContours != 0)
        assert current["post"].italicAngle == prior["post"].italicAngle
        def weight_settings(font):
            return (
                [(axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue)
                 for axis in font["fvar"].axes],
                [(instance.coordinates, font["name"].getDebugName(instance.subfamilyNameID))
                 for instance in font["fvar"].instances],
            )

        assert weight_settings(current) == weight_settings(prior)
        if current["post"].italicAngle == 0:
            assert current.getTableData("GPOS") == prior.getTableData("GPOS")
        else:
            features = lambda font: Counter(
                entry.FeatureTag for entry in font["GPOS"].table.FeatureList.FeatureRecord
            )
            assert features(current) == features(prior)
            layout = lambda font: font["GPOS"].table.LookupList.Lookup
            assert not Counter(k.LookupType for k in layout(prior)) - Counter(k.LookupType for k in layout(current))


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
        prior = ROOT / settings["font"]
        em = TTFont(prior)["head"].unitsPerEm
        if settings.get("reuse"):
            previous = json.loads((prior.parents[2] / "manifest.json").read_text())
            for filename, expected in previous["files"].items():
                if filename.startswith(key + "/"):
                    assert report["files"][filename] == expected, filename
        for filename in record["variable_files"]:
            path = OUT / key / "VF" / filename
            variable = TTFont(path)
            assert variable["name"].getDebugName(16) == record["name"], filename
            assert variable["name"].getDebugName(5) == "Version " + record["version"], filename
            assert variable["head"].unitsPerEm == em, filename
            if settings.get("metadata_source") or settings.get("rebuild_code"):
                from release_metadata import verify_release_metadata

                verify_release_metadata(variable, record)
            if settings.get("metadata_source"):
                with TTFont(ROOT / settings["metadata_source"] / filename) as prior_face:
                    for tag in ("cmap", "glyf", "gvar", "hmtx", "GSUB", "GPOS", "GDEF", "fvar", "STAT"):
                        assert prior_face.getTableData(tag) == variable.getTableData(tag), (filename, tag)
            sanitize(variable)
            check_repeated_stems(variable, path, key)
            if settings.get("sans_rebuild"):
                check_sans_coverage(ROOT / settings["italic_font" if "-Italic" in filename else "font"], variable)
            if settings.get("rebuild_code"):
                from release_code import verify_release

                verify_release(
                    variable, path, ROOT / "releases/2026.11.20/code/VF" / filename,
                    shift_intermediate_texture=settings.get("shift_intermediate_texture", False),
                    working_spacing=settings.get("working_spacing", False),
                )
                if settings.get("capital_spacing_source"):
                    from code_capital_spacing import verify

                    verify(ROOT / settings["capital_spacing_source"] / filename, path, wider=True, smart=True)
            elif key == "code" and not settings.get("reuse"):
                from code_hairline_toggle import check_release

                reference = ROOT / settings["italic_font" if "-Italic" in filename else "font"]
                if settings.get("punctuation"):
                    from code_punctuation_size import release_font

                    expected = release_font(reference, record["name"], record["version"])
                    for tag in ("glyf", "gvar", "hmtx", "cmap", "GSUB", "GPOS", "GDEF", "fvar", "STAT", "HVAR"):
                        assert variable.getTableData(tag) == expected.getTableData(tag), (filename, tag)
                elif settings.get("self_aligning"):
                    if "-Italic" in filename:
                        baseline = TTFont(reference)
                        for tag in ("glyf", "gvar", "hmtx", "cmap", "GSUB", "GPOS", "GDEF"):
                            assert variable.getTableData(tag) == baseline.getTableData(tag), tag
                    elif settings.get("default_hairlining"):
                        from code_compact_operators import build as build_operators, verify as verify_operators
                        from code_hairline_toggle import verify_default

                        operator_source = ROOT / settings["operator_source"]
                        with tempfile.TemporaryDirectory() as temporary:
                            plain = Path(temporary) / "Plain-Operators.ttf"
                            build_operators(operator_source).save(plain)
                            verify_operators(operator_source, plain)
                            verify_default(plain, path)
                    else:
                        from code_compact_operators import verify

                        verify(reference, path)
                else:
                    check_release(reference, path)
            web = TTFont(OUT / key / "WOFF2" / path.with_suffix(".woff2").name)
            assert variable["head"].unitsPerEm == web["head"].unitsPerEm, filename
            for tag in ("cmap", "GSUB", "GPOS", "GDEF", "fvar", "STAT", "HVAR", "name"):
                assert variable.getTableData(tag) == web.getTableData(tag), (filename, tag)
        path = next((OUT / key / "TTC").glob("*.ttc"))
        collection = TTCollection(path)
        assert len(collection.fonts) == record["ttc_faces"]
        assert len({face["name"].getDebugName(6) for face in collection.fonts}) == len(collection.fonts)
        if settings.get("expected_static_faces"):
            assert len(collection.fonts) == settings["expected_static_faces"]
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
            if settings.get("metadata_source") or settings.get("rebuild_code"):
                verify_release_metadata(original, record)
                verify_release_metadata(otf, record)
            assert original["post"].italicAngle == otf["CFF "].cff.topDictIndex[0].ItalicAngle
            sanitize(face)
        if settings.get("punctuation"):
            from code_weight_width_trial import WEIGHTS, WIDTH_PRESETS

            expected_cells = {
                (weight, width * 6, italic)
                for weight in WEIGHTS for width in WIDTH_PRESETS for italic in (False, True)
            }
            actual_cells = {
                (face["OS/2"].usWeightClass, face["hmtx"]["space"][0], bool(face["OS/2"].fsSelection & 1))
                for face in collection.fonts
            }
            assert len(collection.fonts) == len(expected_cells) and actual_cells == expected_cells
        print(
            key, "TTC faces verified against individual TTFs and sanitized", flush=True
        )
    if "code" in report["families"] and not RECIPE["typography"]["code"].get("rebuild_code"):
        from code_texture_healing import verify as verify_texture_healing

        verify_texture_healing(
            ROOT / RECIPE["typography"]["code"]["unhealed_font"],
            ROOT / RECIPE["typography"]["code"].get("operator_source", RECIPE["typography"]["code"]["font"])
            if any(RECIPE["typography"]["code"].get(mode) for mode in ("self_aligning", "punctuation"))
            else OUT / "code" / "VF" / "DaikonicTransitCode-VF.ttf",
            default_on=True,
            lifetime_ampersand=True,
        )


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
            advance = glyphs[letter].width
            combined = glyphs[ligature].width
            if family == "system":
                # Larger lowercase and caption spacing allow tighter proportional pairs.
                assert advance < combined <= 2 * advance + 0.01, (family, instance.coordinates, ligature)
            else:
                assert abs(combined - 2 * advance) < 0.01
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
    families = release_families()
    archives = []
    if len(families) == 1:
        key, config = next(iter(families.items()))
        label = key.title() + "-" + config["version"]
        suffix = "daikonic-transit-" + label.lower()
        checksums = f"SHA256SUMS-{label}.txt"
    else:
        suffix = "daikonic-transit-" + RECIPE["version"]
        checksums = "SHA256SUMS.txt"
    for fmt in ["VF", "TTF", "TTC", "OTF", "WOFF2", "SOURCE", "SPECIMEN"]:
        stem = fmt + "-" + suffix
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
                    with TTFont(OUT / key / "VF" / (cfg["stem"] + "-VF.ttf")) as variable:
                        width = next((axis for axis in variable["fvar"].axes if axis.axisTag == "wdth"), None)
                    z.writestr(
                        str(Path(stem) / key / "font.css"),
                        "".join(
                            "@font-face { "
                            f"font-family: '{cfg['name']}'; "
                            f"src: url('./{cfg['stem']}{suffix}-VF.woff2') format('woff2'); "
                            f"font-weight: {cfg['light']} {cfg['heavy']}; font-style: {style}; "
                            + (f"font-stretch: {width.minValue:g}% {width.maxValue:g}%; " if width else "")
                            + "font-display: swap; }\n"
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
                if set(families) != set(specimen_families()):
                    paths = {p for p in paths if any(p.stem == f"Transit{key.title()}"
                             or p.name.startswith(f"{key}-") for key in families)}
                for source in sorted(paths):
                    z.write(
                        source,
                        Path(stem)
                        / "specimens"
                        / source.relative_to(ROOT / "specimens"),
                    )
                for name in sorted((OUT / "specimens").rglob("*")):
                    if name.is_file():
                        z.write(name, Path(stem) / "specimens" / name.relative_to(OUT / "specimens"))
            for name in (*LICENSE_FILES, "README.md", "requirements.lock"):
                z.write(ROOT / name, Path(stem) / name)
            z.write(OUT / "manifest.json", Path(stem) / "manifest.json")
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            assert len(z.namelist()) == len(set(z.namelist()))
        archives.append(path)
    if RECIPE.get("include_proof_site"):
        from proof_site import build_site

        stem = "PROOF-" + suffix
        path = destination / (stem + ".zip")
        with tempfile.TemporaryDirectory() as directory:
            proof = Path(directory) / stem
            build_site(proof)
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
                for source in sorted(proof.rglob("*")):
                    if source.is_file():
                        z.write(source, source.relative_to(proof.parent))
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
        archives.append(path)
    (destination / checksums).write_text(
        "".join(digest(p) + "  " + p.name + "\n" for p in archives)
    )
    versions = ", ".join(
        cfg["name"] + " " + cfg["version"] for cfg in families.values()
    )
    notes = [
        "Daikonic Transit — coordinated release " + RECIPE["version"] + ".",
        versions + ". All three families ship together as a normal release.",
        "- **Hairlining and Texture healing** are both on by default in upright Code. Enable `ss07` to disable Hairlining or `ss04` to disable Texture healing.",
        "- **Arrow width** is matched across `->`, `<-`, `->>`, `<<-`, and `=>`. Each advances two cells.",
        "- **Code examples** enable Loose Equality for TypeScript and Logic only for the logic sample. In Logic, `[<>]` draws a box then a diamond, while mixed pairs around text retain separate outlines.",
        "- **Self-aligning ligatures in upright Code** move following text left by one cell for selected operators. For example, `parse::<Vec<T>>()` puts the tall angle one cell earlier. Scope uses four plain diamonds with either Hairlining setting.",
        "- `?.`, `!.`, `::`, `//`, logical `||`, `<=` and `>=` advance one cell. The arrow and equality sets advance two cells by default.",
        "- **Loose Equality** (`ss06`) is off by default. It gives all four equality ligatures a one-cell advance and adds a tilde above the bars in `==` and `!=`.",
        "- These advances apply when an app follows font shaping. Fixed-grid editors and terminals can retain source-column placement.",
        "The **VF** and **WOFF2** packages include upright and italic variable fonts. **TTF** and **OTF** contain named styles, and **TTC** includes one collection per family. **SOURCE** contains editable TTX and a verified rebuild script. **SPECIMEN** includes PNG, PDF and outlined SVG proofs. `" + checksums + "` covers all download archives.",
        "Native Code Glyphs/UFO sources remain at 1.017; the full current drawings and layout are editable through the TTX source package.",
    ]
    if RECIPE["typography"].get("sans", {}).get("sans_rebuild"):
        notes = [versions + "."] + [
            "- **Sans 0.112** rebuilds upright and italic from shared, curve-based sources. Related forms reuse components, including the diamond dot and the comma in the semicolon. The italic has a continuous descending `f` and an open, upturned `g` return.",
            "- **Coverage** preserves the 427 encoded characters, ligature and alternate substitutions, and five named weights from Sans 0.111. The specimen archive includes full upright and italic glyph proofs.",
        ] + notes[-2:-1]
    code = RECIPE["typography"].get("code", {})
    if "code" in families and code.get("punctuation") and not code.get("reuse"):
        notes[2:2] = [
            "- **Code punctuation** includes centered commas and semicolons, taller quotes and lifetime markers, larger punctuation diamonds, and more prominent tildes and carets.",
            "- **Code widths and weights** run from 94% to 108% and Book 350 to Medium 500, with Regular 400 as the default. The Code TTC includes Narrow, standard, and Wide in upright and italic at every named weight.",
            "- **Unicode comparisons** include literal `≤`, `≥`, and `≠` alongside the existing programming ligatures.",
        ]
    if RECIPE.get("notes"):
        notes = [versions + ".", *RECIPE["notes"]] + [line for line in notes if line.startswith("The **VF**")]
    if RECIPE.get("include_proof_site"):
        notes.append("**PROOF** contains a local copy of the interactive proof, including all six variable faces and instructions for opening it.")
    (destination / "Release.md").write_text("\n\n".join(notes) + "\n")
    print(destination.relative_to(ROOT), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["build", "check", "package"])
    args = parser.parse_args()
    {"build": build, "check": check, "package": package}[args.action]()
