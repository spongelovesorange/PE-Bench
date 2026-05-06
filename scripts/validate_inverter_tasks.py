from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.tasks.inverter_schema import iter_inverter_task_files, validate_inverter_task_file
from pebench.utils.paths import DEFAULT_INVERTER_TASK_DIR


def main() -> int:
    failures: list[str] = []
    task_files = iter_inverter_task_files(DEFAULT_INVERTER_TASK_DIR)
    for task_file in task_files:
        errors = validate_inverter_task_file(task_file)
        if errors:
            failures.append(f"{task_file.name}: {errors}")
    if failures:
        print("Three-phase inverter task validation failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"Validated {len(task_files)} three-phase inverter tasks successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
