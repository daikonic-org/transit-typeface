"""Build compatible production sources from the accepted 72% static drawings.

Stage only: promotion is a separate, explicit action after fidelity checks.
"""

from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json
import shutil

from fontTools.designspaceLib import DesignSpaceDocument, SourceDescriptor
from fontTools.pens.pointPen import SegmentToPointPen
from fontTools.ttLib import TTFont
from fontTools.varLib import build
from fontTools.varLib.models import VariationModel, normalizeLocation
from fontTools.varLib.instancer import instantiateVariableFont
import glyphsLib
import ufoLib2

from audit import shape
from compatibility import compatible_masters
from derive_weights import coverage_difference, locked
from weighting_support import preserve_layout

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".build/accepted-weighting"
STUDY = ROOT / ".build/weight-studies/approved-regular-ratio-0.72"
VERSIONS = {"sans": "0.107", "system": "0.116", "code": "1.016"}
STYLES = {300: "Light", 350: "Book", 400: "Regular", 500: "Medium", 600: "SemiBold"}
OPTICAL = {10: "Caption", 14: "Text", 36: "Display"}


def stamp(font, old, new):
    for record in font["name"].names:
        value = record.toUnicode().replace(old, new)
        record.string = value.encode(record.getEncoding())
    font["head"].fontRevision = float(new)


def instance(path, weight, optical):
    return instantiateVariableFont(
        TTFont(path),
        {"wght": weight, **({"opsz": optical} if optical else {})},
        inplace=False,
    )


def native_sources(key, cfg, design, fonts, rows, target):
    original = DesignSpaceDocument.fromfile(
        ROOT / "sources" / key / f"DaikonicTransit{key.title()}.designspace"
    )
    originals = [ufoLib2.Font.open(s.path) for s in original.sources]
    axes = {a.name: (a.minimum, a.default, a.maximum) for a in original.axes}
    model = VariationModel(
        [normalizeLocation(s.location, axes) for s in original.sources]
    )
    pairs = set().union(*(set(u.kerning) for u in originals))
    native = deepcopy(original)
    native.sources = []
    for source, font, (weight, optical, _) in zip(design.sources, fonts, rows):
        closest = min(
            original.sources,
            key=lambda s: abs(s.location["Weight"] - weight)
            + (10000 if optical and s.location["Optical Size"] != optical else 0),
        )
        u = ufoLib2.Font.open(closest.path)
        normalized = normalizeLocation(source.location, axes)
        u.kerning.clear()
        for pair in pairs:
            u.kerning[pair] = model.interpolateFromMasters(
                normalized, [old.kerning.get(pair, 0) for old in originals]
            )
        production = u.lib.get("public.postscriptNames", {})
        reverse = {v: k for k, v in production.items()}

        def nice(name):
            return name if name in u else reverse.get(name, name)

        glyphs = font.getGlyphSet()
        unicodes = {}
        for cp, name in font.getBestCmap().items():
            unicodes.setdefault(name, []).append(cp)
        for name in font.getGlyphOrder():
            target_name = nice(name)
            g = u[target_name] if target_name in u else u.newGlyph(target_name)
            g.clearContours()
            g.clearComponents()
            glyphs[name].drawPoints(g.getPointPen())
            g.width = font["hmtx"][name][0]
            g.unicodes = unicodes.get(name, [])
            if all(target_name in old for old in originals):
                anchors = [
                    {a.name: a for a in old[target_name].anchors} for old in originals
                ]
                for anchor in g.anchors:
                    if all(anchor.name in row for row in anchors):
                        for coord in ("x", "y"):
                            setattr(
                                anchor,
                                coord,
                                model.interpolateFromMasters(
                                    normalized,
                                    [
                                        getattr(row[anchor.name], coord)
                                        for row in anchors
                                    ],
                                ),
                            )
        u.glyphOrder = [nice(n) for n in font.getGlyphOrder()]
        u.info.styleName = source.styleName
        u.info.openTypeOS2WeightClass = weight
        u.info.versionMajor, u.info.versionMinor = map(int, VERSIONS[key].split("."))
        u.lib["com.schriftgestaltung.weightValue"] = weight
        u.lib["com.schriftgestaltung.weight"] = STYLES[weight]
        u.lib["com.schriftgestaltung.customParameter.GSFontMaster.weightClass"] = weight
        u.info.postscriptFontName = (
            cfg["stem"] + "-" + source.styleName.replace(" ", "")
        )
        u.lib["com.github.googlei18n.ufo2ft.useProductionNames"] = True
        descriptor = deepcopy(source)
        descriptor.path = str(
            target
            / (
                cfg["stem"].replace("600", "")
                + "-"
                + source.styleName.replace(" ", "")
                + ".ufo"
            )
        )
        u.save(descriptor.path, overwrite=True)
        native.addSource(descriptor)
    nativepath = target / f"DaikonicTransit{key.title()}.designspace"
    native.write(nativepath)
    gs = glyphsLib.to_glyphs(native)
    gs.versionMajor, gs.versionMinor = map(int, VERSIONS[key].split("."))
    gs.customParameters["Use Production Names"] = True
    indices = {a.axisTag: i for i, a in enumerate(gs.axes)}
    gs.customParameters["Variable Font Origin"] = next(
        m.id
        for m in gs.masters
        if all(m.axes[indices[a.tag]] == a.default for a in native.axes)
    )
    gs.save(target / f"DaikonicTransit{key.title()}.glyphs")


