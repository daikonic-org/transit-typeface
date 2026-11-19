"""Build contextual texture healing for upright Transit Code."""

import argparse
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import tempfile
import unicodedata

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
import ots
import pathops
import subprocess
import uharfbuzz as hb

from audit import shape_from_glyphs
from code_receiver_shapes import RECEIVERS, FORM_SHIFT, build_receivers
from font_feature_tools import add_features, append_glyph, compose, label_stylistic_set
from italic_companions import shaped_copy
from specimens import ROOT, specimen_families

DONORS = "aijl"
DONOR_SHIFT = 18
WIDTH = 600
FEATURE = "ss03"
OFF_FEATURE = "ss04"
PUNCTUATION = '.,:;!?"‘’“”'
# The preserved 550-unit A Bowl Trial moved the left bowl edge by 20 units.
# Scale that correction from its x-height to the current Code x-height.
BOWL_RETURN = 20 * 530 / 473


def ramp(value, start, end):
    return min(1, max(0, (value - start) / (end - start)))


def add_centered_donor(font, source):
    glyph = font["glyf"][source]
    name = source + ".heal.center"
    new, deltas = shaped_copy(
        font,
        source,
        source,
        range(len(glyph.coordinates)),
        lambda index, x, y: (
            x + donor_adjustment(source, *glyph.coordinates[index]),
            y,
        ),
    )
    new.recalcBounds(font["glyf"])
    new.coordinates.translate((round((WIDTH - new.xMin - new.xMax) / 2), 0))
    append_glyph(
        font,
        name,
        new,
        [TupleVariation(dict(key), deltas[key]) for key in sorted(deltas)],
        WIDTH,
        metric_source=source,
    )


def donor_adjustment(letter, x, y):
    if letter == "a":
        # Revert only the extra width added to the lower bowl.
        return BOWL_RETURN * (1 - ramp(x, 180, 390)) * (1 - ramp(y, 210, 315))
    if letter == "i":
        if y >= 135:
            return 0
        return 35 * ((1 - ramp(x, 94, 270)) - ramp(x, 378, 546))
    if letter == "l":
        return 29 * ((1 - ramp(x, 66, 237)) - ramp(x, 342, 533))
    # Shorten j at the outer end of its curved descender, keeping the stem
    # and tittle the same width as the upright glyph.
    hook = max(1 - ramp(y, -110, -55), ramp(y, 365, 415) * (1 - ramp(y, 560, 620)))
    return 32 * (1 - ramp(x, 152, 318)) * hook


def build(source, output, *, trial=True, default_on=False):
    font = TTFont(source, recalcTimestamp=False)
    for letter in DONORS:
        add_centered_donor(font, letter)
        for side, offset in (("left", -DONOR_SHIFT), ("right", DONOR_SHIFT)):
            compose(
                font,
                letter + ".heal." + side,
                [(letter + ".heal.center", 1, 1, offset, 0)],
                WIDTH,
            )
    build_receivers(font, alternates=True)

    rules = ["languagesystem DFLT dflt;", "languagesystem latn dflt;"]
    groups = {
        "Donor": list(DONORS),
        "DonatedLeft": [n + ".heal.left" for n in DONORS],
        "DonatedRight": [n + ".heal.right" for n in DONORS],
        "DonatedCenter": [n + ".heal.center" for n in DONORS],
        "Receive": list(RECEIVERS),
        "ReceiveLeft": [n + ".heal.left" for n in RECEIVERS],
        "ReceiveRight": [n + ".heal.right" for n in RECEIVERS],
        "ReceiveBoth": [n + ".heal.both" for n in RECEIVERS],
    }
    groups["FromLeft"] = groups["DonatedLeft"] + groups["DonatedCenter"]
    groups["FromRight"] = groups["DonatedRight"] + groups["DonatedCenter"]
    if default_on:
        cmap = font.getBestCmap()
        punctuation = [cmap[ord(char)] for char in PUNCTUATION]
        groups["FromLeft"] += punctuation
        groups["FromRight"] += punctuation
    for group, names in groups.items():
        rules.append(f"@{group} = [" + " ".join(names) + "];")
    marks = set(font["GDEF"].table.GlyphClassDef.classDefs)
    marks = {n for n in marks if font["GDEF"].table.GlyphClassDef.classDefs[n] == 3}
    marks.update(
        n
        for cp, n in font.getBestCmap().items()
        if unicodedata.category(chr(cp)).startswith("M")
    )
    rules.append("@HealingMarks = [" + " ".join(sorted(marks)) + "];")
    rules.append(
        "@HealingQuotes = [quotesingle quotesingle.lifetime quotesingle.lifetime.compact];"
    )
    activate = "calt" if default_on else FEATURE
    rules += [
        f"feature {activate} {{",
        "lookup GiveSpace {",
        "ignore sub @Donor' @HealingMarks;",
        "ignore sub @HealingQuotes @Donor';",
        "ignore sub @HealingQuotes @Receive @Donor';",
        "sub @Receive @Donor' @Receive by @DonatedCenter;",
        "sub @Donor' @Receive by @DonatedLeft;",
        "sub @Receive @Donor' by @DonatedRight;",
        "} GiveSpace;",
        "lookup TakeSpace {",
        "ignore sub @FromLeft @Receive' @HealingMarks;",
        "sub [i.heal.left i.heal.center] m' by m.heal.both;",
        "sub m' [i.heal.right i.heal.center] by m.heal.both;",
        "sub @FromLeft @Receive' @FromRight by @ReceiveBoth;",
        "sub @FromLeft @Receive' by @ReceiveLeft;",
        "sub @Receive' @FromRight by @ReceiveRight;",
        "} TakeSpace;",
        f"}} {activate};",
    ]
    if default_on:
        rules.extend((
            f"feature {FEATURE} {{ lookup GiveSpace; lookup TakeSpace; }} {FEATURE};",
            f"feature {OFF_FEATURE} {{",
        ))
        for letters, third in ((DONORS, "center"), (RECEIVERS, "both")):
            for letter in letters:
                names = " ".join(f"{letter}.heal.{side}" for side in ("left", "right", third))
                rules.append(f"sub [{names}] by {letter};")
        rules.append(f"}} {OFF_FEATURE};")
    add_features(font, "\n".join(rules))
    label_stylistic_set(font, FEATURE, "Texture healing")
    if default_on:
        label_stylistic_set(font, OFF_FEATURE, "Disable texture healing")
    if trial:
        name_trial(font)
    font.save(output)


