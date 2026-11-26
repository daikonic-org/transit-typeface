"""Apply distribution names and licensing to the released font binaries."""

from fontTools.misc.fixedTools import floatToFixedToFloat

from specimens import ROOT


PROJECT = "https://github.com/daikonic-org/transit-typeface"
DESCRIPTIONS = {
    "sans": "A proportional typeface for general text, derived from Metropolitan Line.",
    "system": "An interface typeface derived from Daikonic Transit Sans with optical size and width axes.",
    "code": "A monospaced typeface derived from Daikonic Transit Sans for source editors and terminals.",
}


def font_revision(version):
    major, minor, *patch = version.split(".")
    patch_revision = int(patch[0]) if patch else 0
    return floatToFixedToFloat(float(f"{major}.{minor}") + patch_revision / 1000, 16)


def stamp_release(font, family, version):
    names = font["name"]
    license_text = (ROOT / "OFL.txt").read_text().strip()
    copyright_notices = license_text.split("\n\n", 1)[0]
    ps_name = names.getDebugName(6)
    records = {
        0: copyright_notices,
        3: f"{ps_name}; Version {version}",
        5: f"Version {version}",
        8: "Daikonic Transit Project",
        9: "Daikonic Transit Project Authors, based on Metropolitan Line by Cyreal, Alexei Vanyashin and Michael Voronin",
        10: DESCRIPTIONS[family],
        11: PROJECT,
        12: PROJECT,
        13: license_text,
        14: "https://openfontlicense.org/",
    }
    for name_id, value in records.items():
        names.removeNames(nameID=name_id)
        names.setName(value, name_id, 3, 1, 0x409)
        names.setName(value, name_id, 0, 4, 0)
    font["OS/2"].achVendID = "    "
    font["OS/2"].fsType = 0
    font["head"].fontRevision = font_revision(version)


def verify_release_metadata(font, record):
    names = font["name"]
    license_text = (ROOT / "OFL.txt").read_text().strip()
    assert names.getDebugName(0) == license_text.split("\n\n", 1)[0]
    assert names.getDebugName(5) == "Version " + record["version"]
    assert font["head"].fontRevision == font_revision(record["version"])
    assert names.getDebugName(8) == "Daikonic Transit Project"
    assert names.getDebugName(13) == license_text
    assert names.getDebugName(14) == "https://openfontlicense.org/"
    assert names.getDebugName(16) == record["name"]
    assert font["OS/2"].fsType == 0 and font["OS/2"].achVendID == "    "
    assert names.getDebugName(6).startswith(record["name"].replace(" ", "") + "-")
    if "fvar" in font:
        postscript_names = [names.getDebugName(instance.postscriptNameID)
                            for instance in font["fvar"].instances
                            if instance.postscriptNameID != 0xFFFF]
        assert len(postscript_names) == len(set(postscript_names))
        assert all(name and name.startswith(record["name"].replace(" ", "") + "-")
                   for name in postscript_names)
