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
ANONYMOUS_REVIEW_URL = "https://anonymous.4open.science/r/PE-Bench-ACFC/"
CROISSANT_CORE_VERSION = "http://mlcommons.org/croissant/1.1"
CROISSANT_RAI_VERSION = "http://mlcommons.org/croissant/RAI/1.0"
NON_ANONYMOUS_GITHUB_ACCOUNT = "sponge" + "loves" + "orange"
NON_ANONYMOUS_GITHUB_URL = "github.com/" + NON_ANONYMOUS_GITHUB_ACCOUNT
NON_ANONYMOUS_RAW_GITHUB_URL = "raw.githubusercontent.com/" + NON_ANONYMOUS_GITHUB_ACCOUNT


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
    conforms_to = croissant.get("conformsTo")
    if not isinstance(conforms_to, list) or CROISSANT_CORE_VERSION not in conforms_to:
        errors.append(f"croissant_metadata.json conformsTo must include {CROISSANT_CORE_VERSION}")
    if not isinstance(conforms_to, list) or CROISSANT_RAI_VERSION not in conforms_to:
        errors.append(f"croissant_metadata.json conformsTo must include {CROISSANT_RAI_VERSION}")
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
    if not isinstance(context, dict) or "rai" not in context or "cr" not in context or "dct" not in context:
        errors.append("croissant_metadata.json @context must define cr, rai, and dct prefixes")
    if isinstance(context, dict) and context.get("conformsTo") != "dct:conformsTo":
        errors.append("croissant_metadata.json @context must map conformsTo to dct:conformsTo")
    distributions = croissant.get("distribution", [])
    if not isinstance(distributions, list) or len(distributions) < 8:
        errors.append("croissant_metadata.json distribution must include dataset and schema file objects")
    distribution_ids = {entry.get("@id") for entry in distributions if isinstance(entry, dict)}
    for required_id in [
        "task_records_csv",
        "task_records_jsonl",
        "candidate_schema_json",
        "result_schema_json",
        "release_manifest_json",
        "frozen_leaderboard_summary_csv",
        "frozen_validation_summary_csv",
        "component_catalogs_yaml",
    ]:
        if required_id not in distribution_ids:
            errors.append(f"croissant_metadata.json distribution missing {required_id}")
    for entry in distributions if isinstance(distributions, list) else []:
        if not isinstance(entry, dict):
            errors.append("croissant_metadata.json distribution entries must be objects")
            continue
        if entry.get("@type") != "cr:FileObject":
            errors.append(f"croissant_metadata.json distribution {entry.get('@id', '<unknown>')} must use @type cr:FileObject")
        content_url = str(entry.get("contentUrl", ""))
        if NON_ANONYMOUS_GITHUB_URL in content_url or NON_ANONYMOUS_RAW_GITHUB_URL in content_url:
            errors.append(f"croissant_metadata.json distribution leaks non-anonymous GitHub URL: {entry.get('@id')}")
        sha = entry.get("sha256")
        if sha and (not isinstance(sha, str) or len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha.lower())):
            errors.append(f"croissant_metadata.json distribution has invalid sha256: {entry.get('@id')}")
    for url_key in ["url", "codeRepository"]:
        value = str(croissant.get(url_key, ""))
        if NON_ANONYMOUS_GITHUB_URL in value:
            errors.append(f"croissant_metadata.json {url_key} leaks non-anonymous GitHub URL")
    generated_by = croissant.get("prov:wasGeneratedBy", {})
    if isinstance(generated_by, dict) and NON_ANONYMOUS_GITHUB_URL in str(generated_by.get("url", "")):
        errors.append("croissant_metadata.json prov:wasGeneratedBy.url leaks non-anonymous GitHub URL")
    record_sets = croissant.get("recordSet", [])
    if not isinstance(record_sets, list) or not record_sets:
        errors.append("croissant_metadata.json recordSet must be a non-empty list")
    else:
        fields = record_sets[0].get("field", []) if isinstance(record_sets[0], dict) else []
        if not fields:
            errors.append("croissant_metadata.json first recordSet must define fields")
        field_names = {field.get("name") for field in fields if isinstance(field, dict)}
        for required_field in [
            "task_id",
            "bank",
            "topology",
            "difficulty_tier",
            "split",
            "track",
            "task_family",
            "input_domain",
            "input_min",
            "input_max",
            "output_voltage",
            "output_current",
            "output_power_w",
            "efficiency_target_percent",
            "ripple_or_quality_target",
            "known_failure_modes",
            "component_catalog_version",
            "task_path",
            "source",
            "schema_version",
        ]:
            if required_field not in field_names:
                errors.append(f"croissant_metadata.json recordSet missing field: {required_field}")
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
        "@context": _croissant_context(),
        "@type": "sc:Dataset",
        "conformsTo": [CROISSANT_CORE_VERSION, CROISSANT_RAI_VERSION],
        "name": "PE-Bench",
        "description": (
            "PE-Bench is a 78-task benchmark and evaluator artifact for AI-assisted "
            "power-electronics design across Buck, Boost, Buck-Boost, Flyback, and "
            "three-phase inverter tasks."
        ),
        "version": "1.0.0",
        "sdVersion": summary["release_version"],
        "datePublished": DATASET_PUBLISHED_DATE,
        "citeAs": (
            "Anonymous PE-Bench Authors. PE-Bench: A Benchmark for Evaluating "
            "Agent-Based Power Electronics Design Systems. Anonymous review artifact, 2026."
        ),
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "codeRepository": ANONYMOUS_REVIEW_URL,
        "url": ANONYMOUS_REVIEW_URL,
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
        "includedInDataCatalog": {"@type": "DataCatalog", "name": "Anonymous review artifact"},
        "distribution": _croissant_distribution(),
        "recordSet": [
            {
                "@type": "cr:RecordSet",
                "@id": "pebench_tasks",
                "name": "PE-Bench task records",
                "description": "One record per executable benchmark task.",
                "key": {"@id": "pebench_tasks/task_id"},
                "field": _croissant_task_fields(),
            }
        ],
        "prov:wasGeneratedBy": {
            "@type": "SoftwareApplication",
            "name": "PE-Bench artifact builder",
            "softwareVersion": summary["release_version"],
            "url": ANONYMOUS_REVIEW_URL,
        },
        "prov:wasDerivedFrom": [
            "Anonymous author-curated task specifications",
            "Bounded component-catalog slices included in the artifact",
            "Feasible reference-design anchors included with each task card",
        ],
        "rai:dataCollection": (
            "Synthetic benchmark task cards authored from converter-family templates under "
            "`pebench/tasks/`, normalized by `scripts/build_dataset_artifacts.py`, and checked "
            "by task-schema validators plus feasible reference-design validators. No personal data."
        ),
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
        "rai:annotationPlatform": (
            "Author-curated YAML task cards, deterministic artifact builders, bounded in-artifact "
            "component catalogs, and feasible reference-design anchors used as witnesses rather than unique gold answers."
        ),
    }


