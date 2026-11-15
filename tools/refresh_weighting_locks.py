"""Retain tuned punctuation/symbols consistently in binary and editable sources."""

from copy import deepcopy
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from fontTools.designspaceLib import DesignSpaceDocument
from fontTools.ttLib import TTFont
import glyphsLib
import ufoLib2

from adopt_weighting import ROOT, instance
from derive_weights import locked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("family", choices=["sans", "system", "code"])
    key = parser.parse_args().family
    cfg = json.loads((ROOT / "family.json").read_text())["families"][key]
    rules = json.loads((ROOT / "recipes/weights.json").read_text())["defaults"]["locks"]
    baseline = ROOT / cfg["weighting_baseline"]
    protected = locked(TTFont(baseline), rules)
    sources = ROOT / "sources" / key
    binary = DesignSpaceDocument.fromfile(
        next(sources.glob("*TTF.designspace"), None)
        or sources / "DaikonicTransitCodeVF.designspace"
    )
    fonts = {}
    for source in binary.sources:
        weight = source.location["Weight"]
        optical = source.location.get("Optical Size")
        old = instance(baseline, weight, optical)
        f = TTFont(source.path)
        for name in protected:
            f["glyf"][name] = deepcopy(old["glyf"][name])
            f["hmtx"][name] = old["hmtx"][name]
        f.save(source.path)
        fonts[weight, optical] = f
    native = DesignSpaceDocument.fromfile(
        sources / f"DaikonicTransit{key.title()}.designspace"
    )
    for source in native.sources:
        font = fonts[source.location["Weight"], source.location.get("Optical Size")]
        u = ufoLib2.Font.open(source.path)
        reverse = {v: k for k, v in u.lib.get("public.postscriptNames", {}).items()}
        for name in protected:
            target = name if name in u else reverse.get(name, name)
            g = u[target]
            g.clearContours()
            g.clearComponents()
            font.getGlyphSet()[name].drawPoints(g.getPointPen())
            g.width = font["hmtx"][name][0]
        u.save(source.path, overwrite=True)
    gs = glyphsLib.to_glyphs(native)
    gs.versionMajor, gs.versionMinor = map(int, cfg["version"].split("."))
    gs.customParameters["Use Production Names"] = True
    indices = {a.axisTag: i for i, a in enumerate(gs.axes)}
    gs.customParameters["Variable Font Origin"] = next(
        m.id
        for m in gs.masters
        if all(m.axes[indices[a.tag]] == a.default for a in native.axes)
    )
    temp = ROOT / ".build" / f"Refreshed-{key}.glyphs"
    gs.save(temp)
    glyphspath = sources / f"DaikonicTransit{key.title()}.glyphs"
    if temp.stat().st_size > 95_000_000:
        with zipfile.ZipFile(
            glyphspath.with_suffix(".glyphs.zip"), "w", zipfile.ZIP_DEFLATED
        ) as z:
            z.write(temp, glyphspath.name)
        temp.unlink()
    else:
        shutil.move(str(temp), str(glyphspath))
    for report in ("compatibility", "fidelity"):
        p = ROOT / "qa" / key / ("weighting-" + report + ".json")
        data = json.loads(p.read_text())
        glyphs = data if report == "compatibility" else data["glyphs"]
        for name in protected:
            glyphs.pop(name, None)
        p.write_text(json.dumps(data, indent=2) + "\n")
    subprocess.run([sys.executable, str(ROOT / "tools/build.py"), key], check=True)
    vf = ROOT / ".build" / key / (cfg["stem"] + "-VF.ttf")
    shutil.copy2(vf, ROOT / cfg["font"])
    shutil.copy2(
        vf.with_suffix(".woff2"),
        ROOT / "fonts" / key / "WOFF2" / vf.with_suffix(".woff2").name,
    )
    for p in (ROOT / "fonts" / key / "TTF").glob("*.ttf"):
        previous = TTFont(p)
        optical = (
            {"Caption": 10, "Text": 14, "Display": 36}[
                previous["name"].getDebugName(17).split()[-1]
            ]
            if key == "system"
            else None
        )
        f = instance(vf, previous["OS/2"].usWeightClass, optical)
        f["name"] = deepcopy(previous["name"])
        f["OS/2"].fsSelection = previous["OS/2"].fsSelection
        f["head"].macStyle = previous["head"].macStyle
        f.save(p)
    print(key, "tuned punctuation and symbol locks refreshed", flush=True)


if __name__ == "__main__":
    main()
