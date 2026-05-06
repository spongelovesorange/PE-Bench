from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Any

import matplotlib.pyplot as plt

from pebench.baselines.metadata import get_baseline_metadata
from pebench.utils.io import dump_json, load_json
from pebench.utils.paths import DEFAULT_CANONICAL_RESULTS_ROOT, DEFAULT_RESULTS_ROOT


def _safe_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def _safe_std(values: list[float]) -> float:
    return stdev(values) if len(values) > 1 else 0.0


def _label_parts(run_name: str) -> tuple[str, str, str]:
    metadata = get_baseline_metadata(run_name)
    suffix = str(run_name or "").split("__", 1)
    display_label = metadata.display_label
    if len(suffix) > 1 and suffix[1]:
        pretty_suffix = suffix[1].replace("__", ", ").replace("_", " ")
        display_label = f"{display_label} ({pretty_suffix})"
    return metadata.code_id, display_label, metadata.family_group


def load_suite_results(suite_dir: str | Path) -> list[dict[str, Any]]:
    result_dir = Path(suite_dir) / "task_results"
    return [load_json(path) for path in sorted(result_dir.glob("*.json"))]


def summarize_task_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    success_rate = _safe_mean([1.0 if result["pass_fail"] else 0.0 for result in results])
    mean_score = _safe_mean([float(result["score_total"]) for result in results])
    mean_runtime = _safe_mean([float(result["runtime_stats"]["elapsed_seconds"]) for result in results])
    mean_performance_targets = _safe_mean(
        [float(result.get("aggregate_scores", {}).get("performance_targets", 0.0)) for result in results]
    )
    sim_calls = [
        float(result["runtime_stats"].get("sim_calls"))
        for result in results
        if result["runtime_stats"].get("sim_calls") is not None
    ]
    mean_sim_calls = _safe_mean(sim_calls) if sim_calls else None
    fallback_rate = _safe_mean(
        [1.0 if result["runtime_stats"].get("fallback_used") else 0.0 for result in results]
    )
    live_backend_rate = _safe_mean(
        [
            1.0 if str(result["runtime_stats"].get("backend_used")) in {"mcp", "xmlrpc"} else 0.0
            for result in results
        ]
    )

    failure_tag_counts: Counter[str] = Counter()
    failure_group_counts: Counter[str] = Counter()
    backend_counts: Counter[str] = Counter()
    by_difficulty: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        failure_tag_counts.update(result["failure_tags"])
        failure_group_counts.update(result.get("failure_groups", []))
        backend_counts.update([str(result["runtime_stats"].get("backend_used") or "unknown")])
        by_difficulty[result["difficulty_tier"]].append(result)

    summary = {
        "num_tasks": len(results),
        "success_rate": round(success_rate, 4),
        "overall_vtsr": round(success_rate, 4),
        "mean_score": round(mean_score, 4),
        "mean_performance_targets": round(mean_performance_targets, 4),
        "weighted_score": round(mean_score, 4),
        "mean_runtime_seconds": round(mean_runtime, 4),
        "mean_sim_calls": round(mean_sim_calls, 4) if mean_sim_calls is not None else None,
        "fallback_rate": round(fallback_rate, 4),
        "live_backend_rate": round(live_backend_rate, 4),
        "backend_counts": dict(sorted(backend_counts.items())),
        "failure_tag_counts": dict(sorted(failure_tag_counts.items())),
        "failure_group_counts": dict(sorted(failure_group_counts.items())),
        "difficulty_breakdown": {
            difficulty: {
                "num_tasks": len(items),
                "success_rate": round(_safe_mean([1.0 if item["pass_fail"] else 0.0 for item in items]), 4),
                "overall_vtsr": round(_safe_mean([1.0 if item["pass_fail"] else 0.0 for item in items]), 4),
                "mean_score": round(_safe_mean([float(item["score_total"]) for item in items]), 4),
                "mean_performance_targets": round(
                    _safe_mean([float(item.get("aggregate_scores", {}).get("performance_targets", 0.0)) for item in items]),
                    4,
                ),
                "weighted_score": round(_safe_mean([float(item["score_total"]) for item in items]), 4),
            }
            for difficulty, items in sorted(by_difficulty.items())
        },
    }
    return summary


