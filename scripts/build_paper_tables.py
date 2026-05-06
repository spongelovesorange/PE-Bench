from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = REPO_ROOT / "artifacts" / "evidence" / "frozen_v1"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "reproduced_tables"
GENERATED_AT_UTC = "2026-05-06T00:00:00+00:00"

TABLE_SPECS = [
    (
        "task_accounting.csv",
        "task_accounting.md",
        "Task Accounting",
        "Released task counts by topology, difficulty, and split.",
    ),
    (
        "leaderboard_summary.csv",
        "leaderboard_summary.md",
        "Main Leaderboard",
        "Paper-facing 78-task VTSR leaderboard summary.",
    ),
    (
        "validation_summary.csv",
        "validation_summary.md",
        "Validation Summary",
        "Evaluator validation, robustness, leakage, and simulation-consistency checks.",
    ),
    (
        "simulation_check_gap.csv",
        "simulation_check_gap.md",
        "Simulation Check Gap",
        "Gap between simulator-executable candidates and full PE-Bench checks.",
    ),
    (
        "ablation_summary.csv",
        "ablation_summary.md",
        "Ablation Summary",
        "Strong-baseline component ablations.",
    ),
    (
        "backbone_robustness.csv",
        "backbone_robustness.md",
        "Backbone Robustness",
        "Performance across backbone classes.",
    ),
    (
        "topology_slice_summary.csv",
        "topology_slice_summary.md",
        "Topology Slice Summary",
        "Per-topology and held-out slice performance.",
    ),
    (
        "heldout_summary.csv",
        "heldout_summary.md",
        "Held-Out Summary",
        "Public-development to held-out robustness comparison.",
    ),
    (
        "retry_budget_summary.csv",
        "retry_budget_summary.md",
        "Retry Budget Summary",
        "Pass-rate sensitivity to retry budget.",
    ),
    (
        "inverter_extension_summary.csv",
        "inverter_extension_summary.md",
        "Inverter Extension Summary",
        "Three-phase inverter extension slice.",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build reviewer-readable paper tables from frozen PE-Bench records.")
    parser.add_argument("--evidence", default=str(DEFAULT_EVIDENCE), help="Path to frozen evidence records.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Directory for generated Markdown tables.")
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
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(evidence)
    paths: dict[str, Path] = {}

    for csv_name, md_name, title, description in TABLE_SPECS:
        source = evidence / csv_name
        target = output_dir / md_name
        rows = _read_csv(source)
        target.write_text(_table_doc(title, description, source, rows), encoding="utf-8")
        paths[md_name] = target

    generated_manifest = {
        "created_for": "anonymous_review_artifact",
        "generated_at_utc": GENERATED_AT_UTC,
        "generated_from": _rel(evidence),
        "source_evidence_kind": manifest.get("evidence_kind"),
        "source_raw_logs_included": manifest.get("raw_logs_included"),
        "source_task_total": manifest.get("task_total"),
        "output_files": sorted(paths),
        "script": "scripts/build_paper_tables.py",
        "notes": [
            "These Markdown tables are generated from frozen evidence CSV files.",
            "They do not call external APIs.",
            "Use scripts/reproduce_paper_tables.py to assert exact paper-facing numeric values.",
        ],
    }
    manifest_path = output_dir / "manifest.json"
    readme_path = output_dir / "README.md"
    manifest_path.write_text(json.dumps(generated_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    readme_path.write_text(_readme(generated_manifest), encoding="utf-8")
    paths["manifest.json"] = manifest_path
    paths["README.md"] = readme_path
    return paths


def validate_paper_tables(evidence: Path = DEFAULT_EVIDENCE, output_dir: Path = DEFAULT_OUTPUT) -> list[str]:
    errors: list[str] = []
    if not evidence.exists():
        return [f"Evidence directory is missing: {evidence}"]
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.exists():
        errors.append(f"Missing reproduced table manifest: {manifest_path}")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source_evidence_kind") != "frozen_manuscript_summary_records":
            errors.append("reproduced_tables manifest must point to frozen manuscript summary records")
        if int(manifest.get("source_task_total", 0)) != 78:
            errors.append("reproduced_tables manifest source_task_total must be 78")
    for csv_name, md_name, _, _ in TABLE_SPECS:
        source = evidence / csv_name
        target = output_dir / md_name
        if not source.exists():
            errors.append(f"Missing source CSV: {source}")
            continue
        if not target.exists():
            errors.append(f"Missing generated Markdown table: {target}")
            continue
        text = target.read_text(encoding="utf-8")
        if f"Source: `{_rel(source)}`" not in text:
            errors.append(f"Generated table does not cite source CSV: {md_name}")
        if "| " not in text:
            errors.append(f"Generated table is not a Markdown table: {md_name}")
    if not (output_dir / "README.md").exists():
        errors.append(f"Missing reproduced tables README: {output_dir / 'README.md'}")
    return errors


def _table_doc(title: str, description: str, source: Path, rows: list[dict[str, str]]) -> str:
    return (
        f"# {title}\n\n"
        f"{description}\n\n"
        f"Source: `{_rel(source)}`\n\n"
        f"{_markdown_table(rows)}\n"
    )


def _markdown_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "_No rows._\n"
    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_cell(row.get(header, "")) for header in headers) + " |")
    return "\n".join(lines) + "\n"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_manifest(evidence: Path) -> dict[str, Any]:
    path = evidence / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing evidence manifest: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _readme(manifest: dict[str, Any]) -> str:
    files = "\n".join(f"- `{name}`" for name in manifest["output_files"])
    return f"""# Reproduced Paper Tables

This directory contains reviewer-readable Markdown tables generated from `artifacts/evidence/frozen_v1`.

Generation command:

```bash
python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check
```

The source evidence kind is `{manifest['source_evidence_kind']}` and the source task total is `{manifest['source_task_total']}`.

Generated tables:

{files}

For exact numeric assertions, run:

```bash
python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1
```
"""


def _cell(value: object) -> str:
    text = str(value).replace("\n", "<br>")
    return text.replace("|", "\\|")


def _rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
