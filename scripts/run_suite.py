from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.adapters.registry import get_baseline
from pebench.analysis.reporting import write_suite_summary
from pebench.evaluator.core import evaluate_candidate
from pebench.tasks.schema import filter_tasks, iter_task_files, load_task, sort_tasks
from pebench.utils.io import dump_json
from pebench.utils.paths import DEFAULT_CANONICAL_RESULTS_ROOT, DEFAULT_TASK_DIR


def _sanitize_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "unnamed"


def _suggested_repairs(failure_tags: list[str]) -> list[str]:
    suggestions: list[str] = []
    if "Invalid or Unsafe BOM" in failure_tags:
        suggestions.append("reselect_catalog_grounded_bom")
    if "Stress Violation / Escalation Required" in failure_tags:
        suggestions.append("reduce_stress_and_add_margin")
    if "Efficiency Miss" in failure_tags:
        suggestions.append("retune_for_efficiency")
    if "Ripple / Regulation Miss" in failure_tags:
        suggestions.append("increase_output_filter_margin")
    if "Infeasible Theory Failure" in failure_tags:
        suggestions.append("repair_theoretical_design")
    if "Optimistic but Unrealistic Claim" in failure_tags:
        suggestions.append("make_claims_more_conservative")
    if "Spec Parsing Failure" in failure_tags:
        suggestions.append("re-read_structured_spec")
    if "Simulation Execution Failure" in failure_tags:
        suggestions.append("use_safer_startup_configuration")
    deduped: list[str] = []
    for suggestion in suggestions:
        if suggestion not in deduped:
            deduped.append(suggestion)
    return deduped


def _build_feedback_entry(attempt: int, result: dict[str, Any]) -> dict[str, Any]:
    failure_tags = list(result["failure_tags"])
    return {
        "attempt": attempt,
        "pass_fail": bool(result["pass_fail"]),
        "failure_tags": failure_tags,
        "suggested_repairs": _suggested_repairs(failure_tags),
        "summary": (
            "PASS"
            if result["pass_fail"]
            else "FAIL: " + (", ".join(failure_tags) if failure_tags else "no failure tags")
        ),
        "score_total": result["score_total"],
        "backend_used": result["runtime_stats"].get("backend_used"),
        "sim_calls": result["runtime_stats"].get("sim_calls"),
    }