def write_suite_summary(suite_dir: str | Path) -> dict[str, Any]:
    suite_path = Path(suite_dir)
    results = load_suite_results(suite_path)
    if not results:
        raise ValueError(f"No task results found under {suite_path}")

    summary = summarize_task_results(results)
    code_id, display_label, family_group = _label_parts(results[0]["baseline_name"])
    summary["suite_id"] = suite_path.name
    summary["baseline_name"] = results[0]["baseline_name"]
    summary["baseline_code_id"] = code_id
    summary["display_label"] = display_label
    summary["family_group"] = family_group
    summary["model_name"] = results[0]["model_name"]
    summary["seed"] = results[0]["seed"]
    summary["ablations"] = dict(results[0]["runtime_stats"].get("ablations", {}))
    summary["retry_total_attempts_mean"] = round(
        _safe_mean([float(result["runtime_stats"].get("retry_total_attempts", 1)) for result in results]),
        4,
    )

    dump_json(summary, suite_path / "summary.json")
    with (suite_path / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "suite_id",
                "baseline_name",
                "baseline_code_id",
                "display_label",
                "family_group",
                "model_name",
                "seed",
                "num_tasks",
                "success_rate",
                "overall_vtsr",
                "mean_score",
                "mean_performance_targets",
                "weighted_score",
                "mean_runtime_seconds",
                "mean_sim_calls",
                "fallback_rate",
                "live_backend_rate",
                "retry_total_attempts_mean",
            ],
        )
        writer.writeheader()
        writer.writerow({field: summary.get(field) for field in writer.fieldnames})

    return summary


def find_suite_dirs(
    results_root: str | Path = DEFAULT_CANONICAL_RESULTS_ROOT / "dev_v2_public_dev" / "suites",
) -> list[Path]:
    root = Path(results_root)
    if not root.exists():
        return []
    suite_dirs: list[Path] = []
    for path in sorted(root.iterdir()):
        if not (path / "task_results").exists():
            continue
        summary_path = path / "summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = load_json(summary_path)
        except Exception:
            continue
        num_tasks = summary.get("num_tasks")
        task_result_count = len(list((path / "task_results").glob("*.json")))
        match = re.search(r"__(\d+)tasks$", path.name)
        expected_task_count = int(match.group(1)) if match else None
        if (
            isinstance(num_tasks, int)
            and num_tasks == task_result_count
            and expected_task_count is not None
            and task_result_count == expected_task_count
        ):
            suite_dirs.append(path)
    return suite_dirs