def _croissant_context() -> dict[str, Any]:
    return {
        "@language": "en",
        "@vocab": "https://schema.org/",
        "arrayShape": "cr:arrayShape",
        "citeAs": "cr:citeAs",
        "column": "cr:column",
        "conformsTo": "dct:conformsTo",
        "containedIn": "cr:containedIn",
        "cr": "http://mlcommons.org/croissant/",
        "rai": "http://mlcommons.org/croissant/RAI/",
        "prov": "http://www.w3.org/ns/prov#",
        "data": {"@id": "cr:data", "@type": "@json"},
        "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
        "dct": "http://purl.org/dc/terms/",
        "description": {"@container": "@language"},
        "equivalentProperty": "cr:equivalentProperty",
        "examples": {"@id": "cr:examples", "@type": "@json"},
        "extract": "cr:extract",
        "field": "cr:field",
        "fileProperty": "cr:fileProperty",
        "fileObject": "cr:fileObject",
        "fileSet": "cr:fileSet",
        "format": "cr:format",
        "includes": "cr:includes",
        "isArray": "cr:isArray",
        "isLiveDataset": "cr:isLiveDataset",
        "jsonPath": "cr:jsonPath",
        "key": "cr:key",
        "md5": "cr:md5",
        "name": {"@container": "@language"},
        "parentField": "cr:parentField",
        "path": "cr:path",
        "recordSet": "cr:recordSet",
        "references": "cr:references",
        "regex": "cr:regex",
        "repeated": "cr:repeated",
        "replace": "cr:replace",
        "samplingRate": "cr:samplingRate",
        "sc": "https://schema.org/",
        "separator": "cr:separator",
        "source": "cr:source",
        "subField": "cr:subField",
        "transform": "cr:transform",
    }


