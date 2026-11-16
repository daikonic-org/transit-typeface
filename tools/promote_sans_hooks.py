"""Promote the selected R2 hook drawings into compatible Sans source masters."""

from copy import deepcopy
import json
import shutil

from fontTools.designspaceLib import DesignSpaceDocument
from fontTools.ttLib import TTFont
import glyphsLib
import ufoLib2

from adopt_weighting import ROOT, stamp
from audit import shape
from compatibility import compatible_masters
from derive_weights import coverage_difference
from hook_ligature_study import preserve_boundary_kerning


def main():
    config = ROOT / "family.json"
    data = json.loads(config.read_text())
    cfg = data["families"]["sans"]
    assert cfg["version"] == "0.108", "Already promoted or unexpected source version"
    frozen = ROOT / "sources/ligature-baseline/sans-0.108-VF.ttf"
    frozen.parent.mkdir(exist_ok=True)
    assert not frozen.exists()
    shutil.copy2(ROOT / cfg["font"], frozen)
    backup = ROOT / ".build/prior-sans-hooks"
    assert not backup.exists()
    shutil.copytree(ROOT / "sources/sans", backup / "sources")
    shutil.copytree(ROOT / "fonts/sans", backup / "fonts")
    source = ROOT / "sources/sans"
    design = DesignSpaceDocument.fromfile(
        source / "DaikonicTransitSans-TTF.designspace"
    )
    trials = [
        TTFont(
            ROOT
            / "trials/2026-11-16-sans-hooks-r2"
            / f'DaikonicTransitSansHookStudy-{int(s.location["Weight"])}.ttf'
        )
        for s in design.sources
    ]
    fonts = [TTFont(s.path) for s in design.sources]
    fidelity = {}
    for name in ("a_i", "l_i"):
        expected = [shape(f, name) for f in trials]
        glyphs, missing = compatible_masters(expected)
        assert missing == 0
        errors = []
        for font, glyph, trial, path in zip(fonts, glyphs, trials, expected):
            font["glyf"][name] = glyph
            glyph.recalcBounds(font["glyf"])
            font["hmtx"][name] = (trial["hmtx"][name][0], glyph.xMin)
            errors.append(coverage_difference(shape(font, name), path))
        assert max(errors) < 0.01, (name, errors)
        fidelity[name] = errors
    native = DesignSpaceDocument.fromfile(source / "DaikonicTransitSans.designspace")
    for descriptor, font, native_descriptor in zip(
        design.sources, fonts, native.sources
    ):
        pairs = preserve_boundary_kerning(font)
        stamp(font, "0.108", "0.109")
        font.save(descriptor.path)
        u = ufoLib2.Font.open(native_descriptor.path)
        production = u.lib.get("public.postscriptNames", {})
        reverse = {v: k for k, v in production.items()}
        nice = lambda name: name if name in u else reverse.get(name, name)
        glyphs = font.getGlyphSet()
        for name in ("a_i", "l_i"):
            g = u[nice(name)]
            g.clearContours()
            g.clearComponents()
            glyphs[name].drawPoints(g.getPointPen())
            g.width = font["hmtx"][name][0]
        for (a, b), amount in pairs.items():
            if nice(a) in u and nice(b) in u:
                u.kerning[(nice(a), nice(b))] = amount
        u.info.versionMajor, u.info.versionMinor = 0, 109
        u.save(overwrite=True)
    gs = glyphsLib.to_glyphs(native)
    gs.versionMajor, gs.versionMinor = 0, 109
    gs.customParameters["Use Production Names"] = True
    finish_glyphs(gs)
    gs.save(source / "DaikonicTransitSans.glyphs")
    metadata = TTFont(frozen)
    stamp(metadata, "0.108", "0.109")
    metadata.saveXML(source / "VariableMetadata.ttx", tables=["name", "fvar", "STAT"])
    cfg.update(
        version="0.109",
        tag="Sans-0.109R",
        ligature_baseline=str(frozen.relative_to(ROOT)),
        layout_revision={
            "metric_overrides": ["a_i", "l_i"],
            "append_kerning_lookup": True,
        },
    )
    data["published_date"] = "2026-11-16"
    config.write_text(json.dumps(data, indent=2) + "\n")
    (ROOT / "qa/sans/hook-master-fidelity.json").write_text(
        json.dumps(fidelity, indent=2) + "\n"
    )
    print(
        "Selected hooks promoted to five compatible TTF/UFO masters and Glyphs source",
        fidelity,
    )


def finish_glyphs(gs):
    # UFO custom parameters and explicit OS/2 fields can produce duplicates.
    for owner in [gs, *gs.masters, *gs.instances]:
        unique = {}
        for parameter in owner.customParameters:
            if parameter.name in unique:
                assert unique[parameter.name].value == parameter.value, parameter.name
            unique[parameter.name] = parameter
        owner.customParameters = list(unique.values())
    gs.customParameters["Variable Font Origin"] = next(
        m.id for m in gs.masters if m.weightValue == 400
    )


if __name__ == "__main__":
    main()
