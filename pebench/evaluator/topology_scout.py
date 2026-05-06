from __future__ import annotations

import math
import time
from random import Random
from typing import Any

from pebench.tasks.topology_scout import SCOUT_COMPONENT_SLOTS, validate_scout_task_dict
from pebench.utils.io import load_yaml
from pebench.utils.paths import DEFAULT_SCOUT_CATALOG_PATH


SCOUT_FAILURE_TAGS = [
    "Spec Parsing Failure",
    "Wrong Topology",
    "Infeasible Theory Failure",
    "Invalid or Unsafe BOM",
    "Efficiency Miss",
    "Ripple / Regulation Miss",
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
    "duty_cycle_nominal",
    "inductance_uh",
    "output_capacitance_uf",
    "switching_frequency_khz",
    "inductor_ripple_current_a",
    "switch_peak_current_a",
}
REQUIRED_CLAIM_FIELDS = {
    "efficiency_percent",
    "ripple_mv",
    "mosfet_voltage_stress_v",
    "diode_reverse_voltage_v",
    "inductor_peak_current_a",
    "estimated_cost_usd",
}


def validate_scout_candidate_dict(candidate: dict[str, Any]) -> list[str]:
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


def _catalog_by_category(catalog_path: str | None) -> dict[str, dict[str, dict[str, Any]]]:
    catalog = load_yaml(catalog_path or DEFAULT_SCOUT_CATALOG_PATH)
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for category, rows in catalog.items():
        if category == "version":
            continue
        result[category] = {str(row["part_id"]): dict(row) for row in rows}
    return result


def _score_numeric_match(actual: float, expected: float, span: float) -> float:
    if span <= 0:
        return 1.0
    return max(0.0, 1.0 - abs(actual - expected) / span)


def _ratio_delta(actual: float, expected: float) -> float:
    if expected == 0:
        return 0.0
    return abs(actual - expected) / abs(expected)


def _compute_spec_score(task: dict[str, Any], candidate: dict[str, Any]) -> float:
    target = task["structured_spec"]
    parsed = candidate["parsed_spec"]
    if not isinstance(parsed, dict):
        return 0.0
    scores = [
        _score_numeric_match(
            float(parsed.get("input_range_volts", {}).get("min", 0.0) or 0.0),
            float(target["input_range_volts"]["min"]),
            max(2.0, 0.2 * float(target["input_range_volts"]["min"])),
        ),
        _score_numeric_match(
            float(parsed.get("input_range_volts", {}).get("max", 0.0) or 0.0),
            float(target["input_range_volts"]["max"]),
            max(4.0, 0.2 * float(target["input_range_volts"]["max"])),
        ),
        _score_numeric_match(
            float(parsed.get("output", {}).get("voltage_v", 0.0) or 0.0),
            float(target["output"]["voltage_v"]),
            max(0.5, 0.2 * float(target["output"]["voltage_v"])),
        ),
        _score_numeric_match(
            float(parsed.get("output", {}).get("current_a", 0.0) or 0.0),
            float(target["output"]["current_a"]),
            max(0.2, 0.2 * float(target["output"]["current_a"])),
        ),
        _score_numeric_match(
            float(parsed.get("targets", {}).get("efficiency_percent", 0.0) or 0.0),
            float(target["targets"]["efficiency_percent"]),
            6.0,
        ),
        _score_numeric_match(
            float(parsed.get("targets", {}).get("ripple_mv", 0.0) or 0.0),
            float(target["targets"]["ripple_mv"]),
            max(10.0, 0.25 * float(target["targets"]["ripple_mv"])),
        ),
    ]
    return round(sum(scores) / len(scores), 4)


def _expected_duty(task: dict[str, Any], topology: str) -> float:
    spec = task["structured_spec"]
    vin_nom = (float(spec["input_range_volts"]["min"]) + float(spec["input_range_volts"]["max"])) / 2.0
    vout = float(spec["output"]["voltage_v"])
    if topology == "buck":
        return vout / vin_nom
    if topology == "boost":
        return 1.0 - vin_nom / vout
    return vout / (vin_nom + vout)


