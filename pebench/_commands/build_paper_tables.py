from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE = REPO_ROOT / "artifacts" / "evidence" / "frozen_v1"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "reproduced_tables"
GENERATED_AT_UTC = "2026-05-06T00:00:00+00:00"

TABLE_SPECS = [
    (
        "task_accounting.csv",
        "Task Accounting",
        "Released task counts by topology, difficulty, and split.",
    ),
    (
        "leaderboard_summary.csv",
        "Main Leaderboard",
        "Paper-facing 78-task VTSR leaderboard summary.",
    ),
    (
        "validation_summary.csv",
        "Validation Summary",
        "Evaluator validation, robustness, leakage, and simulation-consistency checks.",
    ),
    (
        "simulation_check_gap.csv",
        "Simulation Check Gap",
        "Gap between simulator-executable candidates and full PE-Bench checks.",
    ),
    (
        "ablation_summary.csv",
        "Ablation Summary",
        "Strong-baseline component ablations.",
    ),
    (
        "backbone_robustness.csv",
        "Backbone Robustness",
        "Performance across backbone classes.",
    ),
    (
        "topology_slice_summary.csv",
        "Topology Slice Summary",
        "Per-topology and held-out slice performance.",
    ),
    (
        "heldout_summary.csv",
        "Held-Out Summary",
        "Public-development to held-out robustness comparison.",
    ),
    (
        "retry_budget_summary.csv",
        "Retry Budget Summary",
        "Pass-rate sensitivity to retry budget.",
    ),
    (
        "inverter_extension_summary.csv",
        "Inverter Extension Summary",
        "Three-phase inverter extension slice.",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reviewer-readable paper tables from frozen PE-Bench records.")
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE), help="Path to frozen evidence records.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Directory for generated JSON tables.")
    parser.add_argument("--check", action="store_true", help="Validate generated table artifacts.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence = Path(args.evidence)
    output_dir = Path(args.output_dir)
    paths = write_paper_tables(evidence=evidence, output_dir=output_dir)
    for name, path in sorted(paths.items()):
        print(f"{name}: {path}")
    if args.check:
        errors = validate_paper_tables(evidence=evidence, output_dir=output_dir)
        if errors:
            print("Paper-table artifact validation failed:")
            for error in errors:
                print(f"  - {error}")
            return 1
        print("Paper-table artifact validation passed.")
    return 0


def write_paper_tables(evidence: Path = DEFAULT_EVIDENCE, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Path]:
    source_manifest = _load_manifest(evidence)
    tables = _collect_tables(evidence)
    metadata = {
        "source_evidence_kind": source_manifest.get("evidence_kind"),
        "source_raw_logs_included": source_manifest.get("raw_logs_included"),
        "source_task_total": source_manifest.get("task_total"),
    }
    generated_manifest = {
        "created_for": "anonymous_review_artifact",
        "generated_at_utc": GENERATED_AT_UTC,
        "generated_from": _rel(evidence),
        **metadata,
        "output_files": ["tables.json"],
        "command": "python -m pebench tables",
        "notes": [
            "Tables preserve the rows and values in the frozen evidence CSV files.",
            "They do not call external APIs or reproduce model executions.",
            "The tables command also checks the exact paper-facing numeric values.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {"tables.json": output_dir / "tables.json", "manifest.json": output_dir / "manifest.json"}
    paths["tables.json"].write_text(
        json.dumps({**metadata, "tables": tables}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    paths["manifest.json"].write_text(json.dumps(generated_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return paths


def validate_paper_tables(evidence: Path = DEFAULT_EVIDENCE, output_dir: Path = DEFAULT_OUTPUT) -> list[str]:
    if not evidence.exists():
        return [f"Evidence directory is missing: {evidence}"]
    errors: list[str] = []
    for name in ["manifest.json", "tables.json"]:
        if not (output_dir / name).exists():
            errors.append(f"Missing reproduced table artifact: {output_dir / name}")
    for csv_name, _, _ in TABLE_SPECS:
        if not (evidence / csv_name).exists():
            errors.append(f"Missing source CSV: {evidence / csv_name}")
    if errors:
        return errors
    try:
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        payload = json.loads((output_dir / "tables.json").read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return [f"Cannot read reproduced table artifacts: {exc}"]
    for name, document in [("manifest", manifest), ("tables", payload)]:
        if not isinstance(document, dict):
            errors.append(f"reproduced_tables {name} must be a JSON object")
            continue
        if document.get("source_evidence_kind") != "frozen_manuscript_summary_records":
            errors.append(f"reproduced_tables {name} must point to frozen manuscript summary records")
        if document.get("source_task_total") != 78:
            errors.append(f"reproduced_tables {name} source_task_total must be 78")
        if document.get("source_raw_logs_included") is not False:
            errors.append(f"reproduced_tables {name} must identify the source as summary evidence")
    if isinstance(manifest, dict) and manifest.get("output_files") != ["tables.json"]:
        errors.append("reproduced_tables manifest must list tables.json")
    if isinstance(payload, dict) and payload.get("tables") != _collect_tables(evidence):
        errors.append("Generated JSON tables differ from the source CSV records")
    return errors


def _collect_tables(evidence: Path) -> dict[str, Any]:
    return {
        Path(csv_name).stem: {
            "title": title,
            "description": description,
            "source": _rel(evidence / csv_name),
            "rows": _read_csv(evidence / csv_name),
        }
        for csv_name, title, description in TABLE_SPECS
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_manifest(evidence: Path) -> dict[str, Any]:
    path = evidence / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing evidence manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