def family(key, cfg, recipe, defaults, skip_native=False):
    dest = OUT / key
    source_dir = dest / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    baseline = ROOT / cfg.get("weighting_baseline", cfg["font"])
    rows, fonts, trials = [], [], []
    for optical in recipe["optical_sizes"]:
        for w in recipe["target_H_stems"]:
            weight = int(w)
            p = STUDY / (
                f"{key}-{weight}" + (f"-opsz{optical}" if optical else "") + ".ttf"
            )
            rows.append((weight, optical, p))
            trials.append(TTFont(p))
            fonts.append(instance(baseline, weight, optical))
    order = fonts[0].getGlyphOrder()
    protected = locked(fonts[0], defaults["locks"])
    fidelity, compatibility = {}, {}
    for number, name in enumerate(order):
        if name in protected or all(
            not f["glyf"][name].numberOfContours for f in trials
        ):
            continue
        paths = [shape(f, name) for f in trials]
        glyphs, missing = compatible_masters(paths)
        errors = []
        for font, glyph, expected in zip(fonts, glyphs, paths):
            font["glyf"][name] = glyph
            glyph.recalcBounds(font["glyf"])
            font["hmtx"][name] = (
                font["hmtx"][name][0],
                glyph.xMin if glyph.numberOfContours else 0,
            )
            errors.append(coverage_difference(shape(font, name), expected))
        fidelity[name] = errors
        compatibility[name] = {
            "missing_contours": missing,
            "maximum_coverage_difference": max(errors),
        }
        assert max(errors) < 0.025, (key, name, max(errors))
        if number % 50 == 0:
            print(
                key,
                number,
                "/",
                len(order),
                name,
                "maximum difference",
                round(max(errors), 4),
                flush=True,
            )
    template = next((ROOT / "sources" / key).glob("*TTF.designspace"), None)
    if template is None:
        template = ROOT / "sources" / key / "DaikonicTransitCodeVF.designspace"
    design = DesignSpaceDocument.fromfile(template)
    design.sources = []
    for (weight, optical, _), font in zip(rows, fonts):
        style = STYLES[weight] + (" " + OPTICAL[optical] if optical else "")
        stamp(font, cfg["version"], VERSIONS[key])
        path = source_dir / ("Master-" + style.replace(" ", "-") + ".ttf")
        font.save(path)
        source = SourceDescriptor()
        source.path = str(path)
        source.name = style
        source.familyName = cfg["name"]
        source.styleName = style
        source.location = {
            "Weight": weight,
            **({"Optical Size": optical} if optical else {}),
        }
        if all(source.location[a.name] == a.default for a in design.axes):
            source.copyInfo = source.copyLib = source.copyFeatures = True
        design.addSource(source)
    designpath = source_dir / template.name
    design.write(designpath)
    print(key, "building VF", flush=True)
    vf, _, _ = build(designpath, optimize=False)
    old = TTFont(baseline)
    for tag in ("name", "fvar", "STAT"):
        vf[tag] = deepcopy(old[tag])
    preserve_layout(vf, old, protected)
    stamp(vf, cfg["version"], VERSIONS[key])
    vfpath = dest / "fonts/VF" / (cfg["stem"] + "-VF.ttf")
    vfpath.parent.mkdir(parents=True, exist_ok=True)
    vf.save(vfpath)
    web = dest / "fonts/WOFF2"
    web.mkdir(exist_ok=True)
    vf.flavor = "woff2"
    vf.save(web / vfpath.with_suffix(".woff2").name)
    vf.flavor = None
    vf.saveXML(source_dir / "VariableMetadata.ttx", tables=["name", "fvar", "STAT"])
    static = dest / "fonts/TTF"
    static.mkdir(exist_ok=True)
    for path in sorted((ROOT / "fonts" / key / "TTF").glob("*.ttf")):
        metadata = TTFont(path)
        weight = metadata["OS/2"].usWeightClass
        optical = (
            {v: k for k, v in OPTICAL.items()}[
                metadata["name"].getDebugName(17).split()[-1]
            ]
            if key == "system"
            else None
        )
        f = instance(vfpath, weight, optical)
        f["name"] = deepcopy(metadata["name"])
        f["OS/2"].fsSelection = metadata["OS/2"].fsSelection
        f["head"].macStyle = metadata["head"].macStyle
        stamp(f, cfg["version"], VERSIONS[key])
        f.save(static / path.name)
    (dest / "compatibility.json").write_text(json.dumps(compatibility, indent=2) + "\n")
    (dest / "fidelity.json").write_text(
        json.dumps({"rows": [(w, o) for w, o, _ in rows], "glyphs": fidelity}, indent=2)
        + "\n"
    )
    if not skip_native:
        print(key, "exporting editable sources", flush=True)
        native_sources(key, cfg, design, fonts, rows, source_dir)
    print(key, VERSIONS[key], "staged", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "family", choices=["all", "sans", "system", "code"], nargs="?", default="all"
    )
    parser.add_argument("--skip-native", action="store_true")
    parser.add_argument("--native-only", action="store_true")
    parser.add_argument("--finish-only", action="store_true")
    args = parser.parse_args()
    data = json.loads((ROOT / "family.json").read_text())
    config = json.loads((ROOT / "recipes/weights.json").read_text())
    for key, cfg in data["families"].items():
        if args.family not in ("all", key):
            continue
        if args.finish_only:
            dest = OUT / key
            baseline = TTFont(ROOT / cfg.get("weighting_baseline", cfg["font"]))
            path = dest / "fonts/VF" / (cfg["stem"] + "-VF.ttf")
            vf = TTFont(path)
            preserve_layout(vf, baseline, locked(baseline, config["defaults"]["locks"]))
            vf.save(path)
            vf.flavor = "woff2"
            vf.save(dest / "fonts/WOFF2" / path.with_suffix(".woff2").name)
            for p in (dest / "fonts/TTF").glob("*.ttf"):
                previous = TTFont(p)
                weight = previous["OS/2"].usWeightClass
                optical = (
                    {v: k for k, v in OPTICAL.items()}[
                        previous["name"].getDebugName(17).split()[-1]
                    ]
                    if key == "system"
                    else None
                )
                f = instance(path, weight, optical)
                f["name"] = deepcopy(previous["name"])
                f["OS/2"].fsSelection = previous["OS/2"].fsSelection
                f["head"].macStyle = previous["head"].macStyle
                f.save(p)
            print(key, "layout and snapshots finalized", flush=True)
            continue
        if args.native_only:
            target = OUT / key / "sources"
            designpath = (
                next(target.glob("*TTF.designspace"), None)
                or target / "DaikonicTransitCodeVF.designspace"
            )
            design = DesignSpaceDocument.fromfile(designpath)
            fonts = [TTFont(s.path) for s in design.sources]
            rows = [
                (int(s.location["Weight"]), s.location.get("Optical Size"), None)
                for s in design.sources
            ]
            native_sources(key, cfg, design, fonts, rows, target)
            print(key, "native sources exported", flush=True)
            continue
        family(key, cfg, config["families"][key], config["defaults"], args.skip_native)


if __name__ == "__main__":
    main()
