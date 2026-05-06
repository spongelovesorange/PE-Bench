from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.analysis.reporting import find_suite_dirs, load_suite_results
from pebench.baselines.metadata import get_baseline_metadata
from pebench.utils.paths import DEFAULT_CANONICAL_RESULTS_ROOT, DEFAULT_RESULTS_ROOT


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p_hat = successes / total
    denominator = 1.0 + z * z / total
    center = (p_hat + z * z / (2.0 * total)) / denominator
    half_width = z * math.sqrt((p_hat * (1.0 - p_hat) + z * z / (4.0 * total)) / total) / denominator
    return max(0.0, center - half_width), min(1.0, center + half_width)


def exact_paired_binomial_p(win: int, lose: int) -> float:
    trials = win + lose
    if trials <= 0:
        return 1.0
    smaller = min(win, lose)
    tail = sum(math.comb(trials, index) for index in range(smaller + 1)) / (2**trials)
    return min(1.0, 2.0 * tail)


def _label(run_name: str) -> tuple[str, str, str]:
    metadata = get_baseline_metadata(run_name)
    return metadata.code_id, metadata.display_label, metadata.family_group


def _load_results(results_roots: list[Path]) -> tuple[list[dict[str, Any]], dict[str, list[Path]]]:
    rows: list[dict[str, Any]] = []
    suite_map: dict[str, list[Path]] = defaultdict(list)
    for root in results_roots:
        for suite_dir in find_suite_dirs(root):
            suite_results = load_suite_results(suite_dir)
            if not suite_results:
                continue
            split_label = root.parent.name if root.name == "suites" else root.name
            suite_map[split_label].append(suite_dir)
            for result in suite_results:
                enriched = dict(result)
                enriched["_split_label"] = split_label
                enriched["_suite_id"] = suite_dir.name
                rows.append(enriched)
    return rows, suite_map


def _method_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[(result["_split_label"], result["baseline_name"], result["model_name"])].append(result)

    rows: list[dict[str, Any]] = []
    for (split_label, baseline_name, model_name), items in sorted(grouped.items()):
        code_id, display_label, family_group = _label(baseline_name)
        successes = sum(1 for item in items if item["pass_fail"])
        total = len(items)
        ci_low, ci_high = wilson_interval(successes, total)
        by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_seed: dict[int, list[dict[str, Any]]] = defaultdict(list)
        failure_counts: Counter[str] = Counter()
        for item in items:
            by_task[str(item["task_id"])].append(item)
            by_seed[int(item["seed"])].append(item)
            failure_counts.update(item.get("failure_tags", []))
        pass_at_k = sum(1 for task_items in by_task.values() if any(item["pass_fail"] for item in task_items))
        all_k = sum(1 for task_items in by_task.values() if all(item["pass_fail"] for item in task_items))
        seed_vtsr = [
            sum(1 for item in seed_items if item["pass_fail"]) / max(1, len(seed_items))
            for _, seed_items in sorted(by_seed.items())
        ]
        rows.append(
            {
                "split": split_label,
                "baseline_name": baseline_name,
                "baseline_code_id": code_id,
                "display_label": display_label,
                "family_group": family_group,
                "model_name": model_name,
                "num_results": total,
                "num_unique_tasks": len(by_task),
                "successes": successes,
                "overall_vtsr": round(successes / max(1, total), 4),
                "wilson95_low": round(ci_low, 4),
                "wilson95_high": round(ci_high, 4),
                "pass_at_k": round(pass_at_k / max(1, len(by_task)), 4),
                "all_k_success_ratio": round(all_k / max(1, len(by_task)), 4),
                "seed_vtsr_values": ";".join(f"{value:.4f}" for value in seed_vtsr),
                "mean_score": round(
                    sum(float(item["score_total"]) for item in items) / max(1, total),
                    4,
                ),
                "top_failure_tags": ";".join(
                    f"{tag}:{count}" for tag, count in failure_counts.most_common(5)
                ),
            }
        )
    return rows


