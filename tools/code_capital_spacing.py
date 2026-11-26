"""Build a fixed-cell uppercase spacing and texture-healing trial for Code."""

from argparse import ArgumentParser
from collections import defaultdict
from copy import deepcopy
from itertools import product
import json
from math import copysign, radians, tan
from pathlib import Path
from statistics import median
from string import ascii_letters, ascii_lowercase, ascii_uppercase
from unicodedata import category

from fontTools.misc.roundTools import otRound
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
import uharfbuzz as hb

from bundle_release import sanitize
from check_code_rebuild import ROOT, STYLES, shape
from code_boundary_spacing import identifier_glyphs
from code_crossbar_alignment import profile
from code_foundation import ink_columns
from code_receiver_texture import FEATURE, HALF_WIDTH, LANGUAGES, OFF_FEATURE, inherited_positions
from code_width import verify_width
from code_working_spacing import SPACING_PATH
from font_feature_tools import add_features, append_glyph, expanded_variations, label_stylistic_set
from glyph_proof import build_proof
from render_svg import render, render_pdf
from sans_baseline_trial import build_variations, install
from specimens import Panel
from system_italic import designspace


SOURCE = ROOT / "releases/1.1.1/code/VF"
FAMILY = "Daikonic Transit Code Capitals"
STEM = FAMILY.replace(" ", "")
CELL = 600
RECEIVERS = "MW"
COMPACT_CAPITALS = "PSL"
TERMINAL_EDITS = {"R": ("foot", 18), "K": ("arm", -12)}
EDITED_CAPITALS = COMPACT_CAPITALS + "B" + "".join(TERMINAL_EDITS)
WIDTH_RECOVERY = .4
DONORS = ascii_letters + ".,:;!?()[]{}"
TEXTURE_GAP = 108
SPACING_GAP = 68
BOUNDARY_SHIFT = 12
CONCAVE_CAPITALS = "RK"
STRESS_LOCATIONS = tuple(
    {"wght": weight, "wdth": width}
    for weight, width in product((350, 375, 400, 450, 500), (94, 97, 100, 104, 108))
)
SAMPLES = (
    "MAX_WIDTH  MIN_VALUE  HTTPServer  isXMLName",
    "AVATAR  FALLBACK  TYPE  WRITE  JSON",
    "MIM  IMI  IWI  WIM  MMM  WWW  MiWiM",
    "parseHTTPResponse  loadXMLFile  JSRuntime",
    "I l 1   O 0   W V   M N   F E   L I",
    "type XMLNode = Record<URL, HTMLValue>;",
    "return MAX_WIDTH >= MIN_VALUE ? rows?.map(Wrap) : [];",
)
COMPACT_SAMPLES = (
    "SPLIT  SPRINT  ROLLUP  PARSE  SQL",
    "BRB  RKR  LPL  SLS  Bind  Right  Task  objK",
    *SAMPLES[2:3],
    "ParseResponse  ReadBuffer  loadSQLRows  parseR",
    "Ĺ  Ľ  Ķ  Ŕ  Ś    Bind  Pick  List  Task  objK",
    "type SqlRow = ParseResult<SQL, URL>;",
    "return SPLIT_PATHS ? parseSQL(rows) : LOG_LEVEL;",
)
SMART_SAMPLES = (
    "HTTPServer  ParseResponse  Index  itemI",
    "Read  Key  Item  fileI  Task  objK",
    "P  R  K  I    HTTP  eRe  IO  eI",
    "class HTTPServer extends ParseResponse {}",
    "const itemI = new Index(Read, Key);",
)


def glyph_name(font, char):
    return font.getBestCmap()[ord(char)]


def names_with_alternates(font, chars):
    originals = {glyph_name(font, char) for char in chars}
    return [name for name in font.getGlyphOrder() if name.partition(".texture.")[0] in originals]


def profiles(font, names, locations):
    for location in locations:
        glyphs = font.getGlyphSet(location=location)
        yield {
            name: (profile(glyphs, name), glyphs[name].width)
            for name in names
        }


def gaps(left, right):
    rows, width = left
    ahead, _ = right
    return [width + ahead[y][0] - rows[y][1] for y in rows.keys() & ahead.keys()]


def component_dependents(font, letters):
    glyf = font["glyf"]
    return [name for name in font.getGlyphOrder() if glyf[name].isComposite()
            and any(part.glyphName in letters for part in glyf[name].components)]


