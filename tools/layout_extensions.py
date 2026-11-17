"""Variable mark attachment for Code, preserving fixed advances and existing layout."""

from copy import deepcopy
import itertools
import json
import unicodedata
from pathlib import Path
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.feaLib.variableScalar import VariableScalar
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
from fontTools.pens.boundsPen import BoundsPen
from adopt_weighting import ROOT


def bounds(glyphs, name):
    pen = BoundsPen(glyphs)
    glyphs[name].draw(pen)
    return pen.bounds


def locations(font):
    axes = font["fvar"].axes
    values = []
    for axis in axes:
        vals = {axis.minValue, axis.defaultValue, axis.maxValue}
        if axis.axisTag == "wght":
            vals.update(range(int(axis.minValue), int(axis.maxValue) + 1, 5))
            vals.update([312.5, 387.5])
        vals.update(
            i.coordinates[axis.axisTag]
            for i in font["fvar"].instances
            if axis.axisTag in i.coordinates
        )
        values.append(sorted(vals))
    return [dict(zip([a.axisTag for a in axes], v)) for v in itertools.product(*values)]


def merge_features(target, previous):
    """Append retained positioning without rebuilding or dropping its lookups."""
    t = target.table
    p = previous.table
    offset = len(t.LookupList.Lookup)
    copied = deepcopy(p.LookupList.Lookup)

    def relocate(value):
        if isinstance(value, (otTables.SubstLookupRecord, otTables.PosLookupRecord)):
            value.LookupListIndex += offset
        elif isinstance(value, list):
            for item in value:
                relocate(item)
        elif hasattr(value, "__dict__"):
            for item in vars(value).values():
                relocate(item)

    relocate(copied)
    t.LookupList.Lookup.extend(copied)
    t.LookupList.LookupCount = len(t.LookupList.Lookup)
    added = []
    for old in p.FeatureList.FeatureRecord:
        record = deepcopy(old)
        record.Feature.LookupListIndex = [
            i + offset for i in record.Feature.LookupListIndex
        ]
        added.append(len(t.FeatureList.FeatureRecord))
        t.FeatureList.FeatureRecord.append(record)
    for record in t.ScriptList.ScriptRecord:
        for lang in [record.Script.DefaultLangSys] + [
            r.LangSys for r in record.Script.LangSysRecord
        ]:
            if lang is not None:
                lang.FeatureIndex.extend(added)
                lang.FeatureCount = len(lang.FeatureIndex)
    records = t.FeatureList.FeatureRecord
    order = sorted(range(len(records)), key=lambda i: records[i].FeatureTag)
    remap = {old: new for new, old in enumerate(order)}
    t.FeatureList.FeatureRecord = [records[i] for i in order]
    t.FeatureList.FeatureCount = len(records)
    for record in t.ScriptList.ScriptRecord:
        for lang in [record.Script.DefaultLangSys] + [
            r.LangSys for r in record.Script.LangSysRecord
        ]:
            if lang is not None:
                lang.FeatureIndex = sorted(remap[i] for i in lang.FeatureIndex)
                if lang.ReqFeatureIndex != 0xFFFF:
                    lang.ReqFeatureIndex = remap[lang.ReqFeatureIndex]


