from __future__ import annotations

import os
import socket
from pathlib import Path
from random import Random
from typing import Any

from pebench.integrations.reference_agent import get_reference_agent_assets


ALLOWED_SIMULATION_MODES = {"stub", "auto", "live", "mcp", "xmlrpc"}
DEFAULT_PLECS_XMLRPC_HOST = "127.0.0.1"
DEFAULT_PLECS_XMLRPC_PORT = 1080


def _ratio_delta(actual: float, expected: float) -> float:
    if expected == 0:
        return 0.0
    return abs(actual - expected) / abs(expected)


def _resolve_requested_mode(candidate: dict[str, Any], simulator_mode: str | None) -> str:
    requested = str(
        simulator_mode
        or candidate.get("simulation_config", {}).get("mode")
        or "auto"
    ).strip().lower()
    if requested not in ALLOWED_SIMULATION_MODES:
        return "auto"
    return requested


def _port_open(host: str, port: int, timeout: float = 0.15) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def plecs_xmlrpc_endpoint_from_env() -> tuple[str, int]:
    host = str(
        os.getenv("PEBENCH_PLECS_XMLRPC_HOST")
        or os.getenv("PLECS_XMLRPC_HOST")
        or DEFAULT_PLECS_XMLRPC_HOST
    ).strip()
    port_text = str(
        os.getenv("PEBENCH_PLECS_XMLRPC_PORT")
        or os.getenv("PLECS_XMLRPC_PORT")
        or DEFAULT_PLECS_XMLRPC_PORT
    ).strip()
    try:
        port = int(port_text)
    except ValueError:
        port = DEFAULT_PLECS_XMLRPC_PORT
    return host or DEFAULT_PLECS_XMLRPC_HOST, port