def widen_compact_capitals(font):
    locations, model, default = designspace(font)
    glyf = font["glyf"]
    generated = {letter: [] for letter in sorted(EDITED_CAPITALS)}
    angle = -tan(radians(font["post"].italicAngle))
    cap = font["OS/2"].sCapHeight
    for location in locations:
        glyphs = font.getGlyphSet(location=location)
        shear = angle * location["wdth"] / 100

        def neutral_drawing(name):
            pen = TTGlyphPen(None)
            glyphs[name].draw(pen)
            glyph = pen.glyph()
            glyph.coordinates = GlyphCoordinates((x - shear * y, y) for x, y in glyph.coordinates)
            return glyph

        reference = neutral_drawing("H")
        left, _, right, _ = reference.coordinates.calcBounds()
        # H has a flat outside stem. Measure the first two columns at its foot.
        columns = sorted({x for x, y in reference.coordinates if y == 0})
        stem = columns[1] - columns[0]
        for letter, points in generated.items():
            glyph = neutral_drawing(letter)
            x0, _, x1, _ = glyph.coordinates.calcBounds()
            width = x1 - x0
            adjusted = [x for x, _ in glyph.coordinates]
            if letter in COMPACT_CAPITALS:
                expanded = ink_columns(glyph, 2, 1, stem)
                target_gain = max(0, right - left - width) * WIDTH_RECOVERY
                fraction = target_gain / (max(expanded) - min(expanded) - width)
                adjusted = [x + fraction * (wide - x)
                            for x, wide in zip(adjusted, expanded, strict=True)]
                center_shift = (x0 + x1 - min(adjusted) - max(adjusted)) / 2
                adjusted = [x + center_shift for x in adjusted]
            if letter == "B":
                # The outer and inner sides of the upper turn move together.
                # Blend into the waist above the lower counter or the leg.
                upper = max(x for x, (_, y) in zip(adjusted, glyph.coordinates, strict=True) if y > .6 * cap)
                gain = max(0, max(adjusted) - upper) * .38
                inner = upper - stem * 1.25
                join = min(adjusted) + stem * 1.2
                for pos, (_, y) in enumerate(glyph.coordinates):
                    lift = min(1, max(0, (y - .53 * cap) / (.16 * cap)))
                    reach = min(1, max(0, (adjusted[pos] - join) / (inner - join)))
                    adjusted[pos] += gain * lift * lift * (3 - 2 * lift) * reach
            if letter in TERMINAL_EDITS:
                end, shift = TERMINAL_EDITS[letter]
                height = cap if end == "arm" else 0
                center = (x0 + x1) / 2
                # Translate the terminal as a unit to preserve its cut and width.
                terminal = [pos for pos, (x, y) in enumerate(glyph.coordinates)
                            if y == height and x > center]
                assert len(terminal) == 2, (location, letter)
                for pos in terminal:
                    adjusted[pos] += shift * location["wdth"] / 100
            points.append(GlyphCoordinates(
                (otRound(x + shear * y), y)
                for x, (_, y) in zip(adjusted, glyph.coordinates, strict=True)
            ))
    for letter, points in generated.items():
        drawing = deepcopy(glyf[letter])
        drawing.coordinates = points[default]
        install(font, letter, drawing, build_variations(model, points, expanded_variations(font, letter)))
    for name in component_dependents(font, generated):
        glyf[name].recalcBounds(glyf)
        font["hmtx"][name] = font["hmtx"][name][0], glyf[name].xMin


def texture_donors(font):
    names = names_with_alternates(font, DONORS)
    # Keep tall neighbors distinct. A receiver should never donate based on
    # clearance measured against its narrower base drawing.
    names = [name for name in names if name.partition(".texture.")[0] not in RECEIVERS]
    pairs = {(side, receiver): set(names) for side, receiver in product(("Left", "Right"), RECEIVERS)}
    for rows in profiles(font, names + list(RECEIVERS), STRESS_LOCATIONS):
        for (side, receiver), candidates in pairs.items():
            for candidate in tuple(candidates):
                order = (candidate, receiver) if side == "Left" else (receiver, candidate)
                clearances = gaps(*(rows[name] for name in order))
                if not clearances or min(clearances) < TEXTURE_GAP:
                    candidates.remove(candidate)
    return {key: sorted(values, key=font.getGlyphID) for key, values in pairs.items()}


