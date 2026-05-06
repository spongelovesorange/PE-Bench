from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from pebench.utils.io import load_yaml
from pebench.utils.paths import DEFAULT_INVERTER_CATALOG_PATH


INVERTER_REQUIRED_FIELDS = {
    "schema_version",
    "task_id",
    "topology",
    "difficulty_tier",
    "natural_language_spec",
    "benchmark_meta",
    "structured_spec",
    "evaluation_rubric",
    "closure_gates",
    "reference_design",
    "known_failure_modes",
}
INVERTER_STRUCTURED_SPEC_FIELDS = {
    "dc_link_voltage_v",
    "output",
    "switching_frequency_khz",
    "targets",
    "constraints",
    "preferences",
    "component_catalog_version",
}
INVERTER_REFERENCE_FIELDS = {
    "topology",
    "dc_link_voltage_v",
    "modulation_index",
    "switching_frequency_khz",
    "phase_current_rms_a",
    "selected_components",
    "expected_metrics",
    "cost_proxy_usd",
}
INVERTER_COMPONENT_SLOTS = {
    "controller": "controllers",
    "power_module": "power_modules",
    "gate_driver": "gate_drivers",
    "dc_link_capacitor": "dc_link_capacitors",
    "current_sensor": "current_sensors",
    "emi_filter": "emi_filters",
}
ALLOWED_INVERTER_TOPOLOGIES = {"three_phase_inverter"}
ALLOWED_INVERTER_TRACKS = {"three_phase_inverter_design"}
ALLOWED_INVERTER_SPLITS = {"extension"}
ALLOWED_INVERTER_DIFFICULTY_TIERS = {"easy", "medium", "hard", "stress"}
REQUIRED_CLOSURE_GATES = {
    "schema_closure",
    "dc_ac_theory_closure",
    "component_grounding",
    "stress_margin",
    "claim_consistency",
}
INVERTER_RUBRIC_NAMES = {
    "spec_grounding",
    "dc_ac_theory",
    "component_grounding",
    "efficiency_target",
    "quality_target",
    "stress_margin",
    "claim_consistency",
}


def iter_inverter_task_files(task_dir: str | Path) -> list[Path]:
    return sorted(Path(task_dir).glob("*.yaml"))


def load_inverter_task(path: str | Path) -> dict[str, Any]:
    return load_yaml(path)


def load_inverter_tasks(task_dir: str | Path) -> list[dict[str, Any]]:
    return [load_inverter_task(path) for path in iter_inverter_task_files(task_dir)]


def count_by_difficulty(tasks: list[dict[str, Any]]) -> Counter[str]:
    return Counter(str(task["difficulty_tier"]) for task in tasks)


def _catalog_index(catalog_path: str | Path = DEFAULT_INVERTER_CATALOG_PATH) -> dict[str, set[str]]:
    catalog = load_yaml(catalog_path)
    index: dict[str, set[str]] = {}
    for category, items in catalog.items():
        if category == "version":
            continue
        index[category] = {str(item["part_id"]) for item in items}
    return index


