from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from pebench.utils.io import load_yaml


TASK_REQUIRED_FIELDS = {
    "task_id",
    "natural_language_spec",
    "difficulty_tier",
    "benchmark_meta",
    "structured_spec",
    "evaluation_rubric",
    "reference_design",
    "known_failure_modes",
}

STRUCTURED_SPEC_REQUIRED_FIELDS = {
    "input_range_volts",
    "output",
    "switching_frequency_khz",
    "targets",
    "constraints",
    "preferences",
    "component_catalog_version",
}

REFERENCE_DESIGN_REQUIRED_FIELDS = {
    "topology",
    "turns_ratio_primary_to_secondary",
    "magnetizing_inductance_uh",
    "switching_frequency_khz",
    "duty_cycle_max",
    "primary_peak_current_a",
    "selected_components",
    "expected_metrics",
    "cost_proxy_usd",
}

BENCHMARK_META_REQUIRED_FIELDS = {"track", "split", "task_family", "source"}

ALLOWED_DIFFICULTY_TIERS = {"easy", "medium", "hard", "boundary", "stress"}
ALLOWED_TRACKS = {"autonomous_flyback_design"}
ALLOWED_SPLITS = {"public_dev", "private_holdout"}
DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2, "boundary": 3, "stress": 4}
DIFFICULTY_DEFINITIONS = {
    "easy": "Standard flyback tasks with comfortable margins and limited closure burden.",
    "medium": "Standard flyback tasks that still have clean specifications but require nontrivial closure across theory, BOM, and simulator metrics.",
    "hard": "Cleanly specified tasks with stronger engineering requirements such as tighter ripple, higher efficiency, or more demanding operating points.",
    "boundary": "Feasible tasks located near margin or feasibility boundaries where safe closure depends on careful design choices.",
    "stress": "Tasks with conflicting objectives, ambiguity, or escalation-sensitive conditions intended to test robustness rather than only nominal closure.",
}
DEFAULT_RUBRIC_NAMES = {
    "spec_grounding",
    "theoretical_feasibility",
    "bom_validity",
    "efficiency_target",
    "ripple_target",
    "stress_margin",
    "cost_reasonableness",
}
PERFORMANCE_RUBRIC_NAMES = {
    "efficiency_target",
    "ripple_target",
    "stress_margin",
}


def load_task(path: str | Path) -> dict[str, Any]:
    return load_yaml(path)


def iter_task_files(task_dir: str | Path) -> list[Path]:
    return sorted(Path(task_dir).glob("*.yaml"))


def load_tasks(task_dir: str | Path) -> list[dict[str, Any]]:
    return [load_task(path) for path in iter_task_files(task_dir)]


def count_by_difficulty(tasks: list[dict[str, Any]]) -> Counter[str]:
    return Counter(task["difficulty_tier"] for task in tasks)


def filter_tasks(
    tasks: list[dict[str, Any]],
    *,
    split: str | None = None,
    track: str | None = None,
    difficulty_tiers: set[str] | None = None,
) -> list[dict[str, Any]]:
    filtered = tasks
    if split is not None:
        filtered = [task for task in filtered if task.get("benchmark_meta", {}).get("split") == split]
    if track is not None:
        filtered = [task for task in filtered if task.get("benchmark_meta", {}).get("track") == track]
    if difficulty_tiers is not None:
        filtered = [task for task in filtered if task["difficulty_tier"] in difficulty_tiers]
    return filtered


def sort_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        tasks,
        key=lambda task: (DIFFICULTY_ORDER.get(task["difficulty_tier"], 999), task["task_id"]),
    )


def difficulty_definition(tier: str) -> str:
    return DIFFICULTY_DEFINITIONS[tier]


def validate_task_dict(task: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    missing_fields = TASK_REQUIRED_FIELDS - task.keys()
    if missing_fields:
        errors.append(f"Missing top-level fields: {sorted(missing_fields)}")
        return errors

    if task["difficulty_tier"] not in ALLOWED_DIFFICULTY_TIERS:
        errors.append(
            f"Invalid difficulty_tier '{task['difficulty_tier']}'. "
            f"Allowed: {sorted(ALLOWED_DIFFICULTY_TIERS)}"
        )

    if not isinstance(task["natural_language_spec"], str) or not task["natural_language_spec"].strip():
        errors.append("natural_language_spec must be a non-empty string")

    benchmark_meta = task["benchmark_meta"]
    if not isinstance(benchmark_meta, dict):
        errors.append("benchmark_meta must be a mapping")
    else:
        missing_benchmark_meta = BENCHMARK_META_REQUIRED_FIELDS - benchmark_meta.keys()
        if missing_benchmark_meta:
            errors.append(f"Missing benchmark_meta fields: {sorted(missing_benchmark_meta)}")
        if benchmark_meta.get("track") not in ALLOWED_TRACKS:
            errors.append(
                f"Invalid benchmark_meta.track '{benchmark_meta.get('track')}'. "
                f"Allowed: {sorted(ALLOWED_TRACKS)}"
            )
        if benchmark_meta.get("split") not in ALLOWED_SPLITS:
            errors.append(
                f"Invalid benchmark_meta.split '{benchmark_meta.get('split')}'. "
                f"Allowed: {sorted(ALLOWED_SPLITS)}"
            )
        if not str(benchmark_meta.get("task_family") or "").strip():
            errors.append("benchmark_meta.task_family must be a non-empty string")
        if not str(benchmark_meta.get("source") or "").strip():
            errors.append("benchmark_meta.source must be a non-empty string")

    structured_spec = task["structured_spec"]
    if not isinstance(structured_spec, dict):
        errors.append("structured_spec must be a mapping")
    else:
        missing_structured = STRUCTURED_SPEC_REQUIRED_FIELDS - structured_spec.keys()
        if missing_structured:
            errors.append(f"Missing structured_spec fields: {sorted(missing_structured)}")

    rubric = task["evaluation_rubric"]
    if not isinstance(rubric, list) or not rubric:
        errors.append("evaluation_rubric must be a non-empty list")
    else:
        rubric_names = set()
        total_weight = 0.0
        for entry in rubric:
            if not isinstance(entry, dict):
                errors.append("evaluation_rubric entries must be mappings")
                continue
            if "name" not in entry or "weight" not in entry:
                errors.append("Each rubric entry must include name and weight")
                continue
            rubric_names.add(entry["name"])
            total_weight += float(entry["weight"])
        if rubric_names != DEFAULT_RUBRIC_NAMES:
            errors.append(
                "Rubric names must match the PE-Bench v0 set: "
                f"{sorted(DEFAULT_RUBRIC_NAMES)}"
            )
        if round(total_weight, 3) != 100.0:
            errors.append(f"Rubric weights must sum to 100. Got {total_weight}.")

    reference_design = task["reference_design"]
    if not isinstance(reference_design, dict):
        errors.append("reference_design must be a mapping")
    else:
        missing_reference = REFERENCE_DESIGN_REQUIRED_FIELDS - reference_design.keys()
        if missing_reference:
            errors.append(f"Missing reference_design fields: {sorted(missing_reference)}")

    if not isinstance(task["known_failure_modes"], list) or not task["known_failure_modes"]:
        errors.append("known_failure_modes must be a non-empty list")

    return errors


def validate_task_file(path: str | Path) -> list[str]:
    task = load_task(path)
    return validate_task_dict(task)
