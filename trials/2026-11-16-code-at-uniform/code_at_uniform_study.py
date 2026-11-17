"""Larger fresh @, matching inner/outer strokes and fixed coding advances."""

from copy import deepcopy
from io import BytesIO
import json
import tempfile
import subprocess
import pathops
import uharfbuzz as hb
import ots
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from adopt_weighting import ROOT, instance
from audit import shape
from derive_weights import install, topology, coverage_difference
from compatibility import compatible_masters
from code_at_study import BASE, build_at_variant
from code_at_redraw import drawing
from specimens import DATA, Panel
import code_balance_study as review

OUT = ROOT / "trials/2026-11-16-code-at-uniform"
PREVIOUS = (
    ROOT / "trials/2026-11-16-code-at-redraw/DaikonicTransitCodeRedrawnAtStudy-VF.ttf"
)
RATIO = 0.80
SCALE = 1.06
ALT = "at.compact"


def revise(font):
    install(font, "at", drawing(font, outer=RATIO, inner=RATIO, scale=SCALE))


def overlap(a, b):
    return abs(pathops.op(a, b, pathops.PathOp.INTERSECTION).area)


def run(font, text):
    if not hasattr(font, "_review_hb_font"):
        stream = BytesIO()
        font.save(stream)
        font._review_hb_font = hb.Font(hb.Face(stream.getvalue()))
        font._review_hb_font.scale = (1000, 1000)
    h = font._review_hb_font
    b = hb.Buffer()
    b.add_str(text)
    b.guess_segment_properties()
    hb.shape(h, b, {"calt": True, "liga": True})
    return [
        (font.getGlyphOrder()[g.codepoint], g.cluster, p.x_advance, p.x_offset)
        for g, p in zip(b.glyph_infos, b.glyph_positions)
    ]


def add_compact(font):
    font.ensureDecompiled()
    masters = [instance(BASE, w, None) for w in [300, 350, 400]]
    paths = [drawing(f, outer=RATIO, inner=RATIO, scale=1) for f in masters]
    glyphs, missing = compatible_masters(paths)
    assert not missing
    order = font.getGlyphOrder() + [ALT]
    font.setGlyphOrder(order)
    for g in glyphs:
        g.recalcBounds(font["glyf"])
    font["glyf"][ALT] = glyphs[1]
    font["hmtx"][ALT] = (600, glyphs[1].xMin)
    variations = []
    for j, axis in [(0, (-1.0, -1.0, 0.0)), (2, (0.0, 1.0, 1.0))]:
        delta = [
            (x - bx, y - by)
            for (x, y), (bx, by) in zip(glyphs[j].coordinates, glyphs[1].coordinates)
        ] + [(0, 0)] * 4
        variations.append(TupleVariation({"wght": axis}, delta))
    font["gvar"].variations[ALT] = variations
    hvar = font["HVAR"].table
    for name in ["AdvWidthMap", "LsbMap", "RsbMap"]:
        mapping = getattr(hvar, name, None)
        if mapping is not None:
            mapping.mapping[ALT] = mapping.mapping.get("at", 0)
    if "GDEF" in font and font["GDEF"].table.GlyphClassDef:
        font["GDEF"].table.GlyphClassDef.classDefs[ALT] = 1
    return paths


def add_context(font, triggers):
    names = " ".join(sorted(set(triggers) | {"at", ALT}))
    rules = f"""languagesystem DFLT dflt;
    languagesystem latn dflt;
    @CompactNeighbors=[{names}];
    feature calt {{
      sub at' @CompactNeighbors by {ALT};
      sub @CompactNeighbors at' by {ALT};
    }} calt;
    """
    scratch = TTFont()
    scratch.setGlyphOrder(font.getGlyphOrder())
    addOpenTypeFeaturesFromString(scratch, rules)
    source = scratch["GSUB"].table
    target = font["GSUB"].table
    offset = len(target.LookupList.Lookup)

    def remap(value):
        if isinstance(value, (list, tuple)):
            for item in value:
                remap(item)
        elif hasattr(value, "__dict__"):
            if type(value).__name__ == "SubstLookupRecord":
                value.LookupListIndex += offset
            else:
                for item in vars(value).values():
                    remap(item)

    for lookup in source.LookupList.Lookup:
        remap(lookup)
    target.LookupList.Lookup.extend(source.LookupList.Lookup)
    target.LookupList.LookupCount = len(target.LookupList.Lookup)
    extra = [
        i + offset
        for r in source.FeatureList.FeatureRecord
        if r.FeatureTag == "calt"
        for i in r.Feature.LookupListIndex
    ]
    existing = [r for r in target.FeatureList.FeatureRecord if r.FeatureTag == "calt"]
    assert existing
    for r in existing:
        r.Feature.LookupListIndex.extend(extra)
        r.Feature.LookupCount = len(r.Feature.LookupListIndex)
    (OUT / "CompactContext.fea").write_text(rules)


