from __future__ import annotations

import time
from typing import Any

from pebench.evaluator.result_schema import validate_result_dict
from pebench.tasks.inverter_schema import validate_inverter_task_dict
from pebench.tasks.schema import validate_task_dict
from pebench.tasks.topology_full import validate_scout_task_dict


def is_reference_feasibility_candidate(candidate: dict[str, Any]) -> bool:
    return candidate.get("metadata", {}).get("candidate_kind") == "reference_feasibility_anchor"


def evaluate_reference_feasibility(task: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()
    topology = str(task.get("topology") or task.get("reference_design", {}).get("topology") or "flyback")
    if topology in {"buck", "boost", "buck_boost"}:
        task_errors = validate_scout_task_dict(task)
        violations, metrics = _topology_full_reference_checks(task)
    elif topology == "three_phase_inverter":
        task_errors = validate_inverter_task_dict(task)
        violations, metrics = _inverter_reference_checks(task)
    else:
        task_errors = validate_task_dict(task)
        violations, metrics = _flyback_reference_checks(task)

    for error in task_errors:
        violations.append(
            {
                "constraint": "task_schema",
                "observed": error,
                "limit": "valid task schema",
                "severity": "hard",
                "group": "schema",
            }
        )

    pass_fail = not violations
    result = {
        "task_id": task.get("task_id"),
        "difficulty_tier": task.get("difficulty_tier"),
        "baseline_name": candidate.get("baseline_name", "reference_design"),
        "model_name": candidate.get("model_name", "reference-design"),
        "seed": int(candidate.get("seed", 0) or 0),
        "pass_fail": pass_fail,
        "score_total": 100.0 if pass_fail else 0.0,
        "sub_scores": {
            "reference_schema": 100.0 if pass_fail else 0.0,
        },
        "constraint_violations": violations,
        "simulation_metrics": metrics,
        "failure_tags": _reference_failure_tags(violations),
        "failure_groups": sorted({str(item.get("group", "reference")) for item in violations}),
        "aggregate_scores": {
            "reference_feasibility": 1.0 if pass_fail else 0.0,
        },
        "execution_log": [
            {
                "stage": "reference_feasibility",
                "status": "pass" if pass_fail else "fail",
                "note": "Reference designs are feasibility anchors and are not exact-match gold answers.",
            }
        ],
        "runtime_stats": {
            "backend_requested": "reference_feasibility",
            "backend_used": "reference_feasibility",
            "fallback_used": False,
            "fallback_reason": None,
            "simulator_version": "pebench-reference-feasibility-v1",
            "runtime_seconds": round(time.perf_counter() - start, 6),
        },
    }
    schema_errors = validate_result_dict(result)
    if schema_errors:
        raise RuntimeError(f"Reference-feasibility result violated result schema: {schema_errors}")
    return result


def _flyback_reference_checks(task: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spec = task["structured_spec"]
    constraints = spec["constraints"]
    reference = task["reference_design"]
    metrics = dict(reference["expected_metrics"])
    violations: list[dict[str, Any]] = []

    _check(reference.get("topology") == "flyback", violations, "topology", reference.get("topology"), "flyback", "hard", "topology")
    _check(
        float(reference["duty_cycle_max"]) <= float(constraints["max_duty_cycle"]),
        violations,
        "max_duty_cycle",
        reference["duty_cycle_max"],
        constraints["max_duty_cycle"],
        "hard",
        "theory",
    )
    _check(
        float(reference["primary_peak_current_a"]) <= float(constraints["max_primary_peak_current_a"]),
        violations,
        "max_primary_peak_current_a",
        reference["primary_peak_current_a"],
        constraints["max_primary_peak_current_a"],
        "hard",
        "theory",
    )
    freq = spec["switching_frequency_khz"]
    _check(
        float(freq["min"]) <= float(reference["switching_frequency_khz"]) <= float(freq["max"]),
        violations,
        "switching_frequency_khz",
        reference["switching_frequency_khz"],
        [freq["min"], freq["max"]],
        "medium",
        "theory",
    )
    _check(
        float(metrics["efficiency_percent"]) >= float(spec["targets"]["efficiency_percent"]),
        violations,
        "efficiency_target",
        metrics["efficiency_percent"],
        spec["targets"]["efficiency_percent"],
        "medium",
        "performance",
    )
    _check(
        float(metrics["ripple_mv"]) <= float(spec["targets"]["ripple_mv"]),
        violations,
        "ripple_target",
        metrics["ripple_mv"],
        spec["targets"]["ripple_mv"],
        "medium",
        "performance",
    )
    for metric_key, limit_key in [
        ("mosfet_voltage_stress_v", "max_mosfet_voltage_v"),
        ("diode_reverse_voltage_v", "max_diode_reverse_voltage_v"),
        ("flux_density_mt", "max_flux_density_mt"),
    ]:
        _check(
            float(metrics[metric_key]) <= float(constraints[limit_key]),
            violations,
            metric_key,
            metrics[metric_key],
            constraints[limit_key],
            "hard",
            "stress",
        )
    _check(bool(metrics.get("startup_success")), violations, "startup_success", metrics.get("startup_success"), True, "hard", "simulation")
    metrics["estimated_cost_usd"] = reference.get("cost_proxy_usd")
    return violations, metrics


def _topology_full_reference_checks(task: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reference = task["reference_design"]
    metrics = dict(reference["expected_metrics"])
    metrics["estimated_cost_usd"] = reference.get("cost_proxy_usd")
    return [], metrics


def _inverter_reference_checks(task: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spec = task["structured_spec"]
    constraints = spec["constraints"]
    targets = spec["targets"]
    reference = task["reference_design"]
    metrics = dict(reference["expected_metrics"])
    violations: list[dict[str, Any]] = []

    _check(
        reference.get("topology") == "three_phase_inverter",
        violations,
        "topology",
        reference.get("topology"),
        "three_phase_inverter",
        "hard",
        "topology",
    )
    _check(
        float(spec["dc_link_voltage_v"]["min"])
        <= float(reference["dc_link_voltage_v"])
        <= float(spec["dc_link_voltage_v"]["max"]),
        violations,
        "dc_link_voltage_v",
        reference["dc_link_voltage_v"],
        [spec["dc_link_voltage_v"]["min"], spec["dc_link_voltage_v"]["max"]],
        "hard",
        "theory",
    )
    _check(
        float(reference["modulation_index"]) <= float(constraints["max_modulation_index"]),
        violations,
        "max_modulation_index",
        reference["modulation_index"],
        constraints["max_modulation_index"],
        "hard",
        "theory",
    )
    _check(
        float(metrics["efficiency_percent"]) >= float(targets["efficiency_percent"]),
        violations,
        "efficiency_target",
        metrics["efficiency_percent"],
        targets["efficiency_percent"],
        "medium",
        "performance",
    )
    _check(
        float(metrics["thd_percent"]) <= float(targets["thd_percent"]),
        violations,
        "thd_target",
        metrics["thd_percent"],
        targets["thd_percent"],
        "medium",
        "performance",
    )
    for metric_key, limit_key in [
        ("device_stress_v", "max_device_voltage_v"),
        ("phase_current_rms_a", "max_phase_current_rms_a"),
        ("dc_link_ripple_a", "max_dc_link_ripple_a"),
    ]:
        _check(
            float(metrics[metric_key]) <= float(constraints[limit_key]),
            violations,
            metric_key,
            metrics[metric_key],
            constraints[limit_key],
            "hard",
            "stress",
        )
    _check(bool(metrics.get("startup_success")), violations, "startup_success", metrics.get("startup_success"), True, "hard", "simulation")
    metrics["estimated_cost_usd"] = reference.get("cost_proxy_usd")
    return violations, metrics


def _check(
    condition: bool,
    violations: list[dict[str, Any]],
    constraint: str,
    observed: Any,
    limit: Any,
    severity: str,
    group: str,
) -> None:
    if condition:
        return
    violations.append(
        {
            "constraint": constraint,
            "observed": observed,
            "limit": limit,
            "severity": severity,
            "group": group,
        }
    )


def _reference_failure_tags(violations: list[dict[str, Any]]) -> list[str]:
    groups = {str(item.get("group", "")) for item in violations}
    tags: list[str] = []
    if "schema" in groups:
        tags.append("Spec Parsing Failure")
    if "topology" in groups:
        tags.append("Wrong Topology")
    if "theory" in groups:
        tags.append("Infeasible Theory Failure")
    if "component" in groups:
        tags.append("Invalid or Unsafe BOM")
    if "performance" in groups:
        tags.append("Efficiency/Ripple Target Miss")
    if "stress" in groups:
        tags.append("Stress Violation / Escalation Required")
    if "simulation" in groups:
        tags.append("Simulation Execution Failure")
    return tags
