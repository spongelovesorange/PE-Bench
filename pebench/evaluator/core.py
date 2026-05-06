from __future__ import annotations

import time
from typing import Any

from pebench.adapters.candidate import validate_candidate_dict
from pebench.evaluator.result_schema import validate_result_dict
from pebench.evaluator.simulator import run_simulation
from pebench.integrations.reference_agent import (
    build_reference_agent_bom,
    build_reference_agent_design,
    build_reference_agent_specs,
    estimate_formula_metrics,
    get_reference_agent_assets,
)
from pebench.tasks.schema import validate_task_dict
from pebench.utils.io import load_yaml
from pebench.utils.paths import DEFAULT_CATALOG_PATH


FAILURE_TAGS = [
    "Spec Parsing Failure",
    "Infeasible Theory Failure",
    "Invalid or Unsafe BOM",
    "Simulation Execution Failure",
    "Optimistic but Unrealistic Claim",
    "Efficiency Miss",
    "Ripple / Regulation Miss",
    "Stress Violation / Escalation Required",
]

PERFORMANCE_FAILURE_TAGS = {
    "Efficiency Miss",
    "Ripple / Regulation Miss",
    "Stress Violation / Escalation Required",
}


def _score_numeric_match(actual: float, expected: float, span: float) -> float:
    if span <= 0:
        return 1.0
    return max(0.0, 1.0 - abs(actual - expected) / span)


