from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.evaluator.pebench import evaluate_pebench_candidate
from pebench.tasks.schema import load_task
from pebench.utils.io import dump_json, load_json
from pebench.utils.paths import DEFAULT_RESULTS_ROOT


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PE-Bench evaluator v0 on one task.")
    parser.add_argument("--task", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--simulator-mode", default="auto")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task = load_task(args.task)
    candidate = load_json(args.candidate)
    result = evaluate_pebench_candidate(
        task=task,
        candidate=candidate,
        simulator_mode=args.simulator_mode,
    )
    output_path = args.output or (
        DEFAULT_RESULTS_ROOT / "examples" / f"{task['task_id']}__{candidate['baseline_name']}__eval.json"
    )
    dump_json(result, output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
