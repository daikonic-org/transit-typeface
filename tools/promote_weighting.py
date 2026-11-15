"""Adopt validated 72% sources, preserving the frozen baseline and prior work."""

from pathlib import Path
import hashlib
import json
import shutil
import zipfile

from adopt_weighting import OUT, ROOT, VERSIONS


def main():
    path = ROOT / "family.json"
    data = json.loads(path.read_text())
    for key, cfg in data["families"].items():
        stage = OUT / key
        assert (stage / "validation.json").exists(), (
            key,
            "interpolation validation missing",
        )
        assert (stage / "native-validation.json").exists(), (
            key,
            "editable-source validation missing",
        )
        assert cfg["version"] != VERSIONS[key], (key, "already adopted")
    baseline_root = ROOT / "sources/weighting-baseline"
    baseline_root.mkdir(exist_ok=True)
    manifest = {}
    for key, cfg in data["families"].items():
        backup = ROOT / ".build/prior-weighting" / key
        assert not backup.exists(), (key, "preserved backup already exists")
        backup.mkdir(parents=True)
        frozen = baseline_root / (key + "-" + cfg["version"] + "-VF.ttf")
        assert not frozen.exists()
        shutil.copy2(ROOT / cfg["font"], frozen)
        manifest[key] = {
            "path": str(frozen.relative_to(ROOT)),
            "version": cfg["version"],
            "sha256": hashlib.sha256(frozen.read_bytes()).hexdigest(),
        }
        shutil.copytree(ROOT / "fonts" / key, backup / "fonts")
        shutil.move(str(ROOT / "sources" / key), str(backup / "sources"))
        shutil.copytree(OUT / key / "sources", ROOT / "sources" / key)
        # Keep the complete editor source while respecting GitHub's per-file
        # limit. UFO/designspace files remain directly editable in the checkout.
        for native in (ROOT / "sources" / key).glob("*.glyphs"):
            if native.stat().st_size > 95_000_000:
                with zipfile.ZipFile(
                    native.with_suffix(".glyphs.zip"), "w", zipfile.ZIP_DEFLATED
                ) as z:
                    z.write(native, native.name)
                native.unlink()
        shutil.copytree(OUT / key / "fonts", ROOT / "fonts" / key, dirs_exist_ok=True)
        qa = ROOT / "qa" / key
        for name in ("fidelity", "compatibility", "validation", "native-validation"):
            shutil.copy2(
                OUT / key / (name + ".json"), qa / ("weighting-" + name + ".json")
            )
        cfg["weighting_baseline"] = str(frozen.relative_to(ROOT))
        cfg["weighting_baseline_version"] = cfg["version"]
        cfg["version"] = VERSIONS[key]
        cfg["tag"] = key.title() + "-" + VERSIONS[key] + "R"
        cfg["weighting_ratio"] = 0.72
    (baseline_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    path.write_text(json.dumps(data, indent=2) + "\n")
    recipe_path = ROOT / "recipes/weights.json"
    recipe = json.loads(recipe_path.read_text())
    recipe["purpose"] = (
        "Accepted 72% Regular-anchored generation from frozen pre-adoption baselines, with explicit selected-glyph overrides. Compatible production masters rebuild separately."
    )
    recipe["defaults"]["horizontal_growth_ratio"] = 0.72
    recipe_path.write_text(json.dumps(recipe, indent=2) + "\n")
    print(
        "Adopted Sans0.107, System0.116 and Code1.016; original inputs and previous sources preserved."
    )


if __name__ == "__main__":
    main()