def run_task_with_baseline(
    *,
    baseline: Any,
    task: dict[str, Any],
    model_name: str,
    seed: int,
    simulator_mode: str,
    attempt_candidates_dir: Path | None = None,
    attempt_results_dir: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    feedback_history: list[dict[str, Any]] = []
    final_candidate: dict[str, Any] | None = None
    final_result: dict[str, Any] | None = None

    for attempt_index in range(1, baseline.max_attempts + 1):
        candidate = baseline.generate(
            task=task,
            model_name=model_name,
            seed=seed,
            simulator_mode=simulator_mode,
            attempt_index=attempt_index,
            feedback_history=feedback_history,
        )
        result = evaluate_candidate(task=task, candidate=candidate, simulator_mode=simulator_mode)

        if attempt_candidates_dir is not None and attempt_results_dir is not None:
            dump_json(candidate, attempt_candidates_dir / f"{task['task_id']}__attempt{attempt_index}.json")
            dump_json(result, attempt_results_dir / f"{task['task_id']}__attempt{attempt_index}.json")

        feedback_entry = _build_feedback_entry(attempt_index, result)
        feedback_history.append(feedback_entry)

        final_candidate = candidate
        final_result = result
        if result["pass_fail"]:
            break

    if final_candidate is None or final_result is None:
        raise RuntimeError(f"Failed to run baseline {baseline.run_name} on task {task['task_id']}")

    final_candidate.setdefault("metadata", {})["retry_attempts"] = feedback_history
    final_candidate["metadata"]["retry_total_attempts"] = len(feedback_history)
    if baseline.max_attempts > 1:
        final_candidate["metadata"]["sim_calls_used"] = len(feedback_history)
        final_candidate["metadata"]["iterations_used"] = len(feedback_history)

    final_result["runtime_stats"]["retry_total_attempts"] = len(feedback_history)
    final_result["runtime_stats"]["retry_attempts"] = feedback_history
    if baseline.max_attempts > 1:
        final_result["runtime_stats"]["sim_calls"] = len(feedback_history)
        final_result["runtime_stats"]["iterations"] = len(feedback_history)

    return final_candidate, final_result, feedback_history


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a PE-Bench Flyback suite.")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--model", default="heuristic-v0")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--tasks-dir", default=str(DEFAULT_TASK_DIR))
    parser.add_argument("--task-limit", type=int, default=30)
    parser.add_argument(
        "--results-root",
        default=str(DEFAULT_CANONICAL_RESULTS_ROOT / "dev_v2_public_dev" / "suites"),
    )
    parser.add_argument("--simulator-mode", default="auto")
    parser.add_argument("--task-split", default="public_dev")
    parser.add_argument("--difficulty-tier", action="append", default=[])
    parser.add_argument("--disable-formula-guardrails", action="store_true")
    parser.add_argument("--disable-component-grounding", action="store_true")
    parser.add_argument("--disable-correction-memory", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline = get_baseline(
        args.baseline,
        disable_formula_guardrails=args.disable_formula_guardrails,
        disable_component_grounding=args.disable_component_grounding,
        disable_correction_memory=args.disable_correction_memory,
    )
    tasks = [load_task(path) for path in iter_task_files(args.tasks_dir)]
    difficulty_tiers = set(args.difficulty_tier) if args.difficulty_tier else None
    tasks = filter_tasks(
        tasks,
        split=args.task_split if args.task_split != "all" else None,
        track="autonomous_flyback_design",
        difficulty_tiers=difficulty_tiers,
    )
    tasks = sort_tasks(tasks)[: args.task_limit]
    suite_id = f"{baseline.run_name}__{_sanitize_token(args.model)}__seed{args.seed}__{len(tasks)}tasks"
    suite_dir = Path(args.results_root) / suite_id
    if suite_dir.exists():
        shutil.rmtree(suite_dir)
    candidates_dir = suite_dir / "candidates"
    results_dir = suite_dir / "task_results"
    attempt_candidates_dir = suite_dir / "attempt_candidates"
    attempt_results_dir = suite_dir / "attempt_results"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    if baseline.max_attempts > 1:
        attempt_candidates_dir.mkdir(parents=True, exist_ok=True)
        attempt_results_dir.mkdir(parents=True, exist_ok=True)

    print(
        (
            f"[suite-start] suite_id={suite_id} baseline={baseline.run_name} "
            f"model={args.model} seed={args.seed} split={args.task_split} "
            f"tasks={len(tasks)} simulator_mode={args.simulator_mode}"
        ),
        flush=True,
    )
    rows: list[dict[str, object]] = []
    for index, task in enumerate(tasks, start=1):
        candidate, result, feedback_history = run_task_with_baseline(
            baseline=baseline,
            task=task,
            model_name=args.model,
            seed=args.seed,
            simulator_mode=args.simulator_mode,
            attempt_candidates_dir=attempt_candidates_dir if baseline.max_attempts > 1 else None,
            attempt_results_dir=attempt_results_dir if baseline.max_attempts > 1 else None,
        )
        dump_json(candidate, candidates_dir / f"{task['task_id']}.json")
        dump_json(result, results_dir / f"{task['task_id']}.json")
        rows.append(
            {
                "task_id": task["task_id"],
                "difficulty_tier": task["difficulty_tier"],
                "pass_fail": result["pass_fail"],
                "score_total": result["score_total"],
                "failure_tags": ";".join(result["failure_tags"]),
                "attempts_used": len(feedback_history),
                "sim_calls": result["runtime_stats"]["sim_calls"],
                "runtime_seconds": result["runtime_stats"]["elapsed_seconds"],
                "backend_used": result["runtime_stats"].get("backend_used"),
                "fallback_used": result["runtime_stats"].get("fallback_used"),
            }
        )
        print(
            (
                f"[task-complete] {index}/{len(tasks)} task_id={task['task_id']} "
                f"tier={task['difficulty_tier']} pass={result['pass_fail']} "
                f"score={result['score_total']} attempts={len(feedback_history)} "
                f"sim_calls={result['runtime_stats']['sim_calls']} "
                f"backend={result['runtime_stats'].get('backend_used')} "
                f"failures={';'.join(result['failure_tags']) or 'none'}"
            ),
            flush=True,
        )

    with (suite_dir / "per_task_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "task_id",
                "difficulty_tier",
                "pass_fail",
                "score_total",
                "failure_tags",
                "attempts_used",
                "sim_calls",
                "runtime_seconds",
                "backend_used",
                "fallback_used",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    dump_json(
        {
            "suite_id": suite_id,
            "baseline_name": baseline.run_name,
            "model_name": args.model,
            "seed": args.seed,
            "task_ids": [task["task_id"] for task in tasks],
            "simulator_mode": args.simulator_mode,
            "task_split": args.task_split,
            "difficulty_tiers": sorted(difficulty_tiers) if difficulty_tiers else None,
            "max_attempts": baseline.max_attempts,
            "ablations": {
                "disable_formula_guardrails": args.disable_formula_guardrails,
                "disable_component_grounding": args.disable_component_grounding,
                "disable_correction_memory": args.disable_correction_memory,
            },
        },
        suite_dir / "suite_config.json",
    )
    summary = write_suite_summary(suite_dir)
    print(f"[suite-finish] suite_dir={suite_dir}", flush=True)
    print(summary, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
