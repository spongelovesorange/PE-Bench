from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_dataset_artifacts import validate_dataset_artifacts, write_dataset_artifacts
from scripts.build_paper_tables import validate_paper_tables, write_paper_tables
from scripts.validate_public_artifact import validate_public_artifact
from pebench.artifacts.release import validate_release_artifacts, write_release_artifacts
from pebench.baselines.reference import build_reference_candidate
from pebench.evaluator.pebench import evaluate_pebench_candidate
from pebench.tasks.inverter_schema import iter_inverter_task_files, load_inverter_task, validate_inverter_task_file
from pebench.tasks.schema import iter_task_files, load_task, validate_task_file
from pebench.tasks.topology_full import iter_scout_task_files, load_scout_task, validate_scout_task_file
from pebench.utils.paths import DEFAULT_FLYBACK_TASK_DIR, DEFAULT_INVERTER_TASK_DIR, DEFAULT_TOPOLOGY_FULL_TASK_DIR


def main() -> int:
    errors: list[str] = []

    errors.extend(_validate_bank("flyback", iter_task_files(DEFAULT_FLYBACK_TASK_DIR), validate_task_file))
    errors.extend(
        _validate_bank(
            "topology_full",
            iter_scout_task_files(DEFAULT_TOPOLOGY_FULL_TASK_DIR),
            validate_scout_task_file,
        )
    )
    errors.extend(
        _validate_bank(
            "three_phase_inverter",
            iter_inverter_task_files(DEFAULT_INVERTER_TASK_DIR),
            validate_inverter_task_file,
        )
    )
    if not errors:
        errors.extend(_reference_candidate_checks())

    if not errors:
        write_release_artifacts()
        errors.extend(validate_release_artifacts())

    if not errors:
        write_dataset_artifacts()
        errors.extend(validate_dataset_artifacts())

    if not errors:
        write_paper_tables()
        errors.extend(validate_paper_tables())

    if not errors:
        errors.extend(validate_public_artifact())

    if errors:
        print("PE-Bench reviewer smoke test failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("PE-Bench reviewer smoke test passed.")
    print("Validated task banks: 30 Flyback, 36 Topology Full, and 12 Three-Phase Inverter tasks.")
    print("Built and validated release artifacts, dataset/Croissant artifacts, reproduced paper-table artifacts, and public anonymization checks.")
    return 0


def _validate_bank(name: str, paths: list[Path], validator: object) -> list[str]:
    errors: list[str] = []
    for path in paths:
        task_errors = validator(path)  # type: ignore[operator]
        if task_errors:
            errors.append(f"{name} task {path.name}: {task_errors}")
    if not paths:
        errors.append(f"{name} task bank is empty")
    return errors


def _reference_candidate_checks() -> list[str]:
    tasks = []
    tasks.extend(load_task(path) for path in iter_task_files(DEFAULT_FLYBACK_TASK_DIR))
    tasks.extend(load_scout_task(path) for path in iter_scout_task_files(DEFAULT_TOPOLOGY_FULL_TASK_DIR))
    tasks.extend(load_inverter_task(path) for path in iter_inverter_task_files(DEFAULT_INVERTER_TASK_DIR))
    errors: list[str] = []
    for task in tasks:
        candidate = build_reference_candidate(task, simulator_mode="stub")
        result = evaluate_pebench_candidate(task, candidate, simulator_mode="stub")
        if not result.get("pass_fail"):
            errors.append(
                f"reference candidate failed for {task['task_id']}: "
                f"{result.get('failure_tags')} {result.get('constraint_violations')}"
            )
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
