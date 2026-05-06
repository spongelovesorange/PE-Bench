from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.analysis.reporting import write_suite_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize a PE-Bench suite directory.")
    parser.add_argument("--suite", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = write_suite_summary(args.suite)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
