from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.adapters.registry import BASELINE_REGISTRY, get_baseline
from pebench.baselines.reference import build_reference_candidate
from pebench.baselines.inverter import INVERTER_BASELINES, get_inverter_baseline
from pebench.baselines.topology_scout import SCOUT_BASELINES, get_topology_scout_baseline
from pebench.evaluator.pebench import evaluate_pebench_candidate
from pebench.tasks.inverter_schema import iter_inverter_task_files, load_inverter_task
from pebench.tasks.schema import filter_tasks, iter_task_files, load_task, sort_tasks
from pebench.tasks.topology_full import iter_scout_task_files, load_scout_task
from pebench.utils.io import dump_json
from pebench.utils.paths import (
    DEFAULT_FLYBACK_TASK_DIR,
    DEFAULT_INVERTER_TASK_DIR,
    DEFAULT_PEBENCH_RESULTS_ROOT,
    DEFAULT_TASK_DIR,
    DEFAULT_TOPOLOGY_FULL_TASK_DIR,
)


def _sanitize_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "unnamed"


def _apply_runtime_overrides(args: argparse.Namespace) -> None:
    if args.api_base:
        os.environ["PEBENCH_LLM_BASE_URL"] = args.api_base
    if args.api_key_env:
        api_key = os.getenv(args.api_key_env, "").strip()
        if api_key:
            os.environ["PEBENCH_LLM_API_KEY"] = api_key
    if args.temperature is not None:
        os.environ["PEBENCH_LLM_TEMPERATURE"] = str(args.temperature)

    if not os.getenv("PEBENCH_LLM_API_KEY") and os.getenv("FLYBACKBENCH_LLM_API_KEY"):
        os.environ["PEBENCH_LLM_API_KEY"] = os.getenv("FLYBACKBENCH_LLM_API_KEY", "")
    if not os.getenv("PEBENCH_LLM_BASE_URL") and os.getenv("FLYBACKBENCH_LLM_BASE_URL"):
        os.environ["PEBENCH_LLM_BASE_URL"] = os.getenv("FLYBACKBENCH_LLM_BASE_URL", "")


def _resolve_flyback_tasks_dir(path_value: str) -> Path:
    requested = Path(path_value)
    if list(requested.glob("*.yaml")):
        return requested
    fallback = DEFAULT_TASK_DIR
    if list(fallback.glob("*.yaml")):
        return fallback
    return requested


def _filter_scout_tasks(
    tasks: list[dict[str, Any]],
    *,
    topology: str | None,
    difficulty_tiers: set[str] | None,
) -> list[dict[str, Any]]:
    if topology and topology != "all":
        tasks = [task for task in tasks if task.get("topology") == topology]
    if difficulty_tiers:
        tasks = [task for task in tasks if task.get("difficulty_tier") in difficulty_tiers]
    order = {"easy": 0, "medium": 1, "hard": 2, "boundary": 3, "stress": 4}
    return sorted(tasks, key=lambda task: (task.get("topology"), order.get(task.get("difficulty_tier"), 99), task.get("task_id")))


def _write_per_task_summary(rows: list[dict[str, Any]], suite_dir: Path) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with (suite_dir / "per_task_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_suite_summary(
    *,
    suite_dir: Path,
    suite_id: str,
    baseline_name: str,
    model_name: str,
    seed: int,
    track: str,
    topology: str,
    task_ids: list[str],
    results: list[dict[str, Any]],
    ablations: dict[str, Any],
) -> dict[str, Any]:
    successes = sum(1 for result in results if result.get("pass_fail"))
    mean_score = sum(float(result.get("score_total", 0.0)) for result in results) / max(1, len(results))
    summary = {
        "suite_id": suite_id,
        "baseline_name": baseline_name,
        "model_name": model_name,
        "seed": seed,
        "track": track,
        "topology": topology,
        "num_tasks": len(results),
        "successes": successes,
        "vtsr": round(successes / max(1, len(results)), 4),
        "mean_score": round(mean_score, 4),
        "task_ids": task_ids,
        "ablations": ablations,
    }
    dump_json(summary, suite_dir / "suite_summary.json")
    return summary


