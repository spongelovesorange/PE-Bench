from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.baselines.reference import build_reference_candidate
from pebench.evaluator.pebench import evaluate_pebench_candidate
from pebench.tasks.inverter_schema import iter_inverter_task_files, load_inverter_task
from pebench.tasks.schema import iter_task_files, load_task
from pebench.tasks.topology_full import iter_scout_task_files, load_scout_task
from pebench.utils.paths import DEFAULT_FLYBACK_TASK_DIR, DEFAULT_INVERTER_TASK_DIR, DEFAULT_TOPOLOGY_FULL_TASK_DIR


def main() -> int:
    tasks = []
    tasks.extend(load_task(path) for path in iter_task_files(DEFAULT_FLYBACK_TASK_DIR))
    tasks.extend(load_scout_task(path) for path in iter_scout_task_files(DEFAULT_TOPOLOGY_FULL_TASK_DIR))
    tasks.extend(load_inverter_task(path) for path in iter_inverter_task_files(DEFAULT_INVERTER_TASK_DIR))

    failures: list[str] = []
    for task in tasks:
        candidate = build_reference_candidate(task, simulator_mode="stub")
        result = evaluate_pebench_candidate(task, candidate, simulator_mode="stub")
        if not result.get("pass_fail"):
            failures.append(
                f"{task['task_id']}: {result.get('failure_tags')} {result.get('constraint_violations')}"
            )

    if failures:
        print("Reference-design validation failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"Validated {len(tasks)} feasible reference designs successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
