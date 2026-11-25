"""Stage and validate the rebuilt Code family and its release-format downloads."""

from argparse import ArgumentParser
import json
from pathlib import Path
from shutil import copyfile
from zipfile import ZIP_DEFLATED, ZipFile

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTCollection, TTFont
import uharfbuzz as hb

from build_code import RECIPE_PATH
from bundle_release import compress_source, digest, generate_formats
from check_code_rebuild import shape
from code_rebuild_proof import build_package_proofs
from code_weight_width_trial import WEIGHTS, WIDTH_PRESETS, name_trial, sanitize
from code_width import add_code_width, verify_width
from italic_returns import raw_outline
from specimens import ROOT
from system_metrics import set_vertical_metrics


FAMILY = "Daikonic Transit Code"
STEM = FAMILY.replace(" ", "")
FORMATS = ("VF", "TTF", "TTC", "OTF", "WOFF2", "SOURCE")
SAMPLES = ("ff tt ll", "Vec<[T]>", "::<>", "map(|x| x)", "const xs = [...data];",
           "obj?.value obj!.value", "let x = a === b || c !== d;", "a >= b ->> c",
           "fn borrow<'a>(x: &'a str) -> &'a str", "ke KE vi @@")
SWITCHES = ({}, {"ss02": True, "ss06": True, "ss07": True}, {"liga": False, "calt": False})


def save_family(paths, output, config, version):
    fonts = [TTFont(path, recalcTimestamp=False) for path in paths]
    vertical = set_vertical_metrics(*fonts, minimum_ascent=config["line_metrics"]["ascent"],
                                    maximum_descent=config["line_metrics"]["descent"])
    variables = []
    changes = {}
    for font in fonts:
        italic = font["post"].italicAngle != 0
        suffix = "-Italic" if italic else ""
        for rec in font["name"].names:
            if rec.nameID == 5:
                rec.string = f"Version {version}".encode(rec.getEncoding())
        font["head"].fontRevision = float(version)
        name_trial(font, FAMILY, variable=True)
        for instance in font["fvar"].instances:
            style = WEIGHTS[instance.coordinates["wght"]]
            if italic:
                style = "Italic" if style == "Regular" else style + " Italic"
            instance.subfamilyNameID = font["name"].addName(style)
            instance.postscriptNameID = font["name"].addName(STEM + "-" + style.replace(" ", ""))
        font["OS/2"].sTypoAscender = vertical["ascent"]
        font["OS/2"].sTypoDescender = vertical["descent"]
        path = output / "VF" / f"{STEM}{suffix}-VF.ttf"
        changes[path.name] = add_code_width(font, config["cell"])
        font.save(path)
        variables.append(path)
    return variables, vertical, changes


def validate_family(path, normal_path, reference_path, cell):
    engine, unscaled = [hb.Font(hb.Face(p.read_bytes())) for p in (path, normal_path)]
    with TTFont(path) as font, TTFont(normal_path) as normal, TTFont(reference_path) as prior:
        assert set(font.getBestCmap()) == set(prior.getBestCmap())
        assert font["post"].italicAngle == prior["post"].italicAngle
        axes = verify_width(font, cell)
        assert font["post"].isFixedPitch
        features = {record.FeatureTag for record in font["GSUB"].table.FeatureList.FeatureRecord}
        assert features.isdisjoint({"ss03", "ss04"})
        for weight in (350, 375, 400, 450, 500):
            unscaled.set_variations({"wght": weight})
            gs = font.getGlyphSet(location={"wght": weight, "wdth": 100})
            baseline = normal.getGlyphSet(location={"wght": weight})
            for name in ("a", "f", "g", "i", "less.generic", "uni2191", "uni21D2", "uni2195", "uni21D5"):
                before = raw_outline(baseline, name)
                after = raw_outline(gs, name)
                assert all(abs(a - b) <= 1.1 for a, b in zip(before.bounds, after.bounds)), (name, weight)
            for width in (94, 97, 100, 104, 108):
                engine.set_variations({"wght": weight, "wdth": width})
                for settings in SWITCHES:
                    for sample in SAMPLES:
                        old, new = [shape(h, sample, settings) for h in (unscaled, engine)]
                        assert len(new) == len(old)
                        for baseline_row, row in zip(old, new):
                            assert row[:2] == baseline_row[:2], (sample, weight, width, row)
                            assert row[2] == otRound(baseline_row[2] * width / 100), (sample, width, row)
                            assert row[3] == baseline_row[3] and row[5] == baseline_row[5]
                            assert abs(row[4] - baseline_row[4] * width / 100) <= 1.1, (sample, width, row)
    return {"encoded_characters": len(prior.getBestCmap()), "cell_widths": axes,
            "shaping_cases": len(SAMPLES) * len(SWITCHES) * 25}


def package(paths, output, recipe, version):
    for fmt in FORMATS:
        (output / fmt).mkdir(parents=True, exist_ok=True)
    config = recipe["alphabet_review"]
    variables, vertical, components = save_family(paths, output, config, version)
    release = ROOT / recipe["fonts"]["code"]
    validation = {}
    for variant, original in zip(variables, paths, strict=True):
        prior = release.with_name(variant.name)
        validation[variant.name] = validate_family(variant, original, prior, config["cell"])
        generate_formats(variant, output, {"name": FAMILY, "stem": STEM, "version": version})
    snapshots = sorted((output / "TTF").glob("*.ttf"))
    opentype = sorted((output / "OTF").glob("*.otf"))
    assert len(snapshots) == len(opentype) == 2 * len(WEIGHTS) * len(WIDTH_PRESETS)
    for path in snapshots:
        sanitize(path)
        with TTFont(path) as ttf, TTFont(output / "OTF" / path.with_suffix(".otf").name) as otf:
            for tag in ("hmtx", "cmap", "GSUB", "GPOS", "GDEF"):
                assert ttf.getTableData(tag) == otf.getTableData(tag), (path, tag)
    target = output / "TTC" / (STEM + ".ttc")
    collection = TTCollection()
    collection.fonts = [TTFont(path, recalcTimestamp=False) for path in snapshots]
    collection.save(target, shareTables=True)
    with TTCollection(target) as compiled:
        assert len({face["name"].getDebugName(6) for face in compiled.fonts}) == len(snapshots)
        assert all(face["name"].getDebugName(16) == FAMILY for face in compiled.fonts)
    compress_source(output / "SOURCE")
    build_package_proofs(output)
    for notice in ("OFL.txt", "NOTICE.txt"):
        copyfile(ROOT / notice, output / notice)
    report = {
        "family": FAMILY, "version": version, "status": "local review candidate",
        "vertical_metrics": vertical, "transformed_donors": components, "validation": validation,
        "static_faces_per_format": len(snapshots),
        "deferred": ["Texture Healing", "GPOS review of operator compaction and Texture Healing"],
        "files": {str(path.relative_to(output)): digest(path) for fmt in (*FORMATS, "proofs")
                  for path in sorted((output / fmt).rglob("*")) if path.is_file()},
    }
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    archive = output.parent / f"{STEM}-{version}-Review.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=9) as package_file:
        for name in (*report["files"], "OFL.txt", "NOTICE.txt", "manifest.json"):
            package_file.write(output / name, name)
    with ZipFile(archive) as package_file:
        assert package_file.testzip() is None
    return archive


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("upright", type=Path)
    parser.add_argument("italic", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    recipe = json.loads(RECIPE_PATH.read_text())
    print(package((args.upright, args.italic), args.output, recipe, args.version))


if __name__ == "__main__":
    main()
