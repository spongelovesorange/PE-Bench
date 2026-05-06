from __future__ import annotations

import time
from typing import Any

from pebench.evaluator.result_schema import validate_result_dict
from pebench.tasks.inverter_schema import INVERTER_COMPONENT_SLOTS, validate_inverter_task_dict
from pebench.utils.io import load_yaml
from pebench.utils.paths import DEFAULT_INVERTER_CATALOG_PATH


INVERTER_FAILURE_TAGS = [
    "Spec Parsing Failure",
    "Wrong Topology",
    "Infeasible Theory Failure",
    "Invalid or Unsafe BOM",
    "Efficiency Miss",
    "Current Quality Miss",
    "Stress Violation / Escalation Required",
    "Optimistic but Unrealistic Claim",
]
REQUIRED_CANDIDATE_FIELDS = {
    "task_id",
    "baseline_name",
    "model_name",
    "seed",
    "parsed_spec",
    "topology_decision",
    "theoretical_design",
    "bom",
    "simulation_config",
    "final_claimed_metrics",
    "uncertainty_or_escalation_flag",
    "metadata",
}
REQUIRED_THEORY_FIELDS = {
    "topology",
    "dc_link_voltage_v",
    "modulation_index",
    "switching_frequency_khz",
    "phase_current_rms_a",
}
REQUIRED_CLAIM_FIELDS = {
    "efficiency_percent",
    "thd_percent",
    "dc_link_ripple_a",
    "device_stress_v",
    "phase_current_rms_a",
    "estimated_cost_usd",
}


