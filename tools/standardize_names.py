"""One-time canonical family naming update; verify every drawing table unchanged."""

from copy import deepcopy
from io import TextIOWrapper
from pathlib import Path
import hashlib
import json
import plistlib
import re
import shutil
import zipfile

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = {
    "sans": ("0.107", "0.108"),
    "system": ("0.116", "0.117"),
    "code": ("1.016", "1.017"),
}
TABLES = (
    "glyf",
    "gvar",
    "hmtx",
    "cmap",
    "GSUB",
    "GPOS",
    "GDEF",
    "fvar",
    "STAT",
    "HVAR",
    "MVAR",
)


def canonical(value):
    return value.replace("Daikonic Transit Code 600", "Daikonic Transit Code").replace(
        "DaikonicTransitCode600", "DaikonicTransitCode"
    )


def rewrite_font(path, old, new):
    font = TTFont(path)
    before = {tag: font.getTableData(tag) for tag in TABLES if tag in font}
    for record in font["name"].names:
        record.string = (
            canonical(record.toUnicode()).replace(old, new).encode(record.getEncoding())
        )
    font["head"].fontRevision = float(new)
    font.save(path)
    check = TTFont(path)
    assert all(check.getTableData(tag) == data for tag, data in before.items()), path
    assert all(
        "Daikonic Transit Code 600" not in n.toUnicode()
        and "DaikonicTransitCode600" not in n.toUnicode()
        for n in check["name"].names
    ), path
    dest = path.with_name(canonical(path.name))
    if dest != path:
        path.rename(dest)
    return dest


def glyphs_line(line, old, new):
    line = canonical(line)
    previous = int(old.split(".")[1])
    current = int(new.split(".")[1])
    return re.sub(
        r"^(versionMinor\s*=\s*)" + str(previous) + r"(;\s*)$",
        lambda m: m[1] + str(current) + m[2],
        line,
    )


def main():
    config_path = ROOT / "family.json"
    data = json.loads(config_path.read_text())
    backup = ROOT / ".build/name-standardization/before"
    backup.mkdir(parents=True, exist_ok=True)
    results = []
    for key, cfg in data["families"].items():
        old, new = VERSIONS[key]
        assert cfg["version"] == old, (key, "already renamed or unexpected version")
        shutil.copytree(ROOT / "fonts" / key, backup / key, dirs_exist_ok=True)
        files = (
            list((ROOT / "fonts" / key).rglob("*.ttf"))
            + list((ROOT / "fonts" / key).rglob("*.woff2"))
            + list((ROOT / "sources" / key).glob("Master-*.ttf"))
        )
        for path in files:
            dest = rewrite_font(path, old, new)
            results.append(
                {
                    "file": str(dest.relative_to(ROOT)),
                    "outline_variation_metrics_layout": "unchanged",
                }
            )
        cfg["name"] = "Daikonic Transit " + key.title()
        cfg["title"] = cfg["name"]
        cfg["stem"] = canonical(cfg["stem"])
        cfg["font"] = canonical(cfg["font"])
        cfg["version"] = new
        cfg["tag"] = key.title() + "-" + new + "R"
        sources = ROOT / "sources" / key
        vf = TTFont(ROOT / cfg["font"])
        vf.saveXML(sources / "VariableMetadata.ttx", tables=["name", "fvar", "STAT"])
        for path in sources.glob("*.designspace"):
            path.write_text(canonical(path.read_text()))
        for ufo in sources.glob("*.ufo"):
            info_path = ufo / "fontinfo.plist"
            info = plistlib.loads(info_path.read_bytes())
            info["versionMajor"], info["versionMinor"] = map(int, new.split("."))
            info = {
                k: canonical(v) if isinstance(v, str) else v for k, v in info.items()
            }
            info_path.write_bytes(plistlib.dumps(info, sort_keys=False))
            lib = ufo / "lib.plist"
            lib.write_text(canonical(lib.read_text()))
        for path in sources.glob("*.glyphs"):
            temp = path.with_suffix(".glyphs.tmp")
            with path.open() as source, temp.open("w") as target:
                for line in source:
                    target.write(glyphs_line(line, old, new))
            temp.replace(path)
        for path in sources.glob("*.glyphs.zip"):
            temp = path.with_suffix(".zip.tmp")
            with zipfile.ZipFile(path) as source, zipfile.ZipFile(
                temp, "w", zipfile.ZIP_DEFLATED
            ) as target:
                for member in source.infolist():
                    with TextIOWrapper(
                        source.open(member), encoding="utf-8"
                    ) as src, TextIOWrapper(
                        target.open(member.filename, "w"), encoding="utf-8"
                    ) as dest:
                        for line in src:
                            dest.write(glyphs_line(line, old, new))
            with zipfile.ZipFile(temp) as z:
                assert z.testzip() is None
            temp.replace(path)
    config_path.write_text(json.dumps(data, indent=2) + "\n")
    (ROOT / "qa/canonical-names.json").write_text(
        json.dumps(
            {"versions": VERSIONS, "tables_compared": TABLES, "files": results},
            indent=2,
        )
        + "\n"
    )
    print(
        "Canonical names applied; drawing, variation, metric and layout tables unchanged.",
        flush=True,
    )


if __name__ == "__main__":
    main()
