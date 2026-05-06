from __future__ import annotations

from pebench.baselines.reference import build_reference_candidate
from pebench.evaluator.pebench import evaluate_pebench_candidate
from pebench.tasks.inverter_schema import count_by_difficulty, iter_inverter_task_files, load_inverter_task, validate_inverter_task_file
from pebench.utils.paths import DEFAULT_INVERTER_TASK_DIR


def test_inverter_tasks_validate() -> None:
    task_files = iter_inverter_task_files(DEFAULT_INVERTER_TASK_DIR)
    assert len(task_files) == 12
    for task_file in task_files:
        assert validate_inverter_task_file(task_file) == []


def test_inverter_distribution_matches_final_78_scope() -> None:
    tasks = [load_inverter_task(path) for path in iter_inverter_task_files(DEFAULT_INVERTER_TASK_DIR)]
    assert count_by_difficulty(tasks) == {
        "easy": 3,
        "medium": 4,
        "hard": 3,
        "stress": 2,
    }
    assert {task["benchmark_meta"]["split"] for task in tasks} == {"extension"}


def test_inverter_reference_feasibility_passes() -> None:
    for task_file in iter_inverter_task_files(DEFAULT_INVERTER_TASK_DIR):
        task = load_inverter_task(task_file)
        candidate = build_reference_candidate(task, simulator_mode="stub")
        result = evaluate_pebench_candidate(task, candidate, simulator_mode="stub")
        assert result["pass_fail"], (task["task_id"], result["constraint_violations"])
