from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.tasks.schema import count_by_difficulty, iter_task_files, validate_task_file
from pebench.utils.paths import DEFAULT_FLYBACK_TASK_DIR


def main() -> int:
    task_files = iter_task_files(DEFAULT_FLYBACK_TASK_DIR)
    all_errors: dict[str, list[str]] = {}
    tasks = []
    for task_file in task_files:
        errors = validate_task_file(task_file)
        if errors:
            all_errors[str(task_file)] = errors
        else:
            from pebench.tasks.schema import load_task

            tasks.append(load_task(task_file))

    if all_errors:
        for path, errors in all_errors.items():
            print(path)
            for error in errors:
                print(f"  - {error}")
        return 1

    distribution = count_by_difficulty(tasks)
    split_distribution: dict[str, int] = {}
    for task in tasks:
        split = str(task["benchmark_meta"]["split"])
        split_distribution[split] = split_distribution.get(split, 0) + 1
    print(f"Validated {len(task_files)} Flyback tasks successfully.")
    print(f"Difficulty distribution: {dict(sorted(distribution.items()))}")
    print(f"Split distribution: {dict(sorted(split_distribution.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
