from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAPER = REPO_ROOT / "artifacts" / "evidence" / "frozen_v1" / "leaderboard_summary.csv"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "evidence" / "paper_main_alignment_report.json"

BASELINE_ALIASES = {
    "direct_prompting": "direct_prompting",
    "structured_output_only": "structured_output_only",
    "text_only_self_refine": "text_only_self_refine",
    "single_agent_same_tools": "llm_tools",
    "single_agent_retry": "single_agent_retry",
    "generic_two_role_mas": "generic_two_role_mas",
    "pe_gpt_style": "pe_gpt_style",
    "reference_agent": "reference_agent",
}

METRICS = [
    "vtsr_mean",
    "vtsr_std",
    "partial",
    "pass_at_3",
    "unsupported_values_percent",
    "invalid_bom_percent",
    "sim_calls",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare raw API evidence summaries with frozen manuscript records.")
    parser.add_argument("--actual", required=True, help="Path to promoted/frozen leaderboard_summary.csv.")
    parser.add_argument("--paper", default=str(DEFAULT_PAPER))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--tolerance", type=float, default=0.035)
    parser.add_argument("--fail-on-mismatch", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = compare(Path(args.actual), Path(args.paper), tolerance=args.tolerance)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _refresh_evidence_manifest_and_checksums(output.parent)
    print(f"Wrote {output}")
    if args.fail_on_mismatch and not report["within_tolerance"]:
        return 1
    return 0


def compare(actual_path: Path, paper_path: Path, *, tolerance: float) -> dict[str, Any]:
    actual_rows = _read_csv(actual_path)
    paper_rows = _read_csv(paper_path)
    actual_by_code = {
        BASELINE_ALIASES.get(row["baseline_name"], row["baseline_name"]): row
        for row in actual_rows
        if row.get("variant", "full") == "full"
    }
    paper_by_code = {row["code_id"]: row for row in paper_rows}
    rows: list[dict[str, Any]] = []
    max_abs_delta = 0.0
    missing: list[str] = []
    for code_id, paper in sorted(paper_by_code.items()):
        actual = actual_by_code.get(code_id)
        if actual is None:
            missing.append(code_id)
            continue
        row: dict[str, Any] = {
            "code_id": code_id,
            "paper_method": paper.get("method"),
            "actual_baseline_name": actual.get("baseline_name"),
            "actual_model_name": actual.get("model_name"),
        }
        for metric in METRICS:
            if metric not in actual or metric not in paper:
                continue
            paper_value = _float(paper.get(metric))
            actual_value = _float(actual.get(metric))
            delta = round(actual_value - paper_value, 6)
            max_abs_delta = max(max_abs_delta, abs(delta))
            row[f"paper_{metric}"] = paper_value
            row[f"actual_{metric}"] = actual_value
            row[f"delta_{metric}"] = delta
        rows.append(row)
    return {
        "actual": _rel(actual_path),
        "paper": _rel(paper_path),
        "tolerance": tolerance,
        "within_tolerance": not missing and max_abs_delta <= tolerance,
        "max_abs_delta": round(max_abs_delta, 6),
        "missing_code_ids": missing,
        "rows": rows,
        "interpretation": (
            "Actual raw evidence is close enough to act as manuscript-supporting evidence."
            if not missing and max_abs_delta <= tolerance
            else "Actual raw evidence should be treated as a rerun/secondary audit unless the manuscript numbers are updated."
        ),
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _rel(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def _refresh_evidence_manifest_and_checksums(evidence_dir: Path) -> None:
    manifest_path = evidence_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = set(str(item) for item in manifest.get("files", []))
        files.add("paper_alignment_report.json")
        files.add("checksums.sha256")
        manifest["files"] = sorted(files)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = []
    for path in sorted(evidence_dir.rglob("*")):
        if path.is_file() and path.name != "checksums.sha256":
            lines.append(f"{_sha256(path)}  {path.relative_to(evidence_dir)}")
    if lines:
        (evidence_dir / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