def name_trial(font):
    names = font["name"]
    style = {
        1: "Daikonic Transit Code Texture Trial",
        3: "DaikonicTransitCode-TextureTrial-VF",
        4: "Daikonic Transit Code Texture Trial",
        6: "DaikonicTransitCode-TextureTrial-VF",
        16: "Daikonic Transit Code Texture Trial",
        25: "DaikonicTransitCodeTextureTrial",
    }
    for record in names.names:
        if record.nameID in style:
            record.string = style[record.nameID].encode(record.getEncoding())
    for instance in font["fvar"].instances:
        if instance.postscriptNameID != 0xFFFF:
            subfamily = names.getDebugName(instance.subfamilyNameID)
            instance.postscriptNameID = names.addName(
                "DaikonicTransitCodeTextureTrial-" + subfamily.replace(" ", "")
            )


def verify(source, output, *, default_on=False, lifetime_ampersand=False):
    if lifetime_ampersand:
        from code_hairline_toggle import inward_ampersand

    font = TTFont(output)
    original = TTFont(source)
    assert font.getBestCmap() == original.getBestCmap()
    if font["glyf"]["i"].yMin == font["glyf"]["n"].yMin:
        from code_i_baseline import align_i_baseline

        align_i_baseline(original)
    for name in original.getGlyphOrder():
        if name in RECEIVERS:
            continue
        assert font["hmtx"][name] == original["hmtx"][name]
        assert font["glyf"][name].compile(font["glyf"]) == original["glyf"][
            name
        ].compile(original["glyf"])
    new_face = hb.Face(output.read_bytes())
    old_face = hb.Face(source.read_bytes())
    cases = [donor + receiver for donor, receiver in product(DONORS, RECEIVERS)]
    cases += [receiver + donor for donor, receiver in product(DONORS, RECEIVERS)]
    cases += [
        left + center + right
        for left, center, right in product(DONORS, RECEIVERS, DONORS)
    ]
    cases += ["mim", "wiw", "mama", "minimum", "film", "will", "always"]
    controls = [
        "-> ->> != a<>b ::<T>",
        "&'a Vec<Vec<T>> &'mi &'im",
        "[<>] <[]>",
        "áw mą mí j\u0301w",
        "i m j/w xmx xwx" if default_on else "a.w i m j/w xmx xwx",
    ]
    on = {} if default_on else {FEATURE: True}
    off = {OFF_FEATURE: True} if default_on else {FEATURE: False}
    punctuation_cases = []
    if default_on:
        for char, letter in product(PUNCTUATION, RECEIVERS):
            punctuation_cases.extend((
                (f"{char}{letter}x", ".heal.left"),
                (f"x{letter}{char}", ".heal.right"),
                (f"{char}{letter}{char}", ".heal.both"),
            ))
        cases.extend(value for value, _ in punctuation_cases)

    def shape(engine, tt, value, features):
        buffer = hb.Buffer()
        buffer.add_str(value)
        buffer.guess_segment_properties()
        # Paired stems have their own checks. Inspect individual donor cells here.
        hb.shape(engine, buffer, {"liga": False, **features})
        return [
            (tt.getGlyphName(info.codepoint), pos.x_advance, pos.x_offset, pos.y_offset)
            for info, pos in zip(buffer.glyph_infos, buffer.glyph_positions)
        ]

    for weight in range(300, 401, 10):
        location = {"wght": weight}
        gs = font.getGlyphSet(location=location)
        for letter in RECEIVERS:
            normal, left, right, wide = (
                shape_from_glyphs(gs, name)
                for name in (
                    letter,
                    letter + ".heal.left",
                    letter + ".heal.right",
                    letter + ".heal.both",
                )
            )
            width = lambda outline: outline.bounds[2] - outline.bounds[0]
            assert width(normal) < width(left) < width(wide), (weight, letter)
            translated = left.transform(1, 0, 0, 1, FORM_SHIFT[letter] * 2, 0)
            assert abs(pathops.op(translated, right, pathops.PathOp.XOR).area) < 0.01
        for letter in DONORS:
            narrow = shape_from_glyphs(gs, letter + ".heal.center")
            normal = shape_from_glyphs(gs, letter)
            assert (
                narrow.bounds[2] - narrow.bounds[0]
                < normal.bounds[2] - normal.bounds[0]
            )
            for side, offset in (("left", -DONOR_SHIFT), ("right", DONOR_SHIFT)):
                placed = shape_from_glyphs(gs, letter + ".heal." + side)
                shifted = narrow.transform(1, 0, 0, 1, offset, 0)
                assert abs(pathops.op(shifted, placed, pathops.PathOp.XOR).area) < 0.01
        pth = {}
        for f in (engine := hb.Font(new_face), baseline := hb.Font(old_face)):
            f.set_variations(location)
        lifetime_options = (False, True) if any(
            record.FeatureTag == "ss01" for record in font["GSUB"].table.FeatureList.FeatureRecord
        ) else (False,)
        for lifetime, logic in product(lifetime_options, (False, True)):
            features = {"calt": True, "ss01": lifetime, "ss02": logic}
            for value in cases + controls:
                expected = shape(baseline, original, value, features)
                if lifetime_ampersand:
                    expected = inward_ampersand(expected, 1)
                assert shape(engine, font, value, features | off) == expected
            for value in controls:
                assert shape(engine, font, value, features | on) == shape(
                    engine, font, value, features | off
                )
        for value, suffix in punctuation_cases:
            enabled = shape(engine, font, value, on)
            disabled = shape(engine, font, value, off)
            assert enabled[1][0] == value[1] + suffix, (weight, value, enabled)
            assert enabled[0] == disabled[0] and enabled[2] == disabled[2]
            assert shape(engine, font, value, {FEATURE: True}) == enabled
            assert shape(engine, font, value, {FEATURE: True} | off) == disabled
        for letter in RECEIVERS:
            for case, suffix in (
                ("x{}x", ""),
                ("i{}x", ".heal.both" if letter == "m" else ".heal.left"),
                ("x{}i", ".heal.both" if letter == "m" else ".heal.right"),
                ("i{}i", ".heal.both"),
            ):
                context = case.format(letter)
                actual = shape(engine, font, context, on)
                assert actual[1][0] == letter + suffix, (context, actual)
        for case, position, expected in (
            ("im", 1, "m.heal.both"),
            ("mi", 0, "m.heal.both"),
            ("lmx", 1, "m.heal.left"),
            ("xml", 1, "m.heal.right"),
        ):
            actual = shape(engine, font, case, on)
            assert actual[position][0] == expected, (case, actual)
        for donor in DONORS:
            for case, position, side in (
                (donor + "m", 0, "left"),
                ("m" + donor, 1, "right"),
                ("m" + donor + "m", 1, "center"),
            ):
                actual = shape(engine, font, case, on)
                assert actual[position][0] == donor + ".heal." + side, (case, actual)
        for value in cases:
            shaped = shape(engine, font, value, on)
            assert all(
                advance == WIDTH and not x and not y for _, advance, x, y in shaped
            )
            assert any(".heal." in name for name, *_ in shaped), value
            for left, right in zip(shaped, shaped[1:]):
                for name in (left[0], right[0]):
                    if name not in pth:
                        pth[name] = shape_from_glyphs(gs, name)
                a, b = pth[left[0]], pth[right[0]]
                assert a.bounds[2] - b.bounds[0] < WIDTH + 25, (weight, value)
                if a.bounds[2] > WIDTH + b.bounds[0]:
                    overlap = pathops.op(
                        a,
                        b.transform(1, 0, 0, 1, WIDTH, 0),
                        pathops.PathOp.INTERSECTION,
                    )
                    assert overlap.area < 1, (weight, value, left[0], right[0])
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(
            [ots.OTS_SANITIZE, str(output), str(Path(directory) / "checked.ttf")],
            check=True,
            capture_output=True,
        )
    return {
        "weights": list(range(300, 401, 10)),
        "word_and_pair_cases": cases,
        "syntax_controls": controls,
        "advance": WIDTH,
        "feature": FEATURE,
        "default_on": default_on,
        "opt_out_feature": OFF_FEATURE if default_on else None,
        "source_sha256": sha256(source.read_bytes()).hexdigest(),
        "sha256": sha256(output.read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    source = ROOT / specimen_families()["code"]["font"]
    output = args.directory / "DaikonicTransitCode-TextureTrial-VF.ttf"
    build(source, output)
    metadata = verify(source, output)
    (args.directory / "texture-checks.json").write_text(
        json.dumps(metadata, indent=2) + "\n"
    )
    print(
        f"{output.name}: {len(metadata['word_and_pair_cases'])} word and pair cases across 11 weights"
    )
