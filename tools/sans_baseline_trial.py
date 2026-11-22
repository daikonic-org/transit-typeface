"""Build a component-preserving Metropolitan Line baseline and Transit Sans trial."""

import argparse
from copy import deepcopy
import gzip
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from fontTools.misc.roundTools import otRound
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent, GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.varLib.models import VariationModel, normalizeLocation

from audit import shape_from_glyphs
from code_weight_width_trial import name_trial, sanitize
from derive_weights import topology
from dot_palette import indices
from font_feature_tools import append_glyph, expanded_variations
from sans_sparse_outline_trial import SOURCE, UPSTREAM, fit
from specimens import DATA, ROOT, Panel

FAMILY = "Daikonic Transit Sans Component Baseline Trial"
REVIEWED_GLYPHS = "cgsmnrCS5"
CURATED = {
    "one", "zero", "l", "y", "fi", "fl", "bullet", "arrowleft", "arrowright", "at",
}
DOT = "diamond.dot"
DOT_USERS = (
    "period", "colon", "semicolon", "periodcentered", "periodcentered.loclCAT",
    "periodcentered.loclCAT.case", "ellipsis", "exclam", "exclamdown",
    "question", "questiondown", "exclamdbl", "uni2047", "uni2048", "uni2049",
    "uni0307", "uni0307.case", "uni0308", "uni0308.case", "divide",
)


def clear_hints(glyph):
    glyph.program = Program()
    glyph.program.fromBytecode(b"")


def build_variations(model, masters, metrics=None):
    count = len(masters[0])
    supports = {
        tuple(sorted(support.items())): [(otRound(x), otRound(y)) for x, y in values] + [(0, 0)] * 4
        for support, values in zip(model.supports, model.getDeltas(masters)) if support
    }
    for key, values in (metrics or {}).items():
        supports.setdefault(key, [(0, 0)] * (count + 4))[-4:] = values[-4:]
    return [TupleVariation(dict(key), values) for key, values in supports.items()
            if any(value != (0, 0) for value in values)]


def install(font, name, glyph, variations):
    font["glyf"][name] = glyph
    font["gvar"].variations[name] = variations
    glyph.recalcBounds(font["glyf"])
    advance, _ = font["hmtx"][name]
    font["hmtx"][name] = advance, glyph.xMin if glyph.numberOfContours else 0


def components(parts):
    glyph = Glyph()
    glyph.numberOfContours = -1
    glyph.components = []
    for name, offset in parts:
        part = GlyphComponent()
        part.glyphName = name
        part.x, part.y = offset
        part.flags = 0
        glyph.components.append(part)
    clear_hints(glyph)
    return glyph


def normalised_box(points):
    return tuple((min(p[axis] for p in points), max(p[axis] for p in points)) for axis in (0, 1))


def subset_contours(old, selected):
    glyph = Glyph()
    glyph.coordinates = GlyphCoordinates()
    glyph.flags = bytearray()
    glyph.endPtsOfContours = []
    remap = []
    start = 0
    for end in old.endPtsOfContours:
        if end not in selected:
            cells = range(start, end + 1)
            glyph.coordinates.extend(old.coordinates[i] for i in cells)
            glyph.flags.extend(old.flags[i] & ~0x40 for i in cells)
            glyph.endPtsOfContours.append(len(glyph.coordinates) - 1)
            remap.extend(cells)
        start = end + 1
    glyph.numberOfContours = len(glyph.endPtsOfContours)
    clear_hints(glyph)
    return glyph, remap


def add_diamonds(font, released, masters, model):
    groups = indices(released, "period")
    assert len(groups) == 1
    diamonds = []
    for glyphs in masters:
        coords = glyphs["period"]._getGlyphInstance().coordinates
        (left, right), (bottom, top) = normalised_box([coords[i] for i in groups[0]])
        x, y = (right-left)/2, (top-bottom)/2
        diamonds.append(GlyphCoordinates([(0, otRound(y)), (otRound(x), 0),
                                           (0, otRound(-y)), (otRound(-x), 0)]))
    pen = TTGlyphPen(None)
    pen.moveTo(diamonds[0][0])
    for point in diamonds[0][1:]:
        pen.lineTo(point)
    pen.closePath()
    append_glyph(font, DOT, pen.glyph(), build_variations(model, diamonds), 0)
    font["GDEF"].table.GlyphClassDef.classDefs.pop(DOT, None)

    report = {}
    for name in DOT_USERS:
        if name not in released.getGlyphOrder():
            continue
        groups = indices(released, name)
        if not groups:
            continue
        original_deltas = expanded_variations(released, name)
        body, remap = subset_contours(released["glyf"][name], {group[-1] for group in groups})
        parts = []
        if remap:
            part = name + ".diamondBody"
            variants = [TupleVariation(dict(key), [delta[i] for i in remap] + [(0, 0)] * 4)
                        for key, delta in original_deltas.items()]
            append_glyph(font, part, body, variants, 0)
            font["GDEF"].table.GlyphClassDef.classDefs.pop(part, None)
            parts.append((part, (0, 0)))
        placements = []
        for glyphs in masters:
            coords = glyphs[name]._getGlyphInstance().coordinates
            centers = [tuple(otRound((a+b)/2) for a,b in normalised_box([coords[i] for i in group]))
                       for group in groups]
            placements.append(GlyphCoordinates([(0, 0)] * bool(parts) + centers))
        glyph = components(parts + [(DOT, pos) for pos in placements[0][len(parts):]])
        install(font, name, glyph, build_variations(model, placements, original_deltas))
        report[name] = len(groups)
    return report


