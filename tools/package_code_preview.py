"""Package and optionally install the selected Code preview without changing releases."""

from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile

from fontTools.ttLib import TTFont
import ots
from adopt_weighting import ROOT, instance

SOURCE = (
    ROOT
    / "trials/2026-11-16-code-at-single-storey/DaikonicTransitCodeSingleStoreyAtStudy-VF.ttf"
)
FAMILY = "Daikonic Transit Code"
STEM = "DaikonicTransitCode"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_preview(out):
    import uharfbuzz as hb

    selection = json.loads((out / "selection.json").read_text())
    source = ROOT / selection["selected_source"]
    assert digest(source) == selection["source_sha256"]
    vf = out / "VF" / (STEM + "-VF.ttf")
    original, font = TTFont(source), TTFont(vf)
    for tag in [
        "glyf",
        "gvar",
        "GSUB",
        "GPOS",
        "GDEF",
        "hmtx",
        "HVAR",
        "fvar",
        "STAT",
        "cmap",
    ]:
        assert original.getTableData(tag) == font.getTableData(tag), tag
    assert font["name"].getDebugName(16) == FAMILY
    assert (
        font["name"]
        .getDebugName(5)
        .startswith("Version " + selection["version"] + "; preview;")
    )
    assert [
        (a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes
    ] == [("wght", 300, 350, 400)]
    for name, expected in json.loads((out / "SHA256.json").read_text()).items():
        assert digest(out / name) == expected, name
    paths = [vf]
    for weight, style in [(300, "Light"), (350, "Book"), (400, "Regular")]:
        path = out / "TTF" / (STEM + "-" + style + ".ttf")
        expected, actual = instance(vf, weight, None), TTFont(path)
        assert actual["name"].getDebugName(16) == FAMILY
        assert actual["name"].getDebugName(17) == style
        for tag in ["glyf", "hmtx", "GSUB", "GPOS", "GDEF", "cmap"]:
            assert expected.getTableData(tag) == actual.getTableData(tag), (style, tag)
        paths.append(path)
    for path in paths:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [ots.OTS_SANITIZE, str(path), str(Path(tmp) / "checked.ttf")],
                capture_output=True,
            )
            assert result.returncode == 0, result.stderr.decode()
    face = hb.Face(vf.read_bytes())
    for weight in range(300, 401, 10):
        h = hb.Font(face)
        h.scale = (1000, 1000)
        h.set_variations({"wght": weight})

        def run(text):
            b = hb.Buffer()
            b.add_str(text)
            b.guess_segment_properties()
            hb.shape(h, b, {"calt": True, "liga": True})
            return [
                (font.getGlyphName(g.codepoint), p.x_advance, p.x_offset)
                for g, p in zip(b.glyph_infos, b.glyph_positions)
            ]

        assert run("@")[0][0] == "at"
        assert all(n == "at.compact" and advance == 600 for n, advance, x in run("@@@"))
        assert [x for n, advance, x in run("ke")] == [18, -18]
        for token in [
            "->",
            "->>",
            "=>",
            "<-",
            "<<-",
            "==",
            "===",
            "!=",
            "!==",
            "<=",
            ">=",
            "::",
        ]:
            result = run(token)
            assert len(result) == 1 and result[0][1] == 600 * len(token), (
                weight,
                token,
                result,
            )
    print(
        "Code preview checked: source fidelity, hashes, four sanitized fonts, snapshots and 11 shaping weights"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="1.021")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    out = ROOT / "previews" / ("code-" + args.version)
    if args.check:
        if args.install:
            parser.error("--check and --install cannot be combined")
        check_preview(out)
        return
    (out / "VF").mkdir(parents=True, exist_ok=True)
    (out / "TTF").mkdir(exist_ok=True)
    font = TTFont(SOURCE)
    font.recalcTimestamp = False
    old = font["name"].getDebugName(16)
    oldstem = old.replace(" ", "")
    for r in font["name"].names:
        text = r.toUnicode().replace(old, FAMILY).replace(oldstem, STEM)
        if r.nameID == 3:
            text = STEM + "-VF " + args.version + " preview"
        if r.nameID == 5:
            text = (
                "Version "
                + args.version
                + "; preview; selected single-storey at and Code refinements"
            )
        if r.nameID == 10:
            text = "Preview: single-storey at with matching inner/outer strokes, balanced i, stronger delimiters, extended brace pinch, raised heavier gapless underscore, wider hyphen and fixed-advance optical positioning. Repeated at fitting uses calt."
        r.string = text.encode(r.getEncoding())
    font["head"].fontRevision = float(args.version)
    vf = out / "VF" / (STEM + "-VF.ttf")
    font.save(vf)
    paths = [vf]
    baseline = TTFont(SOURCE)
    candidate = TTFont(vf)
    for tag in [
        "glyf",
        "gvar",
        "GSUB",
        "GPOS",
        "GDEF",
        "hmtx",
        "HVAR",
        "fvar",
        "STAT",
        "cmap",
    ]:
        assert baseline.getTableData(tag) == candidate.getTableData(tag), tag
    for weight, style in [(300, "Light"), (350, "Book"), (400, "Regular")]:
        f = instance(vf, weight, None)
        f.recalcTimestamp = False
        names = {
            1: FAMILY if weight == 400 else FAMILY + " " + style,
            2: "Regular",
            3: STEM + "-" + style + " " + args.version + " preview",
            4: FAMILY + " " + style,
            6: STEM + "-" + style,
            16: FAMILY,
            17: style,
        }
        for r in f["name"].names:
            if r.nameID in names:
                r.string = names[r.nameID].encode(r.getEncoding())
        path = out / "TTF" / (STEM + "-" + style + ".ttf")
        f.save(path)
        paths.append(path)
    for path in paths:
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [ots.OTS_SANITIZE, str(path), str(Path(tmp) / "checked.ttf")],
                capture_output=True,
            )
            assert r.returncode == 0, r.stderr.decode()
    proofs = out / "specimens"
    proofs.mkdir(exist_ok=True)
    for stem in ["Book", "NamedWeights"]:
        for suffix in ["png", "pdf", "svg"]:
            shutil.copy2(
                SOURCE.parent / (stem + "." + suffix), proofs / (stem + "." + suffix)
            )
    for name in ["OFL.txt", "NOTICE.txt"]:
        shutil.copy2(ROOT / name, out / name)
    record = {
        "version": args.version,
        "status": "preview",
        "family": FAMILY,
        "default_weight": 350,
        "weight_range": [300, 400],
        "selected_source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": digest(SOURCE),
        "drawing_variation_layout_fidelity": "exact to selected source",
        "sanitized_fonts": 4,
        "source_status": "Scripted trial derivation; released sources/code remains1.017. Native production source adoption and accented/dotless i alignment remain pending.",
    }
    (out / "selection.json").write_text(json.dumps(record, indent=2) + "\n")
    (out / "README.md").write_text(
        f"""# Daikonic Transit Code {args.version} preview

Approved working preview with the single-storey a inside @, its larger smooth
outer loop and matching inner/outer stroke weights. Also includes the balanced i,
stronger inward delimiters, extended brace pinch, heavier full-width baseline
underscore, wider hyphen, and optical placement for selected lowercase/K pairs.
The normal lowercase a is unchanged. Sans and System are unchanged.

Install VF/DaikonicTransitCode-VF.ttf for variable weights300–400, defaultBook350.
TTF/ contains named-weight snapshots of the same VF. Install either format.
The menu family is simply Daikonic Transit Code. Existing Book350 editor settings
continue to work; restart applications after replacing a font.

The larger @ has slight ink overhang but retains its600-unit advance. Repeated
@@/@@@ use an equal-weight compact contextual alternate to avoid touching.
Enable calt/ligatures for this fitting and the existing operator ligatures.
Browser proofs were reviewed; editor/terminal rendering still needs a smoke test.

This preview has not been published as a GitHub release. The released Code font
and native sources/code/ remain1.017. Compatible trial sources/scripts and their
validation records are in trials/2026-11-16-code-at-single-storey/ and tools/.
Production native-source adoption, including accented/dotless i alignment, remains
pending. Earlier studies and released fonts are preserved.

All4preview fonts pass OTS; VF drawing/variation/layout/metrics tables exactly
match the selected trial. See selection.json and the trial validation.json for
11weight interpolation, fixed-advance, repeat-fitting and operator checks.
Specimens show enlarged comparisons and all3weights in light/dark polarity.

Rebuild with python tools/package_code_preview.py --version {args.version}.
Add --install to back up and replace the current user font. OFL.txt/NOTICE.txt apply.
"""
    )
    checksums = {
        str(p.relative_to(out)): digest(p)
        for p in sorted(out.rglob("*"))
        if p.is_file() and p.name != "SHA256.json"
    }
    (out / "SHA256.json").write_text(json.dumps(checksums, indent=2) + "\n")
    if args.install:
        installed = Path.home() / "Library/Fonts" / (STEM + "-VF.ttf")
        backup = (
            Path.home()
            / "Library/Application Support/Daikonic/Font Backups"
            / datetime.now().strftime("%Y%m%d-%H%M%S")
        )
        backup.mkdir(parents=True)
        if installed.exists():
            shutil.copy2(installed, backup / installed.name)
        shutil.copy2(vf, installed)
        assert digest(vf) == digest(installed)
        report = {
            "installed": str(installed),
            "backup": str(backup / installed.name),
            "sha256": digest(installed),
            "version": args.version,
        }
        (ROOT / ".build/code-preview-install.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(json.dumps(report, indent=2))
    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
