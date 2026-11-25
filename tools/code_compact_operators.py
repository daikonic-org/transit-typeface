"""Build a local Code proof of compact operators with shorter advances."""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
import ots
import pathops
import uharfbuzz as hb

from audit import shape_from_glyphs
from code_hairline_study import ROOT, save_trial, shape
from font_feature_tools import add_features, append_glyph, from_paths, label_stylistic_set, master_locations
from italic_texture_proofs import BG, CREAM, MUTED, export, label, rect
from specimens import Panel, specimen_families


CELL = 600
COMPARISONS = {
    "<=": "code.lessEqual", ">=": "code.greaterEqual",
    "==": "code.equal", "!=": "code.notEqual",
    "===": "code.strictEqual", "!==": "code.notStrict",
}
ARROWS = {
    "->": "code.arrow", "<-": "code.leftArrow", "=>": "code.fatArrow",
    "->>": "code.arrowDouble", "<<-": "code.leftDouble",
}
EQUALITY = ("==", "!=", "===", "!==")
TWO_CELL_INK = 1056
LOOSE = "ss06"
LOOSE_GLYPHS = {token: COMPARISONS[token] + ".loose" for token in EQUALITY}
SCOPES = ("code.scope", "code.scope.hairline")
ACCESS = {"?.": ("code.syntax00", "question"), "!.": ("code.syntax01", "exclam")}
ONE_CELL_CARETS = (*SCOPES, *(name for name, _ in ACCESS.values()))
PAIRS = {"//": ("slash", "code.commentSlash", 262), "||": ("bar", "code.logicalOr", 344)}
TARGETS = COMPARISONS | ARROWS | {s: pair[1] for s, pair in PAIRS.items()}

CHANGED_BASE_GLYPHS = frozenset((*COMPARISONS.values(), *ARROWS.values(), *ONE_CELL_CARETS))
SAVED_CELL_GLYPHS = frozenset((
    *SCOPES, *(name for name, _ in ACCESS.values()), *LOOSE_GLYPHS.values(),
    *(TARGETS[token] for token in ("<=", ">=", "->>", "<<-", "===", "!==", "//", "||")),
))


def advance_for(token):
    if token in EQUALITY or token in ARROWS:
        return 2 * CELL
    return (len(token) - 1) * CELL


