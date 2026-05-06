from __future__ import annotations

from typing import Any


REQUIRED_RESULT_FIELDS = {
    "task_id",
    "difficulty_tier",
    "baseline_name",
    "model_name",
    "seed",
    "pass_fail",
    "score_total",
    "sub_scores",
    "constraint_violations",
    "simulation_metrics",
    "failure_tags",
    "failure_groups",
    "aggregate_scores",
    "execution_log",
    "runtime_stats",
}


def validate_result_dict(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing_fields = REQUIRED_RESULT_FIELDS - result.keys()
    if missing_fields:
        errors.append(f"Missing result fields: {sorted(missing_fields)}")
        return errors

    if not isinstance(result["pass_fail"], bool):
        errors.append("pass_fail must be a bool")

    if not isinstance(result["sub_scores"], dict):
        errors.append("sub_scores must be a mapping")

    if not isinstance(result["constraint_violations"], list):
        errors.append("constraint_violations must be a list")

    if not isinstance(result["simulation_metrics"], dict):
        errors.append("simulation_metrics must be a mapping")

    if not isinstance(result["failure_tags"], list):
        errors.append("failure_tags must be a list")

    if not isinstance(result["failure_groups"], list):
        errors.append("failure_groups must be a list")

    if not isinstance(result["aggregate_scores"], dict):
        errors.append("aggregate_scores must be a mapping")

    if not isinstance(result["execution_log"], list):
        errors.append("execution_log must be a list")

    if not isinstance(result["runtime_stats"], dict):
        errors.append("runtime_stats must be a mapping")

    return errors
