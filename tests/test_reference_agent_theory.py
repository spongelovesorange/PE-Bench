from __future__ import annotations

from functools import lru_cache

import pytest

from pebench.adapters.registry import get_baseline
from pebench.tasks.schema import filter_tasks, load_tasks, sort_tasks
from pebench.utils.paths import DEFAULT_TASK_DIR


def _load_easy_tasks() -> dict[str, dict[str, object]]:
    tasks = sort_tasks(
        filter_tasks(
            load_tasks(DEFAULT_TASK_DIR),
            track="autonomous_flyback_design",
            difficulty_tiers={"easy"},
        )
    )
    return {task["task_id"]: task for task in tasks}


@lru_cache(maxsize=1)
def _easy_task_candidates() -> dict[str, dict[str, object]]:
    baseline = get_baseline("reference_agent")
    tasks = _load_easy_tasks()
    return {
        task_id: baseline.generate(
            task=task,
            model_name="gpt-4.1-mini",
            seed=1,
            simulator_mode="stub",
        )
        for task_id, task in tasks.items()
    }


@pytest.mark.parametrize("task_id", sorted(_load_easy_tasks()))
def test_easy_task_theory_repairs_stay_within_basic_constraints(task_id: str) -> None:
    task = _load_easy_tasks()[task_id]
    candidate = _easy_task_candidates()[task_id]
    theory = candidate["theoretical_design"]
    claims = candidate["final_claimed_metrics"]
    constraints = task["structured_spec"]["constraints"]
    integration = candidate["metadata"]["reference_agent_integration"]

    assert "enabled" in integration
    assert theory["duty_cycle_max"] <= float(constraints["max_duty_cycle"])
    assert theory["primary_peak_current_a"] <= float(constraints["max_primary_peak_current_a"])
    assert claims["diode_reverse_voltage_v"] <= 1.05 * float(constraints["max_diode_reverse_voltage_v"])

    if task["structured_spec"]["input_range_volts"]["domain"] == "ac":
        assert theory["magnetizing_inductance_uh"] < 1200.0
        assert theory["primary_peak_current_a"] >= 0.7
