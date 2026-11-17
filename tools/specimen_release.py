"""Package a dated specimen revision without altering font releases."""

from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]

from specimens import specimen_families


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "date",
        nargs="?",
        default="verification",
        help="Specimen revision date, YYYY-MM-DD",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify selected fonts and rendered artifacts without packaging",
    )
    args = parser.parse_args()
    families = specimen_families()
    manifest = json.loads((ROOT / "specimens/manifest.json").read_text())
    content = json.loads((ROOT / "specimens/content.json").read_text())
    rendered = json.loads((ROOT / "qa/specimen-rendering.json").read_text())["files"]
    summary = "; ".join(key.title() + ": " + content[key]["word"] for key in families)
    out = ROOT / ".dist/specimens" / args.date
    members = {}
    for key, cfg in families.items():
        assert manifest[key]["content"] == content[key]
        assert (
            manifest[key]["sha256"]
            == hashlib.sha256((ROOT / cfg["font"]).read_bytes()).hexdigest()
        )
        members[key] = [
            (
                ROOT / "specimens" / ("Transit" + key.title() + suffix),
                cfg["stem"] + suffix,
            )
            for suffix in (".png", ".pdf", ".svg")
        ]
    members["code"] += [
        (
            ROOT / "specimens" / ("TransitCode-Details" + suffix),
            "DaikonicTransitCode-Details" + suffix,
        )
        for suffix in (".png", ".pdf", ".svg")
    ]
    members["family"] = [item for key in families for item in members[key]] + [
        (
            ROOT / "specimens" / ("Transit-Family" + suffix),
            "DaikonicTransit-Family" + suffix,
        )
        for suffix in (".png", ".pdf", ".svg")
    ]
    for src in {src for files in members.values() for src, name in files}:
        assert rendered[src.name] == hashlib.sha256(src.read_bytes()).hexdigest(), (
            src,
            "rendered artifact changed",
        )
    if args.check:
        print("Specimen font selections, content and 15 rendered artifacts verified")
        return
    out.mkdir(parents=True, exist_ok=True)
    versions = ", ".join(
        cfg["name"]
        + " "
        + cfg["version"]
        + (" preview" if cfg.get("status") == "preview" else "")
        for cfg in families.values()
    )
    archives = []
    for key, files in members.items():
        stem = "SPECIMEN-daikonic-transit-" + key + "-" + args.date
        archive = out / (stem + ".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for src, name in files:
                z.write(src, Path(stem) / name)
            for path in ("OFL.txt", "NOTICE.txt"):
                z.write(ROOT / path, Path(stem) / path)
            z.writestr(
                str(Path(stem) / "README.txt"),
                "Daikonic Transit specimens — "
                + args.date
                + "\n\n"
                + summary
                + ".\nBoth main System numeral rows use default figures. The hooked 1 is shown only in the labeled optional tabular (tnum) comparison.\n\nFont versions: "
                + versions
                + ". Font binaries are unchanged.\n",
            )
            z.write(ROOT / "specimens/content.json", Path(stem) / "content.json")
            z.write(ROOT / "specimens/manifest.json", Path(stem) / "manifest.json")
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
        archives.append(archive)
    checksum = out / ("SHA256SUMS-specimens-" + args.date + ".txt")
    checksum.write_text(
        "".join(
            hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
            for p in archives
        )
    )
    (out / "Release.md").write_text(
        "Updated specimen panels for **Daikonic Transit Sans, System and Code**.\n\n"
        + "\n".join(
            "- **"
            + families[key]["name"]
            + "**: **"
            + content[key]["word"]
            + "**, `"
            + content[key]["letters"]
            + "` and a large `"
            + content[key]["showcase"]
            + "`."
            for key in families
        )
        + "\n\nCurrent font cuts: "
        + versions
        + ". Code includes an additional detail sheet across all three weights.\n\nBoth main System numeral rows use default proportional figures. Its hooked 1 appears only in a separately labeled **optional tabular (tnum)** example.\n\nEach ZIP contains matching PNG, vector PDF and outlined SVG exports. Choose an individual typeface or the **family** archive for all three panels and the combined board. Font versions and installed font files are unchanged.\n"
    )
    (out / "release.json").write_text(
        json.dumps(
            {
                "tag": "Specimens-" + args.date,
                "title": "Daikonic Transit — Specimens " + args.date,
                "assets": [p.name for p in archives] + [checksum.name],
            },
            indent=2,
        )
        + "\n"
    )
    print("Packaged four specimen archives and checksums:", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
