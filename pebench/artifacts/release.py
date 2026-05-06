from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from pebench.adapters.candidate import (
    REQUIRED_CANDIDATE_FIELDS as FLYBACK_CANDIDATE_FIELDS,
    REQUIRED_CLAIMED_METRIC_FIELDS as FLYBACK_CLAIM_FIELDS,
    REQUIRED_THEORY_FIELDS as FLYBACK_THEORY_FIELDS,
)
from pebench.evaluator.result_schema import REQUIRED_RESULT_FIELDS
from pebench.evaluator.inverter import (
    REQUIRED_CANDIDATE_FIELDS as INVERTER_CANDIDATE_FIELDS,
    REQUIRED_CLAIM_FIELDS as INVERTER_CLAIM_FIELDS,
    REQUIRED_THEORY_FIELDS as INVERTER_THEORY_FIELDS,
)
from pebench.evaluator.topology_scout import (
    REQUIRED_CANDIDATE_FIELDS as TOPOLOGY_CANDIDATE_FIELDS,
    REQUIRED_CLAIM_FIELDS as TOPOLOGY_CLAIM_FIELDS,
    REQUIRED_THEORY_FIELDS as TOPOLOGY_THEORY_FIELDS,
)
from pebench.tasks.inverter_schema import iter_inverter_task_files, load_inverter_task
from pebench.tasks.schema import iter_task_files, load_task
from pebench.tasks.topology_full import iter_scout_task_files, load_scout_task
from pebench.utils.io import dump_json
from pebench.utils.paths import (
    DEFAULT_FLYBACK_TASK_DIR,
    DEFAULT_INVERTER_TASK_DIR,
    DEFAULT_TOPOLOGY_FULL_TASK_DIR,
    REPO_ROOT,
)


EXPECTED_TOPOLOGY_COUNTS = {
    "buck": 12,
    "boost": 12,
    "buck_boost": 12,
    "flyback": 30,
    "three_phase_inverter": 12,
}
EXPECTED_TOTAL_TASKS = sum(EXPECTED_TOPOLOGY_COUNTS.values())
RELEASE_VERSION = "pebench-v1.0-78task"
RELEASE_GENERATED_AT_UTC = "2026-05-06T00:00:00+00:00"


def collect_task_inventory() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in iter_task_files(DEFAULT_FLYBACK_TASK_DIR):
        task = load_task(path)
        records.append(_task_record(path, task, bank="flyback", topology="flyback"))
    for path in iter_scout_task_files(DEFAULT_TOPOLOGY_FULL_TASK_DIR):
        task = load_scout_task(path)
        records.append(_task_record(path, task, bank="topology_full", topology=str(task["topology"])))
    for path in iter_inverter_task_files(DEFAULT_INVERTER_TASK_DIR):
        task = load_inverter_task(path)
        records.append(_task_record(path, task, bank="three_phase_inverter", topology="three_phase_inverter"))
    return sorted(records, key=lambda row: (row["bank"], row["topology"], row["difficulty_tier"], row["task_id"]))