def validate_inverter_task_dict(
    task: dict[str, Any],
    *,
    catalog_path: str | Path = DEFAULT_INVERTER_CATALOG_PATH,
) -> list[str]:
    errors: list[str] = []
    missing = INVERTER_REQUIRED_FIELDS - task.keys()
    if missing:
        errors.append(f"Missing top-level fields: {sorted(missing)}")
        return errors

    topology = str(task.get("topology") or "")
    if topology not in ALLOWED_INVERTER_TOPOLOGIES:
        errors.append(f"Invalid topology '{topology}'. Allowed: {sorted(ALLOWED_INVERTER_TOPOLOGIES)}")

    if task.get("difficulty_tier") not in ALLOWED_INVERTER_DIFFICULTY_TIERS:
        errors.append(
            f"Invalid difficulty_tier '{task.get('difficulty_tier')}'. "
            f"Allowed: {sorted(ALLOWED_INVERTER_DIFFICULTY_TIERS)}"
        )

    benchmark_meta = task.get("benchmark_meta")
    if not isinstance(benchmark_meta, dict):
        errors.append("benchmark_meta must be a mapping")
    else:
        if benchmark_meta.get("track") not in ALLOWED_INVERTER_TRACKS:
            errors.append(
                f"Invalid benchmark_meta.track '{benchmark_meta.get('track')}'. "
                f"Allowed: {sorted(ALLOWED_INVERTER_TRACKS)}"
            )
        if benchmark_meta.get("split") not in ALLOWED_INVERTER_SPLITS:
            errors.append(
                f"Invalid benchmark_meta.split '{benchmark_meta.get('split')}'. "
                f"Allowed: {sorted(ALLOWED_INVERTER_SPLITS)}"
            )
        if not str(benchmark_meta.get("task_family") or "").strip():
            errors.append("benchmark_meta.task_family must be a non-empty string")
        if not str(benchmark_meta.get("source") or "").strip():
            errors.append("benchmark_meta.source must be a non-empty string")

    structured = task.get("structured_spec")
    if not isinstance(structured, dict):
        errors.append("structured_spec must be a mapping")
    else:
        missing_structured = INVERTER_STRUCTURED_SPEC_FIELDS - structured.keys()
        if missing_structured:
            errors.append(f"Missing structured_spec fields: {sorted(missing_structured)}")
        output = structured.get("output", {})
        if isinstance(output, dict):
            voltage = float(output.get("line_line_rms_v", 0.0) or 0.0)
            power = float(output.get("power_w", 0.0) or 0.0)
            if voltage <= 0.0 or power <= 0.0:
                errors.append("structured_spec.output line-line voltage and power must be positive")
        dc_link = structured.get("dc_link_voltage_v", {})
        if isinstance(dc_link, dict):
            if float(dc_link.get("min", 0.0) or 0.0) <= 0.0 or float(dc_link.get("max", 0.0) or 0.0) <= 0.0:
                errors.append("structured_spec.dc_link_voltage_v min/max must be positive")

    rubric = task.get("evaluation_rubric")
    if not isinstance(rubric, list) or not rubric:
        errors.append("evaluation_rubric must be a non-empty list")
    else:
        names = set()
        total = 0.0
        for item in rubric:
            if not isinstance(item, dict):
                errors.append("evaluation_rubric entries must be mappings")
                continue
            names.add(str(item.get("name")))
            total += float(item.get("weight", 0.0) or 0.0)
        if names != INVERTER_RUBRIC_NAMES:
            errors.append(f"Rubric names must match PE-Bench inverter set: {sorted(INVERTER_RUBRIC_NAMES)}")
        if round(total, 3) != 100.0:
            errors.append(f"Rubric weights must sum to 100. Got {total}.")

    closure_gates = set(task.get("closure_gates") or [])
    missing_gates = REQUIRED_CLOSURE_GATES - closure_gates
    if missing_gates:
        errors.append(f"Missing closure gates: {sorted(missing_gates)}")

    reference = task.get("reference_design")
    if not isinstance(reference, dict):
        errors.append("reference_design must be a mapping")
    else:
        missing_reference = INVERTER_REFERENCE_FIELDS - reference.keys()
        if missing_reference:
            errors.append(f"Missing reference_design fields: {sorted(missing_reference)}")
        if reference.get("topology") != topology:
            errors.append("reference_design.topology must match task topology")
        modulation_index = float(reference.get("modulation_index", 0.0) or 0.0)
        if not 0.05 <= modulation_index <= 1.0:
            errors.append("reference_design.modulation_index must be in [0.05, 1.0]")
        selected = reference.get("selected_components", {})
        if isinstance(selected, dict):
            catalog = _catalog_index(catalog_path)
            for slot, category in INVERTER_COMPONENT_SLOTS.items():
                part_id = selected.get(slot)
                if not part_id:
                    errors.append(f"Missing selected component slot '{slot}'")
                elif str(part_id) not in catalog.get(category, set()):
                    errors.append(f"Selected component '{part_id}' for '{slot}' is absent from {category}")
        expected = reference.get("expected_metrics", {})
        constraints = (structured or {}).get("constraints", {}) if isinstance(structured, dict) else {}
        targets = (structured or {}).get("targets", {}) if isinstance(structured, dict) else {}
        if isinstance(expected, dict) and isinstance(constraints, dict):
            if float(expected.get("efficiency_percent", 0.0) or 0.0) < float(
                targets.get("efficiency_percent", 0.0) or 0.0
            ):
                errors.append("reference efficiency must satisfy target efficiency")
            if float(expected.get("thd_percent", 0.0) or 0.0) > float(targets.get("thd_percent", 0.0) or 0.0):
                errors.append("reference THD must satisfy target THD")
            if float(expected.get("device_stress_v", 0.0) or 0.0) > float(
                constraints.get("max_device_voltage_v", 0.0) or 0.0
            ):
                errors.append("reference device stress exceeds task constraint")
            if float(expected.get("phase_current_rms_a", 0.0) or 0.0) > float(
                constraints.get("max_phase_current_rms_a", 0.0) or 0.0
            ):
                errors.append("reference phase current exceeds task constraint")

    if not isinstance(task.get("known_failure_modes"), list) or not task["known_failure_modes"]:
        errors.append("known_failure_modes must be a non-empty list")

    return errors


def validate_inverter_task_file(
    path: str | Path,
    *,
    catalog_path: str | Path = DEFAULT_INVERTER_CATALOG_PATH,
) -> list[str]:
    return validate_inverter_task_dict(load_inverter_task(path), catalog_path=catalog_path)