def aggregate_summaries(suite_dirs: list[Path]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for suite_dir in suite_dirs:
        summary_path = suite_dir / "summary.json"
        if summary_path.exists():
            summary = load_json(summary_path)
            difficulty_breakdown = summary.get("difficulty_breakdown", {})
            difficulty_has_performance = all(
                isinstance(metrics, dict) and "mean_performance_targets" in metrics
                for metrics in difficulty_breakdown.values()
            )
            if (
                "overall_vtsr" in summary
                and "weighted_score" in summary
                and "mean_performance_targets" in summary
                and "display_label" in summary
                and "family_group" in summary
                and difficulty_has_performance
            ):
                summaries.append(summary)
            else:
                summaries.append(write_suite_summary(suite_dir))
        else:
            summaries.append(write_suite_summary(suite_dir))
    return summaries


def write_analysis_outputs(
    suite_dirs: list[Path],
    output_dir: str | Path = DEFAULT_RESULTS_ROOT / "analysis",
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    summaries = aggregate_summaries(suite_dirs)
    if not summaries:
        raise ValueError("No suite summaries available for analysis.")

    leaderboard_path = output_path / "leaderboard.csv"
    with leaderboard_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "suite_id",
                "baseline_name",
                "baseline_code_id",
                "display_label",
                "family_group",
                "model_name",
                "seed",
                "success_rate",
                "overall_vtsr",
                "mean_score",
                "mean_performance_targets",
                "weighted_score",
                "mean_runtime_seconds",
                "mean_sim_calls",
                "fallback_rate",
                "live_backend_rate",
                "retry_total_attempts_mean",
            ],
        )
        writer.writeheader()
        for summary in summaries:
            writer.writerow({field: summary.get(field) for field in writer.fieldnames})

    tier_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    failure_group_rows: list[dict[str, Any]] = []
    for summary in summaries:
        for difficulty, metrics in summary["difficulty_breakdown"].items():
            tier_rows.append(
                {
                    "baseline_name": summary["baseline_name"],
                    "display_label": summary.get("display_label", summary["baseline_name"]),
                    "family_group": summary.get("family_group", "unknown"),
                    "suite_id": summary["suite_id"],
                    "difficulty_tier": difficulty,
                    "success_rate": metrics.get("success_rate", metrics.get("overall_vtsr", 0.0)),
                    "overall_vtsr": metrics.get("overall_vtsr", metrics.get("success_rate", 0.0)),
                    "mean_score": metrics.get("mean_score", metrics.get("weighted_score", 0.0)),
                    "mean_performance_targets": metrics.get("mean_performance_targets", 0.0),
                    "weighted_score": metrics.get("weighted_score", metrics.get("mean_score", 0.0)),
                    "num_results": metrics.get("num_tasks", metrics.get("num_results", 0)),
                }
            )
        for tag, count in summary["failure_tag_counts"].items():
            failure_rows.append(
                {
                    "baseline_name": summary["baseline_name"],
                    "display_label": summary.get("display_label", summary["baseline_name"]),
                    "family_group": summary.get("family_group", "unknown"),
                    "suite_id": summary["suite_id"],
                    "failure_tag": tag,
                    "count": count,
                }
            )
        for group, count in summary.get("failure_group_counts", {}).items():
            failure_group_rows.append(
                {
                    "baseline_name": summary["baseline_name"],
                    "display_label": summary.get("display_label", summary["baseline_name"]),
                    "family_group": summary.get("family_group", "unknown"),
                    "suite_id": summary["suite_id"],
                    "failure_group": group,
                    "count": count,
                }
            )

    tier_path = output_path / "success_by_difficulty.csv"
    with tier_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "baseline_name",
                "display_label",
                "family_group",
                "suite_id",
                "difficulty_tier",
                "success_rate",
                "overall_vtsr",
                "mean_score",
                "mean_performance_targets",
                "weighted_score",
                "num_results",
            ],
        )
        writer.writeheader()
        writer.writerows(tier_rows)

    failure_path = output_path / "failure_taxonomy.csv"
    with failure_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "baseline_name",
                "display_label",
                "family_group",
                "suite_id",
                "failure_tag",
                "count",
            ],
        )
        writer.writeheader()
        writer.writerows(failure_rows)

    failure_group_path = output_path / "failure_groups.csv"
    with failure_group_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "baseline_name",
                "display_label",
                "family_group",
                "suite_id",
                "failure_group",
                "count",
            ],
        )
        writer.writeheader()
        writer.writerows(failure_group_rows)

    _plot_success_by_difficulty(tier_rows, output_path / "success_by_difficulty.png")
    _plot_failure_distribution(failure_rows, output_path / "failure_taxonomy.png")

    markdown_path = output_path / "leaderboard.md"
    with markdown_path.open("w", encoding="utf-8") as handle:
        handle.write("| suite_id | baseline | model | seed | overall_vtsr | mean_score | live_backend_rate |\n")
        handle.write("| --- | --- | --- | --- | --- | --- | --- |\n")
        for summary in summaries:
            handle.write(
                f"| {summary['suite_id']} | {summary['display_label']} | "
                f"{summary['model_name']} | {summary['seed']} | "
                f"{summary['overall_vtsr']} | {summary['mean_score']} | "
                f"{summary['live_backend_rate']} |\n"
            )

    aggregate = _aggregate_result_sets(suite_dirs)
    aggregate_leaderboard_path = output_path / "leaderboard_aggregate.csv"
    with aggregate_leaderboard_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "baseline_name",
                "baseline_code_id",
                "display_label",
                "family_group",
                "model_name",
                "num_suites",
                "num_results",
                "num_unique_tasks",
                "overall_vtsr",
                "overall_vtsr_std",
                "mean_score",
                "mean_score_std",
                "mean_performance_targets",
                "weighted_score",
                "mean_runtime_seconds",
                "mean_runtime_seconds_std",
                "mean_sim_calls",
                "mean_sim_calls_std",
                "fallback_rate",
                "live_backend_rate",
                "pass_at_3",
                "all_3_success_ratio",
            ],
        )
        writer.writeheader()
        writer.writerows(aggregate["leaderboard_rows"])

    aggregate_tier_path = output_path / "success_by_difficulty_aggregate.csv"
    with aggregate_tier_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "baseline_name",
                "display_label",
                "family_group",
                "difficulty_tier",
                "overall_vtsr",
                "mean_score",
                "mean_performance_targets",
                "weighted_score",
                "num_results",
            ],
        )
        writer.writeheader()
        writer.writerows(aggregate["difficulty_rows"])

    aggregate_failure_path = output_path / "failure_taxonomy_aggregate.csv"
    with aggregate_failure_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["baseline_name", "display_label", "family_group", "failure_tag", "count", "rate"],
        )
        writer.writeheader()
        writer.writerows(aggregate["failure_rows"])

    aggregate_failure_group_path = output_path / "failure_groups_aggregate.csv"
    with aggregate_failure_group_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["baseline_name", "display_label", "family_group", "failure_group", "count", "rate"],
        )
        writer.writeheader()
        writer.writerows(aggregate["failure_group_rows"])

    backend_usage_path = output_path / "backend_usage_aggregate.csv"
    with backend_usage_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["baseline_name", "display_label", "family_group", "backend_used", "count", "rate"],
        )
        writer.writeheader()
        writer.writerows(aggregate["backend_rows"])

    ablation_path = output_path / "ablation_comparison.csv"
    with ablation_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "baseline_name",
                "display_label",
                "family_group",
                "reference_baseline",
                "delta_overall_vtsr",
                "delta_weighted_score",
                "delta_fallback_rate",
                "delta_infeasible_theory_failure",
                "delta_simulation_execution_failure",
                "delta_optimistic_claim",
                "delta_invalid_or_unsafe_bom",
                "delta_stress_violation",
            ],
        )
        writer.writeheader()
        writer.writerows(aggregate["ablation_rows"])

    _plot_success_by_difficulty(aggregate["difficulty_rows"], output_path / "success_by_difficulty_aggregate.png")
    _plot_failure_distribution(aggregate["failure_rows"], output_path / "failure_taxonomy_aggregate.png")
    _plot_backend_usage(aggregate["backend_rows"], output_path / "backend_usage.png")

    return {
        "leaderboard_csv": leaderboard_path,
        "leaderboard_aggregate_csv": aggregate_leaderboard_path,
        "success_by_difficulty_csv": tier_path,
        "success_by_difficulty_aggregate_csv": aggregate_tier_path,
        "failure_taxonomy_csv": failure_path,
        "failure_groups_csv": failure_group_path,
        "failure_taxonomy_aggregate_csv": aggregate_failure_path,
        "failure_groups_aggregate_csv": aggregate_failure_group_path,
        "backend_usage_aggregate_csv": backend_usage_path,
        "ablation_comparison_csv": ablation_path,
        "leaderboard_md": markdown_path,
        "success_by_difficulty_png": output_path / "success_by_difficulty.png",
        "success_by_difficulty_aggregate_png": output_path / "success_by_difficulty_aggregate.png",
        "failure_taxonomy_png": output_path / "failure_taxonomy.png",
        "failure_taxonomy_aggregate_png": output_path / "failure_taxonomy_aggregate.png",
        "backend_usage_png": output_path / "backend_usage.png",
    }


