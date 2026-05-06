from __future__ import annotations

from typing import Any


def build_reference_candidate(
    task: dict[str, Any],
    *,
    model_name: str = "reference-design",
    seed: int = 0,
    simulator_mode: str = "stub",
) -> dict[str, Any]:
    """Build a candidate from the task's feasible reference design.

    This is not a leaderboard baseline. It is a reviewer-facing feasibility
    anchor used by smoke tests and artifact validation.
    """

    topology = str(task.get("topology") or task.get("reference_design", {}).get("topology") or "flyback")
    if topology in {"buck", "boost", "buck_boost"}:
        return _build_topology_full_reference(task, model_name=model_name, seed=seed, simulator_mode=simulator_mode)
    if topology == "three_phase_inverter":
        return _build_inverter_reference(task, model_name=model_name, seed=seed, simulator_mode=simulator_mode)
    return _build_flyback_reference(task, model_name=model_name, seed=seed, simulator_mode=simulator_mode)


def _base(task: dict[str, Any], model_name: str, seed: int) -> dict[str, Any]:
    return {
        "task_id": task["task_id"],
        "baseline_name": "reference_design",
        "model_name": model_name,
        "seed": seed,
        "design_rationale": "Feasible reference-design candidate emitted for artifact validation.",
        "uncertainty_or_escalation_flag": {
            "requires_human_review": False,
            "reason": "reference feasibility anchor",
        },
        "metadata": {
            "candidate_kind": "reference_feasibility_anchor",
            "leaderboard_baseline": False,
        },
    }


def _build_flyback_reference(task: dict[str, Any], *, model_name: str, seed: int, simulator_mode: str) -> dict[str, Any]:
    spec = task["structured_spec"]
    reference = task["reference_design"]
    metrics = reference["expected_metrics"]
    candidate = _base(task, model_name, seed)
    candidate.update(
        {
            "parsed_spec": {
                "input_range_volts": dict(spec["input_range_volts"]),
                "output": dict(spec["output"]),
                "targets": dict(spec["targets"]),
            },
            "theoretical_design": {
                "topology": reference["topology"],
                "turns_ratio_primary_to_secondary": reference["turns_ratio_primary_to_secondary"],
                "magnetizing_inductance_uh": reference["magnetizing_inductance_uh"],
                "switching_frequency_khz": reference["switching_frequency_khz"],
                "duty_cycle_max": reference["duty_cycle_max"],
                "primary_peak_current_a": reference["primary_peak_current_a"],
            },
            "bom": [
                {"category": slot, "part_id": part_id, "source": "reference_design"}
                for slot, part_id in reference["selected_components"].items()
            ],
            "simulation_config": {
                "mode": simulator_mode,
                "max_sim_calls": 1,
                "fallback_policy": "stub_for_artifact_validation",
            },
            "final_claimed_metrics": {
                "efficiency_percent": metrics["efficiency_percent"],
                "ripple_mv": metrics["ripple_mv"],
                "mosfet_voltage_stress_v": metrics["mosfet_voltage_stress_v"],
                "diode_reverse_voltage_v": metrics["diode_reverse_voltage_v"],
                "flux_density_mt": metrics["flux_density_mt"],
                "estimated_cost_usd": reference["cost_proxy_usd"],
            },
        }
    )
    return candidate


def _build_topology_full_reference(task: dict[str, Any], *, model_name: str, seed: int, simulator_mode: str) -> dict[str, Any]:
    spec = task["structured_spec"]
    reference = task["reference_design"]
    metrics = reference["expected_metrics"]
    candidate = _base(task, model_name, seed)
    candidate.update(
        {
            "parsed_spec": {
                "input_range_volts": dict(spec["input_range_volts"]),
                "output": dict(spec["output"]),
                "targets": dict(spec["targets"]),
            },
            "topology_decision": {
                "selected_topology": reference["topology"],
                "rationale": "matches task topology and reference feasibility anchor",
            },
            "theoretical_design": {
                "topology": reference["topology"],
                "duty_cycle_nominal": reference["duty_cycle_nominal"],
                "inductance_uh": reference["inductance_uh"],
                "output_capacitance_uf": reference["output_capacitance_uf"],
                "switching_frequency_khz": reference["switching_frequency_khz"],
                "inductor_ripple_current_a": reference["inductor_ripple_current_a"],
                "switch_peak_current_a": reference["switch_peak_current_a"],
            },
            "bom": [
                {"category": slot, "part_id": part_id, "source": "reference_design"}
                for slot, part_id in reference["selected_components"].items()
            ],
            "simulation_config": {
                "mode": simulator_mode,
                "max_sim_calls": 1,
                "fallback_policy": "formula_stub_for_artifact_validation",
            },
            "final_claimed_metrics": {
                "efficiency_percent": metrics["efficiency_percent"],
                "ripple_mv": metrics["ripple_mv"],
                "mosfet_voltage_stress_v": metrics["mosfet_voltage_stress_v"],
                "diode_reverse_voltage_v": metrics["diode_reverse_voltage_v"],
                "inductor_peak_current_a": metrics["inductor_peak_current_a"],
                "estimated_cost_usd": reference["cost_proxy_usd"],
            },
        }
    )
    return candidate


def _build_inverter_reference(task: dict[str, Any], *, model_name: str, seed: int, simulator_mode: str) -> dict[str, Any]:
    spec = task["structured_spec"]
    reference = task["reference_design"]
    metrics = reference["expected_metrics"]
    candidate = _base(task, model_name, seed)
    candidate.update(
        {
            "parsed_spec": {
                "dc_link_voltage_v": dict(spec["dc_link_voltage_v"]),
                "output": dict(spec["output"]),
                "targets": dict(spec["targets"]),
            },
            "topology_decision": {
                "selected_topology": reference["topology"],
                "rationale": "matches three-phase inverter task and reference feasibility anchor",
            },
            "theoretical_design": {
                "topology": reference["topology"],
                "dc_link_voltage_v": reference["dc_link_voltage_v"],
                "modulation_index": reference["modulation_index"],
                "switching_frequency_khz": reference["switching_frequency_khz"],
                "phase_current_rms_a": reference["phase_current_rms_a"],
            },
            "bom": [
                {"category": slot, "part_id": part_id, "source": "reference_design"}
                for slot, part_id in reference["selected_components"].items()
            ],
            "simulation_config": {
                "mode": simulator_mode,
                "max_sim_calls": 1,
                "fallback_policy": "formula_stub_for_artifact_validation",
            },
            "final_claimed_metrics": {
                "efficiency_percent": metrics["efficiency_percent"],
                "thd_percent": metrics["thd_percent"],
                "dc_link_ripple_a": metrics["dc_link_ripple_a"],
                "device_stress_v": metrics["device_stress_v"],
                "phase_current_rms_a": metrics["phase_current_rms_a"],
                "estimated_cost_usd": reference["cost_proxy_usd"],
            },
        }
    )
    return candidate
