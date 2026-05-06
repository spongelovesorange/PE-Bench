from __future__ import annotations

from typing import Any

from pebench.evaluator.core import evaluate_candidate
from pebench.evaluator.inverter import evaluate_inverter_candidate
from pebench.evaluator.reference import evaluate_reference_feasibility, is_reference_feasibility_candidate
from pebench.evaluator.topology_scout import evaluate_topology_scout_candidate


def evaluate_pebench_candidate(
    task: dict[str, Any],
    candidate: dict[str, Any],
    *,
    simulator_mode: str = "auto",
) -> dict[str, Any]:
    if is_reference_feasibility_candidate(candidate):
        result = evaluate_reference_feasibility(task, candidate)
        pebench_result = dict(result)
        pebench_result.update(
            {
                "vtsr_pass": bool(result.get("pass_fail")),
                "partial_score": round(float(result.get("score_total", 0.0)) / 100.0, 4),
                "gate_scores": {
                    "schema": 1.0 if result.get("pass_fail") else 0.0,
                    "reference_feasibility": 1.0 if result.get("pass_fail") else 0.0,
                },
                "checked_metrics": _checked_metrics(result),
            }
        )
        return pebench_result

    topology = str(task.get("topology") or task.get("reference_design", {}).get("topology") or "").strip()
    if topology in {"buck", "boost", "buck_boost"}:
        result = evaluate_topology_scout_candidate(task, candidate)
    elif topology == "three_phase_inverter":
        result = evaluate_inverter_candidate(task, candidate)
    else:
        result = evaluate_candidate(task, candidate, simulator_mode=simulator_mode)

    gate_scores = _gate_scores(task, result)
    partial_score = round(float(result.get("score_total", 0.0)) / 100.0, 4)
    pebench_result = dict(result)
    pebench_result.update(
        {
            "vtsr_pass": bool(result.get("pass_fail")),
            "partial_score": partial_score,
            "gate_scores": gate_scores,
            "checked_metrics": _checked_metrics(result),
        }
    )
    return pebench_result


def _gate_scores(task: dict[str, Any], result: dict[str, Any]) -> dict[str, float]:
    rubric = {item["name"]: float(item["weight"]) for item in task.get("evaluation_rubric", [])}
    sub_scores = result.get("sub_scores", {})

    def _ratio(name: str) -> float:
        weight = rubric.get(name, 0.0)
        if weight <= 0.0:
            return 0.0
        return round(float(sub_scores.get(name, 0.0)) / weight, 4)

    claim_consistency = _ratio("claim_consistency")
    if claim_consistency == 0.0:
        claim_consistency = 1.0 if "Optimistic but Unrealistic Claim" not in result.get("failure_tags", []) else 0.0

    simulation_ok = 1.0 if result.get("simulation_metrics", {}).get("startup_success") else 0.0
    if simulation_ok == 0.0 and result.get("runtime_stats", {}).get("backend_used") in {"formula_stub", "stub"}:
        simulation_ok = 1.0

    return {
        "schema": 1.0,
        "theory": _ratio("theoretical_feasibility") or _ratio("topology_theory"),
        "component": _ratio("bom_validity") or _ratio("component_grounding"),
        "derating": _ratio("stress_margin"),
        "simulation": simulation_ok,
        "claim_consistency": claim_consistency,
        "escalation": 0.0 if "Stress Violation / Escalation Required" in result.get("failure_tags", []) else 1.0,
    }


def _checked_metrics(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("simulation_metrics", {})
    return {
        "observed_efficiency_percent": metrics.get("observed_efficiency_percent"),
        "observed_ripple_mv": metrics.get("observed_ripple_mv"),
        "observed_thd_percent": metrics.get("observed_thd_percent"),
        "observed_dc_link_ripple_a": metrics.get("observed_dc_link_ripple_a"),
        "mosfet_voltage_stress_v": metrics.get("mosfet_voltage_stress_v"),
        "diode_reverse_voltage_v": metrics.get("diode_reverse_voltage_v"),
        "device_stress_v": metrics.get("device_stress_v"),
        "phase_current_a": metrics.get("phase_current_a"),
        "flux_density_mt": metrics.get("flux_density_mt"),
        "estimated_cost_usd": metrics.get("estimated_cost_usd"),
    }