def caret_positions(token, advance=None):
    advance = advance_for(token) if advance is None else advance
    return [advance * i // len(token) for i in range(1, len(token))]


class HorizontalMapping:
    def __init__(self, map_x):
        self.map_x = map_x

    def transformPoint(self, point):
        x, y = point
        return self.map_x(x), y


def compact_operator(path, token, *, loose=False, width=None):
    advance = CELL if loose else advance_for(token)
    shift = (advance - len(token) * CELL) / 2
    if token in ("<=", ">="):
        return path.transform(1, 0, 0, 1, shift, 0)
    left, _, right, _ = path.bounds
    target = (512 if loose else TWO_CELL_INK) if width is None else width
    center = len(token) * CELL / 2
    if token in ARROWS:
        # Only the straight shaft changes length. Every point in both heads is translated rigidly.
        mirror = -1 if token.startswith("<") else 1
        shaft_start, tip = (left, right) if mirror == 1 else (-right, -left)
        shoulder = tip - (700 if len(token) == 3 else 355)
        new_start = mirror * center - target / 2
        new_tip = new_start + target
        head_shift = new_tip - tip
        shaft_scale = (shoulder + head_shift - new_start) / (shoulder - shaft_start)
        assert shaft_scale > 0

        def map_x(x):
            u = x * mirror
            if u >= shoulder:
                return (u + head_shift) * mirror
            return (new_start + (u - shaft_start) * shaft_scale) * mirror
    else:
        # The slash and its joins sit inside this central span at every master.
        fixed_half = 200 if width is not None else 240
        fixed_left, fixed_right = center - fixed_half, center + fixed_half
        target_left, target_right = center - target / 2, center + target / 2
        left_scale = (fixed_left - target_left) / (fixed_left - left)
        right_scale = (target_right - fixed_right) / (right - fixed_right)

        def map_x(x):
            if x < fixed_left:
                return fixed_left + (x - fixed_left) * left_scale
            if x > fixed_right:
                return fixed_right + (x - fixed_right) * right_scale
            return x

    output = pathops.Path()
    path.draw(TransformPen(output.getPen(), HorizontalMapping(map_x)))
    return output.transform(1, 0, 0, 1, shift, 0)


def loose_equal(glyphs, token):
    equals = shape_from_glyphs(glyphs, "equal")
    tilde = shape_from_glyphs(glyphs, "asciitilde")
    bottom = equals.bounds[1]
    outline = equals
    clearance = 24
    if token == "!=":
        negated = shape_from_glyphs(glyphs, COMPARISONS[token])
        width = equals.bounds[2] - equals.bounds[0]
        outline = compact_operator(negated, token, loose=True, width=width)
    # Reserve the same space above the bars in both forms for the negation stroke.
    slash_top = shape_from_glyphs(glyphs, COMPARISONS["!="]).bounds[3]
    tilde_y = slash_top + clearance - tilde.bounds[1]
    center_y = (bottom + tilde.bounds[3] + tilde_y) / 2
    y = CELL / 2 - center_y
    outline = outline.transform(1, 0, 0, 1, 0, y)
    outline.addPath(tilde.transform(1, 0, 0, 1, 0, y + tilde_y))
    return outline


def install_compact_scope(font, original):
    source = SCOPES[0]
    glyph = deepcopy(original["glyf"][source])
    start = 0
    for end in glyph.endPtsOfContours:
        shift = -187 if glyph.coordinates[start][0] < CELL else -413
        for i in range(start, end + 1):
            x, y = glyph.coordinates[i]
            glyph.coordinates[i] = (x + shift, y)
        start = end + 1
    # Constant translations preserve the original per-contour variation deltas.
    variations = original["gvar"].variations[source]
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    for name in SCOPES:
        glyph_class = classes.get(name)
        append_glyph(font, name, deepcopy(glyph), deepcopy(variations), CELL)
        if glyph_class is None:
            classes.pop(name)
        else:
            classes[name] = glyph_class


def compact_access_parts(glyphs, mark, cell=CELL, *, min_dot_gap=0):
    symbol = shape_from_glyphs(glyphs, mark)
    period = shape_from_glyphs(glyphs, "period")
    tittle = min((contour.bounds for contour in symbol.contours), key=lambda box: box[3])
    dot_width = (tittle[2] - tittle[0] + period.bounds[2] - period.bounds[0]) / 2
    separation = max(238, dot_width + min_dot_gap)
    offset = (tittle[0] + tittle[2] - period.bounds[0] - period.bounds[2]) / 2 + separation
    left = min(symbol.bounds[0], period.bounds[0] + offset)
    right = max(symbol.bounds[2], period.bounds[2] + offset)
    center = (cell - left - right) / 2
    return [(mark, 1, 1, center, 0), ("period", 1, 1, center + offset, 0)]


def compact_access(glyphs, mark):
    parts = compact_access_parts(glyphs, mark)
    result = pathops.Path()
    for base, sx, sy, dx, dy in parts:
        result.addPath(shape_from_glyphs(glyphs, base).transform(sx, 0, 0, sy, dx, dy))
    return result


def paired_offsets(path, distance, cell=CELL):
    left, _, right, _ = path.bounds
    first = (cell - left - right - distance) / 2
    return first, first + distance


def paired_ink(path, distance):
    result = pathops.Path()
    for offset in paired_offsets(path, distance):
        result.addPath(path.transform(1, 0, 0, 1, offset, 0))
    return result


def delimiter_variants(names, order):
    return [name + suffix for name in names for suffix in ("", ".hairline")
            if name + suffix in order]


def register_compact_context(font, comparisons, loose_glyphs, pairs, *, direct=None, cell=CELL):
    comment, logical_or = pairs["//"][1], pairs["||"][1]
    cmap = font.getBestCmap()
    scope_rules = []
    direct_rules = []
    if direct:
        scope = direct["::"]
        scope_rules = [
            f"lookup CompactScope {{ sub colon colon by {scope}; }} CompactScope;",
            "lookup ScopeExactlyTwo {",
            "ignore sub colon colon' colon, colon' colon colon;",
            "sub colon' lookup CompactScope colon;",
            "} ScopeExactlyTwo;",
        ]
        direct_rules.append("lookup ScopeExactlyTwo;")
        for token in ("?.", "!."):
            glyphs = " ".join(cmap[ord(character)] for character in token)
            direct_rules.append(f"sub {glyphs} by {direct[token]};")
    words = [cmap[ord(c)] for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"]
    # These variants may already have been selected by texture healing.
    candidates = set(words)
    words += [g for g in font.getGlyphOrder() if g.split(".")[0] in candidates and ".heal." in g]
    order = set(font.getGlyphOrder())
    closing = ("parenright", "bracketright", "braceright")
    opening = ("parenleft", "bracketleft", "braceleft")
    before = " ".join(words + delimiter_variants(closing, order))
    after = " ".join(words + delimiter_variants(opening, order)
                     + [name for name in ("exclam", "logicalnot") if name in order])
    or_contexts = [
        f"sub @OrLeft{' space' * l} bar' lookup CompactLogicalOr bar{' space' * r} @OrRight;"
        for l in range(2) for r in range(2)
    ]
    add_features(font, "\n".join([
        "languagesystem DFLT dflt;", "languagesystem latn dflt;",
        f"@OrLeft = [{before}];", f"@OrRight = [{after}];",
        f"lookup CompactLogicalOr {{ sub bar bar by {logical_or}; }} CompactLogicalOr;",
        f"lookup CompactCommentSlash {{ sub slash slash by {comment}; }} CompactCommentSlash;",
        *scope_rules,
        "feature calt {",
        "ignore sub slash slash' slash, slash' slash slash, colon slash' slash;",
        "sub slash' lookup CompactCommentSlash slash;",
        *or_contexts, *direct_rules,
        "} calt;", f"feature {LOOSE} {{",
        *(f"sub {comparisons[token]} by {name};" for token, name in loose_glyphs.items()),
        f"}} {LOOSE};", "table GDEF {",
        *(f"LigatureCaretByPos {name} {' '.join(map(str, caret_positions(token, cell)))};"
          for token, name in loose_glyphs.items()),
        *(f"LigatureCaretByPos {name} {cell // 2};"
          for _, name, _ in pairs.values()),
        *(f"LigatureCaretByPos {name} {cell // 2};" for name in (direct or {}).values()),
        "} GDEF;",
    ]))
    label_stylistic_set(font, LOOSE, "Loose Equality")


def build(source):
    font = TTFont(source, recalcTimestamp=False)
    _, locations = master_locations(font)
    # Keep the shipping lookup order. Override only the selected operator outlines and metrics.
    # Generate against a second font so all input masters still read the original outlines.
    original = TTFont(source)
    glyph_sets = [original.getGlyphSet(location=loc) for loc in locations]
    def replace(name, paths, advance):
        classes = font["GDEF"].table.GlyphClassDef.classDefs
        glyph_class = classes.get(name)
        from_paths(font, name, locations, paths, advance)
        if glyph_class is None:
            classes.pop(name)
        else:
            classes[name] = glyph_class

    for token, name in (COMPARISONS | ARROWS).items():
        paths = [compact_operator(shape_from_glyphs(glyphs, name), token) for glyphs in glyph_sets]
        replace(name, paths, advance_for(token))
    # Both contextual aliases draw the same four plain diamonds.
    install_compact_scope(font, original)
    for name, mark in ACCESS.values():
        replace(name, [compact_access(glyphs, mark) for glyphs in glyph_sets], CELL)
    for token, name in LOOSE_GLYPHS.items():
        if token in ("==", "!="):
            paths = [loose_equal(glyphs, token) for glyphs in glyph_sets]
        else:
            paths = [compact_operator(shape_from_glyphs(glyphs, COMPARISONS[token]), token,
                                      loose=True) for glyphs in glyph_sets]
        from_paths(font, name, locations, paths, CELL)
        font["GDEF"].table.GlyphClassDef.classDefs[name] = 2

    for token, (base, name, distance) in PAIRS.items():
        paths = [paired_ink(shape_from_glyphs(glyphs, base), distance) for glyphs in glyph_sets]
        from_paths(font, name, locations, paths, advance_for(token))
        font["GDEF"].table.GlyphClassDef.classDefs[name] = 2

    register_compact_context(font, COMPARISONS, LOOSE_GLYPHS, PAIRS)
    ligatures = font["GDEF"].table.LigCaretList
    carets = dict(zip(ligatures.Coverage.glyphs, ligatures.LigGlyph))
    for token, name in TARGETS.items():
        values = carets[name].CaretValue
        positions = caret_positions(token)
        assert len(values) == len(positions), (token, values)
        for value, position in zip(values, positions):
            value.Coordinate = position
    for name in ONE_CELL_CARETS:
        carets[name].CaretValue[0].Coordinate = CELL // 2
    return font


def verify(source, trial):
    old, new = [TTFont(path) for path in (source, trial)]
    old_engine, new_engine = [hb.Font(hb.Face(path.read_bytes())) for path in (source, trial)]
    for name in set(old.getGlyphOrder()) - CHANGED_BASE_GLYPHS:
        assert old["hmtx"][name] == new["hmtx"][name], name
        assert old["glyf"][name].compile(old["glyf"]) == new["glyf"][name].compile(new["glyf"]), name
        assert old["gvar"].variations.get(name) == new["gvar"].variations.get(name), name
    unchanged = (
        "map(|| f(x))", "map(|w|{ f(w) })", "let f = || 1", "|| f(x)",
        "a ||| b", "Vec<[T]> [<T>]", "Vec<Vec<T>>", "f(((x)))",
        "f([[x]])", "f({{x}})", "a | b", "https://host", "/// note",
    )
    ink = {}
    for weight in range(300, 401, 10):
        location = {"wght": weight}
        for engine in (old_engine, new_engine):
            engine.set_variations(location)
        glyphs = new.getGlyphSet(location=location)
        for token, name in TARGETS.items():
            prefix = "" if token == "//" else "a "
            sample = prefix + token + " b"
            enabled = shape(new, new_engine, sample, {})
            disabled = shape(new, new_engine, sample, {"calt": False, "liga": False})
            matches = [row for row in enabled if row[0] == name]
            advance = advance_for(token)
            assert len(matches) == 1 and matches[0][2] == advance, (sample, enabled)
            assert all(row[0] != name for row in disabled), (sample, disabled)
            assert sum(row[2] for row in disabled) == CELL * len(sample)
            assert sum(row[2] for row in disabled[:-1]) - sum(
                row[2] for row in enabled[:-1]
            ) == len(token) * CELL - advance, (sample, enabled)
            assert enabled[-1][:3] == disabled[-1][:3]
            left, _, right, _ = shape_from_glyphs(glyphs, name).bounds
            assert 0 <= left < right <= advance, (token, weight, left, right)
            width = round(right - left)
            if token in EQUALITY or token in ARROWS:
                assert width == TWO_CELL_INK, (token, weight, left, right)
            if weight == 350:
                ink[token] = width
        for token, name in LOOSE_GLYPHS.items():
            sample = f"a {token} b"
            standard = shape(new, new_engine, sample, {})
            compact = shape(new, new_engine, sample, {LOOSE: True})
            assert [(row[0], row[2]) for row in compact if row[0] == name] == [(name, CELL)]
            assert sum(row[2] for row in standard[:-1]) - sum(
                row[2] for row in compact[:-1]) == CELL, (token, weight)
            left, _, right, _ = shape_from_glyphs(glyphs, name).bounds
            assert 0 <= left < right <= CELL, (name, weight)
        stacked_tildes = []
        for token in ("==", "!="):
            outline = shape_from_glyphs(glyphs, LOOSE_GLYPHS[token])
            *lower, upper = sorted((c.bounds for c in outline.contours), key=lambda box: box[1])
            assert upper[1] - max(box[3] for box in lower) >= 22
            stacked_tildes.append(upper)
        assert stacked_tildes[0] == stacked_tildes[1]
        plain_scope, alternate_scope = [shape_from_glyphs(glyphs, name) for name in SCOPES]
        assert list(plain_scope.segments) == list(alternate_scope.segments)
        assert len([c for c in plain_scope.contours if abs(c.area) >= 1]) == 4
        left, _, right, _ = plain_scope.bounds
        assert 0 <= left < right <= CELL, (weight, left, right)
        for hairline, scope in zip((False, True), SCOPES):
            features = {"ss05": hairline}
            for sample in ("a::b", "Vec::<T>::new()", "::<Vec<T>>"):
                before = shape(old, old_engine, sample, features)
                after = shape(new, new_engine, sample, features)
                assert len(before) == len(after)
                for prior, current in zip(before, after):
                    assert prior[:2] == current[:2] and prior[3:] == current[3:]
                    assert prior[2] - current[2] == (CELL if current[0] == scope else 0)
                assert sum(row[0] == scope for row in after) == sample.count("::")
                if "::<" in sample:
                    opening = next(i for i, row in enumerate(after) if row[0].startswith("less.generic"))
                    shift = sum(row[2] for row in before[:opening]) - sum(
                        row[2] for row in after[:opening])
                    assert shift == CELL
                    scope_row, angle_row = after[opening - 1:opening + 1]
                    scope_right = shape_from_glyphs(glyphs, scope_row[0]).bounds[2] + scope_row[3]
                    angle_left = shape_from_glyphs(glyphs, angle_row[0]).bounds[0] + angle_row[3]
                    assert scope_right < scope_row[2] + angle_left
        for sample in ("a = b", "a >= b", "a <= b", "x => y", "a:::b", "Vec::<T>::new()"):
            assert shape(new, new_engine, sample, {}) == shape(new, new_engine, sample, {LOOSE: True})
        for token, (name, _) in ACCESS.items():
            outline = shape_from_glyphs(glyphs, name)
            assert glyphs[name].width == CELL
            assert 0 <= outline.bounds[0] < outline.bounds[2] <= CELL
            dots = sorted(box for box in (c.bounds for c in outline.contours) if box[1] < 0)
            assert len(dots) == 2 and dots[1][0] - dots[0][2] >= 50
            sample = f"obj{token}value"
            for features in ({}, {"ss02": True, "ss05": True, LOOSE: True}):
                before = shape(old, old_engine, sample, features)
                after = shape(new, new_engine, sample, features)
                assert after[3] == (name, 3, CELL, 0, 0)
                assert sum(row[2] for row in before[:4]) - sum(row[2] for row in after[:4]) == CELL
                assert before[4:] == after[4:]
            disabled = {"calt": False, "liga": False}
            assert shape(old, old_engine, sample, disabled) == shape(new, new_engine, sample, disabled)
        for token in ARROWS:
            rows = shape(new, new_engine, f"x {token} y", {})
            assert sum(row[2] for row in rows[:-1]) + rows[-1][3] == 5 * CELL
        sequence = "a === b || c !== d"
        compact = shape(new, new_engine, sequence, {})
        assert compact[-1][1] == len(sequence) - 1
        assert sum(row[2] for row in compact[:-1]) == (len(sequence) - 4) * CELL
        for pair, expected in (("<[", ("less.generic", "bracketleft")),
                               ("[<", ("bracketleft", "less.generic"))):
            for hairlined in (False, True):
                suffix = ".hairline" if hairlined else ""
                for logic in (False, True):
                    rows = shape(new, new_engine, pair, {"ss02": logic, "ss05": hairlined})
                    assert [(name, advance, x) for name, _, advance, x, _ in rows] == [
                        (expected[0] + suffix, CELL, 30), (expected[1] + suffix, CELL, -30),
                    ], (pair, logic, hairlined, rows)
        for settings in ({}, {"ss05": True}, {"ss02": True}, {"ss05": True, "ss02": True}):
            for sample in ("a||b", "a ||b", "a|| b", "(a) || (b)", "a || !b"):
                assert any(row[0] == "code.logicalOr"
                           for row in shape(new, new_engine, sample, settings)), (sample, settings)
            for sample in unchanged:
                assert shape(old, old_engine, sample, settings) == shape(
                    new, new_engine, sample, settings
                ), (sample, settings, weight)
    for tag in ("cmap", "GPOS", "fvar", "STAT"):
        assert old.getTableData(tag) == new.getTableData(tag), tag
    ligatures = new["GDEF"].table.LigCaretList
    carets = dict(zip(ligatures.Coverage.glyphs, ligatures.LigGlyph))
    for token, name in TARGETS.items():
        assert [v.Coordinate for v in carets[name].CaretValue] == caret_positions(token)
    for token, name in LOOSE_GLYPHS.items():
        assert [v.Coordinate for v in carets[name].CaretValue] == caret_positions(token, CELL)
    for name in ONE_CELL_CARETS:
        assert [v.Coordinate for v in carets[name].CaretValue] == [CELL // 2]
    with TemporaryDirectory() as tmp:
        subprocess.run([ots.OTS_SANITIZE, str(trial), str(Path(tmp) / "out.ttf")],
                       check=True, capture_output=True)
    return ink


def proof(directory, config, trial):
    width, height = 1320, 700
    body = [
        rect(0, 0, width, height, BG),
        label("Daikonic Transit Code · compact operators", 36, 54, 30, bold=True),
        label("Book 350 · shorter advances pull following text left", 36, 82, 15, MUTED),
    ]
    rows = (
        "a >= b    a <= b    a == b    a != b",
        "a === b   a !== b",
        "x -> y  x <- y  x ->> y  x <<- y  x => y",
        "a || b    a||b    (a) || (b)",
        "// a short note",
        "a === b || c !== d",
        "map(|| f(x))     Vec<Vec<T>>",
    )
    for column, (title, features) in enumerate((
        ("Ligatures off", {"calt": False, "liga": False}),
        ("Compact ligatures on", {"ss05": True}),
    )):
        x = 36 + column * 632
        body.append(rect(x, 111, 616, 507, "#101821"))
        body.append(label(title, x + 20, 151, 17, CREAM, True))
        panel = Panel(f"operators-{column}", {**config, "font": str(trial)})
        for i, row in enumerate(rows):
            if i in (3, 5):
                body.append(rect(x + 20, 177 + 60 * i, 576, 1, "#26333e"))
            size = 24 if i == 2 else 26
            panel.text(row, x + 20, 215 + 60 * i, size, 350, CREAM, features=features)
        body.append(panel.body())
    body.append(label("All five arrow ligatures advance two cells.", 36, 653, 15, MUTED))
    export(directory / "Compact-Operators.svg", body, width, height)


def feature_proof(directory, config, trial):
    width, height = 1320, 765
    body = [
        rect(0, 0, width, height, BG),
        label("Daikonic Transit Code · compact punctuation", 36, 54, 30, bold=True),
        label("Book 350", 36, 82, 15, MUTED),
    ]
    for col, enabled in enumerate((False, True)):
        x = 36 + 632 * col
        body.append(rect(x, 111, 616, 205, "#101821"))
        body.append(label("Loose Equality on" if enabled else "Loose Equality off",
                          x + 20, 150, 17, CREAM, True))
        panel = Panel(f"loose-{col}", {**config, "font": str(trial)})
        for i, text in enumerate(("a = b   a == b   a != b", "a === b   a !== b")):
            panel.text(text, x + 20, 215 + 58 * i, 31, 350, CREAM, features={LOOSE: enabled})
        body.append(panel.body())
        body.append(rect(x, 340, 616, 180, "#101821"))
        body.append(label("One-cell scope · Turbofish Hairlining " + ("on" if enabled else "off"),
                          x + 20, 378, 17, CREAM, True))
        panel = Panel(f"scope-{col}", {**config, "font": str(trial)})
        panel.text("foo::bar   parse::<Vec<T>>()", x + 20, 456, 28, 350, CREAM,
                   features={"ss05": enabled, "ss07": not enabled})
        body.append(panel.body())
        body.append(rect(x, 544, 616, 180, "#101821"))
        body.append(label("Optional access · " + ("one-cell ligatures" if enabled else "ligatures off"),
                          x + 20, 582, 17, CREAM, True))
        panel = Panel(f"access-{col}", {**config, "font": str(trial)})
        panel.text("obj?.value    obj!.value", x + 20, 660, 32, 350, CREAM,
                   features={"calt": enabled, "liga": enabled})
        body.append(panel.body())
    export(directory / "Compact-Punctuation.svg", body, width, height)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--proof", action="store_true", help="Render the selected release font")
    parser.add_argument("--source", type=Path, help="Build a trial from a released font predating this feature")
    args = parser.parse_args()
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    config = specimen_families()["code"]
    selected = ROOT / config["font"]
    if args.proof:
        proof(directory, config, selected)
        feature_proof(directory, config, selected)
        return
    from bundle_release import RECIPE

    source = (args.source or ROOT / RECIPE["typography"]["code"].get("operator_source", RECIPE["typography"]["code"]["font"])).resolve()
    trial = save_trial(build(source), directory, "Compact Optional Access")
    ink = verify(source, trial)
    proof(directory, config, trial)
    feature_proof(directory, config, trial)
    metrics = {token: {"ink": width, "advance": advance_for(token), "carets": caret_positions(token)}
               for token, width in ink.items()}
    for token in ("::", *ACCESS):
        metrics[token] = {"advance": CELL, "carets": [CELL // 2]}
    metrics["Loose Equality"] = {
        token: {"advance": CELL, "carets": caret_positions(token, CELL)}
        for token in LOOSE_GLYPHS
    }
    (directory / "Ink-Widths.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(ink, flush=True)


if __name__ == "__main__":
    main()
