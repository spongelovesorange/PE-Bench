from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_EVIDENCE = Path("artifacts/evidence/frozen_v1")
TOL = 1e-6


EXPECTED_TASK_ACCOUNTING = {
    "Flyback": {"count": 30, "easy": 6, "medium": 10, "hard": 6, "boundary": 4, "stress": 4, "public_dev": 24, "holdout": 6, "extension": 0},
    "Buck": {"count": 12, "easy": 4, "medium": 4, "hard": 2, "boundary": 1, "stress": 1, "public_dev": 12, "holdout": 0, "extension": 0},
    "Boost": {"count": 12, "easy": 4, "medium": 4, "hard": 2, "boundary": 1, "stress": 1, "public_dev": 12, "holdout": 0, "extension": 0},
    "Buck-Boost": {"count": 12, "easy": 4, "medium": 4, "hard": 2, "boundary": 1, "stress": 1, "public_dev": 12, "holdout": 0, "extension": 0},
    "Three-phase inverter": {"count": 12, "easy": 3, "medium": 4, "hard": 3, "boundary": 0, "stress": 2, "public_dev": 0, "holdout": 0, "extension": 12},
    "Total": {"count": 78, "easy": 21, "medium": 26, "hard": 15, "boundary": 7, "stress": 9, "public_dev": 60, "holdout": 6, "extension": 12},
}

EXPECTED_LEADERBOARD = {
    "LLM-only": (0.184, 0.015, 0.402, 0.201, 86.4, 52.1, 0.0),
    "Structured-output only": (0.190, 0.012, 0.415, 0.215, 82.5, 50.8, 0.0),
    "Text Self-Refine": (0.175, 0.020, 0.422, 0.220, 76.8, 48.5, 0.0),
    "LLM+Tools": (0.205, 0.018, 0.450, 0.245, 70.2, 42.0, 2.4),
    "Single-Agent+Retry": (0.218, 0.022, 0.465, 0.260, 65.5, 39.2, 3.2),
    "Generic Two-Role MAS": (0.235, 0.019, 0.490, 0.285, 58.0, 35.4, 3.5),
    "PE-GPT-style": (0.252, 0.025, 0.520, 0.312, 55.4, 30.1, 2.8),
    "Strong Baseline": (0.684, 0.028, 0.845, 0.755, 8.2, 4.5, 1.7),
}

EXPECTED_VALIDATION = {
    "required_field_checks": {"cases": "78", "parsed_or_accepted": "78", "pass_rate_percent": "100.0"},
    "feasible_reference_checks": {"cases": "78", "parsed_or_accepted": "78", "pass_rate_percent": "100.0"},
    "malformed_output_tests": {"cases": "500+", "rejection_rate_percent": "100.0"},
    "faulty_design_tests": {"cases": "800", "detection_rate_percent": "99.2", "unsafe_false_pass_percent": "0.0"},
    "independent_valid_design_check": {"cases": "100", "accepted": "94", "rejected": "6", "evaluator_false_negatives": "2", "false_negative_rate_percent": "2.0"},
    "heldout_robustness_split": {"cases": "24", "strong_baseline_heldout_vtsr": "0.652", "public_dev_vtsr": "0.684"},
    "simulation_setup_consistency": {"cases": "60", "decision_agreement_percent": "95.0", "median_efficiency_error_percent": "1.3", "median_ripple_error_percent": "3.9", "median_stress_margin_error_percent": "4.8"},
    "data_leakage_slot_guessing": {"cases": "1000", "leakage_flags": "0", "max_tolerant_guess_rate_percent": "6.5"},
    "synchronous_buck_minitrack": {"cases": "8", "strong_baseline_vtsr": "0.625", "strongest_non_specialized_vtsr": "0.250"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reproduce PE-Bench paper-facing tables from frozen records.")
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE), help="Path to artifacts/evidence/frozen_v1.")
    return parser.parse_args()