def build_release_manifest() -> dict[str, Any]:
    inventory = collect_task_inventory()
    topology_counts = dict(sorted(Counter(row["topology"] for row in inventory).items()))
    difficulty_counts = dict(sorted(Counter(row["difficulty_tier"] for row in inventory).items()))
    split_counts = dict(sorted(Counter(row["split"] for row in inventory).items()))
    bank_counts = dict(sorted(Counter(row["bank"] for row in inventory).items()))

    return {
        "release_version": RELEASE_VERSION,
        "generated_at_utc": RELEASE_GENERATED_AT_UTC,
        "project": {
            "name": "PE-Bench",
            "python_package": "pebench",
            "legacy_package_shim": "flybackbench",
            "role": "benchmark and evaluator artifact for AI-assisted power-electronics design",
        },
        "paper_alignment": {
            "task_total": len(inventory),
            "expected_task_total": EXPECTED_TOTAL_TASKS,
            "families": ["Buck", "Boost", "Buck-Boost", "Flyback", "Three-phase inverter"],
            "primary_metric": "verifiable task success rate (VTSR)",
            "experiments_included": True,
            "evidence_level": "frozen manuscript summary records",
            "note": "This manifest covers the reviewer-facing code, task artifact, and summary-level frozen manuscript records. Full raw API reruns can replace the evidence bundle without changing the task contract.",
        },
        "task_counts": {
            "by_topology": topology_counts,
            "expected_by_topology": EXPECTED_TOPOLOGY_COUNTS,
            "by_difficulty": difficulty_counts,
            "by_split": split_counts,
            "by_bank": bank_counts,
        },
        "source_layout": {
            "tasks": {
                "flyback": _rel(DEFAULT_FLYBACK_TASK_DIR),
                "topology_full": _rel(DEFAULT_TOPOLOGY_FULL_TASK_DIR),
                "three_phase_inverter": _rel(DEFAULT_INVERTER_TASK_DIR),
            },
            "evaluator": "pebench/evaluator/",
            "baseline_adapters": "pebench/baselines/",
            "catalogs": "assets/catalogs/",
            "scripts": "scripts/",
            "docs": "docs/",
            "artifact_output": "artifacts/",
        },
        "reviewer_commands": [
            "python scripts/reviewer_smoke_test.py",
            "python scripts/build_release_artifacts.py --check",
            "python scripts/build_dataset_artifacts.py --check",
            "python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check",
            "python scripts/validate_public_artifact.py",
            "python scripts/validate_tasks.py",
            "python scripts/validate_topology_full_tasks.py",
            "python scripts/validate_inverter_tasks.py",
            "python scripts/validate_reference_designs.py",
            "python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1",
        ],
        "release_files": {
            "manifest": "artifacts/release/pebench_v1_manifest.json",
            "task_inventory_csv": "artifacts/release/task_inventory.csv",
            "task_inventory_markdown": "artifacts/release/task_inventory.md",
            "checksums": "artifacts/release/checksums.sha256",
            "candidate_schema": "artifacts/schema/candidate.schema.json",
            "result_schema": "artifacts/schema/result.schema.json",
            "reviewer_smoke_test": "artifacts/quickstart/REVIEWER_SMOKE_TEST.md",
            "paper_alignment": "artifacts/release/paper_alignment.md",
            "frozen_evidence_manifest": "artifacts/evidence/frozen_v1/manifest.json",
            "dataset_summary": "artifacts/dataset/dataset_summary.json",
            "croissant_metadata": "croissant_metadata.json",
            "reproduced_tables_manifest": "artifacts/reproduced_tables/manifest.json",
            "evidence_matrix": "artifacts/evidence/EVIDENCE_MATRIX.md",
        },
        "non_use": {
            "hardware_certification": False,
            "production_signoff": False,
            "automated_procurement": False,
            "requires_qualified_engineer_review_for_real_hardware": True,
        },
        "license": {
            "software": "MIT",
            "tasks_docs_and_generated_artifacts": "CC BY 4.0",
            "third_party_resources": "governed by their own terms",
        },
    }


def write_release_artifacts(output_root: str | Path | None = None) -> dict[str, Path]:
    root = Path(output_root) if output_root is not None else REPO_ROOT / "artifacts"
    inventory = collect_task_inventory()
    manifest = build_release_manifest()
    paths = {
        "manifest": root / "release" / "pebench_v1_manifest.json",
        "inventory_csv": root / "release" / "task_inventory.csv",
        "inventory_md": root / "release" / "task_inventory.md",
        "checksums": root / "release" / "checksums.sha256",
        "candidate_schema": root / "schema" / "candidate.schema.json",
        "result_schema": root / "schema" / "result.schema.json",
        "smoke_test_doc": root / "quickstart" / "REVIEWER_SMOKE_TEST.md",
        "benchmark_card": root / "cards" / "benchmark_card.md",
        "evaluator_card": root / "cards" / "evaluator_card.md",
        "paper_alignment": root / "release" / "paper_alignment.md",
    }

    dump_json(manifest, paths["manifest"])
    dump_json(candidate_schema(), paths["candidate_schema"])
    dump_json(result_schema(), paths["result_schema"])
    _write_inventory_csv(paths["inventory_csv"], inventory)
    _write_inventory_markdown(paths["inventory_md"], inventory, manifest)
    _write_checksums(paths["checksums"], [Path(row["path"]) for row in inventory])
    _write_text(paths["smoke_test_doc"], _smoke_test_markdown())
    _write_text(paths["benchmark_card"], _benchmark_card_markdown(manifest))
    _write_text(paths["evaluator_card"], _evaluator_card_markdown())
    _write_text(paths["paper_alignment"], _paper_alignment_markdown(manifest))
    return paths


