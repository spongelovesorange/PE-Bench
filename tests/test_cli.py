from __future__ import annotations

import json

import pytest

from pebench.__main__ import main
from pebench.utils.paths import REPO_ROOT


@pytest.mark.parametrize("task_path", [
    "flyback/easy_acdc_5v1a.yaml",
    "topology_full/topology_buck_easy_5v3a.yaml",
    "inverter/inverter_3ph_easy_grid_400v_20kw.yaml",
])
@pytest.mark.parametrize("baseline", ["reference_design", "direct_prompting"])
def test_single_task_cli_generates_and_evaluates_each_track(task_path, baseline, tmp_path):
    task = REPO_ROOT / "pebench" / "tasks" / task_path
    candidate = tmp_path / "candidate.json"
    evaluation = tmp_path / "evaluation.json"
    assert main([
        "run", "--task", str(task), "--baseline", baseline, "--output", str(candidate),
    ]) == 0
    assert main([
        "evaluate", "--task", str(task), "--candidate", str(candidate), "--output", str(evaluation),
    ]) == 0
    result = json.loads(evaluation.read_text())
    assert result["task_id"] == json.loads(candidate.read_text())["task_id"]
    if baseline == "reference_design":
        assert result["pass_fail"] is True


def test_default_cli_suite_evaluates_all_78_reference_designs(tmp_path):
    assert main(["run", "--output-root", str(tmp_path)]) == 0
    summaries = [json.loads(path.read_text()) for path in tmp_path.rglob("suite_summary.json")]
    assert len(summaries) == 3
    assert sum(summary["num_tasks"] for summary in summaries) == 78
    assert sum(summary["successes"] for summary in summaries) == 78