def _paired_rows(results: list[dict[str, Any]], reference: str) -> list[dict[str, Any]]:
    by_split_model: dict[tuple[str, str], dict[tuple[str, tuple[str, int]], dict[str, Any]]] = defaultdict(dict)
    for result in results:
        key = (result["_split_label"], result["model_name"])
        outcome_key = (str(result["task_id"]), int(result["seed"]))
        by_split_model[key][(result["baseline_name"], outcome_key)] = result

    rows: list[dict[str, Any]] = []
    for (split_label, model_name), lookup in sorted(by_split_model.items()):
        reference_keys = {
            outcome_key
            for baseline_name, outcome_key in lookup
            if baseline_name == reference
        }
        baselines = sorted({baseline_name for baseline_name, _ in lookup if baseline_name != reference})
        for baseline_name in baselines:
            candidate_keys = {
                outcome_key
                for other_name, outcome_key in lookup
                if other_name == baseline_name
            }
            paired_keys = sorted(reference_keys & candidate_keys)
            ref_only = other_only = both = neither = 0
            for outcome_key in paired_keys:
                ref_pass = bool(lookup[(reference, outcome_key)]["pass_fail"])
                other_pass = bool(lookup[(baseline_name, outcome_key)]["pass_fail"])
                if ref_pass and not other_pass:
                    ref_only += 1
                elif other_pass and not ref_pass:
                    other_only += 1
                elif ref_pass and other_pass:
                    both += 1
                else:
                    neither += 1
            total_pairs = len(paired_keys)
            p_value = exact_paired_binomial_p(ref_only, other_only)
            rows.append(
                {
                    "split": split_label,
                    "model_name": model_name,
                    "reference_baseline": reference,
                    "comparison_baseline": baseline_name,
                    "num_pairs": total_pairs,
                    "reference_only_success": ref_only,
                    "comparison_only_success": other_only,
                    "both_success": both,
                    "neither_success": neither,
                    "reference_vtsr_on_pairs": round((ref_only + both) / max(1, total_pairs), 4),
                    "comparison_vtsr_on_pairs": round((other_only + both) / max(1, total_pairs), 4),
                    "delta_vtsr": round((ref_only - other_only) / max(1, total_pairs), 4),
                    "exact_paired_binomial_p": round(p_value, 8),
                }
            )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write statistical comparison tables for PE-Bench results.")
    parser.add_argument(
        "--results-root",
        action="append",
        default=[],
        help="Suite root to include. May be passed multiple times.",
    )
    parser.add_argument("--reference", default="reference_agent")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_RESULTS_ROOT / "statistics"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = [Path(path) for path in args.results_root]
    if not roots:
        roots = [
            DEFAULT_CANONICAL_RESULTS_ROOT / "dev_v2_public_dev" / "suites",
            DEFAULT_CANONICAL_RESULTS_ROOT / "dev_v2_private_holdout" / "suites",
        ]

    results, suite_map = _load_results(roots)
    if not results:
        raise SystemExit("No suite results found.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    method_rows = _method_rows(results)
    method_path = output_dir / "method_intervals.csv"
    with method_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(method_rows[0]))
        writer.writeheader()
        writer.writerows(method_rows)

    paired_rows = _paired_rows(results, args.reference)
    paired_path = output_dir / "paired_comparisons.csv"
    with paired_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(paired_rows[0]) if paired_rows else ["split"])
        writer.writeheader()
        writer.writerows(paired_rows)

    manifest_path = output_dir / "included_suites.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["split", "suite_dir"])
        writer.writeheader()
        for split_label, suite_dirs in sorted(suite_map.items()):
            for suite_dir in suite_dirs:
                writer.writerow({"split": split_label, "suite_dir": str(suite_dir)})

    print(
        {
            "method_intervals": str(method_path),
            "paired_comparisons": str(paired_path),
            "included_suites": str(manifest_path),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
