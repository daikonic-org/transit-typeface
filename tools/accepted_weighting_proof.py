"""Reuse the trial proof layout to inspect the adopted variable-font outputs."""

import json

from adopt_weighting import OUT as ACCEPTED, instance
import weighting_proof as proof


def main():
    proof.STYLES.update({w: "Intermediate" for w in (325, 375, 450, 550)})
    previous = proof.load

    def load(key, weight, optical, variant):
        if variant == "production":
            return instance(
                proof.ROOT / proof.DATA["families"][key]["font"],
                weight,
                optical,
            )
        return previous(key, weight, optical, variant)

    proof.load = load
    proof.OUT = ACCEPTED / "proofs"
    proof.OUT.mkdir(exist_ok=True)
    proof.VARIANTS = [
        ("current", "PREVIOUS"),
        ("production", "ADOPTED VARIABLE FONT"),
        ("0.72", "APPROVED 72% LETTER TRIAL"),
    ]
    pages = [
        proof.proof(
            "Overview",
            [
                ("sans", 350, None),
                ("sans", 600, None),
                ("system", 350, 14),
                ("system", 600, 14),
                ("code", 300, None),
                ("code", 350, None),
            ],
        )
    ]
    recipe = json.loads((proof.ROOT / "recipes/weights.json").read_text())
    for key, config in recipe["families"].items():
        for optical in config["optical_sizes"]:
            name = key.title() + (f"-opsz{optical}" if optical else "")
            pages.append(
                proof.proof(
                    name, [(key, int(w), optical) for w in config["target_H_stems"]]
                )
            )
    # At intermediate coordinates the two right columns intentionally show the
    # same VF: there is no separately approved static trial at those locations.
    proof.VARIANTS = [
        ("current", "PREVIOUS"),
        ("production", "ADOPTED VARIABLE FONT"),
        ("production", "ADOPTED VARIABLE FONT / REPEAT"),
    ]
    pages.append(
        proof.proof(
            "Intermediates",
            [("sans", w, None) for w in (325, 375, 450, 550)]
            + [("system", 325, 12), ("system", 450, 24), ("system", 550, 24)]
            + [("code", 325, None), ("code", 375, None)],
        )
    )
    (proof.OUT / "pages.json").write_text(json.dumps(pages, indent=2) + "\n")
    print("Generated adopted-VF proof sheets", flush=True)


if __name__ == "__main__":
    main()
