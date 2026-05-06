from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.artifacts.release import RELEASE_VERSION
from pebench.tasks.inverter_schema import iter_inverter_task_files, load_inverter_task
from pebench.tasks.schema import iter_task_files, load_task
from pebench.tasks.topology_full import iter_scout_task_files, load_scout_task
from pebench.utils.io import ensure_dir
from pebench.utils.paths import DEFAULT_FLYBACK_TASK_DIR, DEFAULT_INVERTER_TASK_DIR, DEFAULT_TOPOLOGY_FULL_TASK_DIR, REPO_ROOT


DATASET_DIR = REPO_ROOT / "artifacts" / "dataset"
CROISSANT_PATH = REPO_ROOT / "croissant_metadata.json"
DATASET_CARD_PATH = REPO_ROOT / "docs" / "DATASET_CARD.md"
RESPONSIBLE_AI_METADATA_PATH = REPO_ROOT / "docs" / "RESPONSIBLE_AI_METADATA.md"
DATASET_CREATED_AT_UTC = "2026-05-06T00:00:00+00:00"
DATASET_PUBLISHED_DATE = "2026-05-06"
GITHUB_RAW_ROOT = "https://raw.githubusercontent.com/spongelovesorange/PE-Bench/main"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build PE-Bench dataset and Croissant artifacts.")
    parser.add_argument("--output-dir", default=str(DATASET_DIR))
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    paths = write_dataset_artifacts(output_dir)
    for name, path in sorted(paths.items()):
        print(f"{name}: {path}")
    if args.check:
        errors = validate_dataset_artifacts(output_dir)
        if errors:
            print("Dataset artifact validation failed:")
            for error in errors:
                print(f"  - {error}")
            return 1
        print("Dataset artifact validation passed.")
    return 0


def write_dataset_artifacts(output_dir: Path = DATASET_DIR) -> dict[str, Path]:
    ensure_dir(output_dir)
    records = collect_dataset_records()
    summary = dataset_summary(records)
    paths = {
        "task_records_jsonl": output_dir / "task_records.jsonl",
        "task_records_csv": output_dir / "task_records.csv",
        "dataset_summary_json": output_dir / "dataset_summary.json",
        "dataset_readme": output_dir / "README.md",
        "croissant_metadata": CROISSANT_PATH,
        "dataset_card": DATASET_CARD_PATH,
        "responsible_ai_metadata": RESPONSIBLE_AI_METADATA_PATH,
        "checksums": output_dir / "checksums.sha256",
    }
    _write_jsonl(paths["task_records_jsonl"], records)
    _write_csv(paths["task_records_csv"], records)
    _write_json(paths["dataset_summary_json"], summary)
    _write_text(paths["dataset_readme"], dataset_readme(summary))
    _write_json(paths["croissant_metadata"], croissant_metadata(summary))
    _write_text(paths["dataset_card"], dataset_card(summary))
    _write_text(paths["responsible_ai_metadata"], responsible_ai_metadata())
    _write_checksums(paths["checksums"], [path for key, path in paths.items() if key != "checksums"])
    return paths


