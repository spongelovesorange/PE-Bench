from __future__ import annotations

from pathlib import Path

import pebench.evaluator.core as evaluator_core
from pebench.adapters.registry import get_baseline
from pebench.evaluator.core import evaluate_candidate
from pebench.evaluator.result_schema import REQUIRED_RESULT_FIELDS, validate_result_dict
from pebench.tasks.schema import iter_task_files, load_task
from pebench.utils.paths import DEFAULT_TASK_DIR


def test_evaluator_returns_stable_schema() -> None:
    task = load_task(iter_task_files(DEFAULT_TASK_DIR)[0])
    candidate = get_baseline("reference_agent").generate(
        task=task,
        model_name="heuristic-v0",
        seed=1,
        simulator_mode="stub",
    )
    result = evaluate_candidate(task=task, candidate=candidate, simulator_mode="stub")

    assert REQUIRED_RESULT_FIELDS.issubset(result.keys())
    assert validate_result_dict(result) == []
    assert result["simulation_metrics"]["simulator_mode"] == "stub"
    assert result["runtime_stats"]["backend_used"] == "stub"
    assert isinstance(result["runtime_stats"]["fallback_used"], bool)
    assert isinstance(result["score_total"], float)
    assert "performance_targets" in result["aggregate_scores"]
    assert 0.0 <= result["aggregate_scores"]["performance_targets"] <= 1.0
    assert isinstance(result["failure_groups"], list)


def test_evaluator_backfills_verified_claims_from_live_sim(monkeypatch) -> None:
    task = load_task(Path(DEFAULT_TASK_DIR) / "easy_acdc_12v1a.yaml")
    candidate = get_baseline("reference_agent").generate(
        task=task,
        model_name="gpt-4.1-mini",
        seed=1,
        simulator_mode="stub",
    )

    def fake_run_simulation(*args, **kwargs):
        return {
            "simulator_mode": "auto",
            "backend_requested": "auto",
            "backend_used": "mcp",
            "fallback_used": False,
            "fallback_reason": None,
            "startup_success": True,
            "observed_efficiency_percent": 88.4,
            "target_efficiency_percent": 84.0,
            "observed_ripple_mv": 21.5,
            "target_ripple_mv": 55.0,
            "mosfet_voltage_stress_v": 138.0,
            "diode_reverse_voltage_v": 64.0,
            "flux_density_mt": 176.0,
            "estimated_cost_usd": 3.5,
            "design_error": 0.0,
            "simulator_version": "fake-live",
            "waveforms_available": True,
        }

    def fake_formula_metrics(*args, **kwargs):
        return {
            "efficiency_percent": 88.4,
            "efficiency_raw_percent": 88.4,
            "mode": "trusted_formula",
            "confidence": "high",
            "flux_density_mt": 176.0,
        }

    monkeypatch.setattr(evaluator_core, "run_simulation", fake_run_simulation)
    monkeypatch.setattr(evaluator_core, "estimate_formula_metrics", fake_formula_metrics)

    result = evaluate_candidate(task=task, candidate=candidate, simulator_mode="auto")

    assert candidate["metadata"]["claim_metrics"]["status"] == "verified_from_live_sim"
    assert candidate["metadata"]["claim_metrics"]["estimated_only"] is False
    assert candidate["final_claimed_metrics"]["efficiency_percent"] == 88.4
    assert candidate["final_claimed_metrics"]["ripple_mv"] == 21.5
    assert candidate["final_claimed_metrics"]["mosfet_voltage_stress_v"] == 138.0
    assert candidate["final_claimed_metrics"]["diode_reverse_voltage_v"] == 64.0
    assert result["runtime_stats"]["claim_status"] == "verified_from_live_sim"
    assert result["aggregate_scores"]["performance_targets"] > 0.0