def scaled_simple(font, released, upstream, review, masters, model):
    restored, reused, fallback = [], [], {}
    for name in upstream.getGlyphOrder():
        source = upstream["glyf"][name]
        if name in CURATED or name in DOT_USERS or source.isComposite():
            continue
        if name not in font.getGlyphOrder() or not source.numberOfContours:
            continue
        original = deepcopy(source)
        clear_hints(original)
        candidate = review["glyf"][name]
        if original.coordinates == candidate.coordinates and original.flags == candidate.flags:
            install(font, name, deepcopy(candidate), deepcopy(review["gvar"].variations.get(name, [])))
            reused.append(name)
            continue
        if len(original.coordinates) > 130:
            fallback[name] = "curated outline retained for high-complexity glyph"
            continue
        coords = [original.coordinates]
        coords.extend(
            fit(original, shape_from_glyphs(gs, name),
                x_offset=(gs[name].width - masters[0][name].width) / 2,
                shared_left_stem=name in {"m", "n", "r"})
            for gs in masters[1:]
        )
        old_deltas = expanded_variations(released, name)
        base_shape = shape_from_glyphs(upstream.getGlyphSet(), name)
        expected = topology(base_shape)
        for factor in (1, 0.75, 0.5, 0.25, 0):
            fitted = [GlyphCoordinates((otRound(a+(x-a)*factor), otRound(b+(y-b)*factor))
                                       for (a,b),(x,y) in zip(original.coordinates, points))
                      for points in coords]
            install(font, name, original, build_variations(model, fitted, old_deltas))
            try:
                valid = all(topology(shape_from_glyphs(font.getGlyphSet(location={"wght": weight}), name)) == expected
                            for weight in range(300, 601, 25))
            except (ValueError, RuntimeError):
                valid = False
            if valid:
                break
        if factor < 1:
            fallback[name] = factor
        restored.append(name)
    return restored, reused, fallback


def restore_components(font, released, upstream, masters, model, dot_users):
    restored = []
    names = set(font.getGlyphOrder())
    parent_order = sorted(upstream.getGlyphOrder(),
                          key=lambda name: upstream["glyf"][name].getCompositeMaxpValues(upstream["glyf"]).maxComponentDepth
                          if upstream["glyf"][name].isComposite() else 0)
    for name in parent_order:
        old = upstream["glyf"][name]
        if not old.isComposite() or name in CURATED or name in dot_users:
            continue
        if any(part.glyphName not in names or not hasattr(part, "x") for part in old.components):
            continue
        glyph = deepcopy(old)
        clear_hints(glyph)
        for part in glyph.components:
            # Transit retains its own advance variation for the parent.
            part.flags &= ~0x0200
        base = glyph.components[0].glyphName
        points = []
        for gs in masters:
            shift = otRound((gs[base].width - masters[0][base].width) / 2)
            points.append(GlyphCoordinates((part.x + (shift if i and not gs[part.glyphName].width else 0), part.y)
                                          for i, part in enumerate(glyph.components)))
        metrics = expanded_variations(released, name)
        install(font, name, glyph, build_variations(model, points, metrics))
        restored.append(name)
    return restored


def rename_variable(font):
    for record in font["fvar"].instances:
        label = font["name"].getDebugName(record.subfamilyNameID).replace(" ", "")
        record.postscriptNameID = font["name"].addName(FAMILY.replace(" ", "") + "-" + label)
    name_trial(font, FAMILY, variable=True)


def inputs(source, review):
    upstream_record = json.loads((UPSTREAM.parent / "PROVENANCE.json").read_text())
    release = source.parents[2]
    expected = json.loads((release / "manifest.json").read_text())["files"]
    upstream_hash = sha256(UPSTREAM.read_bytes()).hexdigest()
    release_hash = sha256(source.read_bytes()).hexdigest()
    if upstream_hash != upstream_record["regular_sha256"]:
        raise ValueError(f"Upstream checksum mismatch for {UPSTREAM}")
    if release_hash != expected[str(source.relative_to(release))]:
        raise ValueError(f"Transit checksum mismatch for {source}")
    return {
        "metropolitan_line": {"path": str(UPSTREAM.relative_to(ROOT)), "sha256": upstream_hash,
                              "commit": upstream_record["commit"]},
        "transit_weight_and_layout_reference": {"path": str(source.relative_to(ROOT)),
                                                 "sha256": release_hash},
        "reviewed_outline_sha256": sha256(review.read_bytes()).hexdigest(),
        "reviewed_glyphs": REVIEWED_GLYPHS,
    }


