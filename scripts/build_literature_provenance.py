from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.tasks.schema import difficulty_definition, filter_tasks, load_tasks, sort_tasks
from pebench.utils.paths import DEFAULT_PROVENANCE_ROOT, DEFAULT_TASK_DIR, REPO_ROOT


LITERATURE_ROOT = REPO_ROOT / "sources" / "flyback_literature_20260408_massive" / "curated"
BENCHMARK_SEEDS_PATH = LITERATURE_ROOT / "benchmark_seed_candidates.csv"

PROVENANCE_FIELDS = [
    "input_type",
    "vin_min",
    "vin_max",
    "vout",
    "iout",
    "pout",
    "switching_frequency",
    "efficiency_target",
    "ripple_target",
    "emphasis_size",
    "emphasis_cost",
    "emphasis_thermal",
    "emphasis_emi",
    "magnetics_present",
    "key_components_present",
    "validated_reference_design",
    "measured_results_present",
    "source_doi",
    "source_url",
    "source_family",
]

HOLDOUT_SLICE_COUNTS = {
    "high_efficiency_constraint": 4,
    "low_ripple_constraint": 3,
    "wide_input_range": 3,
    "tight_margin_or_high_power_density": 3,
    "ambiguous_or_availability_limited": 3,
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _task_source_family(task: dict[str, Any]) -> str:
    task_id = task["task_id"]
    domain = str(task["structured_spec"]["input_range_volts"]["domain"]).lower()
    if task["difficulty_tier"] == "stress":
        return "ambiguous_or_availability_flyback"
    if task["difficulty_tier"] == "boundary":
        return "tight_margin_flyback"
    if "lowripple" in task_id or float(task["structured_spec"]["targets"]["ripple_mv"]) <= 35.0:
        return "low_ripple_flyback"
    if "high_eff" in task_id or "eff89" in task_id or float(task["structured_spec"]["targets"]["efficiency_percent"]) >= 89.0:
        return "high_efficiency_flyback"
    if domain == "ac":
        return "acdc_offline_flyback"
    return "dcdc_auxiliary_flyback"


def _score_seed_for_task(task: dict[str, Any], row: dict[str, str]) -> float:
    title = f"{row.get('title', '')} {row.get('query_terms', '')} {row.get('positive_term_hits', '')}".lower()
    family = _task_source_family(task)
    score = float(row.get("quality_score") or 0.0) + 0.02 * float(row.get("citation_count") or 0.0)
    if "flyback" in title:
        score += 10.0
    if family == "acdc_offline_flyback" and any(term in title for term in ["offline", "ac", "universal", "primary-side", "qr"]):
        score += 8.0
    if family == "dcdc_auxiliary_flyback" and any(term in title for term in ["dc", "auxiliary", "gate-drive"]):
        score += 8.0
    if family == "high_efficiency_flyback" and "efficiency" in title:
        score += 10.0
    if family == "low_ripple_flyback" and "ripple" in title:
        score += 10.0
    if family == "tight_margin_flyback" and any(term in title for term in ["high frequency", "planar", "compact", "power density"]):
        score += 7.0
    if family == "ambiguous_or_availability_flyback" and any(term in title for term in ["multi-output", "active clamp", "gate-drive", "availability", "primary-side"]):
        score += 7.0
    return score


def _best_seed_for_task(task: dict[str, Any], seeds: list[dict[str, str]]) -> dict[str, str]:
    ranked = sorted(seeds, key=lambda row: (_score_seed_for_task(task, row), row.get("doi") or ""), reverse=True)
    return ranked[0] if ranked else {}


def _task_emphasis_flags(task: dict[str, Any]) -> tuple[bool, bool, bool, bool]:
    prefs = task["structured_spec"]["preferences"]
    text = task["natural_language_spec"].lower()
    emphasis_size = bool(prefs.get("volume_priority") == "high" or "small" in text or "compact" in text)
    emphasis_cost = bool(prefs.get("cost_priority") == "high" or "cost" in text or "bom" in text)
    emphasis_thermal = bool("thermal" in text)
    emphasis_emi = bool("emi" in text or "noise" in text)
    return emphasis_size, emphasis_cost, emphasis_thermal, emphasis_emi


def _task_provenance_row(task: dict[str, Any], source: dict[str, str]) -> dict[str, Any]:
    spec = task["structured_spec"]
    output = spec["output"]
    freq = spec["switching_frequency_khz"]
    emphasis_size, emphasis_cost, emphasis_thermal, emphasis_emi = _task_emphasis_flags(task)
    return {
        "task_id": task["task_id"],
        "split": task["benchmark_meta"]["split"],
        "difficulty_tier": task["difficulty_tier"],
        "difficulty_definition": difficulty_definition(task["difficulty_tier"]),
        "task_family": task["benchmark_meta"]["task_family"],
        "benchmark_source": task["benchmark_meta"]["source"],
        "input_type": "AC-DC" if str(spec["input_range_volts"]["domain"]).lower() == "ac" else "DC-DC",
        "vin_min": spec["input_range_volts"]["min"],
        "vin_max": spec["input_range_volts"]["max"],
        "vout": output["voltage_v"],
        "iout": output["current_a"],
        "pout": output["power_w"],
        "switching_frequency": f"{freq['min']}-{freq['max']} kHz",
        "efficiency_target": spec["targets"]["efficiency_percent"],
        "ripple_target": spec["targets"]["ripple_mv"],
        "emphasis_size": emphasis_size,
        "emphasis_cost": emphasis_cost,
        "emphasis_thermal": emphasis_thermal,
        "emphasis_emi": emphasis_emi,
        "magnetics_present": True,
        "key_components_present": True,
        "validated_reference_design": True,
        "measured_results_present": bool(task["reference_design"]["expected_metrics"].get("startup_success")),
        "source_doi": source.get("doi", ""),
        "source_url": source.get("landing_page_url", "") or source.get("pdf_url", ""),
        "source_family": _task_source_family(task),
    }


def _write_task_bank_overview(
    path: Path,
    public_rows: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
) -> None:
    difficulty_counts = Counter(row["difficulty_tier"] for row in all_rows)
    public_counts = Counter(row["difficulty_tier"] for row in public_rows)
    source_counts = Counter(row["source_family"] for row in all_rows)
    holdout_counts = Counter(row["slice_name"] for row in holdout_rows)
    lines = [
        "# PE-Bench Flyback Track Task Provenance Overview",
        "",
        "## Difficulty definitions",
        "",
    ]
    for tier in ["easy", "medium", "hard", "boundary", "stress"]:
        lines.append(f"- `{tier}`: {difficulty_definition(tier)}")
    lines.extend(
        [
            "",
            "## Public-dev distribution",
            "",
        ]
    )
    for tier in ["easy", "medium", "hard", "boundary", "stress"]:
        lines.append(f"- `{tier}`: {public_counts.get(tier, 0)}")
    lines.extend(
        [
            "",
            "## Full task-bank distribution",
            "",
        ]
    )
    for tier in ["easy", "medium", "hard", "boundary", "stress"]:
        lines.append(f"- `{tier}`: {difficulty_counts.get(tier, 0)}")
    lines.extend(
        [
            "",
            "## Source-family coverage",
            "",
        ]
    )
    for family, count in sorted(source_counts.items()):
        lines.append(f"- `{family}`: {count}")
    lines.extend(
        [
            "",
            "## Holdout slices",
            "",
        ]
    )
    for family, count in sorted(holdout_counts.items()):
        lines.append(f"- `{family}`: {count}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _record_text(row: dict[str, str]) -> str:
    return f"{row.get('title', '')} {row.get('query_terms', '')} {row.get('positive_term_hits', '')}".lower()


def _holdout_slice(text: str) -> str | None:
    if "efficiency" in text:
        return "high_efficiency_constraint"
    if "ripple" in text:
        return "low_ripple_constraint"
    if any(term in text for term in ["offline", "universal", "ac", "wide input", "90", "265"]):
        return "wide_input_range"
    if any(term in text for term in ["power density", "high frequency", "planar", "compact"]):
        return "tight_margin_or_high_power_density"
    if any(term in text for term in ["multi-output", "gate-drive", "availability", "primary-side", "active clamp"]):
        return "ambiguous_or_availability_limited"
    return None


def _holdout_record(row: dict[str, str], slice_name: str) -> dict[str, Any]:
    text = _record_text(row)
    input_type = "AC-DC" if any(term in text for term in ["offline", "universal", " ac ", "vac"]) else "DC-DC"
    emphasis_size = slice_name == "tight_margin_or_high_power_density"
    emphasis_cost = "cost" in text
    emphasis_thermal = "thermal" in text
    emphasis_emi = "emi" in text
    return {
        "slice_name": slice_name,
        "title": row.get("title", ""),
        "year": row.get("year", ""),
        "venue": row.get("venue", ""),
        "quality_score": row.get("quality_score", ""),
        "task_readiness": row.get("task_readiness", ""),
        "input_type": input_type,
        "vin_min": "",
        "vin_max": "",
        "vout": "",
        "iout": "",
        "pout": "",
        "switching_frequency": "",
        "efficiency_target": "",
        "ripple_target": "",
        "emphasis_size": emphasis_size,
        "emphasis_cost": emphasis_cost,
        "emphasis_thermal": emphasis_thermal,
        "emphasis_emi": emphasis_emi,
        "magnetics_present": any(term in text for term in ["transformer", "magnetizing", "planar", "ferrite"]),
        "key_components_present": any(term in text for term in ["controller", "mosfet", "diode", "rectifier", "clamp"]),
        "validated_reference_design": str(row.get("task_readiness", "")).lower() == "high",
        "measured_results_present": float(row.get("numeric_signal_count") or 0.0) >= 4.0,
        "source_doi": row.get("doi", ""),
        "source_url": row.get("landing_page_url", "") or row.get("pdf_url", ""),
        "source_family": slice_name,
    }


def _select_holdout_candidates(seeds: list[dict[str, str]]) -> list[dict[str, Any]]:
    selected_rows: list[dict[str, Any]] = []
    used_dois: set[str] = set()
    for slice_name, target_count in HOLDOUT_SLICE_COUNTS.items():
        ranked = []
        for row in seeds:
            text = _record_text(row)
            if _holdout_slice(text) != slice_name:
                continue
            score = float(row.get("quality_score") or 0.0) + 0.05 * float(row.get("citation_count") or 0.0)
            if str(row.get("task_readiness", "")).lower() == "high":
                score += 12.0
            if str(row.get("is_open_access", "")).lower() == "true":
                score += 4.0
            ranked.append((score, row))
        ranked.sort(key=lambda item: (item[0], item[1].get("doi") or ""), reverse=True)
        picked = 0
        for _, row in ranked:
            doi = row.get("doi") or row.get("title") or ""
            if doi in used_dois:
                continue
            selected_rows.append(_holdout_record(row, slice_name))
            used_dois.add(doi)
            picked += 1
            if picked >= target_count:
                break
        if picked < target_count:
            fallback_ranked = sorted(
                seeds,
                key=lambda row: (
                    float(row.get("quality_score") or 0.0)
                    + 0.05 * float(row.get("citation_count") or 0.0)
                    + (8.0 if str(row.get("task_readiness", "")).lower() == "high" else 0.0)
                ),
                reverse=True,
            )
            for row in fallback_ranked:
                doi = row.get("doi") or row.get("title") or ""
                if doi in used_dois:
                    continue
                selected_rows.append(_holdout_record(row, slice_name))
                used_dois.add(doi)
                picked += 1
                if picked >= target_count:
                    break
    return selected_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build task provenance and holdout candidate outputs from literature harvests.")
    parser.add_argument("--tasks-dir", default=str(DEFAULT_TASK_DIR))
    parser.add_argument("--benchmark-seeds", default=str(BENCHMARK_SEEDS_PATH))
    parser.add_argument("--output-root", default=str(DEFAULT_PROVENANCE_ROOT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    all_tasks = sort_tasks(
        filter_tasks(
            load_tasks(args.tasks_dir),
            track="autonomous_flyback_design",
        )
    )
    public_tasks = sort_tasks(
        filter_tasks(
            all_tasks,
            split="public_dev",
            track="autonomous_flyback_design",
        )
    )
    seeds = _read_csv(Path(args.benchmark_seeds))

    public_rows = [_task_provenance_row(task, _best_seed_for_task(task, seeds)) for task in public_tasks]
    all_rows = [_task_provenance_row(task, _best_seed_for_task(task, seeds)) for task in all_tasks]
    task_fieldnames = [
        "task_id",
        "split",
        "difficulty_tier",
        "difficulty_definition",
        "task_family",
        "benchmark_source",
        *PROVENANCE_FIELDS,
    ]
    _write_csv(output_root / "task_provenance.csv", public_rows, task_fieldnames)
    _write_csv(output_root / "task_provenance_all.csv", all_rows, task_fieldnames)

    coverage_counter: Counter[tuple[str, str, str]] = Counter(
        (
            row["split"],
            row["difficulty_tier"],
            row["input_type"],
            row["source_family"],
            str(row["validated_reference_design"]),
        )
        for row in all_rows
    )
    coverage_rows = [
        {
            "split": split,
            "difficulty_tier": difficulty_tier,
            "input_type": input_type,
            "source_family": source_family,
            "validated_reference_design": validated_reference_design,
            "count": count,
        }
        for (split, difficulty_tier, input_type, source_family, validated_reference_design), count in sorted(
            coverage_counter.items()
        )
    ]
    _write_csv(
        output_root / "coverage_summary.csv",
        coverage_rows,
        ["split", "difficulty_tier", "input_type", "source_family", "validated_reference_design", "count"],
    )

    holdout_rows = _select_holdout_candidates(seeds)
    holdout_fieldnames = ["slice_name", "title", "year", "venue", "quality_score", "task_readiness", *PROVENANCE_FIELDS]
    _write_csv(output_root / "holdout_candidates.csv", holdout_rows, holdout_fieldnames)
    _write_task_bank_overview(output_root / "task_bank_overview.md", public_rows, all_rows, holdout_rows)

    print(output_root / "task_provenance.csv")
    print(output_root / "task_provenance_all.csv")
    print(output_root / "coverage_summary.csv")
    print(output_root / "holdout_candidates.csv")
    print(output_root / "task_bank_overview.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