def run_flyback_suite(args: argparse.Namespace, output_root: Path) -> Path:
    baseline = None
    if args.baseline != "reference_design":
        baseline = get_baseline(
            args.baseline,
            disable_formula_guardrails=args.disable_formula_guardrails,
            disable_component_grounding=args.disable_component_grounding,
            disable_correction_memory=args.disable_correction_memory,
        )
    tasks_dir = _resolve_flyback_tasks_dir(args.tasks_dir or str(DEFAULT_FLYBACK_TASK_DIR))
    tasks = [load_task(path) for path in iter_task_files(tasks_dir)]
    difficulty_tiers = set(args.difficulty_tier) if args.difficulty_tier else None
    tasks = filter_tasks(
        tasks,
        split=args.task_split if args.task_split != "all" else None,
        track="autonomous_flyback_design",
        difficulty_tiers=difficulty_tiers,
    )
    tasks = sort_tasks(tasks)[: args.task_limit]

    baseline_name = "reference_design" if baseline is None else baseline.run_name
    suite_id = f"{baseline_name}__{_sanitize_token(args.model)}__seed{args.seed}__flyback__{len(tasks)}tasks"
    suite_dir = output_root / "flyback" / "suites" / suite_id
    if suite_dir.exists():
        shutil.rmtree(suite_dir)
    candidates_dir = suite_dir / "candidates"
    results_dir = suite_dir / "task_results"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for task in tasks:
        try:
            if baseline is None:
                candidate = build_reference_candidate(
                    task,
                    model_name=args.model,
                    seed=args.seed,
                    simulator_mode=args.simulator_mode,
                )
            else:
                candidate = baseline.generate(
                    task=task,
                    model_name=args.model,
                    seed=args.seed,
                    simulator_mode=args.simulator_mode,
                )
            result = evaluate_pebench_candidate(task, candidate, simulator_mode=args.simulator_mode)
        except Exception as error:
            candidate = _error_candidate(task, baseline_name, args.model, args.seed, error)
            result = _error_result(task, baseline_name, args.model, args.seed, error)
        dump_json(candidate, candidates_dir / f"{task['task_id']}.json")
        dump_json(result, results_dir / f"{task['task_id']}.json")
        rows.append(
            {
                "track": "flyback",
                "topology": "flyback",
                "task_id": task["task_id"],
                "difficulty_tier": task["difficulty_tier"],
                "pass_fail": result["pass_fail"],
                "score_total": result["score_total"],
                "failure_tags": ";".join(result.get("failure_tags", [])),
                "backend_used": result.get("runtime_stats", {}).get("backend_used"),
                "vtsr_pass": result.get("vtsr_pass"),
            }
        )
        results.append(result)

    _write_per_task_summary(rows, suite_dir)
    summary = _write_suite_summary(
        suite_dir=suite_dir,
        suite_id=suite_id,
        baseline_name=baseline_name,
        model_name=args.model,
        seed=args.seed,
        track="flyback",
        topology="flyback",
        task_ids=[task["task_id"] for task in tasks],
        results=results,
        ablations={
            "disable_formula_guardrails": args.disable_formula_guardrails,
            "disable_component_grounding": args.disable_component_grounding,
            "disable_correction_memory": args.disable_correction_memory,
        },
    )
    dump_json(summary, suite_dir / "summary.json")
    dump_json(vars(args), suite_dir / "run_config.json")
    return suite_dir


def run_topology_full_suite(args: argparse.Namespace, output_root: Path) -> Path:
    baseline = None
    if args.baseline != "reference_design":
        baseline = get_topology_scout_baseline(
            args.baseline,
            disable_formula_guardrails=args.disable_formula_guardrails,
            disable_component_grounding=args.disable_component_grounding,
            disable_correction_memory=args.disable_correction_memory,
        )
    tasks_dir = Path(args.topology_tasks_dir or DEFAULT_TOPOLOGY_FULL_TASK_DIR)
    tasks = [load_scout_task(path) for path in iter_scout_task_files(tasks_dir)]
    difficulty_tiers = set(args.difficulty_tier) if args.difficulty_tier else None
    tasks = _filter_scout_tasks(tasks, topology=args.topology, difficulty_tiers=difficulty_tiers)[: args.task_limit]

    baseline_name = "reference_design" if baseline is None else baseline.run_name
    suite_id = f"{baseline_name}__{_sanitize_token(args.model)}__seed{args.seed}__{args.topology}__{len(tasks)}tasks"
    suite_dir = output_root / "topology_full" / "suites" / suite_id
    if suite_dir.exists():
        shutil.rmtree(suite_dir)
    candidates_dir = suite_dir / "candidates"
    results_dir = suite_dir / "task_results"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for task in tasks:
        try:
            if baseline is None:
                candidate = build_reference_candidate(task, model_name=args.model, seed=args.seed, simulator_mode="stub")
            else:
                candidate = baseline.generate(
                    task=task,
                    model_name=args.model,
                    seed=args.seed,
                )
            result = evaluate_pebench_candidate(task, candidate)
        except Exception as error:
            candidate = _error_candidate(task, baseline_name, args.model, args.seed, error)
            result = _error_result(task, baseline_name, args.model, args.seed, error)
        dump_json(candidate, candidates_dir / f"{task['task_id']}.json")
        dump_json(result, results_dir / f"{task['task_id']}.json")
        rows.append(
            {
                "track": "topology_full",
                "topology": task["topology"],
                "task_id": task["task_id"],
                "difficulty_tier": task["difficulty_tier"],
                "pass_fail": result["pass_fail"],
                "score_total": result["score_total"],
                "failure_tags": ";".join(result.get("failure_tags", [])),
                "backend_used": result.get("runtime_stats", {}).get("backend_used"),
                "vtsr_pass": result.get("vtsr_pass"),
            }
        )
        results.append(result)

    _write_per_task_summary(rows, suite_dir)
    summary = _write_suite_summary(
        suite_dir=suite_dir,
        suite_id=suite_id,
        baseline_name=baseline_name,
        model_name=args.model,
        seed=args.seed,
        track="topology_full",
        topology=args.topology,
        task_ids=[task["task_id"] for task in tasks],
        results=results,
        ablations={
            "disable_formula_guardrails": args.disable_formula_guardrails,
            "disable_component_grounding": args.disable_component_grounding,
            "disable_correction_memory": args.disable_correction_memory,
        },
    )
    dump_json(summary, suite_dir / "summary.json")
    dump_json(vars(args), suite_dir / "run_config.json")
    return suite_dir