def specimen(variable, output, title="Transit Sans · component baseline"):
    width, height = 1180, 540
    body = [f'<rect width="{width}" height="{height}" fill="#f6f5ef"/>',
            f'<text x="28" y="40" font-weight="700" font-size="26">{title}</text>']
    for row, (weight, label) in enumerate(((300, "Light"), (400, "Regular"), (600, "SemiBold"))):
        y = 76 + row * 150
        body.append(f'<text x="28" y="{y}" fill="#435451" font-size="16">{label} {weight}</text>')
        panel = Panel(f'weight-{weight}', {**DATA["families"]["sans"], "font": str(variable.resolve())})
        panel.text("e é è ê ë   o ö ó   i j   H n m r", 28, y+57, 43, weight, "#151b1b", max_width=550)
        panel.text(". , : ; · … ? !   ‘ ’ “ ”   ai li   ← →", 582, y+57, 43, weight, "#151b1b", max_width=568)
        panel.text("Éléments de signalétique · déjà vu, naïve, façade…", 28, y+96, 21, weight, "#435451")
        body.append(panel.body())
    output.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Arial,sans-serif">'
        + "".join(body) + "</svg>"
    )


def export_regular(variable, output):
    regular = instantiateVariableFont(TTFont(variable, recalcTimestamp=False), {"wght": 400})
    name_trial(regular, FAMILY)
    static = output / REGULAR_NAME
    regular.save(static)
    sanitize(static)


def build(review_path, output):
    output.mkdir(parents=True, exist_ok=True)
    source = SOURCE / "DaikonicTransitSans-VF.ttf"
    provenance = inputs(source, review_path)
    released = TTFont(source)
    font = TTFont(source, recalcTimestamp=False)
    upstream = TTFont(UPSTREAM)
    review = TTFont(review_path)
    stable = output / "MetropolitanLine-Regular-Reference.ttf"
    stable.write_bytes(UPSTREAM.read_bytes())
    axis = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
    weights = (400, 300, 350, 500, 600)
    model = VariationModel([normalizeLocation({"wght": weight}, axis) for weight in weights])
    masters = [released.getGlyphSet(location={"wght": w}) for w in weights]
    restored, reused, fallback = scaled_simple(font, released, upstream, review, masters, model)
    diamonds = add_diamonds(font, released, masters, model)
    compounds = restore_components(font, released, upstream, masters, model, diamonds)
    rename_variable(font)
    variable = output / VARIABLE_NAME
    font.save(variable)
    sanitize(variable)
    rebuilt = TTFont(variable)
    export_regular(variable, output)
    for tag in ("GSUB", "GPOS", "cmap", "STAT"):
        assert released.getTableData(tag) == rebuilt.getTableData(tag), tag
    for weight in range(300, 601, 25):
        old = released.getGlyphSet(location={"wght": weight})
        new = rebuilt.getGlyphSet(location={"wght": weight})
        assert all(old[name].width == new[name].width for name in released.getGlyphOrder()), weight
    assert reused and compounds and diamonds
    report = {"inputs": provenance, "restored_directly": restored, "reviewed_reuse": reused,
              "upstream_composites_restored": compounds, "shared_diamond_users": diamonds,
              "limited_weight_fits": fallback,
              "composite_count": sum(rebuilt["glyf"][name].isComposite() for name in rebuilt.getGlyphOrder())}
    (output / "baseline-report.json").write_text(json.dumps(report, indent=2) + "\n")
    specimen(variable, output / "Baseline-Specimen.svg")
    print({key: len(value) if isinstance(value, (list, dict)) else value
           for key, value in report.items() if key != "inputs"})


BASELINE_SOURCE = ROOT / "sources/sans-component-baseline"
VARIABLE_NAME = "DaikonicTransitSansComponentBaselineTrial-VF.ttf"
REGULAR_NAME = "DaikonicTransitSansComponentBaselineTrial-Regular.ttf"


def xml_tree(font_path, tables=None):
    with TTFont(font_path, recalcTimestamp=False) as font:
        buffer = BytesIO()
        font.saveXML(buffer, tables=tables)
        return ET.fromstring(buffer.getvalue())


def glyph_signature(glyph):
    return (
        glyph.tag,
        tuple(sorted(glyph.attrib.items())),
        (glyph.text or "").strip(),
        tuple(glyph_signature(child) for child in glyph),
    )


