from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze a completed or in-progress final-78 API run into auditable summary evidence."
    )
    parser.add_argument("--run-root", required=True, help="Path to a run created by scripts/run_final78_experiments.py")
    parser.add_argument("--output-dir", default=None, help="Default: <run-root>/frozen_actual_run")
    parser.add_argument(
        "--label",
        default="frozen_actual_api_run_records",
        help="Evidence label written into manifests and CSVs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_root = Path(args.run_root).resolve()
    raw_root = run_root / "raw_records"
    output_dir = Path(args.output_dir).resolve() if args.output_dir else run_root / "frozen_actual_run"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not raw_root.exists():
        raise SystemExit(f"Missing raw_records directory: {raw_root}")

    run_manifest = _load_json(run_root / "run_manifest.json") if (run_root / "run_manifest.json").exists() else {}
    status = _load_json(run_root / "status.json") if (run_root / "status.json").exists() else {}
    queue_rows = _read_csv(run_root / "queue.csv") if (run_root / "queue.csv").exists() else []

    suite_rows: list[dict[str, Any]] = []
    task_rows: list[dict[str, Any]] = []

    for suite_dir in _iter_suite_dirs(raw_root):
        suite_summary = _load_json(suite_dir / "suite_summary.json")
        run_config = _load_json(suite_dir / "run_config.json") if (suite_dir / "run_config.json").exists() else {}
        ablations = _suite_ablations(suite_summary, run_config)
        suite_row = {
            "suite_id": suite_summary.get("suite_id"),
            "baseline_name": suite_summary.get("baseline_name"),
            "model_name": suite_summary.get("model_name"),
            "seed": suite_summary.get("seed"),
            "track": suite_summary.get("track"),
            "topology": suite_summary.get("topology"),
            "num_tasks": suite_summary.get("num_tasks"),
            "successes": suite_summary.get("successes"),
            "vtsr": suite_summary.get("vtsr"),
            "mean_score": suite_summary.get("mean_score"),
            "disable_formula_guardrails": bool(ablations.get("disable_formula_guardrails", False)),
            "disable_component_grounding": bool(ablations.get("disable_component_grounding", False)),
            "disable_correction_memory": bool(ablations.get("disable_correction_memory", False)),
            "suite_dir": str(suite_dir.relative_to(run_root)),
            "evidence_level": args.label,
        }
        suite_rows.append(suite_row)

        for result_path in sorted((suite_dir / "task_results").glob("*.json")):
            result = _load_json(result_path)
            candidate_path = suite_dir / "candidates" / f"{result.get('task_id')}.json"
            candidate = _load_json(candidate_path) if candidate_path.exists() else {}
            failure_tags = [str(tag) for tag in result.get("failure_tags", [])]
            task_rows.append(
                {
                    "suite_id": suite_summary.get("suite_id"),
                    "baseline_name": result.get("baseline_name") or suite_summary.get("baseline_name"),
                    "model_name": result.get("model_name") or suite_summary.get("model_name"),
                    "seed": result.get("seed") or suite_summary.get("seed"),
                    "track": suite_summary.get("track"),
                    "topology": result.get("topology") or suite_summary.get("topology"),
                    "task_id": result.get("task_id"),
                    "pass_fail": bool(result.get("pass_fail", False)),
                    "score_total": _float(result.get("score_total", 0.0)),
                    "partial_score": _partial_score(result),
                    "sim_calls": _sim_calls(result, candidate),
                    "unsupported_value": _has_unsupported_value(result, failure_tags),
                    "invalid_bom": _has_invalid_bom(result, failure_tags),
                    "failure_tags": ";".join(failure_tags),
                    "candidate_path": str(candidate_path.relative_to(run_root)),
                    "result_path": str(result_path.relative_to(run_root)),
                    "disable_formula_guardrails": suite_row["disable_formula_guardrails"],
                    "disable_component_grounding": suite_row["disable_component_grounding"],
                    "disable_correction_memory": suite_row["disable_correction_memory"],
                    "evidence_level": args.label,
                }
            )

    job_rows = _aggregate_jobs(task_rows, evidence_label=args.label)
    leaderboard_rows = _aggregate_leaderboard(
        job_rows,
        task_rows,
        ablation_only=False,
        evidence_label=args.label,
    )
    ablation_rows = _aggregate_leaderboard(
        job_rows,
        task_rows,
        ablation_only=True,
        evidence_label=args.label,
    )
    track_rows = _aggregate_tracks(task_rows, evidence_label=args.label)
    integrity = _integrity_report(
        run_root=run_root,
        run_manifest=run_manifest,
        status=status,
        queue_rows=queue_rows,
        suite_rows=suite_rows,
        task_rows=task_rows,
        job_rows=job_rows,
        evidence_label=args.label,
    )

    _write_csv(
        output_dir / "suite_index.csv",
        suite_rows,
        [
            "suite_id",
            "baseline_name",
            "model_name",
            "seed",
            "track",
            "topology",
            "num_tasks",
            "successes",
            "vtsr",
            "mean_score",
            "disable_formula_guardrails",
            "disable_component_grounding",
            "disable_correction_memory",
            "suite_dir",
            "evidence_level",
        ],
    )
    _write_csv(
        output_dir / "task_results.csv",
        task_rows,
        [
            "suite_id",
            "baseline_name",
            "model_name",
            "seed",
            "track",
            "topology",
            "task_id",
            "pass_fail",
            "score_total",
            "partial_score",
            "sim_calls",
            "unsupported_value",
            "invalid_bom",
            "failure_tags",
            "candidate_path",
            "result_path",
            "disable_formula_guardrails",
            "disable_component_grounding",
            "disable_correction_memory",
            "evidence_level",
        ],
    )
    _write_csv(
        output_dir / "job_summary_78task.csv",
        job_rows,
        [
            "job_label",
            "baseline_name",
            "model_name",
            "seed",
            "variant",
            "task_count",
            "successes",
            "vtsr",
            "mean_score",
            "is_complete_78task_job",
            "evidence_level",
        ],
    )
    _write_csv(
        output_dir / "leaderboard_summary.csv",
        leaderboard_rows,
        [
            "baseline_name",
            "model_name",
            "variant",
            "seed_count",
            "complete_seed_count",
            "task_records",
            "vtsr_mean",
            "vtsr_std",
            "partial",
            "pass_at_3",
            "unsupported_values_percent",
            "invalid_bom_percent",
            "sim_calls",
            "mean_score",
            "evidence_level",
        ],
    )
    _write_csv(
        output_dir / "ablation_summary.csv",
        ablation_rows,
        [
            "baseline_name",
            "model_name",
            "variant",
            "seed_count",
            "complete_seed_count",
            "task_records",
            "vtsr_mean",
            "vtsr_std",
            "partial",
            "pass_at_3",
            "unsupported_values_percent",
            "invalid_bom_percent",
            "sim_calls",
            "mean_score",
            "evidence_level",
        ],
    )
    _write_csv(
        output_dir / "track_summary.csv",
        track_rows,
        [
            "baseline_name",
            "model_name",
            "variant",
            "track",
            "seed_count",
            "task_records",
            "vtsr_mean",
            "mean_score",
            "evidence_level",
        ],
    )
    _write_json(output_dir / "integrity_report.json", integrity)
    _write_json(
        output_dir / "manifest.json",
        {
            "created_at_utc": _utc_now(),
            "run_root": str(run_root),
            "raw_records_root": str(raw_root.relative_to(run_root)),
            "source_runner": "scripts/run_final78_experiments.py",
            "evidence_level": args.label,
            "api_key_recorded": False,
            "files": [
                "suite_index.csv",
                "task_results.csv",
                "job_summary_78task.csv",
                "leaderboard_summary.csv",
                "ablation_summary.csv",
                "track_summary.csv",
                "integrity_report.json",
                "checksums.sha256",
            ],
            "run_manifest": run_manifest,
            "run_status": status,
        },
    )
    _write_checksums(run_root=run_root, output_dir=output_dir)

    print(f"Wrote frozen API-run evidence to {output_dir}")
    print(
        "Integrity: "
        f"{integrity['completed_78task_jobs']}/{integrity['observed_job_count']} observed jobs complete, "
        f"{integrity['task_result_count']} task result records."
    )
    return 0


def _iter_suite_dirs(raw_root: Path) -> Iterable[Path]:
    for path in sorted(raw_root.glob("**/suites/*/suite_summary.json")):
        yield path.parent


def _aggregate_jobs(task_rows: list[dict[str, Any]], *, evidence_label: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in task_rows:
        key = (
            str(row["baseline_name"]),
            str(row["model_name"]),
            str(row["seed"]),
            _variant(row),
        )
        grouped[key].append(row)

    rows: list[dict[str, Any]] = []
    for (baseline, model, seed, variant), rows_for_job in sorted(grouped.items()):
        successes = sum(1 for row in rows_for_job if row["pass_fail"])
        task_count = len(rows_for_job)
        mean_score = sum(_float(row["score_total"]) for row in rows_for_job) / max(1, task_count)
        rows.append(
            {
                "job_label": f"{baseline}__{model}__seed{seed}__{variant}",
                "baseline_name": baseline,
                "model_name": model,
                "seed": seed,
                "variant": variant,
                "task_count": task_count,
                "successes": successes,
                "vtsr": round(successes / max(1, task_count), 6),
                "mean_score": round(mean_score, 6),
                "is_complete_78task_job": task_count == 78,
                "evidence_level": evidence_label,
            }
        )
    return rows


def _aggregate_leaderboard(
    job_rows: list[dict[str, Any]],
    task_rows: list[dict[str, Any]],
    *,
    ablation_only: bool,
    evidence_label: str,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in job_rows:
        is_ablation = row["variant"] != "full"
        if ablation_only != is_ablation:
            continue
        grouped[(str(row["baseline_name"]), str(row["model_name"]), str(row["variant"]))].append(row)

    task_grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in task_rows:
        variant = _variant(row)
        is_ablation = variant != "full"
        if ablation_only != is_ablation:
            continue
        task_grouped[(str(row["baseline_name"]), str(row["model_name"]), variant)].append(row)

    output: list[dict[str, Any]] = []
    for (baseline, model, variant), rows in sorted(grouped.items()):
        raw_rows = task_grouped.get((baseline, model, variant), [])
        vtsrs = [_float(row["vtsr"]) for row in rows]
        mean_scores = [_float(row["mean_score"]) for row in rows]
        by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for raw_row in raw_rows:
            by_task[str(raw_row.get("task_id"))].append(raw_row)
        output.append(
            {
                "baseline_name": baseline,
                "model_name": model,
                "variant": variant,
                "seed_count": len(rows),
                "complete_seed_count": sum(1 for row in rows if row["is_complete_78task_job"]),
                "task_records": sum(int(row["task_count"]) for row in rows),
                "vtsr_mean": round(sum(vtsrs) / max(1, len(vtsrs)), 6),
                "vtsr_std": round(_std(vtsrs), 6),
                "partial": round(sum(_float(row.get("partial_score")) for row in raw_rows) / max(1, len(raw_rows)), 6),
                "pass_at_3": round(
                    sum(1 for task_items in by_task.values() if any(_bool(item.get("pass_fail")) for item in task_items))
                    / max(1, len(by_task)),
                    6,
                ),
                "unsupported_values_percent": round(
                    100.0 * sum(1 for row in raw_rows if _bool(row.get("unsupported_value"))) / max(1, len(raw_rows)),
                    6,
                ),
                "invalid_bom_percent": round(
                    100.0 * sum(1 for row in raw_rows if _bool(row.get("invalid_bom"))) / max(1, len(raw_rows)),
                    6,
                ),
                "sim_calls": round(sum(_float(row.get("sim_calls")) for row in raw_rows) / max(1, len(raw_rows)), 6),
                "mean_score": round(sum(mean_scores) / max(1, len(mean_scores)), 6),
                "evidence_level": evidence_label,
            }
        )
    return output


def _aggregate_tracks(task_rows: list[dict[str, Any]], *, evidence_label: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in task_rows:
        grouped[
            (
                str(row["baseline_name"]),
                str(row["model_name"]),
                _variant(row),
                str(row["track"]),
                str(row["seed"]),
            )
        ].append(row)

    seed_rows: dict[tuple[str, str, str, str], list[dict[str, float]]] = defaultdict(list)
    for (baseline, model, variant, track, _seed), rows in grouped.items():
        successes = sum(1 for row in rows if row["pass_fail"])
        score = sum(_float(row["score_total"]) for row in rows) / max(1, len(rows))
        seed_rows[(baseline, model, variant, track)].append(
            {
                "task_count": float(len(rows)),
                "vtsr": successes / max(1, len(rows)),
                "mean_score": score,
            }
        )

    output: list[dict[str, Any]] = []
    for (baseline, model, variant, track), rows in sorted(seed_rows.items()):
        output.append(
            {
                "baseline_name": baseline,
                "model_name": model,
                "variant": variant,
                "track": track,
                "seed_count": len(rows),
                "task_records": int(sum(row["task_count"] for row in rows)),
                "vtsr_mean": round(sum(row["vtsr"] for row in rows) / max(1, len(rows)), 6),
                "mean_score": round(sum(row["mean_score"] for row in rows) / max(1, len(rows)), 6),
                "evidence_level": evidence_label,
            }
        )
    return output


def _integrity_report(
    *,
    run_root: Path,
    run_manifest: dict[str, Any],
    status: dict[str, Any],
    queue_rows: list[dict[str, Any]],
    suite_rows: list[dict[str, Any]],
    task_rows: list[dict[str, Any]],
    job_rows: list[dict[str, Any]],
    evidence_label: str,
) -> dict[str, Any]:
    jobs_root = run_root / "jobs"
    done_markers = sorted(jobs_root.glob("*.done.json")) if jobs_root.exists() else []
    failed_markers = sorted(jobs_root.glob("*.failed.json")) if jobs_root.exists() else []
    expected_job_count = int(run_manifest.get("job_count") or len(queue_rows) or 0)
    return {
        "created_at_utc": _utc_now(),
        "evidence_level": evidence_label,
        "run_name": run_root.name,
        "runner_state": status.get("state"),
        "expected_job_count": expected_job_count,
        "done_marker_count": len(done_markers),
        "failed_marker_count": len(failed_markers),
        "observed_suite_count": len(suite_rows),
        "observed_job_count": len(job_rows),
        "completed_78task_jobs": sum(1 for row in job_rows if row["is_complete_78task_job"]),
        "task_result_count": len(task_rows),
        "expected_task_results_if_complete": expected_job_count * 78 if expected_job_count else None,
        "api_key_recorded": False,
        "complete": bool(expected_job_count and len(done_markers) == expected_job_count and not failed_markers),
        "notes": [
            "Raw candidate and task-result JSON files remain under raw_records/.",
            "This freeze step records summaries and checksums; it does not store API credentials.",
            "If runner_state is not completed, rerun this script after the API run finishes.",
        ],
    }


def _suite_ablations(suite_summary: dict[str, Any], run_config: dict[str, Any]) -> dict[str, bool]:
    summary_flags = suite_summary.get("ablations", {}) or {}
    return {
        "disable_formula_guardrails": _bool(
            summary_flags.get("disable_formula_guardrails", run_config.get("disable_formula_guardrails", False))
        ),
        "disable_component_grounding": _bool(
            summary_flags.get("disable_component_grounding", run_config.get("disable_component_grounding", False))
        ),
        "disable_correction_memory": _bool(
            summary_flags.get("disable_correction_memory", run_config.get("disable_correction_memory", False))
        ),
    }


def _variant(row: dict[str, Any]) -> str:
    flags = []
    if _bool(row.get("disable_formula_guardrails")):
        flags.append("without_formula_guardrails")
    if _bool(row.get("disable_component_grounding")):
        flags.append("without_component_grounding")
    if _bool(row.get("disable_correction_memory")):
        flags.append("without_correction_memory")
    return "__".join(flags) if flags else "full"


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_checksums(*, run_root: Path, output_dir: Path) -> None:
    lines: list[str] = []
    for root in (run_root / "raw_records", output_dir):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name == "checksums.sha256":
                continue
            try:
                relative = path.relative_to(run_root)
            except ValueError:
                relative = path.relative_to(output_dir)
            lines.append(f"{_sha256(path)}  {relative}")
    (output_dir / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _partial_score(result: dict[str, Any]) -> float:
    if "partial_score" in result:
        return round(_float(result.get("partial_score")), 6)
    aggregate = result.get("aggregate_scores", {})
    if isinstance(aggregate, dict) and "partial_score" in aggregate:
        return round(_float(aggregate.get("partial_score")), 6)
    return round(_float(result.get("score_total")) / 100.0, 6)


def _sim_calls(result: dict[str, Any], candidate: dict[str, Any]) -> float:
    runtime = result.get("runtime_stats", {})
    if isinstance(runtime, dict) and runtime.get("sim_calls") is not None:
        return _float(runtime.get("sim_calls"))
    simulation_config = candidate.get("simulation_config", {})
    if isinstance(simulation_config, dict) and simulation_config.get("max_sim_calls") is not None:
        return _float(simulation_config.get("max_sim_calls"))
    metadata = candidate.get("metadata", {})
    if isinstance(metadata, dict) and metadata.get("sim_calls_used") is not None:
        return _float(metadata.get("sim_calls_used"))
    return 0.0


def _has_unsupported_value(result: dict[str, Any], failure_tags: list[str]) -> bool:
    if "Optimistic but Unrealistic Claim" in failure_tags:
        return True
    for violation in result.get("constraint_violations", []):
        if not isinstance(violation, dict):
            continue
        text = " ".join(str(violation.get(key, "")) for key in ("constraint", "group", "observed", "limit")).lower()
        if "claim" in text or "unsupported" in text or "reported" in text or "unrealistic" in text:
            return True
    runtime = result.get("runtime_stats", {})
    return isinstance(runtime, dict) and str(runtime.get("claim_status", "")).lower() in {"unsupported", "unrealistic"}


def _has_invalid_bom(result: dict[str, Any], failure_tags: list[str]) -> bool:
    if "Invalid or Unsafe BOM" in failure_tags:
        return True
    for violation in result.get("constraint_violations", []):
        if not isinstance(violation, dict):
            continue
        text = " ".join(str(violation.get(key, "")) for key in ("constraint", "group", "observed", "limit")).lower()
        if "bom" in text or "component" in text or "catalog" in text:
            return True
    return False


def _std(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
