"""Trial hooked ai and li with matching stem gaps and retained outer kerning."""

from io import BytesIO
from pathlib import Path
import json
import statistics
import subprocess
import tempfile

import pathops
import uharfbuzz as hb
import ots
from fontTools.ttLib.tables import otTables
from fontTools.ttLib import TTFont

from adopt_weighting import ROOT, instance
from audit import shape, spans
from derive_weights import install
from specimens import DATA, Panel

OUT = ROOT / ".build/hook-ligatures-r2"


def rect(x0, y0, x1, y1):
    p = pathops.Path()
    p.moveTo(x0, y0)
    p.lineTo(x1, y0)
    p.lineTo(x1, y1)
    p.lineTo(x0, y1)
    p.close()
    return p


def op(a, b, operation=pathops.PathOp.UNION):
    return pathops.op(a, b, operation, fix_winding=True, clockwise=True)


def run(font, text, liga=True):
    stream = BytesIO()
    font.save(stream)
    h = hb.Font(hb.Face(stream.getvalue()))
    b = hb.Buffer()
    b.add_str(text)
    b.guess_segment_properties()
    hb.shape(h, b, {"liga": liga})
    return [
        (font.getGlyphName(g.codepoint), p.x_advance, p.x_offset)
        for g, p in zip(b.glyph_infos, b.glyph_positions)
    ]


def whitespace_band(font):
    contours = sorted(
        (c for c in shape(font, "l_i").contours if c.clockwise),
        key=lambda c: c.bounds[1],
    )
    assert len(contours) == 3
    lower, stem, _ = contours
    x0, _, x1, _ = stem.bounds
    gaps = []
    for frac in (0.25, 0.5, 0.75):
        x = x0 + (x1 - x0) * frac
        gaps.append(spans(stem, x, 0)[0][0] - spans(lower, x, 0)[-1][1])
    return statistics.median(gaps)


def extend_hook(l_path, amount):
    if amount <= 0:
        return l_path
    bottom = l_path.bounds[1]
    xs = spans(l_path, bottom + 1, 1)[0]
    cut = sum(xs) / 2
    ys = spans(l_path, cut, 0)[0]
    left = op(l_path, rect(-1000, -1000, cut, 2000), pathops.PathOp.INTERSECTION)
    right = op(
        l_path, rect(cut, -1000, 3000, 2000), pathops.PathOp.INTERSECTION
    ).transform(1, 0, 0, 1, amount, 0)
    return op(op(left, rect(cut, ys[0], cut + amount, ys[1])), right)


def construct(font, pair, band):
    original = run(font, pair, False)
    assert len(original) == 2 and all(p[2] == 0 for p in original)
    origin = original[0][1]
    ordinary_advance = sum(p[1] for p in original)
    a, l, i = shape(font, "a"), shape(font, "l"), shape(font, "i")
    l_stem = spans(l, 275, 1)[0]
    if pair == "li":
        # The i-to-stem gap must match approved ai, rather than ordinary li.
        origin = l_stem[1] + run(font, "ai", False)[0][1] - a.bounds[2]
    origin = round(origin)
    movement = origin - original[0][1]
    advance = ordinary_advance + movement
    i_left, i_right = spans(i, 275, 1)[0]
    i_right += origin
    shift = a.bounds[2] - l_stem[1] if pair == "ai" else 0
    extension = i_right - (l.bounds[2] + shift)
    hook = extend_hook(l, extension).transform(1, 0, 0, 1, shift, 0)
    if pair == "ai":
        hook = op(hook, rect(-1000, -1000, 3000, 180), pathops.PathOp.INTERSECTION)
    # Sweep vertically downward: its top is the exact hook curve plus the
    # existing li whitespace band, without horizontal dilation of either letter.
    mask = pathops.Path()
    for delta in range(0, 577, 32):
        mask = op(mask, hook.transform(1, 0, 0, 1, 0, band - delta))
    normal_i = i.transform(1, 0, 0, 1, origin, 0)
    trimmed_i = op(normal_i, mask, pathops.PathOp.DIFFERENCE)
    if pair == "ai":
        a = trim_old_a_foot(a, hook)
    first = op(a, hook) if pair == "ai" else hook
    result = op(first, trimmed_i)
    # Every part of i above the interaction band retains its ordinary position.
    above = rect(-1000, 260, 3000, 2000)
    assert (
        op(
            op(normal_i, above, pathops.PathOp.INTERSECTION),
            op(trimmed_i, above, pathops.PathOp.INTERSECTION),
            pathops.PathOp.XOR,
        ).area
        < 0.01
    )
    install(font, "a_i" if pair == "ai" else "l_i", result)
    glyph = "a_i" if pair == "ai" else "l_i"
    font["hmtx"][glyph] = (advance, font["hmtx"][glyph][1])
    assert sum(p[1] for p in run(font, pair)) == advance
    return {
        "i_origin": origin,
        "ordinary_pair_advance": ordinary_advance,
        "ligature_advance": advance,
        "i_movement": movement,
        "stem_gap": origin + i_left - (a.bounds[2] if pair == "ai" else l_stem[1]),
        "hook_extension": extension,
        "hook_shift": shift,
        "whitespace_band": band,
    }


