"""Static CFF OpenType exports from the same fully instantiated variable fonts."""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from fontTools.ttLib import TTFont
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.varLib.instancer import instantiateVariableFont
import ots
from specimens import ROOT, specimen_families

OUT = ROOT / "exports/otf"
STYLES = {300: "Light", 350: "Book", 400: "Regular", 500: "Medium", 600: "SemiBold"}


def convert(font, path):
    f = deepcopy(font)
    f.recalcTimestamp = False
    assert "fvar" not in f
    gs = font.getGlyphSet()
    strings = {}
    for name in font.getGlyphOrder():
        pen = T2CharStringPen(font["hmtx"][name][0], gs, roundTolerance=0)
        gs[name].draw(pen)
        strings[name] = pen.getCharString(private=None, globalSubrs=None)
    for tag in ["glyf", "loca", "fpgm", "prep", "cvt ", "gasp", "LTSH", "hdmx", "DSIG"]:
        if tag in f:
            del f[tag]
    f.sfntVersion = "OTTO"
    f["post"].formatType = 3.0
    builder = FontBuilder(font=f, isTTF=False)
    ps = f["name"].getDebugName(6)
    builder.setupCFF(
        ps,
        {
            "FullName": f["name"].getDebugName(4),
            "FamilyName": f["name"].getDebugName(16),
            "Weight": f["name"].getDebugName(17),
            "version": str(f["head"].fontRevision),
            "ItalicAngle": f["post"].italicAngle,
            "isFixedPitch": bool(f["post"].isFixedPitch),
        },
        strings,
        {},
    )
    builder.setupMaxp()
    from cffsubr import subroutinize

    subroutinize(f, inplace=True)
    f.save(path)
    result = TTFont(path)
    assert result.sfntVersion == "OTTO" and "CFF " in result
    for tag in ["GSUB", "GPOS", "GDEF", "cmap", "hmtx"]:
        if tag in font:
            assert font.getTableData(tag) == result.getTableData(tag), (path.name, tag)
    from fontTools.pens.boundsPen import BoundsPen

    exported = result.getGlyphSet()
    for name in font.getGlyphOrder():
        a = BoundsPen(gs)
        gs[name].draw(a)
        b = BoundsPen(exported)
        exported[name].draw(b)
        if a.bounds is not None:
            assert max(abs(x - y) for x, y in zip(a.bounds, b.bounds)) < 0.05, (
                path.name,
                name,
                a.bounds,
                b.bounds,
            )
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(
            [ots.OTS_SANITIZE, str(path), str(Path(tmp) / "checked.otf")],
            capture_output=True,
        )
        assert r.returncode == 0, (path.name, r.stderr.decode())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--optical", action="store_true")
    parser.add_argument(
        "--family", choices=["all", "sans", "system", "code"], default="all"
    )
    args = parser.parse_args()
    families = specimen_families()
    manifest_path = (
        OUT / ("optical-trial" if args.optical else "current") / "manifest.json"
    )
    report = (
        json.loads(manifest_path.read_text())
        if manifest_path.exists() and args.family != "all"
        else {}
    )
    trial = ROOT / "trials/2026-11-17-layout-optical"
    optical = (
        json.loads((trial / "optical-fonts.json").read_text()) if args.optical else {}
    )
    for key, cfg in families.items():
        if args.family not in ("all", key):
            continue
        if args.optical and key == "system":
            import shutil

            current = json.loads((OUT / "current/manifest.json").read_text())["system"]
            folder = OUT / "optical-trial/system"
            folder.mkdir(parents=True, exist_ok=True)
            outputs = []
            for record in current["exports"]:
                destination = folder / Path(record["file"]).name
                shutil.copy2(ROOT / record["file"], destination)
                outputs.append({**record, "file": str(destination.relative_to(ROOT))})
            report[key] = {**current, "exports": outputs}
            continue
        source = ROOT / cfg["font"]
        if key in optical:
            source = ROOT / optical[key]
        original = TTFont(source)
        optical_values = (
            [10, 14, 36]
            if any(a.axisTag == "opsz" for a in original["fvar"].axes)
            else [None]
        )
        weights = sorted({i.coordinates["wght"] for i in original["fvar"].instances})
        out = OUT / ("optical-trial" if args.optical else "current") / key
        out.mkdir(parents=True, exist_ok=True)
        outputs = []
        for weight in weights:
            for size in optical_values:
                loc = {"wght": weight, **({"opsz": size} if size else {})}
                f = instantiateVariableFont(deepcopy(original), loc, inplace=True)
                style = STYLES[weight] + (
                    {10: " Caption", 14: " Text", 36: " Display"}[size] if size else ""
                )
                family = original["name"].getDebugName(16)
                stem = family.replace(" ", "")
                for r in f["name"].names:
                    names = {
                        1: family + " " + style,
                        2: "Regular",
                        3: stem
                        + "-"
                        + style.replace(" ", "")
                        + ";"
                        + f["name"].getDebugName(5),
                        4: family + " " + style,
                        6: stem + "-" + style.replace(" ", ""),
                        16: family,
                        17: style,
                    }
                    if r.nameID in names:
                        r.string = names[r.nameID].encode(r.getEncoding())
                path = out / (stem + "-" + style.replace(" ", "") + ".otf")
                digest = convert(f, path)
                outputs.append(
                    {
                        "file": str(path.relative_to(ROOT)),
                        "location": loc,
                        "sha256": digest,
                    }
                )
        report[key] = {
            "source": str(source.relative_to(ROOT)),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "exports": outputs,
            "validation": "CFF OpenType; OTS; exact cmap, hmtx, GSUB, GPOS, GDEF versus same TTF instance; quadratic curves converted to cubic without integer rounding; all glyph bounds match within0.05units",
        }
        print(key, len(outputs), "OTF fonts exported", flush=True)
    path = OUT / ("optical-trial" if args.optical else "current") / "manifest.json"
    path.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
