"""Verify distributed CFF exports, frozen inputs, hashes and sanitizer results."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import ots
from fontTools.ttLib import TTFont
from specimens import ROOT


def main():
    count = 0
    for lane in ["current", "optical-trial"]:
        data = json.loads((ROOT / "exports/otf" / lane / "manifest.json").read_text())
        for family, record in data.items():
            source = ROOT / record["source"]
            assert (
                hashlib.sha256(source.read_bytes()).hexdigest()
                == record["source_sha256"]
            ), (lane, family, "source hash")
            for item in record["exports"]:
                path = ROOT / item["file"]
                assert (
                    hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
                ), str(path)
                font = TTFont(path)
                assert (
                    font.sfntVersion == "OTTO" and "CFF " in font and "fvar" not in font
                )
                assert font["post"].formatType == 3.0
                if family == "code":
                    assert (
                        font["post"].isFixedPitch
                        and font["CFF "].cff.topDictIndex[0].isFixedPitch
                    )
                with tempfile.TemporaryDirectory() as tmp:
                    r = subprocess.run(
                        [ots.OTS_SANITIZE, str(path), str(Path(tmp) / "font.otf")],
                        capture_output=True,
                    )
                    assert r.returncode == 0, (str(path), r.stderr.decode())
                count += 1
    print(count, "CFF exports verified: input hashes, binary hashes, metadata and OTS")


if __name__ == "__main__":
    main()