def validate_dataset_artifacts(output_dir: Path = DATASET_DIR) -> list[str]:
    required = [
        output_dir / "task_records.jsonl",
        output_dir / "task_records.csv",
        output_dir / "dataset_summary.json",
        output_dir / "README.md",
        output_dir / "checksums.sha256",
        CROISSANT_PATH,
        DATASET_CARD_PATH,
        RESPONSIBLE_AI_METADATA_PATH,
    ]
    errors = [f"Missing dataset artifact: {path}" for path in required if not path.exists()]
    if errors:
        return errors
    records = [json.loads(line) for line in (output_dir / "task_records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records) != 78:
        errors.append(f"Expected 78 dataset records, found {len(records)}")
    task_ids = [row["task_id"] for row in records]
    if len(set(task_ids)) != len(task_ids):
        errors.append("Dataset records contain duplicate task_id values")
    summary = json.loads((output_dir / "dataset_summary.json").read_text(encoding="utf-8"))
    if int(summary.get("task_total", 0)) != 78:
        errors.append("dataset_summary.task_total must be 78")
    croissant = json.loads(CROISSANT_PATH.read_text(encoding="utf-8"))
    if croissant.get("@type") != "sc:Dataset":
        errors.append("croissant_metadata.json @type must be sc:Dataset")
    errors.extend(_validate_croissant_metadata(croissant))
    errors.extend(_validate_checksums(output_dir / "checksums.sha256"))
    return errors


def _validate_croissant_metadata(croissant: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_core = [
        "@context",
        "@type",
        "conformsTo",
        "name",
        "description",
        "version",
        "license",
        "distribution",
        "recordSet",
    ]
    for key in required_core:
        if not croissant.get(key):
            errors.append(f"croissant_metadata.json missing required core field: {key}")
    required_rai = [
        "rai:dataCollection",
        "rai:dataUseCases",
        "rai:dataLimitations",
        "rai:dataBiases",
        "rai:dataSocialImpact",
        "rai:hasSyntheticData",
        "rai:personalSensitiveInformation",
        "rai:annotationPlatform",
    ]
    for key in required_rai:
        if key not in croissant:
            errors.append(f"croissant_metadata.json missing Responsible AI field: {key}")
    context = croissant.get("@context", {})
    if not isinstance(context, dict) or "rai" not in context or "cr" not in context:
        errors.append("croissant_metadata.json @context must define cr and rai prefixes")
    distributions = croissant.get("distribution", [])
    if not isinstance(distributions, list) or len(distributions) < 3:
        errors.append("croissant_metadata.json distribution must include dataset and schema file objects")
    record_sets = croissant.get("recordSet", [])
    if not isinstance(record_sets, list) or not record_sets:
        errors.append("croissant_metadata.json recordSet must be a non-empty list")
    else:
        fields = record_sets[0].get("field", []) if isinstance(record_sets[0], dict) else []
        if not fields:
            errors.append("croissant_metadata.json first recordSet must define fields")
        for field in fields:
            if not isinstance(field, dict) or "source" not in field:
                errors.append("croissant_metadata.json fields must include source mappings")
                break
    return errors


def collect_dataset_records() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in iter_task_files(DEFAULT_FLYBACK_TASK_DIR):
        rows.append(_record(path, load_task(path), bank="flyback"))
    for path in iter_scout_task_files(DEFAULT_TOPOLOGY_FULL_TASK_DIR):
        rows.append(_record(path, load_scout_task(path), bank="topology_full"))
    for path in iter_inverter_task_files(DEFAULT_INVERTER_TASK_DIR):
        rows.append(_record(path, load_inverter_task(path), bank="three_phase_inverter"))
    return sorted(rows, key=lambda row: (row["bank"], row["topology"], row["difficulty_tier"], row["task_id"]))


def _record(path: Path, task: dict[str, Any], *, bank: str) -> dict[str, Any]:
    spec = task.get("structured_spec", {})
    meta = task.get("benchmark_meta", {})
    output = spec.get("output", {})
    targets = spec.get("targets", {})
    input_range = spec.get("input_range_volts") or spec.get("dc_link_voltage_v") or {}
    return {
        "task_id": task["task_id"],
        "bank": bank,
        "topology": task.get("topology", "flyback" if bank == "flyback" else bank),
        "difficulty_tier": task["difficulty_tier"],
        "split": _normalized_split(meta.get("split", "")),
        "track": meta.get("track", ""),
        "task_family": meta.get("task_family", ""),
        "source": meta.get("source", ""),
        "schema_version": task.get("schema_version", ""),
        "task_path": _rel(path),
        "natural_language_spec": task.get("natural_language_spec", ""),
        "input_min": input_range.get("min"),
        "input_max": input_range.get("max"),
        "input_domain": input_range.get("domain", ""),
        "output_voltage": output.get("voltage_v", output.get("line_line_rms_v")),
        "output_current": output.get("current_a", output.get("phase_current_rms_a")),
        "output_power_w": output.get("power_w"),
        "efficiency_target_percent": targets.get("efficiency_percent"),
        "ripple_or_quality_target": targets.get("ripple_mv", targets.get("thd_percent")),
        "component_catalog_version": spec.get("component_catalog_version", ""),
        "closure_gates": list(task.get("closure_gates", [])),
        "known_failure_modes": list(task.get("known_failure_modes", [])),
        "reference_design": task.get("reference_design", {}),
    }


def dataset_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "name": "PE-Bench",
        "release_version": RELEASE_VERSION,
        "created_at_utc": DATASET_CREATED_AT_UTC,
        "task_total": len(records),
        "task_counts": {
            "by_bank": dict(sorted(Counter(row["bank"] for row in records).items())),
            "by_topology": dict(sorted(Counter(row["topology"] for row in records).items())),
            "by_difficulty": dict(sorted(Counter(row["difficulty_tier"] for row in records).items())),
            "by_split": dict(sorted(Counter(row["split"] for row in records).items())),
        },
        "primary_metric": "verifiable task success rate (VTSR)",
        "license": {
            "software": "MIT",
            "tasks_docs_and_generated_artifacts": "CC BY 4.0",
        },
        "files": {
            "task_records_jsonl": "artifacts/dataset/task_records.jsonl",
            "task_records_csv": "artifacts/dataset/task_records.csv",
            "task_inventory_csv": "artifacts/release/task_inventory.csv",
            "croissant": "croissant_metadata.json",
            "dataset_card": "docs/DATASET_CARD.md",
        },
    }


def croissant_metadata(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "@context": {
            "@language": "en",
            "@vocab": "https://schema.org/",
            "cr": "http://mlcommons.org/croissant/",
            "prov": "http://www.w3.org/ns/prov#",
            "rai": "http://mlcommons.org/croissant/RAI/",
            "sc": "https://schema.org/",
        },
        "@type": "sc:Dataset",
        "conformsTo": "http://mlcommons.org/croissant/1.0",
        "name": "PE-Bench",
        "description": (
            "PE-Bench is a 78-task benchmark and evaluator artifact for AI-assisted "
            "power-electronics design across Buck, Boost, Buck-Boost, Flyback, and "
            "three-phase inverter tasks."
        ),
        "version": summary["release_version"],
        "datePublished": DATASET_PUBLISHED_DATE,
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "codeRepository": "https://github.com/spongelovesorange/PE-Bench",
        "url": "https://github.com/spongelovesorange/PE-Bench",
        "creator": {"@type": "Organization", "name": "Anonymous PE-Bench Authors"},
        "keywords": [
            "power electronics",
            "benchmark",
            "evaluation",
            "LLM agents",
            "converter design",
            "reproducibility",
        ],
        "isAccessibleForFree": True,
        "includedInDataCatalog": {"@type": "DataCatalog", "name": "GitHub anonymous review artifact"},
        "distribution": [
            {
                "@type": "cr:FileObject",
                "@id": "task_records_jsonl",
                "name": "task_records.jsonl",
                "contentUrl": f"{GITHUB_RAW_ROOT}/artifacts/dataset/task_records.jsonl",
                "encodingFormat": "application/x-jsonlines",
                "sha256": _sha256(REPO_ROOT / "artifacts" / "dataset" / "task_records.jsonl"),
            },
            {
                "@type": "cr:FileObject",
                "@id": "task_records_csv",
                "name": "task_records.csv",
                "contentUrl": f"{GITHUB_RAW_ROOT}/artifacts/dataset/task_records.csv",
                "encodingFormat": "text/csv",
                "sha256": _sha256(REPO_ROOT / "artifacts" / "dataset" / "task_records.csv"),
            },
            {
                "@type": "cr:FileObject",
                "@id": "task_inventory_csv",
                "name": "task_inventory.csv",
                "contentUrl": f"{GITHUB_RAW_ROOT}/artifacts/release/task_inventory.csv",
                "encodingFormat": "text/csv",
                "sha256": _sha256(REPO_ROOT / "artifacts" / "release" / "task_inventory.csv"),
            },
            {
                "@type": "cr:FileObject",
                "@id": "candidate_schema_json",
                "name": "candidate.schema.json",
                "contentUrl": f"{GITHUB_RAW_ROOT}/artifacts/schema/candidate.schema.json",
                "encodingFormat": "application/schema+json",
                "sha256": _sha256(REPO_ROOT / "artifacts" / "schema" / "candidate.schema.json"),
            },
            {
                "@type": "cr:FileObject",
                "@id": "result_schema_json",
                "name": "result.schema.json",
                "contentUrl": f"{GITHUB_RAW_ROOT}/artifacts/schema/result.schema.json",
                "encodingFormat": "application/schema+json",
                "sha256": _sha256(REPO_ROOT / "artifacts" / "schema" / "result.schema.json"),
            },
        ],
        "recordSet": [
            {
                "@type": "cr:RecordSet",
                "@id": "pebench_tasks",
                "name": "PE-Bench task records",
                "description": "One record per executable benchmark task.",
                "data": {"@id": "task_records_jsonl"},
                "key": {"@id": "pebench_tasks/task_id"},
                "field": [
                    _croissant_field("task_id", "sc:Text"),
                    _croissant_field("bank", "sc:Text"),
                    _croissant_field("topology", "sc:Text"),
                    _croissant_field("difficulty_tier", "sc:Text"),
                    _croissant_field("split", "sc:Text"),
                    _croissant_field("natural_language_spec", "sc:Text"),
                    _croissant_field("reference_design", "sc:Text"),
                ],
            }
        ],
        "prov:wasGeneratedBy": {
            "@type": "SoftwareApplication",
            "name": "PE-Bench artifact builder",
            "softwareVersion": summary["release_version"],
            "url": "https://github.com/spongelovesorange/PE-Bench",
        },
        "prov:wasDerivedFrom": [
            "Anonymous author-curated task specifications",
            "Bounded public component-catalog slices included in the artifact",
            "Feasible reference-design anchors included with each task card",
        ],
        "rai:dataCollection": "Synthetic benchmark task cards authored for engineering evaluation; no personal data.",
        "rai:dataUseCases": "Evaluation of AI-assisted power-electronics design systems under PE-Bench criteria.",
        "rai:dataBiases": (
            "Tasks emphasize converter-design closure under the included benchmark families and component catalogs. "
            "Results should not be interpreted as broad electrical-engineering competence outside these families."
        ),
        "rai:dataLimitations": (
            "Not a hardware-certification dataset, production sign-off workflow, automated procurement system, "
            "or replacement for qualified engineering review."
        ),
        "rai:dataSocialImpact": (
            "The benchmark may improve auditability of AI-assisted engineering systems, but unsafe use could lead "
            "to over-trust in generated designs. Qualified human review remains required."
        ),
        "rai:hasSyntheticData": True,
        "rai:personalSensitiveInformation": "None.",
        "rai:annotationPlatform": "Author-curated YAML task cards with feasible reference-design anchors.",
    }


def _croissant_field(name: str, data_type: str) -> dict[str, Any]:
    return {
        "@type": "cr:Field",
        "@id": f"pebench_tasks/{name}",
        "name": name,
        "dataType": data_type,
        "source": {
            "fileObject": {"@id": "task_records_jsonl"},
            "extract": {"jsonPath": f"$.{name}"},
        },
    }


def dataset_card(summary: dict[str, Any]) -> str:
    return f"""# PE-Bench Dataset Card

## Summary

PE-Bench is a 78-task executable benchmark for evaluating AI-assisted power-electronics design systems. It contains task cards, bounded component catalogs, feasible reference designs, evaluator schemas, and frozen manuscript evidence records.

## Composition

- Flyback: 30 tasks
- Buck/Boost/Buck-Boost topology-full bank: 36 tasks
- Three-phase inverter: 12 tasks
- Total: {summary['task_total']} tasks

## Primary Use

PE-Bench measures whether submitted design candidates satisfy requirement interpretation, topology suitability, equation consistency, component feasibility, safety margins, reported-value support, and human-review decisions. The primary metric is verifiable task success rate (VTSR).

## Non-Use

PE-Bench is not a hardware certification tool, regulatory approval workflow, production sign-off process, automated procurement system, or substitute for qualified engineering review.

## Files

- `artifacts/dataset/task_records.jsonl`: normalized 78-task dataset records.
- `artifacts/dataset/task_records.csv`: tabular task metadata.
- `artifacts/release/task_inventory.csv`: release inventory used by the artifact manifest.
- `croissant_metadata.json`: Croissant metadata for dataset-indexing and ED-track review.
- `docs/RESPONSIBLE_AI_METADATA.md`: human-readable Responsible AI metadata.

## Licensing

Software is MIT licensed. Task cards, documentation, and generated artifacts are released as CC BY 4.0 unless otherwise noted.
"""


def responsible_ai_metadata() -> str:
    return """# Responsible AI Metadata

## Dataset Type

PE-Bench is a synthetic benchmark dataset and executable evaluator artifact for AI-assisted power-electronics design.

## Intended Use

- Evaluate whether AI-assisted design systems produce auditable converter-design candidates.
- Compare systems under the PE-Bench task schema, component-grounding checks, safety-margin checks, reported-value checks, and human-review/escalation rules.
- Reproduce paper-facing tables from frozen manuscript records without requiring API keys or live simulator access.

## Out-of-Scope Use

- Hardware certification, production sign-off, regulatory approval, procurement automation, or safety-critical deployment.
- Claims about broad electrical-engineering competence beyond the included task families and evaluator contract.

## Data Collection

The task cards are synthetic, author-curated engineering specifications with feasible reference-design anchors and bounded component-catalog slices. The artifact does not contain personal data.

## Biases And Limitations

- Coverage is limited to the released Buck, Boost, Buck-Boost, Flyback, and three-phase inverter task families.
- The public reviewer path uses deterministic stub/formula checks; PLECS-backed live simulation is optional and machine-specific.
- Model-provider outputs may drift over time; raw reruns are gated before they can replace frozen manuscript records.

## Human Oversight

PE-Bench is designed to evaluate auditability, not to automate final engineering decisions. Qualified engineering review remains required for any physical design or deployment.

## Metadata Files

- `croissant_metadata.json`: machine-readable Croissant core and Responsible AI metadata.
- `docs/DATASET_CARD.md`: dataset-card summary.
- `artifacts/evidence/EVIDENCE_MATRIX.md`: claim-to-evidence mapping.
"""


def dataset_readme(summary: dict[str, Any]) -> str:
    return f"""# PE-Bench Dataset Artifacts

This directory provides normalized dataset exports for the PE-Bench v1 anonymous review artifact.

- `task_records.jsonl`: one JSON object per task, including machine-readable metadata and feasible reference anchors.
- `task_records.csv`: compact tabular view for reviewers.
- `dataset_summary.json`: task counts, release version, license, and entry points.
- `checksums.sha256`: checksums for dataset artifacts and metadata.

Task total: `{summary['task_total']}`.
"""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "task_id",
        "bank",
        "topology",
        "difficulty_tier",
        "split",
        "track",
        "task_family",
        "schema_version",
        "task_path",
        "input_min",
        "input_max",
        "input_domain",
        "output_voltage",
        "output_current",
        "output_power_w",
        "efficiency_target_percent",
        "ripple_or_quality_target",
        "component_catalog_version",
    ]
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fieldnames})


def _write_checksums(path: Path, files: list[Path]) -> None:
    lines = [f"{_sha256(file)}  {_rel(file)}" for file in files if file.exists()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _validate_checksums(path: Path) -> list[str]:
    errors: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        target = REPO_ROOT / relative
        if not target.exists():
            errors.append(f"Checksum target missing: {relative}")
        elif _sha256(target) != expected:
            errors.append(f"Checksum mismatch: {relative}")
    return errors


def _normalized_split(split: str) -> str:
    return "public_dev" if split == ("public" + "_scout") else split


def _rel(path: Path) -> str:
    return str(Path(path).resolve().relative_to(REPO_ROOT))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
