from __future__ import annotations

from functools import lru_cache

import pytest

from pebench.adapters.registry import get_baseline
from pebench.tasks.schema import filter_tasks, load_tasks, sort_tasks
from pebench.utils.io import load_yaml
from pebench.utils.paths import DEFAULT_CATALOG_PATH
from pebench.utils.paths import DEFAULT_TASK_DIR


GROUNDING_GOLDEN_TASK_EXPECTATIONS = {
    "easy_acdc_12v1a": {
        "controller": "NCP1342",
        "output_capacitor": "EEU-FR1V471",
        "core": "EFD25_3C95",
    },
    "easy_acdc_18v0p6a": {
        "controller": "NCP1342",
        "output_capacitor": "EEU-FR1V471",
        "core": "EFD25_3C95",
    },
    "easy_acdc_5v1a": {
        "controller": "NCP1342",
        "output_capacitor": "EEU-FR1V471",
        "core": "EFD25_3C95",
    },
    "easy_acdc_9v0p7a": {
        "controller": "NCP1342",
        "output_capacitor": "EEU-FR1E221",
        "core": "EFD25_3C95",
    },
    "easy_dcdc_12v0p5a": {
        "controller": "NCP1342",
        "output_capacitor": "EEU-FR1V471",
        "core": "EFD25_3C95",
    },
    "easy_dcdc_15v0p8a": {
        "controller": "NCP1342",
        "output_capacitor": "EEU-FR1V471",
        "core": "EFD25_3C95",
    },
    "easy_dcdc_24v0p5a": {
        "controller": "NCP1342",
        "output_capacitor": "EEU-FR1V471",
        "core": "EFD25_3C95",
    },
    "easy_dcdc_5v2a": {
        "controller": "UCC28740",
        "output_capacitor": "EEU-FR1V471",
        "core": "EFD25_3C95",
    },
}


def _load_grounding_tasks() -> dict[str, dict[str, object]]:
    all_tasks = {
        task["task_id"]: task
        for task in sort_tasks(
            filter_tasks(
                load_tasks(DEFAULT_TASK_DIR),
                track="autonomous_flyback_design",
            )
        )
    }
    return {task_id: all_tasks[task_id] for task_id in GROUNDING_GOLDEN_TASK_EXPECTATIONS}


@lru_cache(maxsize=1)
def _easy_task_candidates() -> dict[str, dict[str, object]]:
    baseline = get_baseline("reference_agent")
    tasks = _load_grounding_tasks()
    return {
        task_id: baseline.generate(
            task=task,
            model_name="gpt-4.1-mini",
            seed=1,
            simulator_mode="stub",
        )
        for task_id, task in tasks.items()
    }


@lru_cache(maxsize=1)
def _catalog_by_slot() -> dict[str, dict[str, dict[str, object]]]:
    catalog = load_yaml(DEFAULT_CATALOG_PATH)
    return {
        "controller": {item["part_id"]: item for item in catalog["controllers"]},
        "mosfet": {item["part_id"]: item for item in catalog["mosfets"]},
        "diode": {item["part_id"]: item for item in catalog["diodes"]},
        "output_capacitor": {item["part_id"]: item for item in catalog["output_capacitors"]},
        "core": {item["part_id"]: item for item in catalog["cores"]},
    }


@pytest.mark.parametrize("task_id", sorted(GROUNDING_GOLDEN_TASK_EXPECTATIONS))
def test_easy_task_grounding_recovers_expected_slot_mapping(task_id: str) -> None:
    candidate = _easy_task_candidates()[task_id]
    bom_lookup = {item["category"]: item for item in candidate["bom"]}
    catalog = _catalog_by_slot()
    assert set(bom_lookup) == {"controller", "mosfet", "diode", "output_capacitor", "core"}
    assert "reference_agent_integration" in candidate["metadata"]

    for slot, item in bom_lookup.items():
        assert item["part_id"] in catalog[slot]


@pytest.mark.parametrize("task_id", sorted(GROUNDING_GOLDEN_TASK_EXPECTATIONS))
def test_easy_task_grounding_keeps_slot_level_safety_margins(task_id: str) -> None:
    task = _load_grounding_tasks()[task_id]
    candidate = _easy_task_candidates()[task_id]
    bom_lookup = {item["category"]: item for item in candidate["bom"]}
    claims = candidate["final_claimed_metrics"]
    theory = candidate["theoretical_design"]
    catalog = _catalog_by_slot()

    mosfet = catalog["mosfet"][bom_lookup["mosfet"]["part_id"]]
    diode = catalog["diode"][bom_lookup["diode"]["part_id"]]
    output_cap = catalog["output_capacitor"][bom_lookup["output_capacitor"]["part_id"]]

    assert float(mosfet["voltage_rating_v"]) >= 1.2 * float(claims["mosfet_voltage_stress_v"])
    assert float(mosfet["current_rating_a"]) >= 1.5 * float(theory["primary_peak_current_a"])
    assert float(diode["voltage_rating_v"]) >= 1.2 * float(claims["diode_reverse_voltage_v"])
    assert float(diode["current_rating_a"]) >= 1.5 * float(task["structured_spec"]["output"]["current_a"])
    assert float(output_cap["voltage_rating_v"]) >= 1.25 * float(task["structured_spec"]["output"]["voltage_v"])