def _should_attempt_live(requested_mode: str, assets: dict[str, Any]) -> tuple[bool, str | None]:
    if requested_mode in {"live", "mcp", "xmlrpc"}:
        return True, None

    if str(os.getenv("PEBENCH_ENABLE_LIVE_SIM") or os.getenv("FLYBACKBENCH_ENABLE_LIVE_SIM") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return True, None

    if assets["available"].get("plecs_mcp"):
        command = str(os.getenv("REFERENCE_AGENT_PLECS_MCP_COMMAND", "")).strip()
        args = str(os.getenv("REFERENCE_AGENT_PLECS_MCP_ARGS", "")).strip()
        if command or args:
            return True, None

    plecs_host, plecs_port = plecs_xmlrpc_endpoint_from_env()
    if assets["available"].get("plecs_xmlrpc") and _port_open(plecs_host, plecs_port):
        return True, None

    return False, "auto mode skipped live probing because no ready circuit-simulation backend was detected"


def _estimate_secondary_reverse_voltage(task: dict[str, Any], candidate: dict[str, Any]) -> float:
    theory = candidate["theoretical_design"]
    output_voltage = float(task["structured_spec"]["output"]["voltage_v"])
    input_max = float(task["structured_spec"]["input_range_volts"]["max"])
    domain = str(task["structured_spec"]["input_range_volts"]["domain"]).lower()
    dc_bus_max = input_max if domain == "dc" else input_max * 1.414
    turns_ratio = max(float(theory["turns_ratio_primary_to_secondary"]), 1.1)
    return round(output_voltage + dc_bus_max / turns_ratio, 2)


def _build_live_simulation_params(task: dict[str, Any], candidate: dict[str, Any]) -> dict[str, float]:
    theory = candidate["theoretical_design"]
    output = task["structured_spec"]["output"]
    meta = candidate.get("metadata", {})
    reference_agent_design = meta.get("reference_agent_design", {})
    reference_agent_bom = meta.get("reference_agent_bom", {})
    mosfet_meta = reference_agent_bom.get("mosfet", {})
    diode_meta = reference_agent_bom.get("diode", {})

    input_max = float(task["structured_spec"]["input_range_volts"]["max"])
    domain = str(task["structured_spec"]["input_range_volts"]["domain"]).lower()
    vin = input_max if domain == "dc" else input_max * 1.414
    turns_ratio = max(float(theory["turns_ratio_primary_to_secondary"]), 1.1)
    np_turns = int(max(16, round(float(reference_agent_design.get("primary_turns", 36)))))
    ns_turns = int(max(1, round(np_turns / turns_ratio)))

    return {
        "Vin": vin,
        "Vref": float(output["voltage_v"]),
        "Ro": max(1.0, float(output["voltage_v"]) / max(0.1, float(output["current_a"]))),
        "fs": float(theory["switching_frequency_khz"]) * 1000.0,
        "Lp": float(theory["magnetizing_inductance_uh"]) * 1e-6,
        "Np": np_turns,
        "Ns": ns_turns,
        "n": round(np_turns / ns_turns, 4),
        "Co": 470e-6,
        "Rsn": float(reference_agent_design.get("snubber_r", 1000.0)),
        "Csn": float(reference_agent_design.get("snubber_c", 1e-9)),
        "PI_Upper": min(0.95, float(theory["duty_cycle_max"]) + 0.08),
        "Tstop": 0.08,
        "Ron": float(mosfet_meta.get("r_ds_on_ohm", 0.38) or 0.38),
        "Vf": float(diode_meta.get("v_f_v", 0.62) or 0.62),
        "Rdiode": float(diode_meta.get("r_diode_ohm", 0.04) or 0.04),
        "Resr": float(reference_agent_design.get("output_cap_esr_ohm", 0.06)),
    }


def _normalize_live_metrics(
    task: dict[str, Any],
    candidate: dict[str, Any],
    requested_mode: str,
    backend_used: str,
    raw_result: dict[str, Any],
) -> dict[str, Any]:
    raw_data = raw_result.get("raw_data", {}) if isinstance(raw_result, dict) else {}
    claims = candidate["final_claimed_metrics"]
    startup_success = bool(raw_result.get("is_converged")) and float(raw_data.get("Efficiency", 0.0) or 0.0) > 0.0
    waveforms_path = raw_data.get("waveforms_absolute_path")
    if waveforms_path:
        waveforms_exists = Path(str(waveforms_path)).exists()
    else:
        waveforms_exists = False

    return {
        "simulator_mode": requested_mode,
        "backend_requested": requested_mode,
        "backend_used": backend_used,
        "fallback_used": False,
        "fallback_reason": None,
        "startup_success": startup_success,
        "observed_efficiency_percent": round(float(raw_data.get("Efficiency", 0.0) or 0.0) * 100.0, 2),
        "target_efficiency_percent": float(task["structured_spec"]["targets"]["efficiency_percent"]),
        "observed_ripple_mv": round(float(raw_data.get("Vout_Ripple", raw_data.get("Vout_Ripple", 0.0)) or 0.0) * 1000.0, 2),
        "target_ripple_mv": float(task["structured_spec"]["targets"]["ripple_mv"]),
        "mosfet_voltage_stress_v": round(float(raw_data.get("Vds_Max", 0.0) or 0.0), 2),
        "diode_reverse_voltage_v": _estimate_secondary_reverse_voltage(task, candidate),
        "flux_density_mt": round(float(claims["flux_density_mt"]), 2),
        "estimated_cost_usd": round(float(claims["estimated_cost_usd"]), 2),
        "design_error": None,
        "simulator_version": "reference-agent-formula-stub-v1",
        "waveforms_path": waveforms_path,
        "waveforms_available": waveforms_exists,
    }


def run_simulator_stub(
    task: dict[str, Any],
    candidate: dict[str, Any],
    requested_mode: str,
    invalid_bom: bool = False,
    *,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    reference = task["reference_design"]
    theory = candidate["theoretical_design"]
    claims = candidate["final_claimed_metrics"]
    spec = task["structured_spec"]

    rng = Random(f"{task['task_id']}:{candidate['baseline_name']}:{candidate['seed']}")

    design_error = min(
        1.5,
        (
            1.1 * _ratio_delta(
                theory["turns_ratio_primary_to_secondary"],
                reference["turns_ratio_primary_to_secondary"],
            )
            + 0.9
            * _ratio_delta(
                theory["magnetizing_inductance_uh"],
                reference["magnetizing_inductance_uh"],
            )
            + 0.8
            * _ratio_delta(
                theory["switching_frequency_khz"],
                reference["switching_frequency_khz"],
            )
            + 1.2 * abs(theory["duty_cycle_max"] - reference["duty_cycle_max"]) / 0.1
            + 1.0
            * _ratio_delta(
                theory["primary_peak_current_a"],
                reference["primary_peak_current_a"],
            )
        )
        / 5.0,
    )

    optimism_penalty = max(
        0.0,
        (claims["efficiency_percent"] - reference["expected_metrics"]["efficiency_percent"]) * 0.12,
    )
    startup_success = (
        design_error < 0.48
        and not invalid_bom
        and spec["switching_frequency_khz"]["min"]
        <= theory["switching_frequency_khz"]
        <= spec["switching_frequency_khz"]["max"]
    )

    observed_efficiency = (
        reference["expected_metrics"]["efficiency_percent"]
        - 11.0 * design_error
        - optimism_penalty
        - rng.uniform(0.2, 1.2)
    )
    observed_ripple = (
        reference["expected_metrics"]["ripple_mv"]
        * (1.0 + 1.5 * design_error)
        + rng.uniform(0.5, 6.0)
    )
    observed_mosfet_stress = (
        reference["expected_metrics"]["mosfet_voltage_stress_v"] * (1.0 + 0.45 * design_error)
    )
    observed_diode_stress = (
        reference["expected_metrics"]["diode_reverse_voltage_v"] * (1.0 + 0.35 * design_error)
    )
    observed_flux_density = (
        reference["expected_metrics"]["flux_density_mt"] * (1.0 + 0.55 * design_error)
    )

    if not startup_success:
        observed_efficiency -= 3.5
        observed_ripple *= 1.2

    return {
        "simulator_mode": requested_mode,
        "backend_requested": requested_mode,
        "backend_used": "stub",
        "fallback_used": fallback_reason is not None,
        "fallback_reason": fallback_reason,
        "startup_success": startup_success,
        "observed_efficiency_percent": round(observed_efficiency, 2),
        "target_efficiency_percent": spec["targets"]["efficiency_percent"],
        "observed_ripple_mv": round(observed_ripple, 2),
        "target_ripple_mv": spec["targets"]["ripple_mv"],
        "mosfet_voltage_stress_v": round(observed_mosfet_stress, 2),
        "diode_reverse_voltage_v": round(observed_diode_stress, 2),
        "flux_density_mt": round(observed_flux_density, 2),
        "estimated_cost_usd": round(claims["estimated_cost_usd"], 2),
        "design_error": round(design_error, 4),
        "simulator_version": "stub-v1",
        "waveforms_available": False,
    }


def run_simulation(
    task: dict[str, Any],
    candidate: dict[str, Any],
    simulator_mode: str | None = None,
    invalid_bom: bool = False,
) -> dict[str, Any]:
    requested_mode = _resolve_requested_mode(candidate, simulator_mode)
    if requested_mode == "stub":
        return run_simulator_stub(
            task=task,
            candidate=candidate,
            requested_mode=requested_mode,
            invalid_bom=invalid_bom,
        )

    assets = get_reference_agent_assets()
    should_attempt_live, skip_reason = _should_attempt_live(requested_mode, assets)
    if not should_attempt_live:
        return run_simulator_stub(
            task=task,
            candidate=candidate,
            requested_mode=requested_mode,
            invalid_bom=invalid_bom,
            fallback_reason=skip_reason,
        )

    params = _build_live_simulation_params(task, candidate)
    errors: list[str] = []
    backends_tried: list[str] = []
    raw_result: dict[str, Any] | None = None
    backend_used = "stub"

    if requested_mode in {"auto", "live", "mcp"}:
        mcp_client = assets["modules"].get("plecs_mcp_client")
        if mcp_client is not None and hasattr(mcp_client, "run_plecs_simulation_via_mcp"):
            backends_tried.append("mcp")
            try:
                mcp_result = mcp_client.run_plecs_simulation_via_mcp(params)
                if isinstance(mcp_result, dict) and mcp_result.get("ok") and isinstance(mcp_result.get("result"), dict):
                    raw_result = mcp_result["result"]
                    backend_used = "mcp"
                else:
                    errors.append(str((mcp_result or {}).get("error") or "mcp backend returned no result"))
            except Exception as exc:
                errors.append(f"mcp backend failed: {exc}")
        else:
            errors.append("mcp backend unavailable in current environment")

    if raw_result is None and requested_mode in {"auto", "live", "xmlrpc", "mcp"}:
        xmlrpc_runner = assets["modules"].get("plecs_interface")
        if xmlrpc_runner is not None and hasattr(xmlrpc_runner, "run_plecs_simulation"):
            backends_tried.append("xmlrpc")
            try:
                xmlrpc_result = xmlrpc_runner.run_plecs_simulation(params)
                if isinstance(xmlrpc_result, dict) and xmlrpc_result.get("is_converged"):
                    raw_result = xmlrpc_result
                    backend_used = "xmlrpc"
                else:
                    errors.append("xmlrpc backend did not converge or returned empty payload")
            except Exception as exc:
                errors.append(f"xmlrpc backend failed: {exc}")
        else:
            errors.append("xmlrpc backend unavailable in current environment")

    if raw_result is None:
        reason = "; ".join(dict.fromkeys(errors)) if errors else "live backend unavailable"
        metrics = run_simulator_stub(
            task=task,
            candidate=candidate,
            requested_mode=requested_mode,
            invalid_bom=invalid_bom,
            fallback_reason=reason,
        )
        metrics["backend_attempts"] = backends_tried
        return metrics

    metrics = _normalize_live_metrics(
        task=task,
        candidate=candidate,
        requested_mode=requested_mode,
        backend_used=backend_used,
        raw_result=raw_result,
    )
    metrics["backend_attempts"] = backends_tried
    return metrics