def original_glyphs():
    upstream_record = json.loads((UPSTREAM.parent / "PROVENANCE.json").read_text())
    if sha256(UPSTREAM.read_bytes()).hexdigest() != upstream_record["regular_sha256"]:
        raise ValueError(f"Upstream checksum mismatch for {UPSTREAM}")
    glyphs = {}
    for glyph in xml_tree(UPSTREAM, ["glyf"]).find("glyf"):
        name = glyph.attrib["name"]
        if not len(glyph):
            continue
        for instructions in glyph.findall("instructions"):
            glyph.remove(instructions)
        ET.SubElement(glyph, "instructions")
        for component in glyph.findall("component"):
            # Transit carries its own variable metrics and does not inherit a component's advance.
            component.set("flags", hex(int(component.attrib["flags"], 16) & ~0x200))
        glyphs[name] = glyph
    return glyphs


def capture_source(reviewed):
    """Refresh the recipe from an explicitly reviewed component baseline."""
    upstream = original_glyphs()
    root = xml_tree(reviewed)
    table = root.find("glyf")
    reused = 0
    for index, glyph in enumerate(table):
        name = glyph.attrib["name"]
        if name in upstream and glyph_signature(glyph) == glyph_signature(upstream[name]):
            table.remove(glyph)
            table.insert(index, ET.Element("upstreamGlyph", name=name))
            reused += 1
    root.set("reviewedSha256", sha256(reviewed.read_bytes()).hexdigest())
    ET.indent(root)
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    BASELINE_SOURCE.mkdir(parents=True, exist_ok=True)
    (BASELINE_SOURCE / "TransitSans.ttx.gz").write_bytes(gzip.compress(payload, mtime=0))
    print(f"Recorded {reused} Metropolitan Line glyph references")


def load_baseline():
    upstream = original_glyphs()
    recipe = BASELINE_SOURCE / "TransitSans.ttx.gz"
    with gzip.open(recipe, "rb") as source:
        root = ET.parse(source).getroot()
    expected = root.attrib.pop("reviewedSha256")
    table = root.find("glyf")
    reused = []
    for index, entry in enumerate(table):
        if entry.tag == "upstreamGlyph":
            name = entry.attrib["name"]
            table.remove(entry)
            table.insert(index, upstream[name])
            reused.append(name)
    assert reused
    font = TTFont(recalcTimestamp=False)
    font.importXML(BytesIO(ET.tostring(root, encoding="utf-8", xml_declaration=True)))
    buffer = BytesIO()
    font.save(buffer)
    payload = buffer.getvalue()
    digest = sha256(payload).hexdigest()
    if digest != expected:
        raise ValueError(f"Rebuilt baseline digest {digest} differs from the reviewed digest {expected}")

    glyf = font["glyf"]
    components_by_glyph = {
        name: [part.glyphName for part in glyf[name].components]
        for name in font.getGlyphOrder() if glyf[name].isComposite()
    }
    diamond_users = [name for name, parts in components_by_glyph.items() if DOT in parts]
    if set(diamond_users) != set(DOT_USERS) or len(glyf[DOT].coordinates) != 4:
        raise ValueError("Rebuilt baseline does not retain the approved shared diamond")
    report = {
        "source": str(recipe.relative_to(ROOT)),
        "metropolitan_line_glyphs": reused,
        "composite_count": len(components_by_glyph),
        "components_by_glyph": components_by_glyph,
        "shared_diamond_users": diamond_users,
        "variable_sha256": digest,
    }
    return payload, report


def rebuild_baseline(output):
    payload, report = load_baseline()
    output.mkdir(parents=True, exist_ok=True)
    variable = output / VARIABLE_NAME
    variable.write_bytes(payload)
    sanitize(variable)
    export_regular(variable, output)
    (output / "MetropolitanLine-Regular-Reference.ttf").write_bytes(UPSTREAM.read_bytes())
    (output / "baseline-report.json").write_text(json.dumps(report, indent=2) + "\n")
    specimen(variable, output / "Baseline-Specimen.svg")
    print(f"Rebuilt {variable} using {len(report['metropolitan_line_glyphs'])} original glyphs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--capture", type=Path, metavar="REVIEWED_VF",
                        help="refresh the recipe from a reviewed component baseline")
    parser.add_argument("--fit-review", type=Path, metavar="REVIEW_VF",
                        help="run the historical fit against a released comparison font")
    args = parser.parse_args()
    if args.capture is not None:
        if args.output is not None or args.fit_review is not None:
            parser.error("--capture takes only the reviewed VF")
        capture_source(args.capture)
    elif args.output is None:
        parser.error("specify an output directory")
    elif args.fit_review is not None:
        build(args.fit_review, args.output)
    else:
        rebuild_baseline(args.output)


if __name__ == "__main__":
    main()
