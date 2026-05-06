from __future__ import annotations

from typing import Any


REQUIRED_CANDIDATE_FIELDS = {
    "task_id",
    "baseline_name",
    "model_name",
    "seed",
    "parsed_spec",
    "design_rationale",
    "theoretical_design",
    "bom",
    "simulation_config",
    "final_claimed_metrics",
    "uncertainty_or_escalation_flag",
    "metadata",
}

REQUIRED_THEORY_FIELDS = {
    "topology",
    "turns_ratio_primary_to_secondary",
    "magnetizing_inductance_uh",
    "switching_frequency_khz",
    "duty_cycle_max",
    "primary_peak_current_a",
}

REQUIRED_CLAIMED_METRIC_FIELDS = {
    "efficiency_percent",
    "ripple_mv",
    "mosfet_voltage_stress_v",
    "diode_reverse_voltage_v",
    "flux_density_mt",
    "estimated_cost_usd",
}

ALLOWED_SIMULATION_MODES = {"stub", "auto", "live", "mcp", "xmlrpc"}


def validate_candidate_dict(candidate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing_fields = REQUIRED_CANDIDATE_FIELDS - candidate.keys()
    if missing_fields:
        errors.append(f"Missing candidate fields: {sorted(missing_fields)}")
        return errors

    if not isinstance(candidate["parsed_spec"], dict):
        errors.append("parsed_spec must be a mapping")

    theory = candidate["theoretical_design"]
    if not isinstance(theory, dict):
        errors.append("theoretical_design must be a mapping")
    else:
        missing_theory = REQUIRED_THEORY_FIELDS - theory.keys()
        if missing_theory:
            errors.append(f"Missing theoretical_design fields: {sorted(missing_theory)}")

    if not isinstance(candidate["bom"], list) or not candidate["bom"]:
        errors.append("bom must be a non-empty list")

    if not isinstance(candidate["simulation_config"], dict):
        errors.append("simulation_config must be a mapping")
    else:
        mode = candidate["simulation_config"].get("mode")
        if mode not in ALLOWED_SIMULATION_MODES:
            errors.append(
                f"simulation_config.mode must be one of {sorted(ALLOWED_SIMULATION_MODES)}"
            )

    claimed = candidate["final_claimed_metrics"]
    if not isinstance(claimed, dict):
        errors.append("final_claimed_metrics must be a mapping")
    else:
        missing_claimed = REQUIRED_CLAIMED_METRIC_FIELDS - claimed.keys()
        if missing_claimed:
            errors.append(f"Missing final_claimed_metrics fields: {sorted(missing_claimed)}")

    if not isinstance(candidate["uncertainty_or_escalation_flag"], dict):
        errors.append("uncertainty_or_escalation_flag must be a mapping")

    if not isinstance(candidate["metadata"], dict):
        errors.append("metadata must be a mapping")

    return errors
