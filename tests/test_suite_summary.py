from __future__ import annotations

from pathlib import Path

from pebench.adapters.registry import get_baseline
from pebench.analysis.reporting import write_suite_summary
from pebench.evaluator.core import evaluate_candidate
from pebench.tasks.schema import iter_task_files, load_task
from pebench.utils.io import dump_json
from pebench.utils.paths import DEFAULT_TASK_DIR


def test_suite_summary_contains_required_aggregates(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suite"
    (suite_dir / "task_results").mkdir(parents=True)

    baseline = get_baseline("single_agent_same_tools")
    for task_file in iter_task_files(DEFAULT_TASK_DIR)[:2]:
        task = load_task(task_file)
        candidate = baseline.generate(task=task, model_name="heuristic-v0", seed=3, simulator_mode="stub")
        result = evaluate_candidate(task=task, candidate=candidate, simulator_mode="stub")
        dump_json(result, suite_dir / "task_results" / f"{task['task_id']}.json")

    summary = write_suite_summary(suite_dir)
    assert "success_rate" in summary
    assert "mean_score" in summary
    assert "failure_tag_counts" in summary
    assert "backend_counts" in summary
    assert "fallback_rate" in summary
    assert summary["num_tasks"] == 2