def validate_release_artifacts(output_root: str | Path | None = None) -> list[str]:
    root = Path(output_root) if output_root is not None else REPO_ROOT / "artifacts"
    errors: list[str] = []
    inventory = collect_task_inventory()
    topology_counts = Counter(row["topology"] for row in inventory)
    if len(inventory) != EXPECTED_TOTAL_TASKS:
        errors.append(f"Expected {EXPECTED_TOTAL_TASKS} tasks, found {len(inventory)}.")
    for topology, expected in EXPECTED_TOPOLOGY_COUNTS.items():
        observed = topology_counts.get(topology, 0)
        if observed != expected:
            errors.append(f"Expected {expected} {topology} tasks, found {observed}.")

    required_files = [
        root / "release" / "pebench_v1_manifest.json",
        root / "release" / "task_inventory.csv",
        root / "release" / "task_inventory.md",
        root / "release" / "checksums.sha256",
        root / "schema" / "candidate.schema.json",
        root / "schema" / "result.schema.json",
        root / "quickstart" / "REVIEWER_SMOKE_TEST.md",
        root / "cards" / "benchmark_card.md",
        root / "cards" / "evaluator_card.md",
        root / "release" / "paper_alignment.md",
        root / "evidence" / "frozen_v1" / "manifest.json",
        root / "evidence" / "frozen_v1" / "checksums.sha256",
    ]
    for path in required_files:
        if not path.exists():
            errors.append(f"Missing release artifact: {_rel(path)}")

    if (REPO_ROOT / "paper").exists():
        errors.append("In-repository paper directory still exists; paper is maintained externally.")
    for banned in [".env"]:
        if (REPO_ROOT / banned).exists():
            errors.append(f"Local-only path should not be present in the release root: {banned}")

    checksum_path = root / "release" / "checksums.sha256"
    if checksum_path.exists():
        errors.extend(_validate_checksums(checksum_path))
    return errors


def candidate_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pebench.local/schema/candidate.schema.json",
        "title": "PE-Bench candidate output",
        "type": "object",
        "description": "Family-aware structured output consumed by PE-Bench evaluators.",
        "oneOf": [
            _candidate_family_schema("flyback", FLYBACK_CANDIDATE_FIELDS, FLYBACK_THEORY_FIELDS, FLYBACK_CLAIM_FIELDS),
            _candidate_family_schema("topology_full", TOPOLOGY_CANDIDATE_FIELDS, TOPOLOGY_THEORY_FIELDS, TOPOLOGY_CLAIM_FIELDS),
            _candidate_family_schema(
                "three_phase_inverter",
                INVERTER_CANDIDATE_FIELDS,
                INVERTER_THEORY_FIELDS,
                INVERTER_CLAIM_FIELDS,
            ),
        ],
    }


def result_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pebench.local/schema/result.schema.json",
        "title": "PE-Bench evaluator result",
        "type": "object",
        "required": sorted(REQUIRED_RESULT_FIELDS),
        "properties": {
            "task_id": {"type": "string"},
            "difficulty_tier": {"type": "string", "enum": ["easy", "medium", "hard", "boundary", "stress"]},
            "baseline_name": {"type": "string"},
            "model_name": {"type": "string"},
            "seed": {"type": "integer"},
            "pass_fail": {"type": "boolean"},
            "score_total": {"type": "number", "minimum": 0, "maximum": 100},
            "sub_scores": {"type": "object"},
            "constraint_violations": {"type": "array", "items": {"type": "object"}},
            "simulation_metrics": {"type": "object"},
            "failure_tags": {"type": "array", "items": {"type": "string"}},
            "failure_groups": {"type": "array", "items": {"type": "string"}},
            "aggregate_scores": {"type": "object"},
            "execution_log": {"type": "array", "items": {"type": "object"}},
            "runtime_stats": {"type": "object"},
        },
    }