def add_code_marks(font, report_path=None):
    old_gpos = deepcopy(font["GPOS"])
    old_gdef = deepcopy(font["GDEF"])
    old_gsub = deepcopy(font["GSUB"])
    # Derive dotless bodies from the selected i/j rather than an older source cut.
    from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

    for base, target in [("i", "dotlessi"), ("j", "dotlessj")]:
        original = font["glyf"][base]
        indices = []
        ends = []
        start = 0
        for end in original.endPtsOfContours:
            part = original.coordinates[start : end + 1]
            if min(y for x, y in part) < 550:
                indices.extend(range(start, end + 1))
                ends.append(len(indices) - 1)
            start = end + 1
        glyph = deepcopy(original)
        glyph.coordinates = GlyphCoordinates([original.coordinates[i] for i in indices])
        glyph.flags = type(original.flags)([original.flags[i] for i in indices])
        glyph.endPtsOfContours = ends
        glyph.numberOfContours = len(ends)
        glyph.recalcBounds(font["glyf"])
        if target not in font.getGlyphOrder():
            order = font.getGlyphOrder() + [target]
            font.setGlyphOrder(order)
            if "HVAR" in font and font["HVAR"].table.AdvWidthMap:
                mapping = font["HVAR"].table.AdvWidthMap.mapping
                mapping[target] = mapping[base]
        font["glyf"][target] = glyph
        font["hmtx"][target] = (600, glyph.xMin)
        font["gvar"].variations[target] = deepcopy(
            font["gvar"].variations.get(base, [])
        )
        for variation in font["gvar"].variations[target]:
            variation.coordinates = [
                variation.coordinates[i] for i in indices
            ] + variation.coordinates[-4:]
    font["maxp"].numGlyphs = len(font.getGlyphOrder())
    cmap = font.getBestCmap()
    classes = {}
    for cp, name in cmap.items():
        if unicodedata.category(chr(cp)).startswith("M"):
            cc = unicodedata.combining(chr(cp))
            classes[name] = (
                "overlay"
                if cc == 1
                else (
                    "ogonek"
                    if cp == 0x328
                    else "attached" if cc == 202 else "bottom" if cc == 220 else "top"
                )
            )
    for name in font.getGlyphOrder():
        if name.endswith(".case") and name[:-5] in classes:
            classes[name] = classes[name[:-5]]
    locs = locations(font)
    glyphsets = [font.getGlyphSet(location=loc) for loc in locs]
    boxes = {
        name: [bounds(gs, name) for gs in glyphsets] for name in font.getGlyphOrder()
    }

    def scalar(values):
        s = VariableScalar()
        for loc, value in zip(locs, values):
            s.add_value(loc, round(value))
        return repr(s)

    def anchor(name, kind, role):
        coords = []
        for box in boxes[name]:
            l, b, r, t = box
            cx = (l + r) / 2
            if role == "mark":
                y = (
                    b
                    if kind == "top"
                    else t if kind in ("bottom", "attached", "ogonek") else (b + t) / 2
                )
            else:
                y = (
                    t + 48
                    if kind == "top"
                    else (
                        b - 48
                        if kind == "bottom"
                        else b + 6 if kind in ("attached", "ogonek") else (b + t) / 2
                    )
                )
                if kind == "ogonek":
                    cx = r - 40
            coords.append((cx, y))
        return (
            "<anchor "
            + scalar([p[0] for p in coords])
            + " "
            + scalar([p[1] for p in coords])
            + ">"
        )

    lines = ["languagesystem DFLT dflt;", "languagesystem latn dflt;"]
    decompositions = []
    for cp, name in cmap.items():
        chars = unicodedata.normalize("NFD", chr(cp))
        if (
            len(chars) > 1
            and all(ord(c) in cmap for c in chars)
            and all(cmap[ord(c)] in classes for c in chars[1:])
        ):
            decompositions.append(
                f"sub {name} by " + " ".join(cmap[ord(c)] for c in chars) + ";"
            )
    above = " ".join(n for n, k in classes.items() if k == "top")
    lines.extend(
        ["@AboveMarks = [" + above + "];", "feature ccmp {"]
        + decompositions
        + [
            "sub i' @AboveMarks by dotlessi;",
            "sub j' @AboveMarks by dotlessj;",
            "} ccmp;",
        ]
    )
    for name, kind in classes.items():
        if all(boxes[name]):
            lines.append(f'markClass {name} {anchor(name,kind,"mark")} @MC_{kind};')
    bases = {
        name
        for cp, name in cmap.items()
        if unicodedata.category(chr(cp))[0] in ("L", "N")
    }
    bases.update(n for n in ("dotlessi", "dotlessj") if n in boxes)
    lines.append("feature mark {")
    for name in sorted(bases):
        if all(boxes[name]):
            for kind in ("top", "bottom", "attached", "ogonek", "overlay"):
                lines.append(
                    f'pos base {name} {anchor(name,kind,"base")} mark @MC_{kind};'
                )
    lines.append("} mark;")
    lines.append("feature mkmk {")
    for name, kind in classes.items():
        if kind != "overlay" and all(boxes[name]):
            lines.append(f'pos mark {name} {anchor(name,kind,"base")} mark @MC_{kind};')
    lines.append("} mkmk;")
    fea = "\n".join(lines) + "\n"
    addOpenTypeFeaturesFromString(font, fea, tables=["GPOS", "GDEF", "GSUB"])
    merge_features(font["GPOS"], old_gpos)
    merge_features(font["GSUB"], old_gsub)
    # Keep existing ligature carets and attachment classes; use new variable anchors.
    new = font["GDEF"].table
    old = old_gdef.table
    new.LigCaretList = deepcopy(old.LigCaretList)
    new.AttachList = deepcopy(old.AttachList)
    new.MarkAttachClassDef = deepcopy(old.MarkAttachClassDef)
    existing = deepcopy(old.GlyphClassDef.classDefs) if old.GlyphClassDef else {}
    existing.update(new.GlyphClassDef.classDefs)
    new.GlyphClassDef.classDefs = existing
    for name in classes:
        advance, lsb = font["hmtx"][name]
        font["hmtx"][name] = (0, lsb)
        # These source marks had constant 600-unit advances; zero stays zero at every weight.
        for variation in font["gvar"].variations.get(name, []):
            assert not any(
                d not in (None, (0, 0)) for d in variation.coordinates[-4:]
            ), name
    if report_path:
        Path(report_path).write_text(
            json.dumps(
                {
                    "marks": classes,
                    "decomposed_accented_forms": len(decompositions),
                    "base_count": len(bases),
                    "anchor_locations": locs,
                    "retained_positioning_lookups": old_gpos.table.LookupList.LookupCount,
                    "mark_gap": 48,
                    "note": "Supported combining marks only; missing Unicode marks remain a separate coverage expansion.",
                },
                indent=2,
            )
            + "\n"
        )
        Path(report_path).with_suffix(".fea").write_text(fea)
    return font