def trim_old_a_foot(a, hook):
    """Replace the baseline foot with a curved join from bowl to new hook."""
    segments = list(a.segments)
    joints = [
        nxt[1][-1]
        for prev, nxt in zip(segments, segments[1:])
        if prev[0] == nxt[0] == "lineTo"
        and prev[1][-1][1] <= 0
        and prev[1][-1][0] == nxt[1][-1][0]
        and nxt[1][-1][1] > 0
    ]
    assert len(joints) == 1, joints
    x0, y0 = joints[0]
    x1 = a.bounds[2]
    y1 = spans(hook, x1, 0)[0][0]
    tangent = (spans(hook, x1 + 1, 0)[0][0] - spans(hook, x1 - 1, 0)[0][0]) / 2
    reach = (x1 - x0) * 0.2
    cut = pathops.Path()
    cut.moveTo(x0, -1000)
    cut.lineTo(x1, -1000)
    cut.lineTo(x1, y1)
    cut.cubicTo(x1 - reach, y1 - reach * tangent, x0 + reach, y0 + reach * 0.7, x0, y0)
    cut.close()
    return op(a, cut, pathops.PathOp.DIFFERENCE)


def bind(panel, font, weight):
    stream = BytesIO()
    font.save(stream)
    h = hb.Font(hb.Face(stream.getvalue()))
    h.scale = (1000, 1000)
    panel.instances[weight] = (font, h)


def preserve_boundary_kerning(font):
    """Give each replacement the left class of a/l and right class of i."""
    corrections = {}
    desired_pairs = {}
    stream = BytesIO()
    font.save(stream)
    h = hb.Font(hb.Face(stream.getvalue()))

    def measured(text, liga):
        b = hb.Buffer()
        b.add_str(text)
        b.guess_segment_properties()
        hb.shape(h, b, {"liga": liga})
        return sum(p.x_advance for p in b.glyph_positions) - sum(
            font["hmtx"][font.getGlyphName(g.codepoint)][0] for g in b.glyph_infos
        )

    for code, glyph in font.getBestCmap().items():
        char = chr(code)
        for pair in ("ai", "li"):
            lig = "a_i" if pair == "ai" else "l_i"
            for left in (True, False):
                ordinary = char + pair[0] if left else "i" + char
                trial = char + pair if left else pair + char
                desired = measured(ordinary, False)
                current = measured(trial, True)
                delta = desired - current
                desired_pairs[(glyph, lig) if left else (lig, glyph)] = desired
                if delta:
                    corrections[(glyph, lig) if left else (lig, glyph)] = delta
    for first in ("ai", "li"):
        for second in ("ai", "li"):
            desired_pairs[(first[0] + "_i", second[0] + "_i")] = measured(
                "i" + second[0], False
            )
            corrections[(first[0] + "_i", second[0] + "_i")] = measured(
                "i" + second[0], False
            ) - measured(first + second, True)
    table = otTables.PairPos()
    table.Format = 1
    table.ValueFormat1, table.ValueFormat2 = 4, 0
    table.Coverage = otTables.Coverage()
    order = font.getReverseGlyphMap()
    table.Coverage.glyphs = sorted({a for a, b in corrections}, key=order.get)
    table.PairSet = []
    for first in table.Coverage.glyphs:
        pairs = otTables.PairSet()
        pairs.PairValueRecord = []
        for (a, b), delta in sorted(corrections.items(), key=lambda p: order[p[0][1]]):
            if a != first:
                continue
            record = otTables.PairValueRecord()
            record.SecondGlyph = b
            record.Value1 = otTables.ValueRecord()
            record.Value1.XAdvance = delta
            record.Value2 = None
            pairs.PairValueRecord.append(record)
        pairs.PairValueCount = len(pairs.PairValueRecord)
        table.PairSet.append(pairs)
    table.PairSetCount = len(table.PairSet)
    lookup = otTables.Lookup()
    lookup.LookupType, lookup.LookupFlag = 2, 0
    lookup.SubTable, lookup.SubTableCount = [table], 1
    gpos = font["GPOS"].table
    index = len(gpos.LookupList.Lookup)
    gpos.LookupList.Lookup.append(lookup)
    gpos.LookupList.LookupCount += 1
    for record in gpos.FeatureList.FeatureRecord:
        if record.FeatureTag == "kern":
            record.Feature.LookupListIndex.append(index)
            record.Feature.LookupCount += 1
    return desired_pairs