def _evaluate_theory(task: dict[str, Any], candidate: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    theory = candidate["theoretical_design"]
    constraints = task["structured_spec"]["constraints"]
    freq = task["structured_spec"]["switching_frequency_khz"]
    topology = str(theory.get("topology") or "")
    expected = task["reference_design"]
    violations: list[dict[str, Any]] = []

    if topology != task["topology"]:
        violations.append(
            {
                "constraint": "topology",
                "observed": topology,
                "limit": task["topology"],
                "severity": "hard",
            }
        )
    expected_duty = _expected_duty(task, task["topology"])
    if abs(float(theory["duty_cycle_nominal"]) - expected_duty) > 0.12:
        violations.append(
            {
                "constraint": "duty_cycle_equation",
                "observed": theory["duty_cycle_nominal"],
                "limit": round(expected_duty, 3),
                "severity": "hard",
            }
        )
    if float(theory["duty_cycle_nominal"]) > float(constraints["max_duty_cycle"]):
        violations.append(
            {
                "constraint": "max_duty_cycle",
                "observed": theory["duty_cycle_nominal"],
                "limit": constraints["max_duty_cycle"],
                "severity": "hard",
            }
        )
    if float(theory["switch_peak_current_a"]) > float(constraints["max_inductor_peak_current_a"]):
        violations.append(
            {
                "constraint": "max_inductor_peak_current_a",
                "observed": theory["switch_peak_current_a"],
                "limit": constraints["max_inductor_peak_current_a"],
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
    if _ratio_delta(float(theory["inductance_uh"]), float(expected["inductance_uh"])) > 0.75:
        violations.append(
            {
                "constraint": "inductance_sizing",
                "observed": theory["inductance_uh"],
                "limit": expected["inductance_uh"],
                "severity": "medium",
            }
        )
    if _ratio_delta(float(theory["output_capacitance_uf"]), float(expected["output_capacitance_uf"])) > 1.0:
        violations.append(
            {
                "constraint": "output_capacitance_sizing",
                "observed": theory["output_capacitance_uf"],
                "limit": expected["output_capacitance_uf"],
                "severity": "medium",
            }
        )

    penalty = sum(0.22 if item["severity"] == "hard" else 0.08 for item in violations)
    return round(max(0.0, 1.0 - penalty), 4), violations


def _bom_lookup(candidate: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for item in candidate.get("bom", []):
        category = str(item.get("category") or "").strip()
        part_id = str(item.get("part_id") or "").strip()
        if category and part_id:
            lookup[category] = part_id
    return lookup


def _evaluate_bom(
    task: dict[str, Any],
    candidate: dict[str, Any],
    catalog: dict[str, dict[str, dict[str, Any]]],
    metrics: dict[str, Any],
) -> tuple[float, list[dict[str, Any]], float]:
    violations: list[dict[str, Any]] = []
    lookup = _bom_lookup(candidate)
    total_cost = 0.0
    for slot, catalog_category in SCOUT_COMPONENT_SLOTS.items():
        part_id = lookup.get(slot)
        if not part_id:
            violations.append(
                {"constraint": f"{slot}_presence", "observed": None, "limit": "required", "severity": "hard"}
            )
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
        if slot == "switch" and float(part["voltage_rating_v"]) < float(metrics["mosfet_voltage_stress_v"]) * 1.2:
            violations.append(
                {
                    "constraint": "switch_voltage_derating",
                    "observed": part["voltage_rating_v"],
                    "limit": round(float(metrics["mosfet_voltage_stress_v"]) * 1.2, 2),
                    "severity": "hard",
                }
            )
        if slot == "switch" and float(part["current_rating_a"]) < float(metrics["inductor_peak_current_a"]) * 1.35:
            violations.append(
                {
                    "constraint": "switch_current_derating",
                    "observed": part["current_rating_a"],
                    "limit": round(float(metrics["inductor_peak_current_a"]) * 1.35, 2),
                    "severity": "medium",
                }
            )
        if slot == "diode" and float(part["voltage_rating_v"]) < float(metrics["diode_reverse_voltage_v"]) * 1.2:
            violations.append(
                {
                    "constraint": "diode_voltage_derating",
                    "observed": part["voltage_rating_v"],
                    "limit": round(float(metrics["diode_reverse_voltage_v"]) * 1.2, 2),
                    "severity": "hard",
                }
            )
        if slot == "diode" and float(part["current_rating_a"]) < float(task["structured_spec"]["output"]["current_a"]) * 1.25:
            violations.append(
                {
                    "constraint": "diode_current_derating",
                    "observed": part["current_rating_a"],
                    "limit": round(float(task["structured_spec"]["output"]["current_a"]) * 1.25, 2),
                    "severity": "medium",
                }
            )
        if slot == "inductor" and float(part["saturation_current_a"]) < float(metrics["inductor_peak_current_a"]) * 1.2:
            violations.append(
                {
                    "constraint": "inductor_saturation_margin",
                    "observed": part["saturation_current_a"],
                    "limit": round(float(metrics["inductor_peak_current_a"]) * 1.2, 2),
                    "severity": "hard",
                }
            )
        if slot == "output_capacitor" and float(part["voltage_rating_v"]) < float(task["structured_spec"]["output"]["voltage_v"]) * 1.25:
            violations.append(
                {
                    "constraint": "capacitor_voltage_derating",
                    "observed": part["voltage_rating_v"],
                    "limit": round(float(task["structured_spec"]["output"]["voltage_v"]) * 1.25, 2),
                    "severity": "medium",
                }
            )

    penalty = sum(0.2 if item["severity"] == "hard" else 0.08 for item in violations)
    return round(max(0.0, 1.0 - penalty), 4), violations, round(total_cost, 2)


def _run_formula_stub(task: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    reference = task["reference_design"]
    theory = candidate["theoretical_design"]
    claims = candidate["final_claimed_metrics"]
    rng = Random(f"{task['task_id']}:{candidate['baseline_name']}:{candidate['seed']}")
    design_error = min(
        1.8,
        (
            1.2 * _ratio_delta(float(theory["duty_cycle_nominal"]), float(reference["duty_cycle_nominal"]))
            + 1.0 * _ratio_delta(float(theory["inductance_uh"]), float(reference["inductance_uh"]))
            + 0.9 * _ratio_delta(float(theory["output_capacitance_uf"]), float(reference["output_capacitance_uf"]))
            + 0.8 * _ratio_delta(float(theory["switching_frequency_khz"]), float(reference["switching_frequency_khz"]))
            + 1.1 * _ratio_delta(float(theory["switch_peak_current_a"]), float(reference["switch_peak_current_a"]))
        )
        / 5.0,
    )
    optimism_penalty = max(
        0.0,
        (float(claims["efficiency_percent"]) - float(reference["expected_metrics"]["efficiency_percent"])) * 0.12,
    )
    return {
        "backend_requested": "formula_stub",
        "backend_used": "formula_stub",
        "startup_success": design_error < 0.55,
        "observed_efficiency_percent": round(
            float(reference["expected_metrics"]["efficiency_percent"])
            - 10.0 * design_error
            - optimism_penalty
            - rng.uniform(0.1, 0.9),
            2,
        ),
        "observed_ripple_mv": round(
            float(reference["expected_metrics"]["ripple_mv"]) * (1.0 + 1.6 * design_error) + rng.uniform(0.5, 4.5),
            2,
        ),
        "mosfet_voltage_stress_v": round(
            float(reference["expected_metrics"]["mosfet_voltage_stress_v"]) * (1.0 + 0.45 * design_error),
            2,
        ),
        "diode_reverse_voltage_v": round(
            float(reference["expected_metrics"]["diode_reverse_voltage_v"]) * (1.0 + 0.38 * design_error),
            2,
        ),
        "inductor_peak_current_a": round(
            float(reference["expected_metrics"]["inductor_peak_current_a"]) * (1.0 + 0.55 * design_error),
            3,
        ),
        "design_error": round(design_error, 4),
        "simulator_version": "pebench-topology-scout-formula-v0",
    }


def _metric_score_higher_is_better(observed: float, target: float, full_span: float) -> float:
    if observed >= target:
        return 1.0
    return max(0.0, 1.0 - (target - observed) / full_span)


def _metric_score_lower_is_better(observed: float, target: float, full_span: float) -> float:
    if observed <= target:
        return 1.0
    return max(0.0, 1.0 - (observed - target) / full_span)


def evaluate_topology_scout_candidate(
    task: dict[str, Any],
    candidate: dict[str, Any],
    *,
    catalog_path: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    task_errors = validate_scout_task_dict(task)
    if task_errors:
        raise ValueError(f"Invalid topology scout task: {task_errors}")
    candidate_errors = validate_scout_candidate_dict(candidate)
    if candidate_errors:
        raise ValueError(f"Invalid topology scout candidate: {candidate_errors}")

    execution_log: list[dict[str, Any]] = [{"stage": "schema_parse", "message": "Task and candidate schema validated."}]
    catalog = _catalog_by_category(catalog_path)
    spec_score = _compute_spec_score(task, candidate)
    topology_score = 1.0 if candidate["topology_decision"].get("selected_topology") == task["topology"] else 0.0
    theory_score, theory_violations = _evaluate_theory(task, candidate)
    metrics = _run_formula_stub(task, candidate)
    bom_score, bom_violations, total_cost = _evaluate_bom(task, candidate, catalog, metrics)
    metrics["estimated_cost_usd"] = total_cost

    claims = candidate["final_claimed_metrics"]
    claim_errors = {
        "efficiency_abs_error": round(abs(float(claims["efficiency_percent"]) - metrics["observed_efficiency_percent"]), 3),
        "ripple_abs_error": round(abs(float(claims["ripple_mv"]) - metrics["observed_ripple_mv"]), 3),
        "mosfet_stress_abs_error": round(abs(float(claims["mosfet_voltage_stress_v"]) - metrics["mosfet_voltage_stress_v"]), 3),
        "diode_stress_abs_error": round(abs(float(claims["diode_reverse_voltage_v"]) - metrics["diode_reverse_voltage_v"]), 3),
    }
    claim_consistency_score = max(
        0.0,
        1.0
        - max(0.0, float(claims["efficiency_percent"]) - metrics["observed_efficiency_percent"]) / 8.0
        - max(0.0, metrics["observed_ripple_mv"] - float(claims["ripple_mv"])) / max(25.0, metrics["observed_ripple_mv"])
        - max(0.0, metrics["mosfet_voltage_stress_v"] - float(claims["mosfet_voltage_stress_v"])) / max(
            50.0, metrics["mosfet_voltage_stress_v"]
        ),
    )

    constraints = task["structured_spec"]["constraints"]
    constraint_violations = list(theory_violations) + list(bom_violations)
    stress_checks = [
        ("max_mosfet_voltage_v", metrics["mosfet_voltage_stress_v"], constraints["max_mosfet_voltage_v"]),
        ("max_diode_reverse_voltage_v", metrics["diode_reverse_voltage_v"], constraints["max_diode_reverse_voltage_v"]),
        ("max_inductor_peak_current_a", metrics["inductor_peak_current_a"], constraints["max_inductor_peak_current_a"]),
    ]
    for name, observed, limit in stress_checks:
        if float(observed) > float(limit):
            constraint_violations.append(
                {"constraint": name, "observed": observed, "limit": limit, "severity": "hard"}
            )

    eff_score = _metric_score_higher_is_better(
        metrics["observed_efficiency_percent"],
        float(task["structured_spec"]["targets"]["efficiency_percent"]),
        12.0,
    )
    ripple_score = _metric_score_lower_is_better(
        metrics["observed_ripple_mv"],
        float(task["structured_spec"]["targets"]["ripple_mv"]),
        max(20.0, float(task["structured_spec"]["targets"]["ripple_mv"])),
    )
    stress_margin_scores = [
        max(0.0, min(1.0, (float(limit) - float(observed)) / max(1.0, float(limit))))
        for _, observed, limit in stress_checks
    ]
    stress_score = sum(stress_margin_scores) / len(stress_margin_scores)
    weights = {item["name"]: float(item["weight"]) for item in task["evaluation_rubric"]}
    sub_scores = {
        "spec_grounding": round(spec_score * weights["spec_grounding"], 2),
        "topology_theory": round(min(topology_score, theory_score) * weights["topology_theory"], 2),
        "component_grounding": round(bom_score * weights["component_grounding"], 2),
        "efficiency_target": round(eff_score * weights["efficiency_target"], 2),
        "ripple_target": round(ripple_score * weights["ripple_target"], 2),
        "stress_margin": round(stress_score * weights["stress_margin"], 2),
        "claim_consistency": round(claim_consistency_score * weights["claim_consistency"], 2),
    }
    score_total = round(sum(sub_scores.values()), 2)
    performance_weight = (
        weights["efficiency_target"] + weights["ripple_target"] + weights["stress_margin"]
    )
    performance_points = (
        sub_scores["efficiency_target"] + sub_scores["ripple_target"] + sub_scores["stress_margin"]
    )
    aggregate_scores = {
        "performance_targets": round(performance_points / max(1.0, performance_weight), 4),
        "performance_target_points": round(performance_points, 2),
    }

    failure_tags: list[str] = []
    if spec_score < 0.8:
        failure_tags.append("Spec Parsing Failure")
    if topology_score < 1.0:
        failure_tags.append("Wrong Topology")
    if theory_score < 0.75:
        failure_tags.append("Infeasible Theory Failure")
    if bom_score < 0.8:
        failure_tags.append("Invalid or Unsafe BOM")
    if metrics["observed_efficiency_percent"] < float(task["structured_spec"]["targets"]["efficiency_percent"]):
        failure_tags.append("Efficiency Miss")
    if metrics["observed_ripple_mv"] > float(task["structured_spec"]["targets"]["ripple_mv"]):
        failure_tags.append("Ripple / Regulation Miss")
    if any(item["severity"] == "hard" for item in constraint_violations):
        failure_tags.append("Stress Violation / Escalation Required")
    if claim_consistency_score < 0.75:
        failure_tags.append("Optimistic but Unrealistic Claim")
    if task["difficulty_tier"] == "stress" and not candidate["uncertainty_or_escalation_flag"].get("escalate", False):
        failure_tags.append("Stress Violation / Escalation Required")
    failure_tags = [tag for tag in SCOUT_FAILURE_TAGS if tag in set(failure_tags)]

    failure_groups: list[str] = []
    if any(tag in {"Efficiency Miss", "Ripple / Regulation Miss", "Stress Violation / Escalation Required"} for tag in failure_tags):
        failure_groups.append("Performance Requirement Miss")

    pass_fail = (
        spec_score >= 0.8
        and topology_score == 1.0
        and theory_score >= 0.75
        and bom_score >= 0.8
        and metrics["startup_success"]
        and metrics["observed_efficiency_percent"] >= float(task["structured_spec"]["targets"]["efficiency_percent"])
        and metrics["observed_ripple_mv"] <= float(task["structured_spec"]["targets"]["ripple_mv"])
        and claim_consistency_score >= 0.75
        and not any(item["severity"] == "hard" for item in constraint_violations)
    )
    execution_log.extend(
        [
            {"stage": "spec_grounding", "message": f"Spec score={spec_score:.3f}"},
            {"stage": "topology_theory", "message": f"Theory score={theory_score:.3f}"},
            {"stage": "component_grounding", "message": f"BOM score={bom_score:.3f}"},
            {"stage": "claim_consistency", "message": f"Claim consistency={claim_consistency_score:.3f}"},
            {"stage": "failure_tagging", "message": f"Tags={failure_tags}"},
        ]
    )
    return {
        "task_id": task["task_id"],
        "topology": task["topology"],
        "difficulty_tier": task["difficulty_tier"],
        "baseline_name": candidate["baseline_name"],
        "model_name": candidate["model_name"],
        "seed": candidate["seed"],
        "pass_fail": pass_fail,
        "score_total": score_total,
        "sub_scores": sub_scores,
        "aggregate_scores": aggregate_scores,
        "constraint_violations": constraint_violations,
        "simulation_metrics": metrics,
        "claim_errors": claim_errors,
        "failure_tags": failure_tags,
        "failure_groups": failure_groups,
        "execution_log": execution_log,
        "runtime_stats": {
            "evaluation_mode": "topology_full_formula",
            "elapsed_seconds": round(time.perf_counter() - started, 4),
            "backend_requested": metrics.get("backend_requested"),
            "backend_used": metrics["backend_used"],
            "sim_calls": int(candidate["metadata"].get("sim_calls_used", 1)),
            "iterations": int(candidate["metadata"].get("iterations_used", 1)),
            "claim_consistency_score": round(claim_consistency_score, 4),
            "topology_correct": topology_score == 1.0,
            "ablations": dict(candidate["metadata"].get("ablations", {})),
        },
    }
