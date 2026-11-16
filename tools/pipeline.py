"""One entry point with separate approved-build and experimental-study lanes."""

from pathlib import Path
import argparse
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["approved", "study", "report", "release"])
    parser.add_argument(
        "--family", choices=["all", "sans", "system", "code"], default="all"
    )
    parser.add_argument("--ratio-y", type=float)
    args = parser.parse_args()
    if args.mode in ["approved", "release"]:
        steps = [["build.py"], ["validate.py", "--rebuilt"], ["check_sans_hooks.py"]]
        if args.mode == "release":
            steps.append(["release.py"])
    elif args.mode == "study":
        steps = [["derive_weights.py", args.family]]
        if args.ratio_y is not None:
            steps[0] += ["--ratio-y", str(args.ratio_y)]
    else:
        steps = [["audit.py"], ["scaling_study.py"]]
    for script, *options in steps:
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / script), *options],
            cwd=ROOT,
            check=True,
        )


if __name__ == "__main__":
    main()
