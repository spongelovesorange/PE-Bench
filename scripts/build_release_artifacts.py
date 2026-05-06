from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.artifacts.release import validate_release_artifacts, write_release_artifacts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reviewer-facing PE-Bench release artifacts.")
    parser.add_argument("--output-root", default="artifacts")
    parser.add_argument("--check", action="store_true", help="Validate artifacts after writing them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = write_release_artifacts(args.output_root)
    for name, path in sorted(paths.items()):
        print(f"{name}: {path}")

    if args.check:
        errors = validate_release_artifacts(args.output_root)
        if errors:
            print("Release artifact validation failed:")
            for error in errors:
                print(f"  - {error}")
            return 1
        print("Release artifact validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