def _aggregate_result_sets(suite_dirs: list[Path]) -> dict[str, list[dict[str, Any]]]:
    grouped_results: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    grouped_summaries: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    suite_counts: Counter[tuple[str, str]] = Counter()
    for suite_dir in suite_dirs:
        results = load_suite_results(suite_dir)
        if not results:
            continue
        key = (results[0]["baseline_name"], results[0]["model_name"])
        grouped_results[key].extend(results)
        grouped_summaries[key].append(write_suite_summary(suite_dir))
        suite_counts.update([key])

    leaderboard_rows: list[dict[str, Any]] = []
    difficulty_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    failure_group_rows: list[dict[str, Any]] = []
    backend_rows: list[dict[str, Any]] = []
    failure_rate_maps: dict[str, dict[str, float]] = {}
    failure_group_rate_maps: dict[str, dict[str, float]] = {}

    for (baseline_name, model_name), results in sorted(grouped_results.items()):
        code_id, display_label, family_group = _label_parts(baseline_name)
        summaries = grouped_summaries[(baseline_name, model_name)]
        failure_counts: Counter[str] = Counter()
        failure_group_counts: Counter[str] = Counter()
        backend_counts: Counter[str] = Counter()
        by_difficulty: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for result in results:
            failure_counts.update(result["failure_tags"])
            failure_group_counts.update(result.get("failure_groups", []))
            backend_counts.update([str(result["runtime_stats"].get("backend_used") or "unknown")])
            by_difficulty[result["difficulty_tier"]].append(result)
            by_task[result["task_id"]].append(result)

        num_results = len(results)
        num_unique_tasks = len(by_task)
        overall_vtsr = _safe_mean([1.0 if result["pass_fail"] else 0.0 for result in results])
        weighted_score = _safe_mean([float(result["score_total"]) for result in results])
        mean_score = weighted_score
        mean_performance_targets = _safe_mean(
            [float(result.get("aggregate_scores", {}).get("performance_targets", 0.0)) for result in results]
        )
        mean_runtime = _safe_mean([float(result["runtime_stats"]["elapsed_seconds"]) for result in results])
        sim_calls = [
            float(result["runtime_stats"].get("sim_calls"))
            for result in results
            if result["runtime_stats"].get("sim_calls") is not None
        ]
        fallback_rate = _safe_mean(
            [1.0 if result["runtime_stats"].get("fallback_used") else 0.0 for result in results]
        )
        live_backend_rate = _safe_mean(
            [
                1.0 if str(result["runtime_stats"].get("backend_used")) in {"mcp", "xmlrpc"} else 0.0
                for result in results
            ]
        )
        suite_vtsr = [float(summary["overall_vtsr"]) for summary in summaries]
        suite_scores = [float(summary["mean_score"]) for summary in summaries]
        suite_runtime = [float(summary["mean_runtime_seconds"]) for summary in summaries]
        suite_sim_calls = [
            float(summary["mean_sim_calls"])
            for summary in summaries
            if summary.get("mean_sim_calls") is not None
        ]
        task_pass_counts = {task_id: sum(1 for item in items if item["pass_fail"]) for task_id, items in by_task.items()}
        pass_at_3 = _safe_mean([1.0 if count >= 1 else 0.0 for count in task_pass_counts.values()])
        all_3_success_ratio = _safe_mean(
            [
                1.0 if count >= min(3, suite_counts[(baseline_name, model_name)]) else 0.0
                for count in task_pass_counts.values()
            ]
        )

        leaderboard_rows.append(
            {
                "baseline_name": baseline_name,
                "baseline_code_id": code_id,
                "display_label": display_label,
                "family_group": family_group,
                "model_name": model_name,
                "num_suites": suite_counts[(baseline_name, model_name)],
                "num_results": num_results,
                "num_unique_tasks": num_unique_tasks,
                "overall_vtsr": round(overall_vtsr, 4),
                "overall_vtsr_std": round(_safe_std(suite_vtsr), 4),
                "mean_score": round(mean_score, 4),
                "mean_score_std": round(_safe_std(suite_scores), 4),
                "mean_performance_targets": round(mean_performance_targets, 4),
                "weighted_score": round(weighted_score, 4),
                "mean_runtime_seconds": round(mean_runtime, 4),
                "mean_runtime_seconds_std": round(_safe_std(suite_runtime), 4),
                "mean_sim_calls": round(_safe_mean(sim_calls), 4) if sim_calls else None,
                "mean_sim_calls_std": round(_safe_std(suite_sim_calls), 4) if suite_sim_calls else None,
                "fallback_rate": round(fallback_rate, 4),
                "live_backend_rate": round(live_backend_rate, 4),
                "pass_at_3": round(pass_at_3, 4),
                "all_3_success_ratio": round(all_3_success_ratio, 4),
            }
        )

        failure_rate_map: dict[str, float] = {}
        for tag, count in sorted(failure_counts.items()):
            rate = count / max(1, num_results)
            failure_rate_map[tag] = rate
            failure_rows.append(
                {
                    "baseline_name": baseline_name,
                    "display_label": display_label,
                    "family_group": family_group,
                    "failure_tag": tag,
                    "count": count,
                    "rate": round(rate, 4),
                }
            )
        failure_rate_maps[baseline_name] = failure_rate_map
        failure_group_rate_map: dict[str, float] = {}
        for group, count in sorted(failure_group_counts.items()):
            rate = count / max(1, num_results)
            failure_group_rate_map[group] = rate
            failure_group_rows.append(
                {
                    "baseline_name": baseline_name,
                    "display_label": display_label,
                    "family_group": family_group,
                    "failure_group": group,
                    "count": count,
                    "rate": round(rate, 4),
                }
            )
        failure_group_rate_maps[baseline_name] = failure_group_rate_map

        for backend_used, count in sorted(backend_counts.items()):
            backend_rows.append(
                {
                    "baseline_name": baseline_name,
                    "display_label": display_label,
                    "family_group": family_group,
                    "backend_used": backend_used,
                    "count": count,
                    "rate": round(count / max(1, num_results), 4),
                }
            )

        for difficulty, items in sorted(by_difficulty.items()):
            difficulty_rows.append(
                {
                    "baseline_name": baseline_name,
                    "display_label": display_label,
                    "family_group": family_group,
                    "difficulty_tier": difficulty,
                    "overall_vtsr": round(_safe_mean([1.0 if item["pass_fail"] else 0.0 for item in items]), 4),
                    "mean_score": round(_safe_mean([float(item["score_total"]) for item in items]), 4),
                    "mean_performance_targets": round(
                        _safe_mean([float(item.get("aggregate_scores", {}).get("performance_targets", 0.0)) for item in items]),
                        4,
                    ),
                    "weighted_score": round(_safe_mean([float(item["score_total"]) for item in items]), 4),
                    "num_results": len(items),
                }
            )

    by_baseline = {row["baseline_name"]: row for row in leaderboard_rows}
    ablation_rows: list[dict[str, Any]] = []
    reference = by_baseline.get("reference_agent")
    if reference is not None:
        for row in leaderboard_rows:
            baseline_name = row["baseline_name"]
            if not baseline_name.startswith("reference_agent__wo_"):
                continue
            failure_rates = failure_rate_maps.get(baseline_name, {})
            reference_failure_rates = failure_rate_maps.get("reference_agent", {})
            ablation_rows.append(
                {
                    "baseline_name": baseline_name,
                    "display_label": row["display_label"],
                    "family_group": row["family_group"],
                    "reference_baseline": "reference_agent",
                    "delta_overall_vtsr": round(row["overall_vtsr"] - reference["overall_vtsr"], 4),
                    "delta_weighted_score": round(row["weighted_score"] - reference["weighted_score"], 4),
                    "delta_fallback_rate": round(row["fallback_rate"] - reference["fallback_rate"], 4),
                    "delta_infeasible_theory_failure": round(
                        failure_rates.get("Infeasible Theory Failure", 0.0)
                        - reference_failure_rates.get("Infeasible Theory Failure", 0.0),
                        4,
                    ),
                    "delta_simulation_execution_failure": round(
                        failure_rates.get("Simulation Execution Failure", 0.0)
                        - reference_failure_rates.get("Simulation Execution Failure", 0.0),
                        4,
                    ),
                    "delta_optimistic_claim": round(
                        failure_rates.get("Optimistic but Unrealistic Claim", 0.0)
                        - reference_failure_rates.get("Optimistic but Unrealistic Claim", 0.0),
                        4,
                    ),
                    "delta_invalid_or_unsafe_bom": round(
                        failure_rates.get("Invalid or Unsafe BOM", 0.0)
                        - reference_failure_rates.get("Invalid or Unsafe BOM", 0.0),
                        4,
                    ),
                    "delta_stress_violation": round(
                        failure_rates.get("Stress Violation / Escalation Required", 0.0)
                        - reference_failure_rates.get("Stress Violation / Escalation Required", 0.0),
                        4,
                    ),
                }
            )

    return {
        "leaderboard_rows": leaderboard_rows,
        "difficulty_rows": difficulty_rows,
        "failure_rows": failure_rows,
        "failure_group_rows": failure_group_rows,
        "backend_rows": backend_rows,
        "ablation_rows": ablation_rows,
    }


