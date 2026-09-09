from __future__ import annotations

import json
import zipfile
from argparse import Namespace
from collections import Counter

from pebench._commands import export_anonymous_artifact
from pebench._commands import validate_public_artifact as public_artifact_validator
from pebench._commands.build_dataset_artifacts import collect_dataset_records
from pebench._commands.build_paper_tables import DEFAULT_EVIDENCE, DEFAULT_OUTPUT, validate_paper_tables, write_paper_tables
from pebench._commands.promote_api_run_evidence import _sanitize
from pebench._commands.validate_croissant_metadata import main as validate_croissant_metadata_main
from pebench._commands.validate_public_artifact import validate_public_artifact


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


def test_json_table_export_preserves_source_values_and_detects_changes(tmp_path) -> None:
    paths = write_paper_tables(DEFAULT_EVIDENCE, tmp_path)
    assert set(path.name for path in tmp_path.iterdir()) == {"tables.json", "manifest.json"}
    assert validate_paper_tables(DEFAULT_EVIDENCE, tmp_path) == []
    payload = json.loads(paths["tables.json"].read_text(encoding="utf-8"))
    assert len(payload["tables"]) == 10
    leaderboard = payload["tables"]["leaderboard_summary"]["rows"]
    reference = next(row for row in leaderboard if row["code_id"] == "reference_agent")
    assert reference["vtsr_mean"] == "0.684"
    reference["vtsr_mean"] = "1.0"
    paths["tables.json"].write_text(json.dumps(payload), encoding="utf-8")
    assert "Generated JSON tables differ from the source CSV records" in validate_paper_tables(DEFAULT_EVIDENCE, tmp_path)


def test_public_artifact_scan_is_clean() -> None:
    assert validate_public_artifact() == []


def test_git_history_accepts_anonymous_roles_but_flags_personal_names(tmp_path, monkeypatch) -> None:
    maintainer = "PE-Bench Artifact Maintainer"
    anonymous = "Anonymous PE-Bench Authors"
    personal = "Alex Morgan"
    identities = [(maintainer, maintainer), (anonymous, anonymous), (personal, maintainer), (anonymous, personal)]
    history = "\n".join(
        f"commit{index}\t{author}\treview@example.invalid\t{committer}\treview@example.invalid"
        for index, (author, committer) in enumerate(identities)
    )
    monkeypatch.setattr(
        public_artifact_validator.subprocess,
        "run",
        lambda *args, **kwargs: Namespace(returncode=0, stdout=history),
    )
    assert public_artifact_validator._scan_git_history(tmp_path, []) == [
        "non-anonymous author or committer: git commit metadata commit2",
        "non-anonymous author or committer: git commit metadata commit3",
    ]


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


def test_anonymous_zip_includes_only_named_readme_figures(tmp_path, monkeypatch) -> None:
    root = tmp_path / "repo"
    included = {
        "assets/figures/overview.png",
        "assets/figures/verification-gap.png",
    }
    excluded = {
        "assets/figures/other.png",
        "assets/figures/overview.jpg",
        "assets/other/overview.png",
        "results/assets/figures/overview.png",
    }
    for relative in included | excluded:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
    output = tmp_path / "anonymous.zip"
    monkeypatch.setattr(export_anonymous_artifact, "REPO_ROOT", root)
    monkeypatch.setattr(export_anonymous_artifact, "write_release_artifacts", lambda: None)
    monkeypatch.setattr(export_anonymous_artifact, "validate_release_artifacts", lambda: [])
    monkeypatch.setattr(
        export_anonymous_artifact,
        "parse_args",
        lambda: Namespace(output=str(output), check=False, skip_smoke=True),
    )

    assert export_anonymous_artifact.main() == 0
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {
            f"pebench_anonymous_artifact/{relative}" for relative in included
        }


def test_promoted_records_redact_endpoints_and_preserve_results() -> None:
    endpoint = "https://gateway.test/v1"
    record = {
        "task_id": "task-1",
        "model_name": "model-1",
        "seed": 3,
        "metrics": {"vtsr_mean": 0.684},
        "metadata": {"base_url": endpoint, "api_key": "private-test-value"},
        "run_config": {"api_base": endpoint},
    }
    assert _sanitize(record) == {
        **record,
        "metadata": {"base_url": "<redacted_endpoint>"},
        "run_config": {"api_base": "<redacted_endpoint>"},
    }


def test_generic_privacy_checks_scan_jsonl_and_allow_public_links(tmp_path, monkeypatch) -> None:
    (tmp_path / "README.md").write_text("https://github.com/python/cpython\nhttps://neurips.cc\n", encoding="utf-8")
    assert validate_public_artifact(tmp_path) == []
    endpoint = "https://gateway.test/v1"
    path = tmp_path / "records.jsonl"
    path.write_text(json.dumps({"api_base": endpoint}) + "\n", encoding="utf-8")
    assert validate_public_artifact(tmp_path) == ["private provider endpoint: records.jsonl"]
    monkeypatch.setattr(export_anonymous_artifact, "REPO_ROOT", tmp_path)
    assert export_anonymous_artifact._anonymity_errors([path.relative_to(tmp_path)]) == [
        "private provider endpoint: records.jsonl"
    ]