def receiver_drawings(font):
    locations, model, default = designspace(font)
    shear = -tan(radians(font["post"].italicAngle))
    aliases = {}
    for letter in RECEIVERS:
        drawings = []
        for location in locations:
            glyphs = font.getGlyphSet(location=location)
            pen = TTGlyphPen(None)
            glyphs[letter].draw(pen)
            drawings.append(pen.glyph())
        source = drawings[default]
        assert all(g.flags == source.flags and g.endPtsOfContours == source.endPtsOfContours
                   for g in drawings), letter
        aliases[letter] = []
        for form, step in (("middle", HALF_WIDTH), ("wide", HALF_WIDTH * 2)):
            name = f"{letter}.texture.{form}"
            points = []
            for location, drawing in zip(locations, drawings, strict=True):
                width = CELL * location["wdth"] / 100
                unslanted = [x - shear * y for x, y in drawing.coordinates]
                center = (min(unslanted) + max(unslanted)) / 2
                # Hold the middle join and move the outer stroke bands intact.
                # Italic letterfit can offset the unslanted drawing from its cell.
                distance = [(x - center) / width for x in unslanted]
                points.append([
                    (otRound(x + copysign(step / 2 * min(1, max(0, (abs(d) - .08) / .012)), d)), y)
                    for (x, y), d in zip(drawing.coordinates, distance, strict=True)
                ])
            variant = deepcopy(source)
            variant.coordinates[:] = points[default]
            append_glyph(font, name, variant, build_variations(model, points), CELL, letter)
            aliases[letter].append(name)
    inherited_positions(font, aliases)


def add_texture(font, donors):
    receiver_drawings(font)
    marks = {name for cp, name in font.getBestCmap().items() if category(chr(cp)).startswith("M")}
    marks.update(name for name, kind in font["GDEF"].table.GlyphClassDef.classDefs.items() if kind == 3)
    mark_class = f"@CapTextureMarks = [{' '.join(sorted(marks))}];"
    definitions, lookups, restore = [mark_class], [], []
    for letter in RECEIVERS:
        left, right = (f"@Cap{letter}{side}" for side in ("Left", "Right"))
        for side, cls in (("Left", left), ("Right", right)):
            definitions.append(f"{cls} = [{' '.join(donors[side, letter])}];")
        middle, wide = f"{letter}.texture.middle", f"{letter}.texture.wide"
        lookups.extend([
            f"lookup CapTexture{letter} {{",
            f"ignore sub @CapTextureMarks {letter}', {letter}' @CapTextureMarks;",
            f"sub {left} {letter}' {right} by {wide};",
            f"sub {left} {letter}' by {middle};",
            f"sub {letter}' {right} by {middle};",
            f"}} CapTexture{letter};",
        ])
        restore.append(f"sub [{middle} {wide}] by {letter};")
        shift = HALF_WIDTH // 2
        lookups.extend([
            f"lookup CapPlace{letter} {{",
            f"pos {left} {middle}' <-{shift} 0 0 0>;",
            f"pos {middle}' <{shift} 0 0 0> {right};",
            f"}} CapPlace{letter};",
        ])
    calls = " ".join(f"lookup CapTexture{c}; lookup CapPlace{c};" for c in RECEIVERS)
    add_features(font, "\n".join([
        *LANGUAGES, *definitions, *lookups,
        f"feature calt {{ {calls} }} calt;",
        f"feature {FEATURE} {{ {calls} }} {FEATURE};",
        f"feature {OFF_FEATURE} {{ {' '.join(restore)} }} {OFF_FEATURE};",
    ]))
    if font["post"].italicAngle:
        label_stylistic_set(font, FEATURE, "Texture healing")
        label_stylistic_set(font, OFF_FEATURE, "Disable texture healing")


def edge_class(rows, advance, side, shear, height):
    margins = [
        median(
            x0 - shear * y if side == "Left" else advance - x1 + shear * y
            for y, (x0, x1) in rows.items() if lo * height <= y < hi * height
        )
        for lo, hi in ((.12, .29), (.38, .62), (.72, .89))
    ]
    low, middle, high = margins
    if min(margins) >= 90:
        return "Inset"
    if low - high > 58:
        return "OpenLow"
    if high - low > 58:
        return "OpenHigh"
    return "Curved" if max(low, high) - middle > 45 else "Stem"


