from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.utils.io import dump_json
from pebench.utils.paths import DEFAULT_PEBENCH_RESULTS_ROOT


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _iter_suite_dirs(results_root: Path) -> Iterable[Path]:
    for summary_path in sorted(results_root.glob("**/suites/*/suite_summary.json")):
        yield summary_path.parent


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _aggregate_results(task_results: list[dict[str, Any]]) -> dict[str, float]:
    successes = sum(1 for result in task_results if result.get("pass_fail"))
    mean_score = sum(float(result.get("score_total", 0.0)) for result in task_results) / max(1, len(task_results))
    return {
        "num_tasks": len(task_results),
        "vtsr": round(successes / max(1, len(task_results)), 4),
        "mean_score": round(mean_score, 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize PE-Bench suite results for paper-ready tables.")
    parser.add_argument("--results-root", default=str(DEFAULT_PEBENCH_RESULTS_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_PEBENCH_RESULTS_ROOT / "analysis"))
    args = parser.parse_args()

    results_root = Path(args.results_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    suite_rows: list[dict[str, Any]] = []
    main_agg: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    topology_agg: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    failure_counts: Counter[tuple[str, str]] = Counter()
    claim_rows: list[dict[str, Any]] = []
    ablation_rows: list[dict[str, Any]] = []

    for suite_dir in _iter_suite_dirs(results_root):
        suite_summary = _load_json(suite_dir / "suite_summary.json")
        suite_rows.append(suite_summary)
        task_results = [
            _load_json(path) for path in sorted((suite_dir / "task_results").glob("*.json"))
        ]

        key = (
            str(suite_summary.get("baseline_name")),
            str(suite_summary.get("model_name")),
            str(suite_summary.get("track")),
        )
        main_agg[key].extend(task_results)

        for result in task_results:
            topology = str(result.get("topology") or suite_summary.get("topology") or "flyback")
            topology_key = (
                topology,
                str(result.get("baseline_name") or suite_summary.get("baseline_name")),
                str(result.get("model_name") or suite_summary.get("model_name")),
            )
            topology_agg[topology_key].append(result)
            for tag in result.get("failure_tags", []):
                failure_counts[(topology, str(tag))] += 1

            claim_rows.append(
                {
                    "task_id": result.get("task_id"),
                    "track": suite_summary.get("track"),
                    "topology": topology,
                    "baseline_name": result.get("baseline_name"),
                    "model_name": result.get("model_name"),
                    "claim_consistency_score": result.get("gate_scores", {}).get("claim_consistency", 0.0),
                }
            )

        ablations = suite_summary.get("ablations", {})
        ablation_rows.append(
            {
                "suite_id": suite_summary.get("suite_id"),
                "baseline_name": suite_summary.get("baseline_name"),
                "model_name": suite_summary.get("model_name"),
                "track": suite_summary.get("track"),
                "topology": suite_summary.get("topology"),
                "disable_formula_guardrails": ablations.get("disable_formula_guardrails"),
                "disable_component_grounding": ablations.get("disable_component_grounding"),
                "disable_correction_memory": ablations.get("disable_correction_memory"),
                "vtsr": suite_summary.get("vtsr"),
                "mean_score": suite_summary.get("mean_score"),
            }
        )

    main_rows: list[dict[str, Any]] = []
    for (baseline, model, track), results in sorted(main_agg.items()):
        metrics = _aggregate_results(results)
        main_rows.append(
            {
                "baseline_name": baseline,
                "model_name": model,
                "track": track,
                **metrics,
            }
        )

    topology_rows: list[dict[str, Any]] = []
    for (topology, baseline, model), results in sorted(topology_agg.items()):
        metrics = _aggregate_results(results)
        topology_rows.append(
            {
                "topology": topology,
                "baseline_name": baseline,
                "model_name": model,
                **metrics,
            }
        )

    failure_rows = [
        {"topology": topology, "failure_tag": tag, "count": count}
        for (topology, tag), count in sorted(failure_counts.items())
    ]

    component_rows = [
        row for row in ablation_rows if row.get("disable_component_grounding") is not None
    ]

    backbone_rows: list[dict[str, Any]] = []
    backbone_agg: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (baseline, model, _track), results in main_agg.items():
        backbone_agg[(model, baseline)].extend(results)
    for (model, baseline), results in sorted(backbone_agg.items()):
        metrics = _aggregate_results(results)
        backbone_rows.append(
            {
                "model_name": model,
                "baseline_name": baseline,
                **metrics,
            }
        )

    _write_csv(output_dir / "main_leaderboard.csv", main_rows, ["baseline_name", "model_name", "track", "num_tasks", "vtsr", "mean_score"])
    _write_csv(output_dir / "topology_leaderboard.csv", topology_rows, ["topology", "baseline_name", "model_name", "num_tasks", "vtsr", "mean_score"])
    _write_csv(output_dir / "failure_tags_by_topology.csv", failure_rows, ["topology", "failure_tag", "count"])
    _write_csv(output_dir / "gate_ablation.csv", ablation_rows, [
        "suite_id",
        "baseline_name",
        "model_name",
        "track",
        "topology",
        "disable_formula_guardrails",
        "disable_component_grounding",
        "disable_correction_memory",
        "vtsr",
        "mean_score",
    ])
    _write_csv(output_dir / "claim_consistency.csv", claim_rows, [
        "task_id",
        "track",
        "topology",
        "baseline_name",
        "model_name",
        "claim_consistency_score",
    ])
    _write_csv(output_dir / "component_grounding_ablation.csv", component_rows, [
        "suite_id",
        "baseline_name",
        "model_name",
        "track",
        "topology",
        "disable_component_grounding",
        "vtsr",
        "mean_score",
    ])
    _write_csv(output_dir / "backbone_comparison.csv", backbone_rows, [
        "model_name",
        "baseline_name",
        "num_tasks",
        "vtsr",
        "mean_score",
    ])

    dump_json(
        {
            "main_leaderboard_csv": str(output_dir / "main_leaderboard.csv"),
            "topology_leaderboard_csv": str(output_dir / "topology_leaderboard.csv"),
            "failure_tags_by_topology_csv": str(output_dir / "failure_tags_by_topology.csv"),
            "gate_ablation_csv": str(output_dir / "gate_ablation.csv"),
            "claim_consistency_csv": str(output_dir / "claim_consistency.csv"),
            "component_grounding_ablation_csv": str(output_dir / "component_grounding_ablation.csv"),
            "backbone_comparison_csv": str(output_dir / "backbone_comparison.csv"),
        },
        output_dir / "analysis_manifest.json",
    )

    print(f"Wrote PE-Bench analysis tables to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