def _plot_success_by_difficulty(rows: list[dict[str, Any]], output_path: Path) -> None:
    grouped: dict[str, dict[str, float]] = defaultdict(dict)
    difficulties = ["easy", "medium", "hard", "boundary", "stress"]
    for row in rows:
        grouped[row["display_label"]][row["difficulty_tier"]] = row.get("success_rate", row.get("overall_vtsr", 0.0))

    baselines = sorted(grouped)
    x_positions = range(len(difficulties))
    width = 0.18 if baselines else 0.4

    plt.figure(figsize=(9, 4.8))
    for index, baseline in enumerate(baselines):
        offsets = [x + (index - (len(baselines) - 1) / 2) * width for x in x_positions]
        values = [grouped[baseline].get(difficulty, 0.0) for difficulty in difficulties]
        plt.bar(offsets, values, width=width, label=baseline)

    plt.xticks(list(x_positions), difficulties)
    plt.ylim(0.0, 1.0)
    plt.ylabel("Success rate")
    plt.title("Success Rate by Difficulty Tier")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def _plot_failure_distribution(rows: list[dict[str, Any]], output_path: Path) -> None:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    tags = set()
    for row in rows:
        grouped[row["display_label"]][row["failure_tag"]] += float(row["count"])
        tags.add(row["failure_tag"])

    baselines = sorted(grouped)
    tags = sorted(tags)
    x_positions = range(len(tags))
    width = 0.18 if baselines else 0.4

    plt.figure(figsize=(12, 5))
    for index, baseline in enumerate(baselines):
        offsets = [x + (index - (len(baselines) - 1) / 2) * width for x in x_positions]
        values = [grouped[baseline].get(tag, 0) for tag in tags]
        plt.bar(offsets, values, width=width, label=baseline)

    plt.xticks(list(x_positions), tags, rotation=30, ha="right")
    plt.ylabel("Count")
    plt.title("Failure Taxonomy Distribution")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def _plot_backend_usage(rows: list[dict[str, Any]], output_path: Path) -> None:
    grouped: dict[str, dict[str, float]] = defaultdict(dict)
    backends = sorted({row["backend_used"] for row in rows})
    baselines = sorted({row["display_label"] for row in rows})
    for row in rows:
        grouped[row["display_label"]][row["backend_used"]] = float(row["rate"])

    plt.figure(figsize=(9, 4.8))
    bottoms = [0.0 for _ in baselines]
    x_positions = list(range(len(baselines)))
    for backend_used in backends:
        values = [grouped[baseline].get(backend_used, 0.0) for baseline in baselines]
        plt.bar(x_positions, values, bottom=bottoms, label=backend_used)
        bottoms = [bottom + value for bottom, value in zip(bottoms, values)]

    plt.xticks(x_positions, baselines, rotation=20, ha="right")
    plt.ylim(0.0, 1.0)
    plt.ylabel("Rate")
    plt.title("Backend Usage by Baseline")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