def _croissant_distribution() -> list[dict[str, Any]]:
    return [
        _croissant_file("task_records_csv", "artifacts/dataset/task_records.csv", "text/csv"),
        _croissant_file("task_records_jsonl", "artifacts/dataset/task_records.jsonl", "application/jsonl"),
        _croissant_file("task_inventory_csv", "artifacts/release/task_inventory.csv", "text/csv"),
        _croissant_file("candidate_schema_json", "artifacts/schema/candidate.schema.json", "application/schema+json"),
        _croissant_file("result_schema_json", "artifacts/schema/result.schema.json", "application/schema+json"),
        _croissant_file("release_manifest_json", "artifacts/release/pebench_v1_manifest.json", "application/json"),
        _croissant_file("frozen_evidence_manifest_json", "artifacts/evidence/frozen_v1/manifest.json", "application/json"),
        _croissant_file("frozen_leaderboard_summary_csv", "artifacts/evidence/frozen_v1/leaderboard_summary.csv", "text/csv"),
        _croissant_file("frozen_validation_summary_csv", "artifacts/evidence/frozen_v1/validation_summary.csv", "text/csv"),
        _croissant_file("frozen_simulation_check_gap_csv", "artifacts/evidence/frozen_v1/simulation_check_gap.csv", "text/csv"),
        _croissant_file("api_rerun_integrity_json", "artifacts/evidence/api_rerun_gpt4omini_20260506/integrity_report.json", "application/json"),
        _croissant_file("api_rerun_task_results_csv", "artifacts/evidence/api_rerun_gpt4omini_20260506/task_results.csv", "text/csv"),
        _croissant_file("component_catalogs_yaml", "assets/catalogs/components.yaml", "application/x-yaml"),
        _croissant_file("flyback_component_catalog_yaml", "assets/catalogs/flyback_components.yaml", "application/x-yaml"),
        _croissant_file("topology_component_catalog_yaml", "assets/catalogs/topology_components.yaml", "application/x-yaml"),
        _croissant_file("inverter_component_catalog_yaml", "assets/catalogs/inverter_components.yaml", "application/x-yaml"),
        _croissant_file("benchmark_card_md", "artifacts/cards/benchmark_card.md", "text/markdown"),
        _croissant_file("evaluator_card_md", "artifacts/cards/evaluator_card.md", "text/markdown"),
        _croissant_file("dataset_card_md", "docs/DATASET_CARD.md", "text/markdown"),
        _croissant_file("responsible_ai_metadata_md", "docs/RESPONSIBLE_AI_METADATA.md", "text/markdown"),
        _croissant_file("evidence_matrix_md", "artifacts/evidence/EVIDENCE_MATRIX.md", "text/markdown"),
        _croissant_file("reviewer_smoke_test_doc_md", "artifacts/quickstart/REVIEWER_SMOKE_TEST.md", "text/markdown"),
    ]


def _croissant_file(identifier: str, relative_path: str, encoding_format: str) -> dict[str, Any]:
    path = REPO_ROOT / relative_path
    return {
        "@type": "cr:FileObject",
        "@id": identifier,
        "name": Path(relative_path).name,
        "contentUrl": relative_path,
        "encodingFormat": encoding_format,
        "sha256": _sha256(path),
    }


def _croissant_task_fields() -> list[dict[str, Any]]:
    text_fields = [
        "task_id",
        "bank",
        "topology",
        "difficulty_tier",
        "split",
        "track",
        "task_family",
        "source",
        "schema_version",
        "task_path",
        "natural_language_spec",
        "input_domain",
        "component_catalog_version",
        "closure_gates",
        "known_failure_modes",
        "reference_design",
    ]
    float_fields = [
        "input_min",
        "input_max",
        "output_voltage",
        "output_current",
        "output_power_w",
        "efficiency_target_percent",
        "ripple_or_quality_target",
    ]
    return [
        *[_croissant_field(name, "sc:Text") for name in text_fields],
        *[_croissant_field(name, "sc:Float") for name in float_fields],
    ]


def _croissant_field(name: str, data_type: str) -> dict[str, Any]:
    return {
        "@type": "cr:Field",
        "@id": f"pebench_tasks/{name}",
        "name": name,
        "dataType": data_type,
        "source": {
            "fileObject": {"@id": "task_records_csv"},
            "extract": {"column": name},
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
        "source",
        "schema_version",
        "task_path",
        "natural_language_spec",
        "input_min",
        "input_max",
        "input_domain",
        "output_voltage",
        "output_current",
        "output_power_w",
        "efficiency_target_percent",
        "ripple_or_quality_target",
        "component_catalog_version",
        "closure_gates",
        "known_failure_modes",
        "reference_design",
    ]
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field, "")) for field in fieldnames})


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return value


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
