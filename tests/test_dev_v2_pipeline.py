from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

from pebench.adapters.registry import BASELINE_METADATA, get_baseline, get_baseline_metadata
from pebench.evaluator.core import evaluate_candidate
from pebench.tasks.schema import iter_task_files, load_task
from pebench.utils.paths import DEFAULT_TASK_DIR
from scripts.build_literature_provenance import main as build_provenance_main
from scripts.run_suite import run_task_with_baseline


def test_baseline_registry_metadata_covers_all_dev_v2_baselines() -> None:
    assert sorted(BASELINE_METADATA) == [
        "direct_prompting",
        "generic_two_role_mas",
        "pe_gpt_style",
        "reference_agent",
        "single_agent_retry",
        "single_agent_same_tools",
        "structured_output_only",
        "text_only_self_refine",
    ]
    assert get_baseline_metadata("single_agent_retry").display_label == "Single-Agent+Retry"
    assert get_baseline_metadata("generic_two_role_mas").family_group == "generic_mas_baselines"
    assert get_baseline_metadata("reference_agent__wo_formula_guardrails").family_group == "external_pe_baselines"


def test_single_agent_retry_tracks_attempt_history(monkeypatch) -> None:
    task = load_task(iter_task_files(DEFAULT_TASK_DIR)[0])
    baseline = get_baseline("single_agent_retry")
    call_counter = {"count": 0}

    def fake_evaluate_candidate(*, task, candidate, simulator_mode):  # type: ignore[override]
        call_counter["count"] += 1
        failure_tags = [] if call_counter["count"] == 2 else ["Invalid or Unsafe BOM"]
        return {
            "task_id": task["task_id"],
            "difficulty_tier": task["difficulty_tier"],
            "baseline_name": candidate["baseline_name"],
            "model_name": candidate["model_name"],
            "seed": candidate["seed"],
            "pass_fail": call_counter["count"] == 2,
            "score_total": 98.0 if call_counter["count"] == 2 else 71.0,
            "sub_scores": {},
            "aggregate_scores": {"performance_targets": 0.5, "performance_target_points": 22.5},
            "constraint_violations": [],
            "simulation_metrics": {},
            "failure_tags": failure_tags,
            "failure_groups": ["Performance Requirement Miss"] if failure_tags else [],
            "execution_log": [],
            "runtime_stats": {
                "evaluation_mode": simulator_mode,
                "elapsed_seconds": 0.1,
                "sim_calls": call_counter["count"],
                "iterations": call_counter["count"],
                "backend_requested": "stub",
                "backend_used": "stub",
                "backend_attempts": ["stub"],
                "fallback_used": False,
                "fallback_reason": None,
                "reference_agent_assets_used": False,
                "reference_agent_available_modules": {},
                "ablations": candidate["metadata"]["ablations"],
                "claim_status": "estimated_only",
            },
        }

    monkeypatch.setattr("scripts.run_suite.evaluate_candidate", fake_evaluate_candidate)

    candidate, result, feedback_history = run_task_with_baseline(
        baseline=baseline,
        task=task,
        model_name="heuristic-v0",
        seed=1,
        simulator_mode="stub",
    )

    assert len(feedback_history) == 2
    assert candidate["metadata"]["retry_total_attempts"] == 2
    assert result["runtime_stats"]["retry_total_attempts"] == 2
    assert result["runtime_stats"]["sim_calls"] == 2
    assert feedback_history[0]["failure_tags"] == ["Invalid or Unsafe BOM"]


def test_disable_correction_memory_propagates_to_result() -> None:
    task = load_task(iter_task_files(DEFAULT_TASK_DIR)[0])
    baseline = get_baseline("reference_agent", disable_correction_memory=True)
    candidate = baseline.generate(task=task, model_name="gpt-4.1-mini", seed=1, simulator_mode="stub")
    result = evaluate_candidate(task=task, candidate=candidate, simulator_mode="stub")

    assert candidate["metadata"]["ablations"]["disable_correction_memory"] is True
    assert result["runtime_stats"]["ablations"]["disable_correction_memory"] is True
    assert candidate["simulation_config"]["max_iterations"] == 1
    assert candidate["simulation_config"]["max_sim_calls"] == 1


def test_build_literature_provenance_outputs_required_files(monkeypatch, tmp_path) -> None:
    default_seed_file = Path("sources/flyback_literature_20260408_massive/curated/benchmark_seed_candidates.csv")
    if not default_seed_file.exists():
        pytest.skip("literature source exports are intentionally excluded from the anonymous artifact")
    monkeypatch.setattr(sys, "argv", ["build_literature_provenance.py", "--output-root", str(tmp_path)])
    assert build_provenance_main() == 0

    task_rows = list(csv.DictReader((tmp_path / "task_provenance.csv").open()))
    all_rows = list(csv.DictReader((tmp_path / "task_provenance_all.csv").open()))
    holdout_rows = list(csv.DictReader((tmp_path / "holdout_candidates.csv").open()))

    assert len(task_rows) == 24
    assert len(all_rows) == 30
    assert len(holdout_rows) == 16
    assert all(row["source_url"] or row["source_doi"] for row in holdout_rows)
    assert all("validated_reference_design" in row and "measured_results_present" in row for row in holdout_rows)