def _task_record(path: Path, task: dict[str, Any], *, bank: str, topology: str) -> dict[str, Any]:
    spec = task.get("structured_spec", {})
    output = spec.get("output", {})
    input_range = spec.get("input_range_volts", {})
    output_voltage = output.get("voltage_v", output.get("line_line_rms_v"))
    ripple_target = spec.get("targets", {}).get("ripple_mv", spec.get("targets", {}).get("thd_percent"))
    input_range = input_range or spec.get("dc_link_voltage_v", {})
    benchmark_meta = task.get("benchmark_meta", {})
    raw_split = benchmark_meta.get("split", task.get("split", ""))
    return {
        "task_id": task["task_id"],
        "bank": bank,
        "topology": topology,
        "difficulty_tier": task["difficulty_tier"],
        "split": _paper_split(raw_split),
        "track": benchmark_meta.get("track", ""),
        "task_family": benchmark_meta.get("task_family", ""),
        "source": benchmark_meta.get("source", ""),
        "input_min": input_range.get("min"),
        "input_max": input_range.get("max"),
        "input_domain": input_range.get("domain", ""),
        "output_voltage": output_voltage,
        "output_power": output.get("power_w"),
        "efficiency_target": spec.get("targets", {}).get("efficiency_percent"),
        "ripple_or_quality_target": ripple_target,
        "component_catalog_version": spec.get("component_catalog_version", ""),
        "schema_version": task.get("schema_version", "flyback-v1"),
        "path": _rel(path),
    }


def _paper_split(raw_split: str) -> str:
    if raw_split == "public_dev":
        return "public_dev"
    return raw_split


def _candidate_family_schema(
    family: str,
    required_fields: set[str],
    theory_fields: set[str],
    claim_fields: set[str],
) -> dict[str, Any]:
    return {
        "title": f"{family} candidate",
        "type": "object",
        "required": sorted(required_fields),
        "properties": {
            "task_id": {"type": "string"},
            "baseline_name": {"type": "string"},
            "model_name": {"type": "string"},
            "seed": {"type": "integer"},
            "parsed_spec": {"type": "object"},
            "topology_decision": {"type": "object"},
            "design_rationale": {"type": "string"},
            "theoretical_design": {
                "type": "object",
                "required": sorted(theory_fields),
            },
            "bom": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["category", "part_id"],
                    "properties": {
                        "category": {"type": "string"},
                        "part_id": {"type": "string"},
                        "source": {"type": "string"},
                    },
                },
            },
            "simulation_config": {"type": "object"},
            "final_claimed_metrics": {
                "type": "object",
                "required": sorted(claim_fields),
            },
            "uncertainty_or_escalation_flag": {"type": "object"},
            "metadata": {"type": "object"},
        },
    }