def main():
    vf = build_at_variant(
        revise,
        OUT,
        "Daikonic Transit Code Uniform At Study",
        "larger at with equal inner and outer strokes",
        compatible_paths=True,
    )
    f = TTFont(vf)
    compact_paths = add_compact(f)
    characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789()[]{}!#$%&*+,-./:;<=>?^_|~@"
    triggers = set()
    for w in [300, 350, 400]:
        large = instance(vf, w, None)
        a = shape(large, "at")
        for char in characters:
            name = large.getBestCmap()[ord(char)]
            b = shape(large, name)
            if (
                max(
                    overlap(a, b.transform(1, 0, 0, 1, 600, 0)),
                    overlap(b, a.transform(1, 0, 0, 1, 600, 0)),
                )
                > 1
            ):
                triggers.add(name)
    add_context(f, triggers)
    f.save(vf)
    paths = [vf]
    for w, style in [(300, "Light"), (350, "Book"), (400, "Regular")]:
        path = OUT / f"DaikonicTransitCodeUniformAtStudy-{style}.ttf"
        names = TTFont(path)["name"]
        snap = instance(vf, w, None)
        snap["name"] = names
        snap.save(path)
        paths.append(path)
    for p in paths:
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [
                    ots.OTS_SANITIZE,
                    str(p),
                    str(ROOT / ".build" / ("uniform-at-" + p.name)),
                ],
                capture_output=True,
            )
            assert r.returncode == 0, r.stderr.decode()
    checks = []
    for w in range(300, 401, 10):
        font = instance(vf, w, None)
        p = shape(font, "at")
        compact = shape(font, ALT)
        assert topology(pathops.simplify(p, fix_winding=True, clockwise=True)) == (1, 1)
        assert topology(
            pathops.simplify(compact, fix_winding=True, clockwise=True)
        ) == (1, 1)
        assert font["hmtx"]["at"][0] == font["hmtx"][ALT][0] == 600
        assert abs(p.bounds[0] + 10) < 2 and abs(p.bounds[3] - 579) < 2, (w, p.bounds)
        assert compact.bounds[0] >= 0 and compact.bounds[2] <= 600
        expected = drawing(
            instance(BASE, w, None), outer=RATIO, inner=RATIO, scale=SCALE
        )
        err = coverage_difference(p, expected)
        assert err < 0.015
        for text in ["@@", "@@@", "name@@host"]:
            shaped = run(font, text)
            assert all(n == ALT for n, c, a, x in shaped if text[c] == "@"), (
                w,
                text,
                shaped,
            )
            assert all(a == 600 for n, c, a, x in shaped)
        assert overlap(compact, compact.transform(1, 0, 0, 1, 600, 0)) < 1
        for text in [
            "snake_case",
            "ke Ke KE",
            "-> ->> <- <<- => == === != !==",
            "vi yi iv iy",
        ]:
            assert run(font, text) == run(instance(BASE, w, None), text), (w, text)
        checks.append(
            {
                "weight": w,
                "bounds": p.bounds,
                "compact_bounds": compact.bounds,
                "coverage_error": err,
            }
        )
    (OUT / "validation.json").write_text(
        json.dumps(
            {
                "scale_centerline_both_axes": SCALE,
                "inner_and_outer_weight_ratio": RATIO,
                "compact_triggers": sorted(triggers),
                "sanitized_fonts": 4,
                "checks": checks,
            },
            indent=2,
        )
        + "\n"
    )
    parts = []
    for row, w in enumerate([300, 350, 400]):
        for col, (label, path) in enumerate(
            [
                ("previous / lighter inside", PREVIOUS),
                ("larger / equal inside and outside", vf),
            ]
        ):
            p = Panel(f"{row}-{col}", DATA["families"]["code"])
            review.bind(p, instance(path, w, None))
            x = 25 + 600 * col
            y = 35 + row * 235
            p.text(f"{w} / {label}", x, y, 12, 400, "#194454")
            p.text("o@o", x, y + 90, 110, 400, "#101712")
            p.text("user@example.com", x, y + 145, 27, 400, "#101712")
            p.text("@name  @@  @@@  @property", x, y + 180, 15, 400, "#101712")
            p.elements.append(
                f'<rect x="{600*col}" y="{y+190}" width="600" height="31" fill="#101712"/>'
            )
            p.text("email@host.io  @@  @@@", x, y + 211, 14, 400, "#EEECD9")
            parts.append(p.body())
    (OUT / "Comparison.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="750"><rect width="1200" height="750" fill="#EEECD9"/>'
        + "".join(parts)
        + "</svg>"
    )
    review.OUT = OUT
    review.browser_proof(
        {
            "Book / previous": instance(PREVIOUS, 350, None),
            "Book / larger and equal strokes": instance(vf, 350, None),
        },
        samples=[
            (13, "o@o user@example.com @name @decorator @@ @@@"),
            (14, "email@host.io  @property  @staticmethod  @@"),
            (16, "o @ o  user@example.com  @@ @@@"),
        ],
        title="Code / larger at with equal strokes / Book 350",
    )
    print(
        "Built and sanitized four fonts; checked11weights, equal stroke construction, repeat fitting and retained operators."
    )


if __name__ == "__main__":
    main()
