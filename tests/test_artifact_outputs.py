from __future__ import annotations

import json
from collections import Counter

from scripts.build_dataset_artifacts import collect_dataset_records
from scripts.build_paper_tables import DEFAULT_EVIDENCE, DEFAULT_OUTPUT, validate_paper_tables
from scripts.validate_croissant_metadata import main as validate_croissant_metadata_main
from scripts.validate_public_artifact import validate_public_artifact


def test_dataset_records_cover_final_78_task_release() -> None:
    records = collect_dataset_records()
    assert len(records) == 78
    assert len({record["task_id"] for record in records}) == 78
    assert Counter(record["topology"] for record in records) == {
        "buck": 12,
        "boost": 12,
        "buck_boost": 12,
        "flyback": 30,
        "three_phase_inverter": 12,
    }


def test_reproduced_table_artifacts_are_valid() -> None:
    assert validate_paper_tables(DEFAULT_EVIDENCE, DEFAULT_OUTPUT) == []


def test_public_artifact_scan_is_clean() -> None:
    assert validate_public_artifact() == []


def test_croissant_and_responsible_ai_metadata_are_valid() -> None:
    assert validate_croissant_metadata_main() == 0


def test_sanitized_api_rerun_manifest_is_secondary_evidence() -> None:
    manifest = json.loads(
        (DEFAULT_EVIDENCE.parent / "api_rerun_gpt4omini_20260506" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["task_total"] == 78
    assert manifest["complete"] is True
    assert manifest["api_key_recorded"] is False
    assert manifest["raw_logs_included"] is False
    assert manifest["used_for_main_paper_tables"] is False