def validate_inverter_candidate_dict(candidate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_CANDIDATE_FIELDS - candidate.keys()
    if missing:
        errors.append(f"Missing candidate fields: {sorted(missing)}")
        return errors
    if not isinstance(candidate["parsed_spec"], dict):
        errors.append("parsed_spec must be a mapping")
    if not isinstance(candidate["topology_decision"], dict):
        errors.append("topology_decision must be a mapping")
    theory = candidate["theoretical_design"]
    if not isinstance(theory, dict):
        errors.append("theoretical_design must be a mapping")
    else:
        missing_theory = REQUIRED_THEORY_FIELDS - theory.keys()
        if missing_theory:
            errors.append(f"Missing theoretical_design fields: {sorted(missing_theory)}")
    if not isinstance(candidate["bom"], list) or not candidate["bom"]:
        errors.append("bom must be a non-empty list")
    claims = candidate["final_claimed_metrics"]
    if not isinstance(claims, dict):
        errors.append("final_claimed_metrics must be a mapping")
    else:
        missing_claims = REQUIRED_CLAIM_FIELDS - claims.keys()
        if missing_claims:
            errors.append(f"Missing final_claimed_metrics fields: {sorted(missing_claims)}")
    if not isinstance(candidate["simulation_config"], dict):
        errors.append("simulation_config must be a mapping")
    if not isinstance(candidate["uncertainty_or_escalation_flag"], dict):
        errors.append("uncertainty_or_escalation_flag must be a mapping")
    if not isinstance(candidate["metadata"], dict):
        errors.append("metadata must be a mapping")
    return errors


def evaluate_inverter_candidate(
    task: dict[str, Any],
    candidate: dict[str, Any],
    *,
    catalog_path: str | None = None,
) -> dict[str, Any]:
    start = time.perf_counter()
    constraint_violations: list[dict[str, Any]] = []

    for error in validate_inverter_task_dict(task):
        constraint_violations.append(
            {"constraint": "task_schema", "observed": error, "limit": "valid task schema", "severity": "hard"}
        )
    for error in validate_inverter_candidate_dict(candidate):
        constraint_violations.append(
            {"constraint": "candidate_schema", "observed": error, "limit": "valid candidate schema", "severity": "hard"}
        )

    if constraint_violations:
        return _result(task, candidate, start, constraint_violations, {}, total_cost=0.0)

    metrics = _metrics_from_claims(task, candidate)
    theory_score, theory_violations = _evaluate_theory(task, candidate)
    bom_score, bom_violations, total_cost = _evaluate_bom(
        task,
        candidate,
        _catalog_by_category(catalog_path),
        metrics,
    )
    performance_score, performance_violations = _evaluate_performance(task, metrics)
    claim_score, claim_violations = _evaluate_claims(task, candidate, metrics)
    constraint_violations.extend(theory_violations)
    constraint_violations.extend(bom_violations)
    constraint_violations.extend(performance_violations)
    constraint_violations.extend(claim_violations)

    if total_cost:
        metrics["estimated_cost_usd"] = round(total_cost, 3)
    metrics["startup_success"] = True

    sub_scores = {
        "spec_grounding": 10.0,
        "dc_ac_theory": round(18.0 * theory_score, 4),
        "component_grounding": round(18.0 * bom_score, 4),
        "efficiency_target": round(14.0 * performance_score["efficiency"], 4),
        "quality_target": round(14.0 * performance_score["quality"], 4),
        "stress_margin": round(16.0 * performance_score["stress"], 4),
        "claim_consistency": round(10.0 * claim_score, 4),
    }
    result = _result(task, candidate, start, constraint_violations, metrics, total_cost=total_cost, sub_scores=sub_scores)
    schema_errors = validate_result_dict(result)
    if schema_errors:
        raise RuntimeError(f"Inverter evaluator result violated result schema: {schema_errors}")
    return result


def _catalog_by_category(catalog_path: str | None) -> dict[str, dict[str, dict[str, Any]]]:
    catalog = load_yaml(catalog_path or DEFAULT_INVERTER_CATALOG_PATH)
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for category, rows in catalog.items():
        if category == "version":
            continue
        result[category] = {str(row["part_id"]): dict(row) for row in rows}
    return result


def _bom_lookup(candidate: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for item in candidate.get("bom", []):
        category = str(item.get("category") or "").strip()
        part_id = str(item.get("part_id") or "").strip()
        if category and part_id:
            lookup[category] = part_id
    return lookup


def _metrics_from_claims(task: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    claims = candidate["final_claimed_metrics"]
    theory = candidate["theoretical_design"]
    metrics = {
        "observed_efficiency_percent": float(claims["efficiency_percent"]),
        "observed_thd_percent": float(claims["thd_percent"]),
        "observed_dc_link_ripple_a": float(claims["dc_link_ripple_a"]),
        "device_stress_v": float(claims["device_stress_v"]),
        "phase_current_rms_a": float(claims.get("phase_current_rms_a", theory["phase_current_rms_a"])),
        "dc_link_voltage_v": float(theory["dc_link_voltage_v"]),
        "modulation_index": float(theory["modulation_index"]),
        "backend_used": candidate.get("simulation_config", {}).get("mode", "formula_stub"),
    }
    reference = task.get("reference_design", {})
    expected = reference.get("expected_metrics", {})
    for key in ["efficiency_percent", "thd_percent", "dc_link_ripple_a", "device_stress_v"]:
        if key in expected:
            metrics[f"reference_{key}"] = expected[key]
    return metrics


def _evaluate_theory(task: dict[str, Any], candidate: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    spec = task["structured_spec"]
    theory = candidate["theoretical_design"]
    constraints = spec["constraints"]
    freq = spec["switching_frequency_khz"]
    violations: list[dict[str, Any]] = []
    topology = str(theory.get("topology") or "")
    if topology != "three_phase_inverter":
        violations.append({"constraint": "topology", "observed": topology, "limit": "three_phase_inverter", "severity": "hard"})

    dc_link = float(theory["dc_link_voltage_v"])
    if not float(spec["dc_link_voltage_v"]["min"]) <= dc_link <= float(spec["dc_link_voltage_v"]["max"]):
        violations.append(
            {
                "constraint": "dc_link_voltage_v",
                "observed": dc_link,
                "limit": [spec["dc_link_voltage_v"]["min"], spec["dc_link_voltage_v"]["max"]],
                "severity": "hard",
            }
        )
    if not float(freq["min"]) <= float(theory["switching_frequency_khz"]) <= float(freq["max"]):
        violations.append(
            {
                "constraint": "switching_frequency_khz",
                "observed": theory["switching_frequency_khz"],
                "limit": [freq["min"], freq["max"]],
                "severity": "medium",
            }
        )
    if float(theory["modulation_index"]) > float(constraints["max_modulation_index"]):
        violations.append(
            {
                "constraint": "max_modulation_index",
                "observed": theory["modulation_index"],
                "limit": constraints["max_modulation_index"],
                "severity": "hard",
            }
        )
    if float(theory["phase_current_rms_a"]) > float(constraints["max_phase_current_rms_a"]):
        violations.append(
            {
                "constraint": "max_phase_current_rms_a",
                "observed": theory["phase_current_rms_a"],
                "limit": constraints["max_phase_current_rms_a"],
                "severity": "hard",
            }
        )

    penalty = sum(0.22 if item["severity"] == "hard" else 0.08 for item in violations)
    return round(max(0.0, 1.0 - penalty), 4), violations


def _evaluate_bom(
    task: dict[str, Any],
    candidate: dict[str, Any],
    catalog: dict[str, dict[str, dict[str, Any]]],
    metrics: dict[str, Any],
) -> tuple[float, list[dict[str, Any]], float]:
    violations: list[dict[str, Any]] = []
    lookup = _bom_lookup(candidate)
    total_cost = 0.0
    for slot, catalog_category in INVERTER_COMPONENT_SLOTS.items():
        part_id = lookup.get(slot)
        if not part_id:
            violations.append({"constraint": f"{slot}_presence", "observed": None, "limit": "required", "severity": "hard"})
            continue
        part = catalog.get(catalog_category, {}).get(part_id)
        if not part:
            violations.append(
                {
                    "constraint": f"{slot}_catalog_lookup",
                    "observed": part_id,
                    "limit": "catalog membership",
                    "severity": "hard",
                }
            )
            continue
        total_cost += float(part.get("cost_usd", 0.0) or 0.0)
        if slot == "power_module" and float(part["voltage_rating_v"]) < float(metrics["device_stress_v"]) * 1.2:
            violations.append(
                {
                    "constraint": "power_module_voltage_derating",
                    "observed": part["voltage_rating_v"],
                    "limit": round(float(metrics["device_stress_v"]) * 1.2, 2),
                    "severity": "hard",
                }
            )
        if slot == "power_module" and float(part["current_rating_a"]) < float(metrics["phase_current_rms_a"]) * 1.35:
            violations.append(
                {
                    "constraint": "power_module_current_derating",
                    "observed": part["current_rating_a"],
                    "limit": round(float(metrics["phase_current_rms_a"]) * 1.35, 2),
                    "severity": "medium",
                }
            )
        if slot == "dc_link_capacitor" and float(part["ripple_current_a"]) < float(metrics["observed_dc_link_ripple_a"]) * 1.25:
            violations.append(
                {
                    "constraint": "dc_link_capacitor_ripple_current",
                    "observed": part["ripple_current_a"],
                    "limit": round(float(metrics["observed_dc_link_ripple_a"]) * 1.25, 2),
                    "severity": "medium",
                }
            )
    hard = sum(1 for item in violations if item["severity"] == "hard")
    medium = sum(1 for item in violations if item["severity"] != "hard")
    return round(max(0.0, 1.0 - 0.22 * hard - 0.08 * medium), 4), violations, total_cost


def _evaluate_performance(task: dict[str, Any], metrics: dict[str, Any]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    spec = task["structured_spec"]
    targets = spec["targets"]
    constraints = spec["constraints"]
    violations: list[dict[str, Any]] = []
    scores = {"efficiency": 1.0, "quality": 1.0, "stress": 1.0}
    if float(metrics["observed_efficiency_percent"]) < float(targets["efficiency_percent"]):
        violations.append(
            {
                "constraint": "efficiency_target",
                "observed": metrics["observed_efficiency_percent"],
                "limit": targets["efficiency_percent"],
                "severity": "medium",
            }
        )
        scores["efficiency"] = 0.0
    if float(metrics["observed_thd_percent"]) > float(targets["thd_percent"]):
        violations.append(
            {
                "constraint": "thd_target",
                "observed": metrics["observed_thd_percent"],
                "limit": targets["thd_percent"],
                "severity": "medium",
            }
        )
        scores["quality"] = 0.0
    if float(metrics["observed_dc_link_ripple_a"]) > float(constraints["max_dc_link_ripple_a"]):
        violations.append(
            {
                "constraint": "max_dc_link_ripple_a",
                "observed": metrics["observed_dc_link_ripple_a"],
                "limit": constraints["max_dc_link_ripple_a"],
                "severity": "medium",
            }
        )
        scores["stress"] = 0.0
    if float(metrics["device_stress_v"]) > float(constraints["max_device_voltage_v"]):
        violations.append(
            {
                "constraint": "max_device_voltage_v",
                "observed": metrics["device_stress_v"],
                "limit": constraints["max_device_voltage_v"],
                "severity": "hard",
            }
        )
        scores["stress"] = 0.0
    return scores, violations


def _evaluate_claims(task: dict[str, Any], candidate: dict[str, Any], metrics: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    reference = task.get("reference_design", {}).get("expected_metrics", {})
    violations: list[dict[str, Any]] = []
    checks = [
        ("efficiency_percent", "observed_efficiency_percent", 2.5),
        ("thd_percent", "observed_thd_percent", 1.5),
        ("dc_link_ripple_a", "observed_dc_link_ripple_a", 1.0),
        ("device_stress_v", "device_stress_v", 0.12),
    ]
    for expected_key, observed_key, tolerance in checks:
        if expected_key not in reference:
            continue
        expected = float(reference[expected_key])
        observed = float(metrics[observed_key])
        limit = tolerance if tolerance > 1.0 else abs(expected) * tolerance
        if abs(observed - expected) > max(1e-9, limit):
            violations.append(
                {
                    "constraint": f"{expected_key}_claim_consistency",
                    "observed": observed,
                    "limit": expected,
                    "severity": "medium",
                }
            )
    score = max(0.0, 1.0 - 0.12 * len(violations))
    return round(score, 4), violations


def _failure_tags(violations: list[dict[str, Any]]) -> list[str]:
    constraints = {str(item.get("constraint", "")) for item in violations}
    tags: list[str] = []
    if "candidate_schema" in constraints or "task_schema" in constraints:
        tags.append("Spec Parsing Failure")
    if "topology" in constraints:
        tags.append("Wrong Topology")
    if any("modulation" in item or "dc_link_voltage" in item for item in constraints):
        tags.append("Infeasible Theory Failure")
    if any("presence" in item or "catalog_lookup" in item or "derating" in item for item in constraints):
        tags.append("Invalid or Unsafe BOM")
    if "efficiency_target" in constraints:
        tags.append("Efficiency Miss")
    if "thd_target" in constraints:
        tags.append("Current Quality Miss")
    if any("max_" in item for item in constraints):
        tags.append("Stress Violation / Escalation Required")
    if any("claim_consistency" in item for item in constraints):
        tags.append("Optimistic but Unrealistic Claim")
    return tags


def _result(
    task: dict[str, Any],
    candidate: dict[str, Any],
    start: float,
    violations: list[dict[str, Any]],
    metrics: dict[str, Any],
    *,
    total_cost: float,
    sub_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    if sub_scores is None:
        sub_scores = {
            "spec_grounding": 0.0,
            "dc_ac_theory": 0.0,
            "component_grounding": 0.0,
            "efficiency_target": 0.0,
            "quality_target": 0.0,
            "stress_margin": 0.0,
            "claim_consistency": 0.0,
        }
    pass_fail = not any(str(item.get("severity")) == "hard" for item in violations) and not violations
    score_total = round(sum(float(value) for value in sub_scores.values()), 4)
    if total_cost and "estimated_cost_usd" not in metrics:
        metrics["estimated_cost_usd"] = round(total_cost, 3)
    metrics.setdefault("backend_used", candidate.get("simulation_config", {}).get("mode", "formula_stub"))
    return {
        "task_id": task.get("task_id"),
        "difficulty_tier": task.get("difficulty_tier"),
        "baseline_name": candidate.get("baseline_name"),
        "model_name": candidate.get("model_name"),
        "seed": int(candidate.get("seed", 0) or 0),
        "pass_fail": pass_fail,
        "score_total": score_total if pass_fail else min(score_total, 99.0),
        "sub_scores": sub_scores,
        "constraint_violations": violations,
        "simulation_metrics": metrics,
        "failure_tags": _failure_tags(violations),
        "failure_groups": sorted({str(item.get("severity", "unknown")) for item in violations}),
        "aggregate_scores": {
            "vtsr": 1.0 if pass_fail else 0.0,
            "partial_score": round((score_total if pass_fail else min(score_total, 99.0)) / 100.0, 4),
        },
        "execution_log": [
            {
                "stage": "inverter_formula_stub",
                "status": "pass" if pass_fail else "fail",
                "note": "CI-safe DC-AC evaluator path; live waveform replay can be attached as frozen run records.",
            }
        ],
        "runtime_stats": {
            "backend_requested": candidate.get("simulation_config", {}).get("mode", "formula_stub"),
            "backend_used": "formula_stub",
            "fallback_used": False,
            "fallback_reason": None,
            "simulator_version": "pebench-inverter-formula-v1",
            "runtime_seconds": round(time.perf_counter() - start, 6),
        },
    }