def run_inverter_suite(args: argparse.Namespace, output_root: Path) -> Path:
    baseline = None
    if args.baseline != "reference_design":
        baseline = get_inverter_baseline(
            args.baseline,
            disable_formula_guardrails=args.disable_formula_guardrails,
            disable_component_grounding=args.disable_component_grounding,
            disable_correction_memory=args.disable_correction_memory,
        )
    tasks_dir = Path(args.inverter_tasks_dir or DEFAULT_INVERTER_TASK_DIR)
    tasks = [load_inverter_task(path) for path in iter_inverter_task_files(tasks_dir)]
    difficulty_tiers = set(args.difficulty_tier) if args.difficulty_tier else None
    if difficulty_tiers:
        tasks = [task for task in tasks if task.get("difficulty_tier") in difficulty_tiers]
    order = {"easy": 0, "medium": 1, "hard": 2, "boundary": 3, "stress": 4}
    tasks = sorted(tasks, key=lambda task: (order.get(task.get("difficulty_tier"), 99), task.get("task_id")))[: args.task_limit]

    baseline_name = "reference_design" if baseline is None else baseline.run_name
    suite_id = f"{baseline_name}__{_sanitize_token(args.model)}__seed{args.seed}__three_phase_inverter__{len(tasks)}tasks"
    suite_dir = output_root / "three_phase_inverter" / "suites" / suite_id
    if suite_dir.exists():
        shutil.rmtree(suite_dir)
    candidates_dir = suite_dir / "candidates"
    results_dir = suite_dir / "task_results"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for task in tasks:
        try:
            if baseline is None:
                candidate = build_reference_candidate(
                    task,
                    model_name=args.model,
                    seed=args.seed,
                    simulator_mode=args.simulator_mode,
                )
            else:
                candidate = baseline.generate(
                    task=task,
                    model_name=args.model,
                    seed=args.seed,
                    simulator_mode=args.simulator_mode,
                )
            result = evaluate_pebench_candidate(task, candidate, simulator_mode=args.simulator_mode)
        except Exception as error:
            candidate = _error_candidate(task, baseline_name, args.model, args.seed, error)
            result = _error_result(task, baseline_name, args.model, args.seed, error)
        dump_json(candidate, candidates_dir / f"{task['task_id']}.json")
        dump_json(result, results_dir / f"{task['task_id']}.json")
        rows.append(
            {
                "track": "three_phase_inverter",
                "topology": "three_phase_inverter",
                "task_id": task["task_id"],
                "difficulty_tier": task["difficulty_tier"],
                "pass_fail": result["pass_fail"],
                "score_total": result["score_total"],
                "failure_tags": ";".join(result.get("failure_tags", [])),
                "backend_used": result.get("runtime_stats", {}).get("backend_used"),
                "vtsr_pass": result.get("vtsr_pass"),
            }
        )
        results.append(result)

    _write_per_task_summary(rows, suite_dir)
    summary = _write_suite_summary(
        suite_dir=suite_dir,
        suite_id=suite_id,
        baseline_name=baseline_name,
        model_name=args.model,
        seed=args.seed,
        track="three_phase_inverter",
        topology="three_phase_inverter",
        task_ids=[task["task_id"] for task in tasks],
        results=results,
        ablations={
            "disable_formula_guardrails": args.disable_formula_guardrails,
            "disable_component_grounding": args.disable_component_grounding,
            "disable_correction_memory": args.disable_correction_memory,
        },
    )
    dump_json(summary, suite_dir / "summary.json")
    dump_json(vars(args), suite_dir / "run_config.json")
    return suite_dir