def main():
    from specimens import specimen_families

    out = ROOT / "trials/2026-11-17-layout-optical/code"
    out.mkdir(parents=True, exist_ok=True)
    source = json.loads((ROOT / "recipes/layout-sources.json").read_text())["code"]
    import hashlib

    assert (
        hashlib.sha256((ROOT / source["font"]).read_bytes()).hexdigest()
        == source["sha256"]
    )
    font = TTFont(ROOT / source["font"])
    font.recalcTimestamp = False
    add_code_marks(font, out / "mark-attachment.json")
    font["head"].fontRevision = 1.023
    for record in font["name"].names:
        if record.nameID == 5:
            record.string = "Version 1.023; preview; variable mark attachment and canonical accent shaping".encode(
                record.getEncoding()
            )
        elif record.nameID == 3:
            record.string = "DaikonicTransitCode-VF 1.023 preview".encode(
                record.getEncoding()
            )
    font.save(out / "CodePositioned-VF.ttf")
    from adopt_weighting import instance
    from code_at_weight_proof import main as weight_proof

    for w, label in [(300, "Light"), (350, "Book"), (400, "Regular")]:
        instance(out / "CodePositioned-VF.ttf", w, None).save(
            out / f"CodePositioned-{label}.ttf"
        )
    weight_proof(out=out, stem="CodePositioned")
    print(out / "CodePositioned-VF.ttf")


if __name__ == "__main__":
    main()
