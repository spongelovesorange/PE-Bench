from __future__ import annotations

from pebench.tasks.topology_full import (
    count_by_difficulty,
    count_by_topology,
    iter_scout_task_files,
    load_scout_task,
    validate_scout_task_file,
)
from pebench.utils.paths import DEFAULT_TOPOLOGY_SCOUT_TASK_DIR


def test_topology_full_tasks_validate() -> None:
    task_files = iter_scout_task_files(DEFAULT_TOPOLOGY_SCOUT_TASK_DIR)
    assert len(task_files) == 36
    for task_file in task_files:
        assert validate_scout_task_file(task_file) == []


def test_topology_full_distribution_matches_pe_bench_extension_scope() -> None:
    tasks = [load_scout_task(path) for path in iter_scout_task_files(DEFAULT_TOPOLOGY_SCOUT_TASK_DIR)]
    assert count_by_topology(tasks) == {"buck": 12, "boost": 12, "buck_boost": 12}
    assert count_by_difficulty(tasks) == {
        "easy": 12,
        "medium": 12,
        "hard": 6,
        "boundary": 3,
        "stress": 3,
    }
    assert {task["benchmark_meta"]["split"] for task in tasks} == {"public_dev"}