def _make_catalog_index(catalog: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    index: dict[str, dict[str, dict[str, Any]]] = {}
    for category, items in catalog.items():
        if category == "version":
            continue
        index[category] = {item["part_id"]: item for item in items}
    return index


def _build_bom_lookup(candidate: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for item in candidate["bom"]:
        category = item.get("category")
        part_id = item.get("part_id")
        if category and part_id:
            lookup[category] = part_id
    return lookup


def _candidate_uses_reference_agent_assets(candidate: dict[str, Any]) -> bool:
    if candidate.get("metadata", {}).get("reference_agent_integration", {}).get("enabled"):
        return True
    return any(item.get("source") == "reference_agent_local_db" for item in candidate.get("bom", []))


def _compute_spec_score(task: dict[str, Any], candidate: dict[str, Any]) -> float:
    target = task["structured_spec"]
    parsed = candidate["parsed_spec"]
    if not isinstance(parsed, dict):
        return 0.0

    numeric_scores = [
        _score_numeric_match(
            parsed.get("input_range_volts", {}).get("min", 0.0),
            target["input_range_volts"]["min"],
            max(10.0, 0.2 * target["input_range_volts"]["min"]),
        ),
        _score_numeric_match(
            parsed.get("input_range_volts", {}).get("max", 0.0),
            target["input_range_volts"]["max"],
            max(10.0, 0.2 * target["input_range_volts"]["max"]),
        ),
        _score_numeric_match(
            parsed.get("output", {}).get("voltage_v", 0.0),
            target["output"]["voltage_v"],
            max(0.5, 0.2 * target["output"]["voltage_v"]),
        ),
        _score_numeric_match(
            parsed.get("output", {}).get("current_a", 0.0),
            target["output"]["current_a"],
            max(0.2, 0.2 * target["output"]["current_a"]),
        ),
        _score_numeric_match(
            parsed.get("targets", {}).get("efficiency_percent", 0.0),
            target["targets"]["efficiency_percent"],
            6.0,
        ),
        _score_numeric_match(
            parsed.get("targets", {}).get("ripple_mv", 0.0),
            target["targets"]["ripple_mv"],
            max(10.0, 0.25 * target["targets"]["ripple_mv"]),
        ),
    ]

    domain_score = 1.0 if parsed.get("input_range_volts", {}).get("domain") == target["input_range_volts"]["domain"] else 0.0
    return round((sum(numeric_scores) + domain_score) / (len(numeric_scores) + 1), 4)


def _evaluate_theory(
    task: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[float, list[dict[str, Any]], dict[str, Any]]:
    theory = candidate["theoretical_design"]
    constraints = task["structured_spec"]["constraints"]
    freq_range = task["structured_spec"]["switching_frequency_khz"]
    violations: list[dict[str, Any]] = []
    details: dict[str, Any] = {}

    if theory["duty_cycle_max"] > constraints["max_duty_cycle"]:
        violations.append(
            {
                "constraint": "max_duty_cycle",
                "observed": theory["duty_cycle_max"],
                "limit": constraints["max_duty_cycle"],
                "severity": "hard",
            }
        )

    if theory["primary_peak_current_a"] > constraints["max_primary_peak_current_a"]:
        violations.append(
            {
                "constraint": "max_primary_peak_current_a",
                "observed": theory["primary_peak_current_a"],
                "limit": constraints["max_primary_peak_current_a"],
                "severity": "hard",
            }
        )

    if not freq_range["min"] <= theory["switching_frequency_khz"] <= freq_range["max"]:
        violations.append(
            {
                "constraint": "switching_frequency_khz",
                "observed": theory["switching_frequency_khz"],
                "limit": [freq_range["min"], freq_range["max"]],
                "severity": "medium",
            }
        )

    if theory["turns_ratio_primary_to_secondary"] <= 1.0:
        violations.append(
            {
                "constraint": "turns_ratio_primary_to_secondary",
                "observed": theory["turns_ratio_primary_to_secondary"],
                "limit": "> 1.0",
                "severity": "hard",
            }
        )

    assets = get_reference_agent_assets()
    guardrails = assets["modules"].get("formula_guardrails")
    if guardrails is not None:
        pe_specs = build_reference_agent_specs(task)
        normalized = guardrails.normalize_and_validate_specs(pe_specs)
        pe_design = build_reference_agent_design(task, candidate)
        equation_checks = guardrails.check_design_equations(normalized["normalized"], pe_design)
        details["reference_agent_normalization"] = normalized
        details["reference_agent_equation_checks"] = equation_checks

        for fatal in normalized.get("fatal", []):
            violations.append(
                {
                    "constraint": "reference_agent_spec_normalization",
                    "observed": fatal,
                    "limit": "normalized engineering spec",
                    "severity": "hard",
                }
            )
        for fatal in equation_checks.get("fatal", []):
            violations.append(
                {
                    "constraint": "reference_agent_equation_fatal",
                    "observed": fatal,
                    "limit": "engineering bounds",
                    "severity": "hard",
                }
            )
        for check in equation_checks.get("checks", []):
            if check.get("pass"):
                continue
            violations.append(
                {
                    "constraint": check.get("name", "reference_agent_equation_check"),
                    "observed": check.get("actual"),
                    "limit": check.get("expected"),
                    "severity": "medium",
                }
            )

    penalty = 0.0
    for violation in violations:
        penalty += 0.18 if violation["severity"] == "hard" else 0.07
    score = max(0.0, 1.0 - penalty)
    return round(score, 4), violations, details


def _evaluate_bom(
    task: dict[str, Any],
    candidate: dict[str, Any],
    catalog_index: dict[str, dict[str, dict[str, Any]]],
    simulated_metrics: dict[str, Any],
) -> tuple[float, list[dict[str, Any]], float, dict[str, Any]]:
    if _candidate_uses_reference_agent_assets(candidate):
        assets = get_reference_agent_assets()
        guardrails = assets["modules"].get("formula_guardrails")
        if guardrails is not None:
            pe_specs = build_reference_agent_specs(task)
            pe_design = build_reference_agent_design(task, candidate)
            pe_bom = build_reference_agent_bom(candidate)
            checks = guardrails.check_bom_margins(pe_specs, pe_design, pe_bom)
            violations: list[dict[str, Any]] = []
            required_aliases = {"controller", "mosfet", "diode", "output_cap", "transformer"}
            missing = sorted(alias for alias in required_aliases if alias not in pe_bom)
            for alias in missing:
                violations.append(
                    {
                        "constraint": f"{alias}_presence",
                        "observed": None,
                        "limit": "required",
                        "severity": "hard",
                    }
                )

            for check in checks.get("checks", []):
                if check.get("pass"):
                    continue
                name = str(check.get("name") or "reference_agent_bom_check")
                severity = "hard" if any(token in name for token in ["mosfet", "diode"]) else "medium"
                violations.append(
                    {
                        "constraint": name,
                        "observed": check.get("actual"),
                        "limit": check.get("required"),
                        "severity": severity,
                    }
                )

            total_cost = round(
                sum(
                    float(item.get("price") or item.get("attributes", {}).get("price") or 0.0)
                    for item in candidate.get("bom", [])
                ),
                2,
            )
            penalty = 0.0
            for violation in violations:
                penalty += 0.2 if violation["severity"] == "hard" else 0.08
            score = max(0.0, 1.0 - penalty)
            return round(score, 4), violations, total_cost, {"path": "reference_agent", "checks": checks}

    bom_lookup = _build_bom_lookup(candidate)
    output_voltage = task["structured_spec"]["output"]["voltage_v"]
    output_current = task["structured_spec"]["output"]["current_a"]
    theory = candidate["theoretical_design"]
    violations: list[dict[str, Any]] = []
    total_cost = 0.0

    category_aliases = {
        "controllers": "controller",
        "mosfets": "mosfet",
        "diodes": "diode",
        "output_capacitors": "output_capacitor",
        "cores": "core",
    }

    for category, alias in category_aliases.items():
        part_id = bom_lookup.get(alias)
        if not part_id:
            violations.append(
                {
                    "constraint": f"{alias}_presence",
                    "observed": None,
                    "limit": "required",
                    "severity": "hard",
                }
            )
            continue
        part = catalog_index.get(category, {}).get(part_id)
        if not part:
            violations.append(
                {
                    "constraint": f"{alias}_catalog_lookup",
                    "observed": part_id,
                    "limit": "catalog membership",
                    "severity": "hard",
                }
            )
            continue
        total_cost += float(part.get("cost_usd", 0.0))

        if category == "mosfets":
            if part["voltage_rating_v"] < simulated_metrics["mosfet_voltage_stress_v"] * 1.2:
                violations.append(
                    {
                        "constraint": "mosfet_voltage_derating",
                        "observed": part["voltage_rating_v"],
                        "limit": round(simulated_metrics["mosfet_voltage_stress_v"] * 1.2, 2),
                        "severity": "hard",
                    }
                )
            if part["current_rating_a"] < theory["primary_peak_current_a"] * 1.5:
                violations.append(
                    {
                        "constraint": "mosfet_current_derating",
                        "observed": part["current_rating_a"],
                        "limit": round(theory["primary_peak_current_a"] * 1.5, 2),
                        "severity": "medium",
                    }
                )

        if category == "diodes":
            if part["voltage_rating_v"] < simulated_metrics["diode_reverse_voltage_v"] * 1.2:
                violations.append(
                    {
                        "constraint": "diode_voltage_derating",
                        "observed": part["voltage_rating_v"],
                        "limit": round(simulated_metrics["diode_reverse_voltage_v"] * 1.2, 2),
                        "severity": "hard",
                    }
                )
            if part["current_rating_a"] < output_current * 1.5:
                violations.append(
                    {
                        "constraint": "diode_current_derating",
                        "observed": part["current_rating_a"],
                        "limit": round(output_current * 1.5, 2),
                        "severity": "medium",
                    }
                )

        if category == "output_capacitors":
            if part["voltage_rating_v"] < output_voltage * 1.25:
                violations.append(
                    {
                        "constraint": "capacitor_voltage_derating",
                        "observed": part["voltage_rating_v"],
                        "limit": round(output_voltage * 1.25, 2),
                        "severity": "medium",
                    }
                )

        if category == "cores":
            if part["max_power_w"] < task["structured_spec"]["output"]["power_w"] * 1.15:
                violations.append(
                    {
                        "constraint": "core_power_margin",
                        "observed": part["max_power_w"],
                        "limit": round(task["structured_spec"]["output"]["power_w"] * 1.15, 2),
                        "severity": "medium",
                    }
                )

    score = max(0.0, 1.0 - 0.18 * len(violations))
    return round(score, 4), violations, round(total_cost, 2), {"path": "benchmark_catalog"}


def _metric_score_higher_is_better(observed: float, target: float, full_span: float) -> float:
    if observed >= target:
        return 1.0
    return max(0.0, 1.0 - (target - observed) / full_span)


def _metric_score_lower_is_better(observed: float, target: float, full_span: float) -> float:
    if observed <= target:
        return 1.0
    return max(0.0, 1.0 - (observed - target) / full_span)


def _get_claim_status(candidate: dict[str, Any]) -> str:
    return str(candidate.get("metadata", {}).get("claim_metrics", {}).get("status") or "unspecified")


def _backfill_verified_claims_from_simulation(
    candidate: dict[str, Any],
    simulated_metrics: dict[str, Any],
) -> None:
    if simulated_metrics.get("backend_used") == "stub":
        return
    if not simulated_metrics.get("startup_success"):
        return

    claims = candidate.get("final_claimed_metrics", {})
    claims["efficiency_percent"] = round(float(simulated_metrics["observed_efficiency_percent"]), 2)
    claims["ripple_mv"] = round(float(simulated_metrics["observed_ripple_mv"]), 2)
    claims["mosfet_voltage_stress_v"] = round(float(simulated_metrics["mosfet_voltage_stress_v"]), 2)
    claims["diode_reverse_voltage_v"] = round(float(simulated_metrics["diode_reverse_voltage_v"]), 2)
    if float(simulated_metrics.get("flux_density_mt") or 0.0) > 0.0:
        claims["flux_density_mt"] = round(float(simulated_metrics["flux_density_mt"]), 2)
    candidate["final_claimed_metrics"] = claims

    metric_sources = {
        "efficiency_percent": "live_sim",
        "ripple_mv": "live_waveform",
        "mosfet_voltage_stress_v": "live_sim",
        "diode_reverse_voltage_v": "validated_estimate_from_design_and_vin",
        "flux_density_mt": "formula_validation",
        "estimated_cost_usd": "bom_sum",
    }
    claim_metadata = dict(candidate.get("metadata", {}).get("claim_metrics", {}))
    claim_metadata["status"] = "verified_from_live_sim"
    claim_metadata["estimated_only"] = False
    claim_metadata["metric_sources"] = metric_sources
    candidate.setdefault("metadata", {})["claim_metrics"] = claim_metadata


def evaluate_candidate(
    task: dict[str, Any],
    candidate: dict[str, Any],
    catalog_path: str | None = None,
    simulator_mode: str = "auto",
) -> dict[str, Any]:
    started = time.perf_counter()
    execution_log: list[dict[str, Any]] = []

    task_errors = validate_task_dict(task)
    if task_errors:
        raise ValueError(f"Invalid task definition: {task_errors}")
    execution_log.append({"stage": "schema_parse", "message": "Task schema validated."})

    candidate_errors = validate_candidate_dict(candidate)
    if candidate_errors:
        raise ValueError(f"Invalid candidate design: {candidate_errors}")
    execution_log.append({"stage": "schema_parse", "message": "Candidate schema validated."})

    catalog = load_yaml(catalog_path or DEFAULT_CATALOG_PATH)
    catalog_index = _make_catalog_index(catalog)
    reference_agent_assets = get_reference_agent_assets()
    if _candidate_uses_reference_agent_assets(candidate):
        execution_log.append(
            {
                "stage": "reference_agent_provenance",
                "message": f"Reference-agent modules available={reference_agent_assets.get('available', {})}",
            }
        )
    ablations = dict(candidate.get("metadata", {}).get("ablations", {}))
    if any(bool(value) for value in ablations.values()):
        execution_log.append(
            {
                "stage": "baseline_ablation",
                "message": f"Active ablations={ablations}",
            }
        )

    spec_score = _compute_spec_score(task, candidate)
    execution_log.append({"stage": "spec_grounding", "message": f"Spec score={spec_score:.3f}"})

    theory_score, theory_violations, theory_details = _evaluate_theory(task, candidate)
    execution_log.append(
        {"stage": "formula_guardrails", "message": f"Theory score={theory_score:.3f}"}
    )
    if theory_details.get("reference_agent_equation_checks"):
        execution_log.append(
            {
                "stage": "formula_guardrails",
                "message": (
                    "Reference-agent equation checks run with "
                    f"{len(theory_details['reference_agent_equation_checks'].get('checks', []))} checks."
                ),
            }
        )

    simulated_metrics = run_simulation(
        task=task,
        candidate=candidate,
        simulator_mode=simulator_mode,
        invalid_bom=False,
    )
    execution_log.append(
        {
            "stage": "sim_generation",
            "message": (
                f"Simulator requested={simulated_metrics.get('backend_requested')} "
                f"used={simulated_metrics.get('backend_used')} "
                f"startup={simulated_metrics['startup_success']}"
            ),
        }
    )
    if simulated_metrics.get("fallback_used"):
        execution_log.append(
            {
                "stage": "sim_generation",
                "message": f"Fallback to stub: {simulated_metrics.get('fallback_reason')}",
            }
        )

    _backfill_verified_claims_from_simulation(candidate, simulated_metrics)
    claim_status = _get_claim_status(candidate)
    execution_log.append(
        {
            "stage": "claim_verification",
            "message": f"Claim status={claim_status}",
        }
    )

    reference_agent_formula_metrics = estimate_formula_metrics(task, candidate)
    if reference_agent_formula_metrics:
        simulated_metrics["formula_efficiency_estimate_percent"] = reference_agent_formula_metrics["efficiency_percent"]
        simulated_metrics["formula_efficiency_raw_percent"] = reference_agent_formula_metrics["efficiency_raw_percent"]
        simulated_metrics["formula_mode"] = reference_agent_formula_metrics["mode"]
        simulated_metrics["formula_confidence"] = reference_agent_formula_metrics["confidence"]
        simulated_metrics["formula_flux_density_mt"] = reference_agent_formula_metrics["flux_density_mt"]
        execution_log.append(
            {
                "stage": "sim_generation",
                "message": (
                    "Reference-agent formula estimator produced "
                    f"{reference_agent_formula_metrics['efficiency_percent']:.2f}% efficiency "
                    f"({reference_agent_formula_metrics['confidence']} confidence)."
                ),
            }
        )

    bom_score, bom_violations, total_cost, bom_details = _evaluate_bom(
        task=task,
        candidate=candidate,
        catalog_index=catalog_index,
        simulated_metrics=simulated_metrics,
    )
    simulated_metrics["estimated_cost_usd"] = total_cost
    candidate["final_claimed_metrics"]["estimated_cost_usd"] = round(total_cost, 2)
    candidate.setdefault("metadata", {}).setdefault("claim_metrics", {}).setdefault("metric_sources", {})[
        "estimated_cost_usd"
    ] = "bom_sum"
    execution_log.append(
        {
            "stage": "bom_grounding",
            "message": f"BOM score={bom_score:.3f} via {bom_details.get('path', 'unknown')}.",
        }
    )

    constraints = task["structured_spec"]["constraints"]
    efficiency_score = _metric_score_higher_is_better(
        simulated_metrics["observed_efficiency_percent"],
        task["structured_spec"]["targets"]["efficiency_percent"],
        full_span=12.0,
    )
    ripple_score = _metric_score_lower_is_better(
        simulated_metrics["observed_ripple_mv"],
        task["structured_spec"]["targets"]["ripple_mv"],
        full_span=max(20.0, task["structured_spec"]["targets"]["ripple_mv"]),
    )

    stress_margins = [
        constraints["max_mosfet_voltage_v"] - simulated_metrics["mosfet_voltage_stress_v"],
        constraints["max_diode_reverse_voltage_v"] - simulated_metrics["diode_reverse_voltage_v"],
        constraints["max_flux_density_mt"] - simulated_metrics["flux_density_mt"],
    ]
    positive_margin = sum(max(0.0, margin) for margin in stress_margins)
    total_margin = sum(abs(margin) for margin in stress_margins)
    stress_score = max(0.0, min(1.0, positive_margin / max(1.0, total_margin)))

    reference_cost = task["reference_design"]["cost_proxy_usd"]
    cost_score = max(0.0, 1.0 - max(0.0, total_cost - reference_cost) / max(1.0, reference_cost))

    rubric_weights = {item["name"]: float(item["weight"]) for item in task["evaluation_rubric"]}
    sub_scores = {
        "spec_grounding": round(spec_score * rubric_weights["spec_grounding"], 2),
        "theoretical_feasibility": round(
            theory_score * rubric_weights["theoretical_feasibility"], 2
        ),
        "bom_validity": round(bom_score * rubric_weights["bom_validity"], 2),
        "efficiency_target": round(efficiency_score * rubric_weights["efficiency_target"], 2),
        "ripple_target": round(ripple_score * rubric_weights["ripple_target"], 2),
        "stress_margin": round(stress_score * rubric_weights["stress_margin"], 2),
        "cost_reasonableness": round(cost_score * rubric_weights["cost_reasonableness"], 2),
    }
    performance_weight = (
        rubric_weights["efficiency_target"]
        + rubric_weights["ripple_target"]
        + rubric_weights["stress_margin"]
    )
    performance_points = (
        sub_scores["efficiency_target"] + sub_scores["ripple_target"] + sub_scores["stress_margin"]
    )
    aggregate_scores = {
        "performance_targets": round(performance_points / max(1.0, performance_weight), 4),
        "performance_target_points": round(performance_points, 2),
    }
    score_total = round(sum(sub_scores.values()), 2)

    constraint_violations = list(theory_violations) + list(bom_violations)
    if simulated_metrics["mosfet_voltage_stress_v"] > constraints["max_mosfet_voltage_v"]:
        constraint_violations.append(
            {
                "constraint": "max_mosfet_voltage_v",
                "observed": simulated_metrics["mosfet_voltage_stress_v"],
                "limit": constraints["max_mosfet_voltage_v"],
                "severity": "hard",
            }
        )
    if simulated_metrics["diode_reverse_voltage_v"] > constraints["max_diode_reverse_voltage_v"]:
        constraint_violations.append(
            {
                "constraint": "max_diode_reverse_voltage_v",
                "observed": simulated_metrics["diode_reverse_voltage_v"],
                "limit": constraints["max_diode_reverse_voltage_v"],
                "severity": "hard",
            }
        )
    if simulated_metrics["flux_density_mt"] > constraints["max_flux_density_mt"]:
        constraint_violations.append(
            {
                "constraint": "max_flux_density_mt",
                "observed": simulated_metrics["flux_density_mt"],
                "limit": constraints["max_flux_density_mt"],
                "severity": "medium",
            }
        )

    consistency_warnings: list[str] = []
    guardrails = reference_agent_assets["modules"].get("formula_guardrails")
    if guardrails is not None and reference_agent_formula_metrics:
        consistency = guardrails.check_simulation_consistency(
            build_reference_agent_specs(task),
            {
                "efficiency_measured": simulated_metrics["observed_efficiency_percent"] / 100.0,
                "efficiency_formula_est": reference_agent_formula_metrics["efficiency_percent"] / 100.0,
                "v_out_ripple_measured": simulated_metrics["observed_ripple_mv"] / 1000.0,
                "ripple_voltage": simulated_metrics["observed_ripple_mv"] / 1000.0,
            },
            build_reference_agent_bom(candidate),
        )
        consistency_warnings = list(consistency.get("warnings", []))
        simulated_metrics["consistency_warning_count"] = len(consistency_warnings)
        if consistency_warnings:
            execution_log.append(
                {
                    "stage": "sim_generation",
                    "message": "Reference-agent consistency warnings: " + " | ".join(consistency_warnings[:3]),
                }
            )

    sim_consistency_tools = reference_agent_assets["modules"].get("simulation_consistency_tools")
    if sim_consistency_tools is not None and hasattr(sim_consistency_tools, "check_consistency"):
        try:
            consistency_report = sim_consistency_tools.check_consistency(
                {
                    "specifications": build_reference_agent_specs(task),
                    "simulation_results": {
                        "efficiency_measured": simulated_metrics["observed_efficiency_percent"] / 100.0,
                        "v_out_ripple_measured": simulated_metrics["observed_ripple_mv"] / 1000.0,
                        "ripple_voltage": simulated_metrics["observed_ripple_mv"] / 1000.0,
                        "v_ds_spike_max": simulated_metrics["mosfet_voltage_stress_v"],
                    },
                }
            )
            simulated_metrics["corner_consistency_score"] = consistency_report.get("consistency_score")
            simulated_metrics["stability_score"] = consistency_report.get("stability_score")
            simulated_metrics["corner_fail_count"] = len(consistency_report.get("failed_corners", []))
            artifact_path = (consistency_report.get("artifacts") or {}).get("corner_plot")
            if artifact_path:
                simulated_metrics["corner_plot_path"] = artifact_path
            execution_log.append(
                {
                    "stage": "sim_generation",
                    "message": (
                        "Reference-agent consistency skill score="
                        f"{consistency_report.get('consistency_score')} "
                        f"failed_corners={len(consistency_report.get('failed_corners', []))}"
                    ),
                }
            )
        except Exception as exc:
            execution_log.append(
                {
                    "stage": "sim_generation",
                    "message": f"Reference-agent consistency skill unavailable at runtime: {exc}",
                }
            )

    failure_tags: list[str] = []
    if spec_score < 0.8:
        failure_tags.append("Spec Parsing Failure")
    if theory_score < 0.75:
        failure_tags.append("Infeasible Theory Failure")
    if bom_score < 0.8:
        failure_tags.append("Invalid or Unsafe BOM")
    if not simulated_metrics["startup_success"]:
        failure_tags.append("Simulation Execution Failure")

    claims = candidate["final_claimed_metrics"]
    if claim_status not in {"estimated_only", "verified_from_live_sim"} and (
        claims["efficiency_percent"] - simulated_metrics["observed_efficiency_percent"] > 2.0
        or simulated_metrics["observed_ripple_mv"] - claims["ripple_mv"] > 15.0
    ):
        failure_tags.append("Optimistic but Unrealistic Claim")
    if consistency_warnings and claim_status != "verified_from_live_sim":
        failure_tags.append("Optimistic but Unrealistic Claim")

    if simulated_metrics["observed_efficiency_percent"] < task["structured_spec"]["targets"]["efficiency_percent"]:
        failure_tags.append("Efficiency Miss")

    if simulated_metrics["observed_ripple_mv"] > task["structured_spec"]["targets"]["ripple_mv"]:
        failure_tags.append("Ripple / Regulation Miss")

    if any(
        violation["constraint"]
        in {"max_mosfet_voltage_v", "max_diode_reverse_voltage_v", "max_flux_density_mt"}
        or violation["severity"] == "hard"
        for violation in constraint_violations
    ):
        failure_tags.append("Stress Violation / Escalation Required")

    if (
        task["difficulty_tier"] == "stress"
        and not candidate["uncertainty_or_escalation_flag"].get("escalate", False)
    ):
        failure_tags.append("Stress Violation / Escalation Required")

    failure_tags = [tag for tag in FAILURE_TAGS if tag in set(failure_tags)]
    failure_groups: list[str] = []
    if any(tag in PERFORMANCE_FAILURE_TAGS for tag in failure_tags):
        failure_groups.append("Performance Requirement Miss")
    pass_fail = (
        spec_score >= 0.8
        and theory_score >= 0.75
        and bom_score >= 0.8
        and simulated_metrics["startup_success"]
        and simulated_metrics["observed_efficiency_percent"]
        >= task["structured_spec"]["targets"]["efficiency_percent"]
        and simulated_metrics["observed_ripple_mv"] <= task["structured_spec"]["targets"]["ripple_mv"]
        and not any(violation["severity"] == "hard" for violation in constraint_violations)
    )

    peer_review_summary: dict[str, Any] | None = None
    peer_review_tools = reference_agent_assets["modules"].get("design_peer_review_tools")
    if peer_review_tools is not None and hasattr(peer_review_tools, "review_design"):
        try:
            peer_review_summary = peer_review_tools.review_design(
                {
                    "specifications": build_reference_agent_specs(task),
                    "simulation_results": {
                        "efficiency_measured": simulated_metrics["observed_efficiency_percent"] / 100.0,
                        "v_out_ripple_measured": simulated_metrics["observed_ripple_mv"] / 1000.0,
                        "ripple_voltage": simulated_metrics["observed_ripple_mv"] / 1000.0,
                    },
                    "verification": {"status": "PASS" if pass_fail else "FAIL"},
                    "formula_checks": {
                        "theory": {
                            "fatal": [
                                violation["constraint"]
                                for violation in theory_violations
                                if violation["severity"] == "hard"
                            ],
                            "warnings": [
                                violation["constraint"]
                                for violation in theory_violations
                                if violation["severity"] != "hard"
                            ],
                        }
                    },
                    "node_verification": {
                        "bom_grounding": {"status": "PASS" if bom_score >= 0.8 else "WARN"},
                        "simulator": {
                            "status": "PASS" if simulated_metrics["startup_success"] else "FAIL"
                        },
                    },
                }
            )
            execution_log.append(
                {
                    "stage": "peer_review",
                    "message": (
                        f"Reference-agent peer review={peer_review_summary.get('review_status')} "
                        f"risk={peer_review_summary.get('false_pass_risk_score')}"
                    ),
                }
            )
        except Exception as exc:
            execution_log.append(
                {
                    "stage": "peer_review",
                    "message": f"Reference-agent peer review unavailable at runtime: {exc}",
                }
            )

    execution_log.append({"stage": "score_aggregation", "message": f"Total score={score_total:.2f}"})
    execution_log.append({"stage": "failure_tagging", "message": f"Tags={failure_tags}"})
    if failure_groups:
        execution_log.append({"stage": "failure_grouping", "message": f"Groups={failure_groups}"})

    runtime_stats = {
        "evaluation_mode": simulator_mode,
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "sim_calls": int(candidate["metadata"].get("sim_calls_used", 0)),
        "iterations": int(candidate["metadata"].get("iterations_used", 0)),
        "backend_requested": simulated_metrics.get("backend_requested"),
        "backend_used": simulated_metrics.get("backend_used"),
        "backend_attempts": simulated_metrics.get("backend_attempts", []),
        "fallback_used": bool(simulated_metrics.get("fallback_used")),
        "fallback_reason": simulated_metrics.get("fallback_reason"),
        "reference_agent_assets_used": _candidate_uses_reference_agent_assets(candidate),
        "reference_agent_available_modules": dict(reference_agent_assets.get("available", {})),
        "ablations": ablations,
    }
    if peer_review_summary:
        runtime_stats["peer_review_status"] = peer_review_summary.get("review_status")
        runtime_stats["false_pass_risk_score"] = peer_review_summary.get("false_pass_risk_score")
    runtime_stats["claim_status"] = claim_status

    result = {
        "task_id": task["task_id"],
        "difficulty_tier": task["difficulty_tier"],
        "baseline_name": candidate["baseline_name"],
        "model_name": candidate["model_name"],
        "seed": candidate["seed"],
        "pass_fail": pass_fail,
        "score_total": score_total,
        "sub_scores": sub_scores,
        "aggregate_scores": aggregate_scores,
        "constraint_violations": constraint_violations,
        "simulation_metrics": simulated_metrics,
        "failure_tags": failure_tags,
        "failure_groups": failure_groups,
        "execution_log": execution_log,
        "runtime_stats": runtime_stats,
    }

    result_errors = validate_result_dict(result)
    if result_errors:
        raise ValueError(f"Invalid evaluator output: {result_errors}")
    return result
