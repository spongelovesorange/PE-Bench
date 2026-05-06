from __future__ import annotations

from pathlib import Path

from pebench.utils.io import dump_json, load_json


def test_dump_json_serializes_paths(tmp_path: Path) -> None:
    target = tmp_path / "example.json"
    dump_json({"artifact_path": tmp_path / "artifact.txt"}, target)
    loaded = load_json(target)
    assert loaded["artifact_path"] == str(tmp_path / "artifact.txt")
