from __future__ import annotations

from typing import Any


PEBENCH_TASK_REQUIRED_FIELDS = {
    "task_id",
    "topology",
    "difficulty_tier",
    "split",
    "input_voltage_range",
    "output_voltage",
    "output_power",
    "efficiency_target",
    "ripple_target",
    "isolation_required",
    "safety_margin",
    "component_constraints",
    "reference_design",
    "evaluation_requirements",
}


def validate_pebench_task_dict(task: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = PEBENCH_TASK_REQUIRED_FIELDS - task.keys()
    if missing:
        errors.append(f"Missing top-level fields: {sorted(missing)}")
        return errors

    if not isinstance(task.get("task_id"), str) or not task["task_id"].strip():
        errors.append("task_id must be a non-empty string")

    if not isinstance(task.get("topology"), str) or not task["topology"].strip():
        errors.append("topology must be a non-empty string")

    if not isinstance(task.get("difficulty_tier"), str) or not task["difficulty_tier"].strip():
        errors.append("difficulty_tier must be a non-empty string")

    if not isinstance(task.get("split"), str) or not task["split"].strip():
        errors.append("split must be a non-empty string")

    if not isinstance(task.get("input_voltage_range"), dict):
        errors.append("input_voltage_range must be a mapping")

    for key in ["output_voltage", "output_power", "efficiency_target", "ripple_target", "safety_margin"]:
        value = task.get(key)
        if not isinstance(value, (int, float)):
            errors.append(f"{key} must be numeric")

    if not isinstance(task.get("isolation_required"), bool):
        errors.append("isolation_required must be a bool")

    if not isinstance(task.get("component_constraints"), dict):
        errors.append("component_constraints must be a mapping")

    if not isinstance(task.get("reference_design"), dict):
        errors.append("reference_design must be a mapping")

    if not isinstance(task.get("evaluation_requirements"), dict):
        errors.append("evaluation_requirements must be a mapping")

    return errors


def normalize_pebench_task(task: dict[str, Any]) -> dict[str, Any]:
    if PEBENCH_TASK_REQUIRED_FIELDS.issubset(task.keys()):
        return dict(task)

    if "structured_spec" in task and "benchmark_meta" in task:
        return _normalize_flyback_task(task)

    if "structured_spec" in task and "topology" in task:
        if task.get("topology") == "three_phase_inverter":
            return _normalize_inverter_task(task)
        return _normalize_scout_task(task)

    raise ValueError("Unsupported task schema for normalization")


def _normalize_flyback_task(task: dict[str, Any]) -> dict[str, Any]:
    spec = task["structured_spec"]
    output = spec.get("output", {})
    targets = spec.get("targets", {})
    constraints = spec.get("constraints", {})
    return {
        "task_id": task["task_id"],
        "topology": str(task.get("reference_design", {}).get("topology", "flyback")),
        "difficulty_tier": task["difficulty_tier"],
        "split": task.get("benchmark_meta", {}).get("split", "unknown"),
        "input_voltage_range": dict(spec.get("input_range_volts", {})),
        "output_voltage": float(output.get("voltage_v", 0.0)),
        "output_power": float(output.get("power_w", 0.0)),
        "efficiency_target": float(targets.get("efficiency_percent", 0.0)),
        "ripple_target": float(targets.get("ripple_mv", 0.0)),
        "isolation_required": True,
        "safety_margin": float(constraints.get("max_duty_cycle", 0.0)),
        "component_constraints": dict(spec.get("constraints", {})),
        "reference_design": dict(task.get("reference_design", {})),
        "evaluation_requirements": {
            "evaluation_rubric": list(task.get("evaluation_rubric", [])),
            "known_failure_modes": list(task.get("known_failure_modes", [])),
        },
    }


def _normalize_scout_task(task: dict[str, Any]) -> dict[str, Any]:
    spec = task["structured_spec"]
    output = spec.get("output", {})
    targets = spec.get("targets", {})
    constraints = spec.get("constraints", {})
    return {
        "task_id": task["task_id"],
        "topology": str(task.get("topology", "")),
        "difficulty_tier": task["difficulty_tier"],
        "split": task.get("benchmark_meta", {}).get("split", "unknown"),
        "input_voltage_range": dict(spec.get("input_range_volts", {})),
        "output_voltage": float(output.get("voltage_v", 0.0)),
        "output_power": float(output.get("power_w", 0.0)),
        "efficiency_target": float(targets.get("efficiency_percent", 0.0)),
        "ripple_target": float(targets.get("ripple_mv", 0.0)),
        "isolation_required": False,
        "safety_margin": float(constraints.get("max_duty_cycle", 0.0)),
        "component_constraints": dict(spec.get("constraints", {})),
        "reference_design": dict(task.get("reference_design", {})),
        "evaluation_requirements": {
            "evaluation_rubric": list(task.get("evaluation_rubric", [])),
            "closure_gates": list(task.get("closure_gates", [])),
            "known_failure_modes": list(task.get("known_failure_modes", [])),
        },
    }


def _normalize_inverter_task(task: dict[str, Any]) -> dict[str, Any]:
    spec = task["structured_spec"]
    output = spec.get("output", {})
    targets = spec.get("targets", {})
    constraints = spec.get("constraints", {})
    return {
        "task_id": task["task_id"],
        "topology": str(task.get("topology", "")),
        "difficulty_tier": task["difficulty_tier"],
        "split": task.get("benchmark_meta", {}).get("split", "unknown"),
        "input_voltage_range": dict(spec.get("dc_link_voltage_v", {})),
        "output_voltage": float(output.get("line_line_rms_v", 0.0)),
        "output_power": float(output.get("power_w", 0.0)),
        "efficiency_target": float(targets.get("efficiency_percent", 0.0)),
        "ripple_target": float(targets.get("thd_percent", 0.0)),
        "isolation_required": False,
        "safety_margin": float(constraints.get("max_modulation_index", 0.0)),
        "component_constraints": dict(spec.get("constraints", {})),
        "reference_design": dict(task.get("reference_design", {})),
        "evaluation_requirements": {
            "evaluation_rubric": list(task.get("evaluation_rubric", [])),
            "closure_gates": list(task.get("closure_gates", [])),
            "known_failure_modes": list(task.get("known_failure_modes", [])),
        },
    }
