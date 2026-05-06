from __future__ import annotations

from pebench.tasks.schema import count_by_difficulty, iter_task_files, load_task, validate_task_file
from pebench.utils.paths import DEFAULT_TASK_DIR


def test_all_tasks_validate() -> None:
    task_files = iter_task_files(DEFAULT_TASK_DIR)
    assert len(task_files) == 30
    for task_file in task_files:
        assert validate_task_file(task_file) == []


def test_difficulty_distribution_matches_v1_scope() -> None:
    tasks = [load_task(path) for path in iter_task_files(DEFAULT_TASK_DIR)]
    assert count_by_difficulty(tasks) == {
        "easy": 6,
        "medium": 10,
        "hard": 6,
        "boundary": 4,
        "stress": 4,
    }


def test_all_tasks_are_on_track_a_public_dev() -> None:
    tasks = [load_task(path) for path in iter_task_files(DEFAULT_TASK_DIR)]
    assert {task["benchmark_meta"]["track"] for task in tasks} == {"autonomous_flyback_design"}
    split_counts: dict[str, int] = {}
    for task in tasks:
        split = task["benchmark_meta"]["split"]
        split_counts[split] = split_counts.get(split, 0) + 1
    assert split_counts == {"public_dev": 24, "private_holdout": 6}
