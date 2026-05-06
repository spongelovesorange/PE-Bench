from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from compare_api_evidence_to_paper import DEFAULT_PAPER, compare


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_EVIDENCE_ROOT = REPO_ROOT / "artifacts" / "evidence"
SUMMARY_FILES = [
    "suite_index.csv",
    "task_results.csv",
    "job_summary_78task.csv",
    "leaderboard_summary.csv",
    "ablation_summary.csv",
    "track_summary.csv",
    "integrity_report.json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote a completed API run into sanitized reviewer evidence.")
    parser.add_argument("--run-root", required=True, help="Run created by scripts/run_final78_experiments.py.")
    parser.add_argument("--output-dir", default=None, help="Default: artifacts/evidence/paper_main_raw_<run_name>.")
    parser.add_argument("--label", default="paper_main_raw_api_evidence")
    parser.add_argument("--used-for-main-paper-tables", action="store_true")
    parser.add_argument("--paper-leaderboard", default=str(DEFAULT_PAPER))
    parser.add_argument("--paper-tolerance", type=float, default=0.035)
    parser.add_argument("--skip-freeze", action="store_true", help="Do not regenerate <run-root>/frozen_actual_run first.")
    parser.add_argument("--include-raw-jsonl", action="store_true", default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_root = Path(args.run_root).resolve()
    if not run_root.exists():
        raise SystemExit(f"Missing run root: {run_root}")
    output_dir = Path(args.output_dir).resolve() if args.output_dir else _default_output_dir(run_root)
    frozen_dir = run_root / "frozen_actual_run"

    if not args.skip_freeze:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/freeze_api_run_records.py",
                "--run-root",
                str(run_root),
                "--output-dir",
                str(frozen_dir),
                "--label",
                args.label,
            ],
            cwd=REPO_ROOT,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode

    output_dir.mkdir(parents=True, exist_ok=True)
    for name in SUMMARY_FILES:
        source = frozen_dir / name
        if source.exists():
            shutil.copy2(source, output_dir / name)

    run_manifest = _load_json(run_root / "run_manifest.json") if (run_root / "run_manifest.json").exists() else {}
    status = _load_json(run_root / "status.json") if (run_root / "status.json").exists() else {}
    integrity = _load_json(output_dir / "integrity_report.json") if (output_dir / "integrity_report.json").exists() else {}
    files = [name for name in SUMMARY_FILES if (output_dir / name).exists()]

    if args.include_raw_jsonl:
        raw_files = write_raw_jsonl(run_root=run_root, output_dir=output_dir)
        files.extend(raw_files)

    promotion_decision = _paper_table_promotion_decision(args, output_dir)
    _write_json(output_dir / "promotion_decision.json", promotion_decision)
    files.append("promotion_decision.json")
    used_for_main_paper_tables = bool(promotion_decision["used_for_main_paper_tables"])

    manifest = {
        "api_key_recorded": False,
        "complete": bool(integrity.get("complete")),
        "evidence_kind": "paper_main_raw_api_evidence" if used_for_main_paper_tables else "independent_api_rerun_summary",
        "evidence_level": args.label if used_for_main_paper_tables else "independent_api_rerun_summary",
        "files": sorted(files + ["checksums.sha256", "manifest.json", "README.md"]),
        "interpretation": (
            "Raw task-level API evidence intended to support the manuscript main tables."
            if used_for_main_paper_tables
            else "Sanitized API rerun evidence included for pipeline audit; not used as the manuscript leaderboard source."
        ),
        "job_count": int(run_manifest.get("job_count") or integrity.get("expected_job_count") or 0),
        "main_table_promotion": promotion_decision,
        "model": run_manifest.get("model"),
        "profile": run_manifest.get("profile"),
        "raw_jsonl_included": bool(args.include_raw_jsonl),
        "raw_logs_included": False,
        "run_name": run_root.name,
        "runner": run_manifest.get("runner", "scripts/run_final78_experiments.py"),
        "seeds": run_manifest.get("seeds", []),
        "source_endpoint_class": "openai_compatible",
        "task_result_count": int(integrity.get("task_result_count") or 0),
        "task_total": int(run_manifest.get("task_total_per_main_job") or 78),
        "used_for_main_paper_tables": used_for_main_paper_tables,
        "status": _sanitize(status),
    }
    _write_json(output_dir / "manifest.json", manifest)
    (output_dir / "README.md").write_text(_readme(manifest), encoding="utf-8")
    _write_checksums(output_dir)

    errors = validate_promoted_evidence(output_dir)
    if errors:
        print("Promoted evidence validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"Promoted sanitized API evidence to {output_dir}")
    return 0


def _paper_table_promotion_decision(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    actual = output_dir / "leaderboard_summary.csv"
    paper = Path(args.paper_leaderboard).resolve()
    decision: dict[str, Any] = {
        "requested_for_main_paper_tables": bool(args.used_for_main_paper_tables),
        "used_for_main_paper_tables": False,
        "paper_leaderboard": _rel(paper),
        "actual_leaderboard": _rel(actual),
        "tolerance": float(args.paper_tolerance),
    }
    if not args.used_for_main_paper_tables:
        decision["reason"] = "main-paper-table promotion was not requested"
        return decision
    if not actual.exists():
        decision["reason"] = "leaderboard_summary.csv is missing from the promoted evidence"
        return decision
    if not paper.exists():
        decision["reason"] = "paper leaderboard evidence is missing"
        return decision
    report = compare(actual, paper, tolerance=float(args.paper_tolerance))
    decision.update(
        {
            "alignment_within_tolerance": bool(report["within_tolerance"]),
            "max_abs_delta": report["max_abs_delta"],
            "missing_code_ids": report["missing_code_ids"],
            "interpretation": report["interpretation"],
        }
    )
    if report["within_tolerance"]:
        decision["used_for_main_paper_tables"] = True
        decision["reason"] = "alignment gate passed"
    else:
        decision["reason"] = (
            "alignment gate failed; promoted as independent rerun evidence so stochastic/provider drift "
            "does not replace the frozen manuscript records"
        )
    return decision


def write_raw_jsonl(*, run_root: Path, output_dir: Path) -> list[str]:
    raw_root = run_root / "raw_records"
    task_records_path = output_dir / "raw_task_records.jsonl"
    suite_records_path = output_dir / "raw_suite_records.jsonl"
    task_count = 0
    suite_count = 0
    with task_records_path.open("w", encoding="utf-8") as task_handle, suite_records_path.open(
        "w", encoding="utf-8"
    ) as suite_handle:
        for suite_summary_path in sorted(raw_root.glob("**/suites/*/suite_summary.json")):
            suite_dir = suite_summary_path.parent
            suite_summary = _load_json(suite_summary_path)
            run_config = _load_json(suite_dir / "run_config.json") if (suite_dir / "run_config.json").exists() else {}
            suite_payload = {
                "suite_summary": _sanitize(suite_summary),
                "run_config": _sanitize(run_config),
                "suite_relative_path": str(suite_dir.relative_to(run_root)),
            }
            suite_handle.write(json.dumps(suite_payload, sort_keys=True) + "\n")
            suite_count += 1
            for result_path in sorted((suite_dir / "task_results").glob("*.json")):
                task_id = result_path.stem
                candidate_path = suite_dir / "candidates" / f"{task_id}.json"
                payload = {
                    "suite_id": suite_summary.get("suite_id"),
                    "baseline_name": suite_summary.get("baseline_name"),
                    "model_name": suite_summary.get("model_name"),
                    "seed": suite_summary.get("seed"),
                    "track": suite_summary.get("track"),
                    "topology": suite_summary.get("topology"),
                    "task_id": task_id,
                    "candidate": _sanitize(_load_json(candidate_path)) if candidate_path.exists() else {},
                    "result": _sanitize(_load_json(result_path)),
                }
                task_handle.write(json.dumps(payload, sort_keys=True) + "\n")
                task_count += 1
    _write_json(
        output_dir / "raw_record_summary.json",
        {
            "raw_suite_records": suite_count,
            "raw_task_records": task_count,
            "raw_logs_included": False,
            "api_key_recorded": False,
        },
    )
    return ["raw_task_records.jsonl", "raw_suite_records.jsonl", "raw_record_summary.json"]


def validate_promoted_evidence(output_dir: Path) -> list[str]:
    errors: list[str] = []
    required = ["manifest.json", "integrity_report.json", "leaderboard_summary.csv", "task_results.csv", "checksums.sha256"]
    for name in required:
        if not (output_dir / name).exists():
            errors.append(f"Missing promoted evidence file: {name}")
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl", ".csv", ".md", ".sha256"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"sk-[A-Za-z0-9]{20,}", text):
            errors.append(f"API key-like token found in {path.name}")
        if ("/" + "Users" + "/") in text:
            errors.append(f"Local absolute path found in {path.name}")
    errors.extend(_validate_checksums(output_dir / "checksums.sha256"))
    return errors


def _default_output_dir(run_root: Path) -> Path:
    return DEFAULT_ARTIFACT_EVIDENCE_ROOT / f"paper_main_raw_{run_root.name}"


def _rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items() if str(key).lower() not in {"api_key"}}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        text = re.sub(r"sk-[A-Za-z0-9]{20,}", "<redacted_api_key>", value)
        text = text.replace(str(REPO_ROOT), "<repo_root>")
        text = re.sub(r"/" + r"Users/[^\\s\"']+", "<local_path>", text)
        return text
    return value


def _readme(manifest: dict[str, Any]) -> str:
    promotion = manifest.get("main_table_promotion", {})
    if manifest["used_for_main_paper_tables"]:
        table_status = "This run passed the paper-table alignment gate and is marked as main-table raw evidence."
    elif promotion.get("requested_for_main_paper_tables"):
        table_status = (
            "Main-table promotion was requested, but the alignment gate withheld it. "
            "This run is therefore retained as independent rerun evidence, not as the manuscript leaderboard source."
        )
    else:
        table_status = "This run is retained as independent rerun evidence, not as the manuscript leaderboard source."
    return f"""# Promoted API Evidence

Run: `{manifest['run_name']}`

Model: `{manifest.get('model')}`

Evidence kind: `{manifest['evidence_kind']}`

Complete: `{manifest['complete']}`

This directory contains sanitized task-level API evidence. It includes full candidate/result JSONL records and summary CSV/JSON files, but not raw provider logs or API credentials.

{table_status}
"""


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_checksums(output_dir: Path) -> None:
    lines = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "checksums.sha256":
            lines.append(f"{_sha256(path)}  {path.relative_to(output_dir)}")
    (output_dir / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _validate_checksums(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"Missing checksum file: {path}"]
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        target = path.parent / relative
        if not target.exists():
            errors.append(f"Checksum target missing: {relative}")
        elif _sha256(target) != expected:
            errors.append(f"Checksum mismatch: {relative}")
    return errors


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