def proof(
    fonts,
    source,
    reference=None,
    title="SANS / CLEAN ai FOOT + MATCHED li GAP",
    columns=None,
    weights=(350, 400, 500, 600),
):
    cfg = DATA["families"]["sans"]
    labels = Panel("hook-labels", cfg)
    labels.text(title, 24, 34, 22, 400, "#194454")
    for col, title in enumerate(
        columns
        or ["PREVIOUS HOOK STUDY", "ORDINARY LETTERS", "REVISED / MATCHED STEM GAPS"]
    ):
        labels.text(title, 24 + 400 * col, 70, 12, 400, "#194454")
    fragments = []
    for row, w in enumerate(weights):
        y = 103 + row * 210
        labels.text("Weight " + str(w), 24, y, 12, 400, "#194454")
        for col in range(3):
            f = (
                fonts[w]
                if col == 2
                else (
                    TTFont(
                        (reference or ROOT / "trials/2026-11-16-sans-hooks")
                        / f"DaikonicTransitSansHookStudy-{w}.ttf"
                    )
                    if col == 0
                    else instance(source, w, None)
                )
            )
            p = Panel(f"hook-{w}-{col}", cfg)
            bind(p, f, w)
            x = 24 + 400 * col
            p.text("ai   li", x, y + 88, 100, w, "#101712", features={"liga": col != 1})
            p.text(
                "Daikonic", x, y + 134, 36, w, "#101712", features={"liga": col != 1}
            )
            p.text(
                "rain daily liquid",
                x,
                y + 169,
                22,
                w,
                "#101712",
                features={"liga": col != 1},
            )
            p.text(
                "ai aim rain daily liquid mailing",
                x,
                y + 193,
                14,
                w,
                "#101712",
                features={"liga": col != 1},
            )
            fragments.append(p.body())
    fragments.insert(0, labels.body())
    height = 115 + len(weights) * 210
    (OUT / "Comparison.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}"><rect width="1200" height="{height}" fill="#EEECD9"/>'
        + "".join(fragments)
        + "</svg>"
    )


def main():
    OUT.mkdir(exist_ok=True)
    cfg = DATA["families"]["sans"]
    source = ROOT / cfg.get("ligature_baseline", cfg["font"])
    fonts = {}
    reports = []
    for w in (300, 350, 400, 500, 600):
        f = instance(source, w, None)
        band = whitespace_band(f)
        details = {pair: construct(f, pair, band) for pair in ("ai", "li")}
        preserve_boundary_kerning(f)
        family = "Daikonic Transit Sans Hook Study R2"
        style = {
            300: "Light",
            350: "Book",
            400: "Regular",
            500: "Medium",
            600: "SemiBold",
        }[w]
        for n in f["name"].names:
            text = (
                n.toUnicode()
                .replace(cfg["name"], family)
                .replace("DaikonicTransitSans", "DaikonicTransitSansHookStudyR2")
            )
            n.string = text.encode(n.getEncoding())
        names = {
            1: family if w == 400 else family + " " + style,
            2: "Regular",
            3: "0.002;DaikonicTransitSansHookStudyR2-" + style,
            4: family + " " + style,
            6: "DaikonicTransitSansHookStudyR2-" + style,
            16: family,
            17: style,
        }
        for record in f["name"].names:
            if record.nameID in names:
                record.string = names[record.nameID].encode(record.getEncoding())
        f["OS/2"].usWeightClass = w
        f["head"].fontRevision = 0.002
        for n in f["name"].names:
            if n.nameID == 5:
                n.string = "Version0.002; hook ligature study".encode(n.getEncoding())
        path = OUT / f"DaikonicTransitSansHookStudy-{w}.ttf"
        f.save(path)
        with tempfile.TemporaryDirectory() as tmp:
            check = subprocess.run(
                [ots.OTS_SANITIZE, str(path), str(Path(tmp) / "checked.ttf")],
                capture_output=True,
            )
            assert check.returncode == 0, check.stderr.decode()
        fonts[w] = f
        words = {
            word: {
                "plain": sum(p[1] for p in run(f, word, False)),
                "ligatures": sum(p[1] for p in run(f, word, True)),
            }
            for word in ("ai", "li", "Daikonic", "daily", "liquid", "mailing")
        }
        for word, values in words.items():
            expected = values["plain"] + word.count("li") * details["li"]["i_movement"]
            values["expected"] = expected
            assert values["ligatures"] == expected, (word, values)
        assert abs(details["ai"]["stem_gap"] - details["li"]["stem_gap"]) <= 0.5
        reports.append(
            {
                "weight": w,
                "pairs": details,
                "word_advances": words,
                "sanitizer": "passed",
            }
        )
        print(w, details, flush=True)
    (OUT / "report.json").write_text(json.dumps(reports, indent=2) + "\n")
    proof(fonts, source)


if __name__ == "__main__":
    main()
