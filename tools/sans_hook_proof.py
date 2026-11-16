"""Proof named and intermediate release weights against the selected hooks."""

from adopt_weighting import ROOT, instance
import hook_ligature_study as proof


def main():
    current = ROOT / proof.DATA["families"]["sans"]["font"]
    baseline = ROOT / proof.DATA["families"]["sans"]["ligature_baseline"]
    for folder, weights in [
        ("Named", (300, 350, 400, 500, 600)),
        ("Intermediate", (325, 375, 450, 550)),
    ]:
        proof.OUT = ROOT / "qa/sans" / ("Hooks-" + folder)
        proof.OUT.mkdir(exist_ok=True)
        fonts = {w: instance(current, w, None) for w in weights}
        reference = ROOT / "trials/2026-11-16-sans-hooks-r2"
        if folder == "Intermediate":
            reference = ROOT / ".build/hook-intermediate-references"
            reference.mkdir(exist_ok=True)
            for w in weights:
                f = instance(baseline, w, None)
                band = proof.whitespace_band(f)
                for pair in ("ai", "li"):
                    proof.construct(f, pair, band)
                proof.preserve_boundary_kerning(f)
                f.save(reference / f"DaikonicTransitSansHookStudy-{w}.ttf")
        proof.proof(
            fonts,
            current,
            reference=reference,
            title="SANS 0.109 / SELECTED HOOKS IN THE VARIABLE FONT",
            columns=[
                "SELECTED CONSTRUCTION",
                "ORDINARY LETTERS",
                "RELEASE VARIABLE FONT",
            ],
            weights=weights,
        )


if __name__ == "__main__":
    main()
