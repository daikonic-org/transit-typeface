"""Enable the reviewed Code layout and stamp the release faces."""

from itertools import product

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
import uharfbuzz as hb

from check_code_rebuild import shape
from code_receiver_texture import FEATURE as TEXTURE_FEATURE, HALF_WIDTH, add_texture
from code_weight_width_trial import WEIGHTS, name_trial
from code_width import verify_width
from release_metadata import stamp_release


def share_feature(font, table_name, source_tag, dest_tag):
    """Share the same lookup indices so either feature enables each lookup once."""
    table = font[table_name].table
    records = table.FeatureList.FeatureRecord
    source_index = next(i for i, entry in enumerate(records) if entry.FeatureTag == source_tag)
    source = records[source_index].Feature.LookupListIndex
    dest_index = next((i for i, entry in enumerate(records) if entry.FeatureTag == dest_tag), None)
    if dest_index is None:
        entry = otTables.FeatureRecord()
        entry.FeatureTag = dest_tag
        entry.Feature = otTables.Feature()
        entry.Feature.FeatureParams = None
        entry.Feature.LookupListIndex = []
        dest_index = len(records)
        records.append(entry)
    feature = records[dest_index].Feature
    feature.LookupListIndex = sorted(set(feature.LookupListIndex) | set(source))
    feature.LookupCount = len(feature.LookupListIndex)

    order = sorted(range(len(records)), key=lambda index: records[index].FeatureTag)
    indexes = {old: new for new, old in enumerate(order)}
    table.FeatureList.FeatureRecord = [records[i] for i in order]
    table.FeatureList.FeatureCount = len(records)
    for entry in table.ScriptList.ScriptRecord:
        languages = [entry.Script.DefaultLangSys, *(row.LangSys for row in entry.Script.LangSysRecord)]
        for language in filter(None, languages):
            active = set(language.FeatureIndex)
            if source_index in active:
                active.add(dest_index)
            language.FeatureIndex = sorted(indexes[index] for index in active)
            language.FeatureCount = len(active)
            if language.ReqFeatureIndex != 0xFFFF:
                language.ReqFeatureIndex = indexes[language.ReqFeatureIndex]


def release_font(source, version, *, italic, shift_intermediate_texture=False):
    font = TTFont(source, recalcTimestamp=False)
    share_feature(font, "GSUB", "ss08", "calt")
    share_feature(font, "GPOS", "ss08", "kern")
    if not italic:
        add_texture(font, shift_intermediate=shift_intermediate_texture)
    family = "Daikonic Transit Code"
    name_trial(font, family, variable=True)
    for instance in font["fvar"].instances:
        style = WEIGHTS[instance.coordinates["wght"]]
        if italic:
            style = "Italic" if style == "Regular" else f"{style} Italic"
        instance.subfamilyNameID = font["name"].addName(style)
        instance.postscriptNameID = font["name"].addName(f"DaikonicTransitCode-{style.replace(' ', '')}")
    stamp_release(font, "code", version)
    return font


def verify_release(font, path, prior, *, shift_intermediate_texture=False):
    verify_width(font, 600)
    with TTFont(prior) as baseline:
        assert set(baseline.getBestCmap()) <= set(font.getBestCmap())
        for table in ("GSUB", "GPOS"):
            tags = lambda face: {r.FeatureTag for r in face[table].table.FeatureList.FeatureRecord}
            retained = tags(baseline)
            if table == "GPOS" and not shift_intermediate_texture:
                retained.discard(TEXTURE_FEATURE)
            assert retained <= tags(font), (path, table)
    engine = hb.Font(hb.Face(path.read_bytes()))
    italic = bool(font["OS/2"].fsSelection & 1)
    shift = HALF_WIDTH // 2 if shift_intermediate_texture else 0
    textures = {
        "im": ("m.texture.wide", 0), "mi": ("m.texture.wide", 0),
        "imi": ("m.texture.wide", 0), "imx": ("m.texture.middle", -shift),
        "xmi": ("m.texture.middle", shift), "xmx": ("m", 0),
        "iwi": ("w.texture.wide", 0), ".w.": ("w.texture.wide", 0),
        "namespace": ("m.texture.middle", -shift), "window": ("w.texture.middle", shift),
    }
    expected = {
        "::": 1, "?.": 1, "!.": 1, "//": 1, "<=": 1, ">=": 1,
        "===": 2, "!==": 2, "->>": 2, "<<-": 2, "=>": 2, "...items": 7,
    }
    for weight, width in product((350, 375, 400, 450, 500), (94, 97, 100, 104, 108)):
        engine.set_variations({"wght": weight, "wdth": width})
        cell = width * 6
        for sample, cells in expected.items():
            actual = shape(engine, sample, {})
            assert sum(row[2] for row in actual) == cells * cell, (path, sample, actual)
            assert actual == shape(engine, sample, {"ss08": True}), (path, sample)
        for sample, (glyph, offset) in textures.items():
            on, off = (shape(engine, sample, flags) for flags in ({}, {"ss04": True}))
            assert [row[2] for row in on] == [row[2] for row in off] == [cell] * len(sample)
            index = next(i for i, row in enumerate(off) if row[0] in {"m", "w"})
            assert off[index][4] == 0, (path, sample, off)
            if italic:
                assert on == off
            else:
                assert on[index][0] == glyph and on[index][4] == offset, (path, sample)
                assert shape(engine, sample, {"ss03": True, "ss04": True}) == off
                assert all(".texture." not in row[0] for row in off)