def _error_candidate(task: dict[str, Any], baseline_name: str, model_name: str, seed: int, error: Exception) -> dict[str, Any]:
    return {
        "task_id": task.get("task_id"),
        "baseline_name": baseline_name,
        "model_name": model_name,
        "seed": seed,
        "parsed_spec": {},
        "topology_decision": {},
        "design_rationale": "Candidate generation failed; failure recorded for reproducibility.",
        "theoretical_design": {},
        "bom": [],
        "simulation_config": {"mode": "generation_failed", "max_sim_calls": 0},
        "final_claimed_metrics": {},
        "uncertainty_or_escalation_flag": {"escalate": True, "reason": "candidate_generation_failed"},
        "metadata": {
            "candidate_kind": "generation_error",
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(limit=8),
        },
    }


def _error_result(task: dict[str, Any], baseline_name: str, model_name: str, seed: int, error: Exception) -> dict[str, Any]:
    return {
        "task_id": task.get("task_id"),
        "difficulty_tier": task.get("difficulty_tier"),
        "baseline_name": baseline_name,
        "model_name": model_name,
        "seed": int(seed),
        "pass_fail": False,
        "score_total": 0.0,
        "sub_scores": {},
        "constraint_violations": [
            {
                "constraint": "candidate_generation",
                "observed": f"{type(error).__name__}: {error}",
                "limit": "candidate generated and parsed",
                "severity": "hard",
                "group": "runtime",
            }
        ],
        "simulation_metrics": {},
        "failure_tags": ["Spec Parsing Failure"],
        "failure_groups": ["runtime"],
        "aggregate_scores": {"vtsr": 0.0, "partial_score": 0.0},
        "execution_log": [
            {
                "stage": "candidate_generation",
                "status": "fail",
                "note": f"{type(error).__name__}: {error}",
            }
        ],
        "runtime_stats": {
            "backend_requested": "llm_or_baseline",
            "backend_used": "generation_error",
            "fallback_used": True,
            "fallback_reason": "candidate_generation_failed",
            "simulator_version": "pebench-error-record-v1",
            "runtime_seconds": 0.0,
            "recorded_at_unix": round(time.time(), 3),
        },
        "vtsr_pass": False,
        "partial_score": 0.0,
        "gate_scores": {
            "schema": 0.0,
            "theory": 0.0,
            "component": 0.0,
            "derating": 0.0,
            "simulation": 0.0,
            "claim_consistency": 0.0,
            "escalation": 0.0,
        },
        "checked_metrics": {},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PE-Bench suites across flyback, topology-full, and inverter tracks.")
    parser.add_argument("--track", choices=["flyback", "topology_full", "three_phase_inverter", "all"], default="all")
    parser.add_argument("--topology", choices=["all", "buck", "boost", "buck_boost", "flyback", "three_phase_inverter"], default="all")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--model", default="heuristic-v0")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--api-base", dest="api_base", default=None)
    parser.add_argument("--api-key-env", dest="api_key_env", default=None)
    parser.add_argument("--task-limit", type=int, default=999)
    parser.add_argument("--difficulty-tier", action="append", default=[])
    parser.add_argument("--disable-formula-guardrails", action="store_true")
    parser.add_argument("--disable-component-grounding", action="store_true")
    parser.add_argument("--disable-correction-memory", action="store_true")
    parser.add_argument("--task-split", default="all")
    parser.add_argument("--tasks-dir", default=str(DEFAULT_FLYBACK_TASK_DIR))
    parser.add_argument("--topology-tasks-dir", default=str(DEFAULT_TOPOLOGY_FULL_TASK_DIR))
    parser.add_argument("--inverter-tasks-dir", default=str(DEFAULT_INVERTER_TASK_DIR))
    parser.add_argument("--output-root", default=str(DEFAULT_PEBENCH_RESULTS_ROOT))
    parser.add_argument("--simulator-mode", default="auto")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _apply_runtime_overrides(args)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    if args.track in {"flyback", "all"} and args.baseline not in BASELINE_REGISTRY and args.baseline != "reference_design":
        raise ValueError(f"Baseline '{args.baseline}' is not registered for flyback baselines.")
    if args.track in {"topology_full", "all"} and args.baseline not in SCOUT_BASELINES and args.baseline != "reference_design":
        raise ValueError(f"Baseline '{args.baseline}' is not registered for topology full baselines.")
    if args.track in {"three_phase_inverter", "all"} and args.baseline not in INVERTER_BASELINES and args.baseline != "reference_design":
        raise ValueError(f"Baseline '{args.baseline}' is not registered for three-phase inverter baselines.")

    if args.track in {"flyback", "all"}:
        run_flyback_suite(args, output_root)
    if args.track in {"topology_full", "all"}:
        if args.topology == "flyback":
            args.topology = "all"
        run_topology_full_suite(args, output_root)
    if args.track in {"three_phase_inverter", "all"}:
        run_inverter_suite(args, output_root)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
