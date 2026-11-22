"""Build local upright Sans deliverables from the approved component recipe."""

import argparse
from io import BytesIO
import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTCollection, TTFont

from bundle_release import compress_source, digest, generate_formats
from code_weight_width_trial import name_trial
from render_svg import render
from sans_baseline_trial import load_baseline, specimen
from sans_component_relationships import apply_relationships
from sans_complete_rebuild import direct_outline_findings, rebuild_drawn_outlines, repair_components
from sans_diamond_punctuation import EDGES, INSET_TRIANGLE, edit_crowns, reuse_comma_in_semicolon
from sans_glyph_proof import build_proof
from sans_ligature_construction import rebuild_ligatures
from sans_weight_refinement import check_composites
from specimens import DATA, ROOT


def glyph_bounds(glyph_set, name):
    pen = BoundsPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.bounds


def apply_approved_components(font):
    for name in EDGES:
        edit_crowns(font, name, *INSET_TRIANGLE)
    reuse_comma_in_semicolon(font)
    return apply_relationships(font)


def validate_outlines(baseline, finished, mirrored, ligatures):
    for tag in ("GSUB", "GPOS", "GDEF", "cmap", "HVAR", "STAT"):
        if baseline.getTableData(tag) != finished.getTableData(tag):
            raise ValueError(f"Unexpected change in the {tag} table")
    rebuilt_bearings = {"semicolon", "equal", "divide", *ligatures, *(target for _, target in mirrored)}
    for name, metrics in baseline["hmtx"].metrics.items():
        advance, bearing = finished["hmtx"][name]
        if advance != metrics[0] or (name not in rebuilt_bearings and bearing != metrics[1]):
            raise ValueError(f"Unexpected horizontal metric change for {name}")
    semicolon_parts = finished["glyf"]["semicolon"].components
    if [part.glyphName for part in semicolon_parts] != ["comma", "diamond.dot"]:
        raise ValueError("Semicolon must reuse comma and diamond components")
    for weight in range(300, 601):
        glyphs = finished.getGlyphSet(location={"wght": weight})
        if abs(glyph_bounds(glyphs, "comma")[3] - glyph_bounds(glyphs, "period")[3]) > 1e-9:
            raise ValueError(f"Comma and period tops do not align at weight {weight}")


def complete_outline_pipeline(font, *, proof_only=False):
    drawn = rebuild_drawn_outlines(font)
    mirrored, normalized = apply_approved_components(font)
    attachments = repair_components(font)
    ligatures = rebuild_ligatures(font, proof_only=proof_only)
    ligature_attachments = repair_components(font, ligatures=True)
    for kind, changes in ligature_attachments.items():
        attachments[kind].update(changes)
    return drawn, mirrored, normalized, ligatures, attachments


def direct_weight_proof(output):
    """Render the complete direct-weight pipeline without packaging a font."""
    payload, _ = load_baseline()
    with TTFont(BytesIO(payload), recalcTimestamp=False) as font:
        drawn, mirrored, normalized, ligatures, attachments = complete_outline_pipeline(font, proof_only=True)
        with TemporaryDirectory(prefix="transit-direct-proof-") as scratch:
            source = Path(scratch) / "proof-input.ttf"
            font.save(source)
            with TTFont(source) as finished, TTFont(BytesIO(payload)) as baseline:
                validate_outlines(baseline, finished, mirrored, ligatures)
                outline_findings = direct_outline_findings(finished, drawn)
            flagged = {name for name, row in outline_findings.items()
                       if row.get("topology_changes") or row.get("ink_loss")}
            build_proof(source, output, flagged=flagged)
    (output / "proof-pipeline.json").write_text(json.dumps({
        "mirrored_pairs": mirrored,
        "drawn_outlines": outline_findings,
        "regular_rounding_normalized": normalized,
        "ligatures": ligatures,
        "attachment_adjustments": attachments,
    }, indent=2) + "\n")


def build(output):
    payload, baseline_report = load_baseline()
    family = DATA["families"]["sans"]
    stem = family["stem"]
    with TTFont(BytesIO(payload), recalcTimestamp=False) as font:
        rebuild_report, mirrored, normalized, ligatures, attachments = complete_outline_pipeline(font)
        for instance in font["fvar"].instances:
            label = font["name"].getDebugName(instance.subfamilyNameID)
            instance.postscriptNameID = font["name"].addName(f"{stem}-{label.replace(' ', '')}")
        name_trial(font, family["name"], variable=True)
        for fmt in ("VF", "TTF", "TTC", "OTF", "WOFF2", "SOURCE"):
            (output / fmt).mkdir(parents=True, exist_ok=True)
        variable = output / "VF" / f"{stem}-VF.ttf"
        font.save(variable)

    baseline = TTFont(BytesIO(payload))
    finished = TTFont(variable)
    validate_outlines(baseline, finished, mirrored, ligatures)

    (output / "complete-rebuild-report.json").write_text(json.dumps({
        "drawn_outlines": direct_outline_findings(finished, rebuild_report),
        "components": check_composites(baseline, finished),
        "ligatures": ligatures,
        "attachment_adjustments": attachments,
        "empty": [name for name in finished.getGlyphOrder() if finished["glyf"][name].numberOfContours == 0],
    }, indent=2) + "\n")

    version = finished["name"].getDebugName(5).removeprefix("Version ")
    generate_formats(variable, output, {**family, "version": version})
    compress_source(output / "SOURCE")
    collection = TTCollection()
    collection.fonts = [TTFont(path, recalcTimestamp=False) for path in sorted((output / "TTF").glob(f"{stem}-*.ttf"))]
    collection.save(output / "TTC" / f"{stem}.ttc", shareTables=True)
    collection.close()

    for name in ("OFL.txt", "NOTICE.txt"):
        copyfile(ROOT / name, output / name)
    svg = output / f"{stem}-Specimen.svg"
    specimen(variable, svg, title=family["name"])
    render(svg, scale=2)
    build_proof(variable, output / "Proof")
    report = {
        "family": family["name"],
        "style": "Upright",
        "status": "complete rebuild trial",
        "source_version": version,
        "reviewed_baseline_sha256": baseline_report["variable_sha256"],
        "upstream_glyphs": len(baseline_report["metropolitan_line_glyphs"]),
        "component_glyphs": sum(finished["glyf"][name].isComposite() for name in finished.getGlyphOrder()),
        "approved_punctuation": [*EDGES, "semicolon"],
        "weight_refinement": list(rebuild_report),
        "ligature_construction": ligatures,
        "mirrored_pairs": mirrored,
        "regular_rounding_normalized": normalized,
        "shared_math_bar": ["minus", "equal", "divide"],
        "semicolon_components": [part.glyphName for part in finished["glyf"]["semicolon"].components],
        "files": {
            path.relative_to(output).as_posix(): digest(path)
            for path in sorted(output.rglob("*"))
            if path.is_file() and not path.name.startswith(".") and path.name != "manifest.json"
        },
    }
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Built {family['name']} upright in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--complete-rebuild", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--direct-proof", action="store_true",
                        help="render the complete direct-weight trial without packaging a font")
    args = parser.parse_args()
    if args.direct_proof:
        direct_weight_proof(args.output)
    else:
        build(args.output)
