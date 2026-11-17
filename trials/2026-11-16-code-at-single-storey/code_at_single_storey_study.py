"""Compare a single-storey a inside @ at the selected size and stroke weight."""

from code_at_redraw import drawing
from code_at_uniform_study import main as build
from adopt_weighting import ROOT

OUT = ROOT / "trials/2026-11-16-code-at-single-storey"
PREVIOUS = (
    ROOT / "trials/2026-11-16-code-at-uniform/DaikonicTransitCodeUniformAtStudy-VF.ttf"
)


def single_storey(font, **kwargs):
    return drawing(font, single_storey=True, **kwargs)


def main():
    return build(
        out=OUT,
        family="Daikonic Transit Code Single Storey At Study",
        draw=single_storey,
        previous=PREVIOUS,
        labels=("double-storey a", "single-storey a"),
    )


if __name__ == "__main__":
    main()