def spacing_classes(font, *, edge_fit):
    cmap = font.getBestCmap()
    base_names = {char: cmap[ord(char)] for char in ascii_letters}
    glyphs = font.getGlyphSet()
    shear = -tan(radians(font["post"].italicAngle))
    classes, mixed = defaultdict(list), defaultdict(list)
    for char, name in base_names.items():
        rows = profile(glyphs, name)
        height = font["OS/2"].sCapHeight if char.isupper() else font["OS/2"].sxHeight
        aliases = names_with_alternates(font, char)
        for side in ("Left", "Right"):
            form = edge_class(rows, glyphs[name].width, side, shear, height)
            classes[side, char.isupper(), form].extend(aliases)
            if edge_fit:
                # The space above the lowercase is irrelevant to a mixed-case fit.
                margins = sorted(left if side == "Left" else glyphs[name].width - right
                                 for y, (left, right) in rows.items()
                                 if 0 <= y <= font["OS/2"].sxHeight)
                bucket = max(0, int(margins[len(margins) // 10] // 32))
                mixed[side, char.isupper(), f"Edge{bucket}"].extend(aliases)
    return dict(classes), dict(mixed)


def add_spacing(font, *, edge_fit=False, smart=False):
    ordinary, mixed = spacing_classes(font, edge_fit=edge_fit)
    classes = ordinary | mixed
    labels = {key: f"@CapFit{key[0]}{int(key[1])}{key[2]}" for key in classes}
    pairs = {
        (left, right): float("inf")
        for left, right in product(ordinary, repeat=2)
        if left[0] == "Right" and right[0] == "Left" and (left[1] or right[1])
    }
    edge_pairs = {
        (left, right): float("inf")
        for left, right in product(mixed, repeat=2)
        if left[0] == "Right" and right[0] == "Left" and left[1] != right[1]
    }
    glyph_gaps = {
        (a, b): float("inf")
        for left, right in pairs
        for a, b in product(classes[left], classes[right])
    }
    all_names = sorted({name for pair in glyph_gaps for name in pair})
    for rows in profiles(font, all_names, STRESS_LOCATIONS):
        for a, b in glyph_gaps:
            glyph_gaps[a, b] = min(glyph_gaps[a, b], min(gaps(rows[a], rows[b]), default=0))

    def clearance(left, right):
        return min(glyph_gaps[a, b] for a, b in product(left, right))

    def lookup(name, rows):
        return f"lookup {name} {{\n" + "\n".join(rows) + f"\n}} {name};"

    rules = {"Trailing": [], "Leading": []}
    boundary = {"Start": [], "End": []}
    moved = {}
    for left, right in pairs:
        gap = clearance(classes[left], classes[right])
        contraction = 20 if gap >= SPACING_GAP + 20 else 12 if gap >= SPACING_GAP + 12 else 0
        if not contraction:
            continue
        a, b = labels[left], labels[right]
        shift = contraction // 2 if left[1] and right[1] else contraction
        if left[1]:
            rules["Trailing"].append(f"pos {a}' <{shift} 0 0 0> {b};")
        if right[1]:
            rules["Leading"].append(f"pos {a} {b}' <-{shift} 0 0 0>;")
        moved[f"{a[1:]} / {b[1:]}"] = contraction
    assert moved
    for left, right in edge_pairs:
        # Reserve the largest possible existing class contraction as well.
        if clearance(classes[left], classes[right]) >= 56 + 20 + BOUNDARY_SHIFT:
            a, b = labels[left], labels[right]
            if left[1]:
                boundary["Start"].append(f"pos {a}' <{BOUNDARY_SHIFT} 0 0 0> {b};")
            else:
                boundary["End"].append(f"pos {a} {b}' <-{BOUNDARY_SHIFT} 0 0 0>;")
    boundary_classes, boundary_rules, interior = [], [], []
    if edge_fit:
        caps = names_with_alternates(font, ascii_uppercase)
        lowercase = names_with_alternates(font, ascii_lowercase)
        boundary_classes = [
            f"@CapContinue = [{' '.join(sorted(identifier_glyphs(font)))}];",
            f"@CapUpper = [{' '.join(caps)}];",
            f"@CapLower = [{' '.join(lowercase)}];",
        ]
        guard_neighbors = "@CapLower"
        if smart:
            boundary_classes.append(f"@CapLetters = [{' '.join(caps + lowercase)}];")
            guard_neighbors = "@CapLetters"
            for rows in rules.values():
                if rows:
                    rows.insert(0, "ignore pos @CapContinue @CapUpper' @CapContinue;")

            def safe_neighbors(cap, neighbors, *, cap_first, minimum):
                return [name for name in neighbors
                        if glyph_gaps[(cap, name) if cap_first else (name, cap)] >= minimum]

            # A measured exception for exposed I and the open side of R/K.
            # Put these before the ordinary edge rules so a cap moves only once.
            directions = json.loads(SPACING_PATH.read_text())["directional_boundaries"]
            rounded = names_with_alternates(font, directions["convex_left"])
            for direction, cap_first in (("Start", True), ("End", False)):
                direct = []
                specs = [("I", caps + lowercase)]
                if cap_first:
                    specs.extend((cap, rounded) for cap in CONCAVE_CAPITALS)
                for cap, neighbors in specs:
                    safe = safe_neighbors(cap, neighbors, cap_first=cap_first, minimum=78)
                    if safe:
                        others = "[" + " ".join(safe) + "]"
                        if cap_first:
                            direct.append(f"pos {cap}' <{BOUNDARY_SHIFT} 0 0 0> {others};")
                        else:
                            direct.append(f"pos {others} {cap}' <-{BOUNDARY_SHIFT} 0 0 0>;")
                boundary[direction][:0] = direct

            # Every interior capital is a wide anchor. Group capitals by how
            # much clearance they can safely give up to a lowercase glyph.
            for direction, cap_first in (("After", True), ("Before", False)):
                groups = defaultdict(list)
                for char in ascii_lowercase:
                    neighbors = names_with_alternates(font, char)
                    distant, open_gaps = [], []
                    for cap in caps:
                        size = min(glyph_gaps[(cap, name) if cap_first else (name, cap)]
                                   for name in neighbors)
                        if size >= 125:
                            distant.append(cap)
                        elif size >= 95:
                            open_gaps.append(cap)
                    for names, shift in ((distant, 16), (open_gaps, 10)):
                        if names:
                            groups[tuple(names), shift].extend(neighbors)
                rows = []
                for (names, shift), neighbors in groups.items():
                    anchors, lower = (f"[{' '.join(group)}]" for group in (names, neighbors))
                    if cap_first:
                        rows.append(f"pos @CapContinue {anchors} {lower}' <-{shift} 0 0 0>;")
                    else:
                        rows.append(f"pos {lower}' <{shift} 0 0 0> {anchors} @CapContinue;")
                if rows:
                    interior.append(lookup(f"CapInterior{direction}", rows))
        guards = {"Start": f"@CapContinue @CapUpper' {guard_neighbors}",
                  "End": f"{guard_neighbors} @CapUpper' @CapContinue"}
        boundary_rules = [lookup(f"CapEdge{edge}", [f"ignore pos {guards[edge]};", *rows])
                          for edge, rows in boundary.items() if rows]
    add_features(font, "\n".join([
        *LANGUAGES,
        *(f"{labels[key]} = [{' '.join(names)}];" for key, names in classes.items()),
        *boundary_classes,
        "feature calt {",
        *(lookup(f"{name}CapFit", rows) for name, rows in rules.items() if rows),
        *boundary_rules,
        *interior,
        "} calt;",
    ]))
    return {
        "classes": {labels[key].lstrip("@"): names for key, names in classes.items()},
        "contractions": moved,
        "boundary_rules": boundary,
        "interior_rules": interior,
    }


def apply_capital_spacing(font, *, wider=False, smart=False):
    if wider:
        widen_compact_capitals(font)
    donors = texture_donors(font)
    add_texture(font, donors)
    spacing = add_spacing(font, edge_fit=wider, smart=smart)
    return spacing | {"texture_donors": {"".join(key): values for key, values in donors.items()}}


def build(source, target, *, wider=False, smart=False):
    with TTFont(source, recalcTimestamp=False) as font:
        report = apply_capital_spacing(font, wider=wider, smart=smart)
        family = FAMILY + " Wide Trial" if wider else FAMILY
        if smart:
            family += " Smart"
        for record in font["name"].names:
            name = record.toUnicode().replace("Daikonic Transit Code", family)
            record.string = name.replace("DaikonicTransitCode", family.replace(" ", "")).encode(record.getEncoding())
        verify_width(font, CELL)
        sanitize(font)
        font.save(target)
    return report


def verify(source, target, *, wider=False, smart=False):
    baseline, candidate = [hb.Font(hb.Face(path.read_bytes())) for path in (source, target)]
    with TTFont(source) as original, TTFont(target) as font:
        assert original.getBestCmap() == font.getBestCmap()
        assert set(original.getGlyphOrder()) | {f"{c}.texture.{form}" for c, form in
                                                  product(RECEIVERS, ("middle", "wide"))} == set(font.getGlyphOrder())
        redrawn = set(EDITED_CAPITALS) if wider else set()
        dependents = set(component_dependents(original, redrawn))
        for name in set(original.getGlyphOrder()) - redrawn:
            old, new = original["glyf"][name], font["glyf"][name]
            if name in dependents:
                assert old.components == new.components, name
            else:
                assert old.compile(original["glyf"]) == new.compile(font["glyf"]), name
        assert all(original["gvar"].variations.get(name) == font["gvar"].variations.get(name)
                   for name in set(original.getGlyphOrder()) - redrawn)
        names = names_with_alternates(font, ascii_letters)
        revised_profiles = profiles(font, names, STRESS_LOCATIONS)
        original_profiles = profiles(original, redrawn, STRESS_LOCATIONS)
        for location, rows, prior_rows in zip(STRESS_LOCATIONS, revised_profiles, original_profiles, strict=True):
            baseline_edges = rows | prior_rows
            for engine in (baseline, candidate):
                engine.set_variations(location)
            for name in redrawn:
                before, advance = prior_rows[name]
                after, revised_advance = rows[name]
                assert before.keys() == after.keys() and advance == revised_advance, (location, name)
                get_width = lambda profile: max(x[1] for x in profile.values()) - min(x[0] for x in profile.values())
                if name in COMPACT_CAPITALS:
                    assert get_width(after) > get_width(before) + 4, (location, name)
                if name == "B":
                    assert after[500][1] > before[500][1] + 10, (location, name)
                    assert abs(after[180][1] - before[180][1]) <= 1, (location, name)
                if name == "R":
                    assert after[0][1] > before[0][1] + 15, (location, name)
                    assert abs(after[500][1] - before[500][1]) <= 1, (location, name)
                if name == "K":
                    assert after[650][1] < before[650][1] - 9, (location, name)
                    assert abs(after[0][1] - before[0][1]) <= 1, (location, name)
            for sample in ("exit hexit window windows sweep", "namespace awwi imi", "a === b && c?.d", "fn f<'a>(arg: &'a str)"):
                assert shape(baseline, sample, {}) == shape(candidate, sample, {}), (location, sample)
            for sample in ("IMI", "IWI", "IW", "WI", "MMM", "WWW", *SAMPLES):
                on = shape(candidate, sample, {})
                off = shape(candidate, sample, {OFF_FEATURE: True})
                prior = shape(baseline, sample, {})
                assert [r[2] for r in on] == [r[2] for r in off] == [r[2] for r in prior], (location, sample)
                assert all(".texture." not in r[0] for r in off), (location, sample)
                assert shape(candidate, sample, {FEATURE: True}) == on
            assert shape(candidate, "IMI", {})[1][0] == "M.texture.wide"
            assert shape(candidate, "WI", {})[0][0] == "W.texture.middle"
            assert shape(candidate, "MMM WWW", {}) == shape(candidate, "MMM WWW", {OFF_FEATURE: True})
            assert shape(candidate, "AM\u0301I", {})[1][0] == "M"
            if wider:
                start = shape(candidate, "Task", {})[0][4]
                inside_start = shape(candidate, "_Task", {})[1][4]
                end = shape(candidate, "objK", {})[-1][4]
                inside_end = shape(candidate, "objK_", {})[-2][4]
                assert (start - inside_start, end - inside_end) == (BOUNDARY_SHIFT, -BOUNDARY_SHIFT), location
            if smart:
                for text, index, moved in (("Read", 0, 12), ("Key", 0, 12), ("Index", 0, 12),
                                            ("itemI", -1, -12), ("ParseResponse", 6, -16),
                                            ("HTTPServer", 5, -10)):
                    run = shape(candidate, text, {})
                    prior = shape(baseline, text, {})[index]
                    direction = 1 if moved > 0 else -1
                    assert direction * (run[index][4] - prior[4]) >= abs(moved), (location, text, run)
                anchor = shape(candidate, "ParseResponse", {})[5]
                assert anchor[0] == "R" and anchor[4] == 0

            def clearances(edges, run):
                return [
                    min(gaps(edges[left[0]], edges[right[0]])) + right[4] - left[4]
                    for left, right in zip(run, run[1:])
                ]

            for a, b in product(ascii_letters, repeat=2):
                if a.islower() and b.islower():
                    continue
                samples = [a + b]
                if smart and a.isupper() != b.isupper():
                    samples.append("n" + a + b if a.isupper() else a + b + "n")
                for sample in samples:
                    before = clearances(baseline_edges, shape(baseline, sample, {}))
                    after = clearances(rows, shape(candidate, sample, {}))
                    assert all(new >= min(old, 16) - 1 for old, new in zip(before, after, strict=True)), (
                        location, sample, before, after)


def comparison_specimen(before, after, style, output, *, smart=False, versions=None):
    paper, ink, dark = "#f7f5ee", "#182b31", "#171e22"
    width, height = 1340, 830
    page = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img">',
        f'<rect width="{width}" height="{height}" fill="{paper}"/>',
        '<g font-family="Arial, sans-serif">',
        f'<text x="40" y="42" font-size="15" fill="#526971">DAIKONIC TRANSIT CODE · {style.upper()}</text>',
        f'<text x="40" y="86" font-size="34" font-weight="700" fill="{ink}">Capitals before and after</text>',
    ]
    columns = ((40, before, "Before · Previous spacing trial" if smart else "Before · Previous uppercase trial"),
               (710, after, "After · Smart kerning trial" if smart else "After · Revised capitals"))
    if versions:
        columns = tuple((x, font, f"{label.partition(' · ')[0]} · {version}")
                        for (x, font, label), version in zip(columns, versions, strict=True))
    for x, _, label in columns:
        page.append(f'<text x="{x}" y="129" font-size="21" font-weight="700" fill="{ink}">{label}</text>')
    page.append('</g><path d="M670 113V655" stroke="#d6ddd7"/>')
    settings = ((350, 100, "Book 350"), (400, 100, "Regular 400"), (500, 94, "Medium Narrow 500"))
    samples = SMART_SAMPLES[:3] if smart else (*COMPACT_SAMPLES[:2], "B  P  R  K  S  L    BR  RK  SL")
    for index, (weight, width_axis, label) in enumerate(settings):
        top = 150 + 169 * index
        page.extend([
            f'<path d="M40 {top}H1300" stroke="#d6ddd7"/>',
            f'<text x="40" y="{top+25}" font-family="Arial" font-size="15" fill="#526971">{label}</text>',
        ])
        for col, (x, font, _) in enumerate(columns):
            panel = Panel(f"compare-{index}-{col}", {"font": font.resolve(), "axes": {"wdth": width_axis}})
            for line, sample in enumerate(samples):
                panel.text(sample, x, top + 59 + line * 38, (24, 24, 32)[line], weight, ink)
            page.append(panel.body())
    page.extend([
        f'<rect y="664" width="{width}" height="166" fill="{dark}"/>',
        '<path d="M670 684V804" stroke="#3f5359"/>',
    ])
    for col, (x, font, label) in enumerate(columns):
        state = label.partition(" · ")[0]
        page.append(f'<text x="{x}" y="697" font-family="Arial" font-size="15" fill="#a8c3c4">{state} · Editor samples at 16 px</text>')
        panel = Panel(f"compare-editor-{col}", {"font": font.resolve(), "axes": {"wdth": 100}})
        text = (*SMART_SAMPLES[3:], *SMART_SAMPLES[:2]) if smart else (
            *COMPACT_SAMPLES[-2:], COMPACT_SAMPLES[3], COMPACT_SAMPLES[4])
        for line, sample in enumerate(text):
            panel.text(sample, x, 728 + line * 24, 16, 400, "#eeefeb")
        page.append(panel.body())
    destination = output / f"Code-Capitals-{style.title()}.svg"
    destination.write_text("".join(page) + "</svg>\n")
    return destination


def specimen(target, style, output, samples, title):
    paper, ink, dark = "#f7f5ee", "#182b31", "#171e22"
    page = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="940" height="810" viewBox="0 0 940 810" role="img">',
        f'<rect width="940" height="810" fill="{paper}"/>',
        '<g font-family="Arial, sans-serif">',
        f'<text x="40" y="44" font-size="15" fill="#526971">DAIKONIC TRANSIT CODE · {style.upper()}</text>',
        f'<text x="40" y="85" font-size="33" font-weight="700" fill="{ink}">{title}</text>',
        '</g>',
    ]
    for index, (weight, width, label) in enumerate(((350, 100, "Book"),
                                                   (400, 100, "Regular"),
                                                   (500, 94, "Medium Narrow"))):
        top = 109 + 184 * index
        panel = Panel(f"caps{index}", {"font": target.resolve(), "axes": {"wdth": width}})
        page.extend([
            f'<line x1="40" x2="900" y1="{top}" y2="{top}" stroke="#d6ddd7"/>',
            f'<text x="40" y="{top+23}" font-family="Arial" font-size="14" fill="#526971">{label} {weight}</text>',
        ])
        panel.text(samples[0], 40, top + 54, 27, weight, ink)
        panel.text(samples[1], 40, top + 87, 27, weight, ink)
        for x, features in ((40, {}), (475, {OFF_FEATURE: True})):
            panel.text("IMI IWI WIM MMM WWW MiWiM", x, top + 128, 26, weight, ink,
                       features=features)
        for x, text in ((40, "Texture healing on"), (475, "Texture healing off")):
            page.append(f'<text x="{x}" y="{top+149}" font-family="Arial" font-size="12" fill="#526971">{text}</text>')
        page.append(panel.body())
    page.append(f'<rect y="663" width="940" height="147" fill="{dark}"/>')
    panel = Panel("editor-size", {"font": target.resolve(), "axes": {"wdth": 100}})
    page.append('<text x="40" y="696" font-family="Arial" font-size="14" fill="#a8c3c4">Editor samples · 16 px</text>')
    for line, text in enumerate((samples[-2], samples[-1], samples[3], samples[4])):
        panel.text(text, 40, 724 + line * 21, 16, 400, "#eeefeb")
    page.append(panel.body())
    destination = output / f"Code-Capitals-{style.title()}.svg"
    destination.write_text("".join(page) + "</svg>\n")
    return destination


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", type=Path, default=SOURCE,
                        help="directory containing the upright and italic Code variable fonts")
    parser.add_argument("--proofs", action="store_true")
    parser.add_argument("--widen-compact-caps", action="store_true",
                        help="try revised B, K, P, R, S, and L and inward mixed-case edge fitting")
    parser.add_argument("--smart-cap-kerning", action="store_true",
                        help="treat interior capitals as wide anchors and fit R, K, and I at edges")
    args = parser.parse_args()
    if args.smart_cap_kerning and not args.widen_compact_caps:
        parser.error("--smart-cap-kerning requires --widen-compact-caps")
    args.output.mkdir(parents=True, exist_ok=True)
    report, pages = {}, []
    wider = args.widen_compact_caps
    smart = args.smart_cap_kerning
    samples = SMART_SAMPLES if smart else COMPACT_SAMPLES if wider else SAMPLES
    variation = ("WideTrial" if wider else "") + ("Smart" if smart else "")
    for style, suffix in STYLES.items():
        source = args.source / f"DaikonicTransitCode{suffix}"
        target = args.output / f"{STEM}{variation}{suffix}"
        report[style] = build(source, target, wider=wider, smart=smart)
        verify(source, target, wider=wider, smart=smart)
        print(target, flush=True)
        if args.proofs:
            if wider:
                before = args.output / f"{STEM}{'WideTrial' if smart else ''}{suffix}"
                build(source, before, wider=smart)
                pages.append(comparison_specimen(before, target, style, args.output, smart=smart))
            else:
                pages.append(specimen(target, style, args.output, samples, "Uppercase spacing"))
            build_proof(target, args.output / style, svg_only=True, interactive_axes=True,
                        sample="\n".join(samples))
    if pages:
        render_pdf(pages, args.output / "Code-Capitals.pdf")
        for page in pages:
            render(page, scale=2, pdf=False)
    (args.output / "spacing.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
