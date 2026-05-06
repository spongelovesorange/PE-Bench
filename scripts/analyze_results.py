from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.analysis.reporting import find_suite_dirs, write_analysis_outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate PE-Bench analysis assets.")
    parser.add_argument("--results-root", default="results/canonical/dev_v2_public_dev/suites")
    parser.add_argument("--output-dir", default="results/canonical/dev_v2_public_dev/analysis")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    suite_dirs = find_suite_dirs(args.results_root)
    outputs = write_analysis_outputs(suite_dirs=suite_dirs, output_dir=args.output_dir)
    print(outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
