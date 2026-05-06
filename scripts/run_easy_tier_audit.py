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
from pebench.tasks.schema import count_by_difficulty, difficulty_definition, filter_tasks, iter_task_files, load_task, sort_tasks
from pebench.utils.io import dump_json
from pebench.utils.paths import DEFAULT_AUDITS_RESULTS_ROOT, DEFAULT_TASK_DIR
from scripts.run_suite import run_task_with_baseline


BASELINES = ("reference_agent", "direct_prompting")
CSV_COLUMNS = [
    "task_id",
    "reference_design_stably_solvable",
    "reference_agent_failure_reason",
    "direct_prompting_failure_reason",
    "tier_should_be_promoted",
    "change_needed",
    "recommended_action",
]


def _sanitize_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "unnamed"


def _reference_design_stably_solvable(task: dict[str, Any]) -> bool:
    expected = task["reference_design"]["expected_metrics"]
    targets = task["structured_spec"]["targets"]
    constraints = task["structured_spec"]["constraints"]
    return bool(
        expected.get("startup_success")
        and float(expected["efficiency_percent"]) >= float(targets["efficiency_percent"])
        and float(expected["ripple_mv"]) <= float(targets["ripple_mv"])
        and float(expected["mosfet_voltage_stress_v"]) <= float(constraints["max_mosfet_voltage_v"])
        and float(expected["diode_reverse_voltage_v"]) <= float(constraints["max_diode_reverse_voltage_v"])
        and float(expected["flux_density_mt"]) <= float(constraints["max_flux_density_mt"])
    )


def _failure_reason(result: dict[str, Any]) -> str:
    if result["pass_fail"]:
        return "PASS"
    tags = list(result["failure_tags"])
    return ", ".join(tags) if tags else "FAIL_NO_TAG"


def _classify_change(
    *,
    reference_stable: bool,
    pe_tags: list[str],
    direct_tags: list[str],
) -> tuple[bool, str, str]:
    if not reference_stable:
        return False, "reference", "tighten_reference"
    if not pe_tags and direct_tags:
        return False, "none", "keep"
    if pe_tags and not direct_tags:
        if any(tag in pe_tags for tag in {"Efficiency Miss", "Ripple / Regulation Miss"}):
            return False, "rubric", "relax_threshold"
        return False, "guardrail", "tighten_guardrail"
    if pe_tags and direct_tags:
        if any(tag in pe_tags + direct_tags for tag in {"Stress Violation / Escalation Required", "Infeasible Theory Failure"}):
            return True, "tier", "promote_tier"
        if all(tag in {"Efficiency Miss", "Ripple / Regulation Miss"} for tag in set(pe_tags + direct_tags)):
            return False, "rubric", "relax_threshold"
        return True, "tier", "promote_tier"
    return False, "none", "keep"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the easy-tier calibration audit for PE-Bench dev_v2.")
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--tasks-dir", default=str(DEFAULT_TASK_DIR))
    parser.add_argument(
        "--results-root",
        default=str(DEFAULT_AUDITS_RESULTS_ROOT / "easy_tier_calibration_v2"),
    )
    parser.add_argument("--simulator-mode", default="auto")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit_root = Path(args.results_root)
    suites_root = audit_root / "suites"
    if audit_root.exists():
        shutil.rmtree(audit_root)
    suites_root.mkdir(parents=True, exist_ok=True)

    tasks = [load_task(path) for path in iter_task_files(args.tasks_dir)]
    tasks = filter_tasks(
        tasks,
        split="public_dev",
        track="autonomous_flyback_design",
        difficulty_tiers={"easy"},
    )
    tasks = sort_tasks(tasks)

    per_baseline_results: dict[str, dict[str, dict[str, Any]]] = {}
    details: dict[str, Any] = {}

    for baseline_name in BASELINES:
        baseline = get_baseline(baseline_name)
        suite_id = f"{baseline.run_name}__{_sanitize_token(args.model)}__seed{args.seed}__{len(tasks)}tasks"
        suite_dir = suites_root / suite_id
        candidates_dir = suite_dir / "candidates"
        results_dir = suite_dir / "task_results"
        candidates_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)
        per_baseline_results[baseline_name] = {}
        for task in tasks:
            candidate, result, feedback_history = run_task_with_baseline(
                baseline=baseline,
                task=task,
                model_name=args.model,
                seed=args.seed,
                simulator_mode=args.simulator_mode,
            )
            dump_json(candidate, candidates_dir / f"{task['task_id']}.json")
            dump_json(result, results_dir / f"{task['task_id']}.json")
            per_baseline_results[baseline_name][task["task_id"]] = result
            details.setdefault(task["task_id"], {})[baseline_name] = {
                "candidate_path": str(candidates_dir / f"{task['task_id']}.json"),
                "result_path": str(results_dir / f"{task['task_id']}.json"),
                "feedback_history": feedback_history,
            }
        write_suite_summary(suite_dir)

    rows: list[dict[str, Any]] = []
    for task in tasks:
        task_id = task["task_id"]
        pe_result = per_baseline_results["reference_agent"][task_id]
        direct_result = per_baseline_results["direct_prompting"][task_id]
        reference_stable = _reference_design_stably_solvable(task)
        tier_should_be_promoted, change_needed, recommended_action = _classify_change(
            reference_stable=reference_stable,
            pe_tags=list(pe_result["failure_tags"]),
            direct_tags=list(direct_result["failure_tags"]),
        )
        rows.append(
            {
                "task_id": task_id,
                "reference_design_stably_solvable": reference_stable,
                "reference_agent_failure_reason": _failure_reason(pe_result),
                "direct_prompting_failure_reason": _failure_reason(direct_result),
                "tier_should_be_promoted": tier_should_be_promoted,
                "change_needed": change_needed,
                "recommended_action": recommended_action,
            }
        )

    csv_path = audit_root / "easy_tier_calibration.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    dump_json(
        {
            "model_name": args.model,
            "seed": args.seed,
            "num_tasks": len(tasks),
            "rows": rows,
            "details": details,
        },
        audit_root / "easy_tier_calibration_details.json",
    )
    public_tasks = filter_tasks(
        [load_task(path) for path in iter_task_files(args.tasks_dir)],
        split="public_dev",
        track="autonomous_flyback_design",
    )
    dump_json(
        {
            "model_name": args.model,
            "seed": args.seed,
            "num_easy_tasks_audited": len(tasks),
            "public_dev_distribution": dict(count_by_difficulty(public_tasks)),
            "difficulty_definitions": {
                tier: difficulty_definition(tier) for tier in ["easy", "medium", "hard", "boundary", "stress"]
            },
            "recommended_task_updates": rows,
        },
        audit_root / "public_dev_v2_freeze.json",
    )
    print(csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
