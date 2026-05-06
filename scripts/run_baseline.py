from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.adapters.registry import get_baseline
from pebench.tasks.schema import load_task
from pebench.utils.io import dump_json
from pebench.utils.paths import DEFAULT_RESULTS_ROOT
from scripts.run_suite import run_task_with_baseline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a PE-Bench baseline on one task.")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--model", default="heuristic-v0")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--simulator-mode", default="auto")
    parser.add_argument("--disable-formula-guardrails", action="store_true")
    parser.add_argument("--disable-component-grounding", action="store_true")
    parser.add_argument("--disable-correction-memory", action="store_true")
    parser.add_argument("--output", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task = load_task(args.task)
    baseline = get_baseline(
        args.baseline,
        disable_formula_guardrails=args.disable_formula_guardrails,
        disable_component_grounding=args.disable_component_grounding,
        disable_correction_memory=args.disable_correction_memory,
    )
    candidate, _, _ = run_task_with_baseline(
        baseline=baseline,
        task=task,
        model_name=args.model,
        seed=args.seed,
        simulator_mode=args.simulator_mode,
    )
    output_path = args.output or (
        DEFAULT_RESULTS_ROOT / "examples" / f"{task['task_id']}__{candidate['baseline_name']}__candidate.json"
    )
    dump_json(candidate, output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
