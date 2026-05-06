from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.tasks.topology_full import (
    count_by_difficulty,
    count_by_topology,
    iter_scout_task_files,
    load_scout_task,
    validate_scout_task_file,
)
from pebench.utils.paths import DEFAULT_TOPOLOGY_FULL_TASK_DIR


def main() -> int:
    task_files = iter_scout_task_files(DEFAULT_TOPOLOGY_FULL_TASK_DIR)
    all_errors: dict[str, list[str]] = {}
    tasks = []
    for task_file in task_files:
        errors = validate_scout_task_file(task_file)
        if errors:
            all_errors[str(task_file)] = errors
        else:
            tasks.append(load_scout_task(task_file))

    if all_errors:
        for path, errors in all_errors.items():
            print(path)
            for error in errors:
                print(f"  - {error}")
        return 1

    print(f"Validated {len(task_files)} Topology Full tasks successfully.")
    print(f"Topology distribution: {dict(sorted(count_by_topology(tasks).items()))}")
    print(f"Difficulty distribution: {dict(sorted(count_by_difficulty(tasks).items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