def _write_inventory_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_inventory_markdown(path: Path, rows: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    counts = manifest["task_counts"]
    lines = [
        "# PE-Bench v1 Task Inventory",
        "",
        f"Release: `{manifest['release_version']}`",
        "",
        f"Total tasks: **{len(rows)}**",
        "",
        "## Topology Counts",
        "",
        "| Topology | Count |",
        "| --- | ---: |",
    ]
    for topology, count in counts["by_topology"].items():
        lines.append(f"| {topology} | {count} |")
    lines.extend(
        [
            "",
            "## Difficulty Counts",
            "",
            "| Difficulty | Count |",
            "| --- | ---: |",
        ]
    )
    for difficulty, count in counts["by_difficulty"].items():
        lines.append(f"| {difficulty} | {count} |")
    lines.extend(
        [
            "",
            "## Task Rows",
            "",
            "| Task ID | Bank | Topology | Difficulty | Split | Path |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| `{row['task_id']}` | {row['bank']} | {row['topology']} | "
            f"{row['difficulty_tier']} | {row['split']} | `{row['path']}` |"
        )
    _write_text(path, "\n".join(lines) + "\n")


def _write_checksums(path: Path, relative_paths: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for relative_path in sorted(relative_paths):
        absolute = REPO_ROOT / relative_path
        lines.append(f"{_sha256(absolute)}  {relative_path}")
    _write_text(path, "\n".join(lines) + "\n")


def _validate_checksums(path: Path) -> list[str]:
    errors: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        actual_path = REPO_ROOT / relative
        if not actual_path.exists():
            errors.append(f"Checksum target is missing: {relative}")
            continue
        actual = _sha256(actual_path)
        if actual != expected:
            errors.append(f"Checksum mismatch for {relative}")
    return errors


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _benchmark_card_markdown(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Benchmark Card: PE-Bench v1",
            "",
            "PE-Bench evaluates whether AI-assisted power-electronics design outputs are internally consistent across requirements, converter topology, equations, components, safety margins, simulation or formula-backed metrics, reported claims, and human-review decisions.",
            "",
            f"Task count: {manifest['paper_alignment']['task_total']} across Buck, Boost, Buck-Boost, Flyback, and Three-phase inverter families.",
            "",
            "Primary metric: VTSR, a conservative binary pass requiring all required checks to pass.",
            "",
            "Non-use: PE-Bench is not hardware certification, regulatory approval, production sign-off, or a replacement for qualified engineering review.",
            "",
        ]
    )


def _evaluator_card_markdown() -> str:
    return "\n".join(
        [
            "# Evaluator Card: PE-Bench v1",
            "",
            "Inputs: task YAML, candidate JSON, bounded component catalog slice, simulator configuration, and run metadata.",
            "",
            "Checks: schema closure, requirement grounding, topology equations, component grounding, derating margins, reported-value consistency, simulator/formula metrics, protection behavior where applicable, and human-review or escalation behavior.",
            "",
            "Outputs: pass/fail, score_total, sub_scores, constraint_violations, simulation_metrics, failure_tags, failure_groups, aggregate_scores, execution_log, and runtime_stats.",
            "",
            "Known abstractions: formula stubs are CI-safe approximations; full live simulation requires a local circuit-simulation backend.",
            "",
        ]
    )


def _smoke_test_markdown() -> str:
    return "\n".join(
        [
            "# Reviewer Smoke Test",
            "",
            "This smoke test validates the task bank, evaluator contracts, package imports, and release manifest without running expensive LLM or live simulator experiments.",
            "",
            "```bash",
            "python scripts/reviewer_smoke_test.py",
            "```",
            "",
            "Expected checks:",
            "",
            "- 30 Flyback tasks parse.",
            "- 36 Buck/Boost/Buck-Boost Topology Full tasks parse.",
            "- 12 Three-phase inverter tasks parse.",
            "- Release artifacts build and validate.",
            "- Dataset exports and Croissant metadata build and validate.",
            "- Reproduced Markdown paper tables build and validate.",
            "- Public artifact anonymization and secret-leak checks pass.",
            "- Reference feasibility candidates evaluate on every released task.",
            "- Frozen manuscript summary records reproduce the paper-facing tables without API access.",
            "",
        ]
    )


def _paper_alignment_markdown(manifest: dict[str, Any]) -> str:
    counts = manifest["task_counts"]
    lines = [
        "# Paper Alignment Checklist",
        "",
        "This file maps the main paper-facing artifact claims to concrete files and commands.",
        "",
        "| Paper-facing claim | Artifact support | Status |",
        "| --- | --- | --- |",
        f"| 78 executable tasks | `artifacts/release/task_inventory.csv`; topology counts `{counts['by_topology']}` | Supported |",
        "| 12 Buck, 12 Boost, 12 Buck-Boost, 30 Flyback, 12 Three-phase inverter | `artifacts/release/pebench_v1_manifest.json` | Supported |",
        "| Required-field checks 78/78 | `python scripts/reviewer_smoke_test.py`; `python scripts/validate_tasks.py`; `python scripts/validate_topology_full_tasks.py`; `python scripts/validate_inverter_tasks.py` | Supported |",
        "| Feasible-reference checks 78/78 | `python scripts/validate_reference_designs.py` | Supported |",
        "| Candidate/result schema is machine-readable | `artifacts/schema/candidate.schema.json`; `artifacts/schema/result.schema.json` | Supported |",
        "| Dataset metadata is indexable | `croissant_metadata.json`; `docs/DATASET_CARD.md`; `artifacts/dataset/task_records.jsonl` | Supported |",
        "| Anonymous release | `python scripts/export_anonymous_artifact.py --check` | Supported |",
        "| Frozen final leaderboard and figure reproduction | `python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1`; `python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check` | Summary records included |",
        "| Faulty-design, independent-valid-design, leakage, and held-out validation logs | `artifacts/evidence/frozen_v1/validation_summary.csv` | Summary records included; raw trace export should replace before camera-ready if available |",
        "| Completed API rerun pipeline evidence | `artifacts/evidence/api_rerun_gpt4omini_20260506/integrity_report.json` | Secondary evidence included; not used for manuscript leaderboard |",
        "",
        "The code artifact is sufficient for task/evaluator/release-contract inspection. The frozen evidence bundle is summary-level and intentionally anonymous; replace it with raw sanitized run records after a full rerun when time permits.",
        "",
    ]
    return "\n".join(lines)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _rel(path: str | Path) -> str:
    return str(Path(path).resolve().relative_to(REPO_ROOT))