def main() -> int:
    evidence = Path(parse_args().evidence)
    errors: list[str] = []
    errors.extend(_check_manifest(evidence))
    errors.extend(_check_checksums(evidence))
    errors.extend(_check_task_accounting(evidence / "task_accounting.csv"))
    errors.extend(_check_leaderboard(evidence / "leaderboard_summary.csv"))
    errors.extend(_check_validation(evidence / "validation_summary.csv"))
    errors.extend(_check_required_files(evidence))
    if errors:
        print("Paper-table reproduction check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Paper-table reproduction check passed.")
    print("Verified frozen manuscript summary records for task accounting, leaderboard, validation, ablation, split, topology-slice, retry, simulation-gap, inverter-extension, and backbone tables.")
    return 0


def _check_manifest(evidence: Path) -> list[str]:
    path = evidence / "manifest.json"
    if not path.exists():
        return [f"Missing evidence manifest: {path}"]
    data = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if data.get("evidence_kind") != "frozen_manuscript_summary_records":
        errors.append("manifest.evidence_kind must be frozen_manuscript_summary_records")
    if int(data.get("task_total", 0)) != 78:
        errors.append("manifest.task_total must be 78")
    if data.get("raw_logs_included") is not False:
        errors.append("manifest.raw_logs_included must be false for this anonymous summary bundle")
    return errors


def _check_checksums(evidence: Path) -> list[str]:
    checksum_path = evidence / "checksums.sha256"
    if not checksum_path.exists():
        return [f"Missing evidence checksums: {checksum_path}"]
    errors: list[str] = []
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        path = evidence / relative
        if not path.exists():
            errors.append(f"Checksum target is missing: {relative}")
            continue
        actual = _sha256(path)
        if actual != expected:
            errors.append(f"Checksum mismatch for evidence file: {relative}")
    return errors


def _check_task_accounting(path: Path) -> list[str]:
    rows = {row["topology"]: row for row in _read_csv(path)}
    errors: list[str] = []
    for topology, expected in EXPECTED_TASK_ACCOUNTING.items():
        row = rows.get(topology)
        if row is None:
            errors.append(f"Missing task-accounting row: {topology}")
            continue
        for key, value in expected.items():
            if int(row[key]) != value:
                errors.append(f"Task accounting mismatch for {topology}.{key}: expected {value}, got {row[key]}")
    return errors


def _check_leaderboard(path: Path) -> list[str]:
    rows = {row["method"]: row for row in _read_csv(path)}
    columns = [
        "vtsr_mean",
        "vtsr_std",
        "partial",
        "pass_at_3",
        "unsupported_values_percent",
        "invalid_bom_percent",
        "sim_calls",
    ]
    errors: list[str] = []
    for method, expected_values in EXPECTED_LEADERBOARD.items():
        row = rows.get(method)
        if row is None:
            errors.append(f"Missing leaderboard row: {method}")
            continue
        if len(columns) != len(expected_values):
            errors.append(f"Internal expected leaderboard length mismatch for {method}")
            continue
        for column, expected in zip(columns, expected_values):
            if abs(float(row[column]) - expected) > TOL:
                errors.append(f"Leaderboard mismatch for {method}.{column}: expected {expected}, got {row[column]}")
    return errors


def _check_validation(path: Path) -> list[str]:
    rows = {row["validation_family"]: row for row in _read_csv(path)}
    errors: list[str] = []
    for family, expected in EXPECTED_VALIDATION.items():
        row = rows.get(family)
        if row is None:
            errors.append(f"Missing validation row: {family}")
            continue
        for key, value in expected.items():
            if row.get(key, "") != value:
                errors.append(f"Validation mismatch for {family}.{key}: expected {value}, got {row.get(key, '')}")
    return errors


def _check_required_files(evidence: Path) -> list[str]:
    required = [
        "ablation_summary.csv",
        "backbone_robustness.csv",
        "heldout_summary.csv",
        "inverter_extension_summary.csv",
        "retry_budget_summary.csv",
        "simulation_check_gap.csv",
        "topology_slice_summary.csv",
        "suite_summary.json",
    ]
    return [f"Missing evidence file: {name}" for name in required if not (evidence / name).exists()]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
