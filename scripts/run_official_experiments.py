from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.adapters.registry import get_baseline
from pebench.analysis.reporting import find_suite_dirs, write_analysis_outputs
from pebench.tasks.schema import filter_tasks, iter_task_files, load_task
from pebench.utils.io import load_json
from pebench.utils.paths import (
    DEFAULT_ABLATIONS_RESULTS_ROOT,
    DEFAULT_CANONICAL_RESULTS_ROOT,
    DEFAULT_FLYBACK_TASK_DIR,
    DEFAULT_RESULTS_ROOT,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_CONTROL_ROOT = DEFAULT_RESULTS_ROOT / "orchestration"
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_SEEDS = (1, 2, 3)
CANONICAL_BASELINES = (
    "direct_prompting",
    "text_only_self_refine",
    "single_agent_same_tools",
    "single_agent_retry",
    "generic_two_role_mas",
    "pe_gpt_style",
    "reference_agent",
)
ABLATION_VARIANTS = (
    ("reference_agent", {}),
    ("reference_agent", {"disable_formula_guardrails": True}),
    ("reference_agent", {"disable_component_grounding": True}),
    ("reference_agent", {"disable_correction_memory": True}),
)


@dataclass(frozen=True)
class SuitePlan:
    bucket: str
    baseline: str
    model: str
    seed: int
    task_split: str
    task_count: int
    results_root: str
    analysis_dir: str
    disable_formula_guardrails: bool = False
    disable_component_grounding: bool = False
    disable_correction_memory: bool = False

    @property
    def run_name(self) -> str:
        baseline = get_baseline(
            self.baseline,
            disable_formula_guardrails=self.disable_formula_guardrails,
            disable_component_grounding=self.disable_component_grounding,
            disable_correction_memory=self.disable_correction_memory,
        )
        return baseline.run_name

    @property
    def suite_id(self) -> str:
        from scripts.run_suite import _sanitize_token

        return f"{self.run_name}__{_sanitize_token(self.model)}__seed{self.seed}__{self.task_count}tasks"

    @property
    def suite_dir(self) -> Path:
        return Path(self.results_root) / self.suite_id

    @property
    def summary_path(self) -> Path:
        return self.suite_dir / "summary.json"

    @property
    def task_results_dir(self) -> Path:
        return self.suite_dir / "task_results"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_task_count(split: str) -> int:
    tasks = [load_task(path) for path in iter_task_files(DEFAULT_FLYBACK_TASK_DIR)]
    return len(filter_tasks(tasks, split=split, track="autonomous_flyback_design"))


def _expected_task_snapshot(split: str) -> dict[str, dict[str, Any]]:
    tasks = []
    for path in iter_task_files(DEFAULT_FLYBACK_TASK_DIR):
        task = load_task(path)
        tasks.append((Path(path), task))
    filtered = filter_tasks([task for _, task in tasks], split=split, track="autonomous_flyback_design")
    filtered_ids = {str(task["task_id"]) for task in filtered}
    snapshot: dict[str, dict[str, Any]] = {}
    for path, task in tasks:
        task_id = str(task["task_id"])
        if task_id not in filtered_ids:
            continue
        snapshot[task_id] = {
            "difficulty_tier": str(task["difficulty_tier"]),
            "task_path": str(path),
            "mtime": path.stat().st_mtime,
        }
    return snapshot


def _bar(done: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return "[" + "-" * width + "]"
    filled = int(width * min(max(done / total, 0.0), 1.0))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _build_plan(model: str, seeds: tuple[int, ...]) -> list[SuitePlan]:
    public_count = _load_task_count("public_dev")
    private_count = _load_task_count("private_holdout")
    canonical_public_root = DEFAULT_CANONICAL_RESULTS_ROOT / "dev_v2_public_dev" / "suites"
    canonical_public_analysis = DEFAULT_CANONICAL_RESULTS_ROOT / "dev_v2_public_dev" / "analysis"
    canonical_private_root = DEFAULT_CANONICAL_RESULTS_ROOT / "dev_v2_private_holdout" / "suites"
    canonical_private_analysis = DEFAULT_CANONICAL_RESULTS_ROOT / "dev_v2_private_holdout" / "analysis"
    ablations_root = DEFAULT_ABLATIONS_RESULTS_ROOT / "dev_v2" / "public_dev" / "suites"
    ablations_analysis = DEFAULT_ABLATIONS_RESULTS_ROOT / "dev_v2" / "public_dev" / "analysis"

    plan: list[SuitePlan] = []
    for seed in seeds:
        for baseline in CANONICAL_BASELINES:
            plan.append(
                SuitePlan(
                    bucket="canonical_public_dev",
                    baseline=baseline,
                    model=model,
                    seed=seed,
                    task_split="public_dev",
                    task_count=public_count,
                    results_root=str(canonical_public_root),
                    analysis_dir=str(canonical_public_analysis),
                )
            )
    for seed in seeds:
        for baseline in CANONICAL_BASELINES:
            plan.append(
                SuitePlan(
                    bucket="canonical_private_holdout",
                    baseline=baseline,
                    model=model,
                    seed=seed,
                    task_split="private_holdout",
                    task_count=private_count,
                    results_root=str(canonical_private_root),
                    analysis_dir=str(canonical_private_analysis),
                )
            )
    for seed in seeds:
        for baseline, flags in ABLATION_VARIANTS:
            plan.append(
                SuitePlan(
                    bucket="ablations_public_dev",
                    baseline=baseline,
                    model=model,
                    seed=seed,
                    task_split="public_dev",
                    task_count=public_count,
                    results_root=str(ablations_root),
                    analysis_dir=str(ablations_analysis),
                    disable_formula_guardrails=bool(flags.get("disable_formula_guardrails")),
                    disable_component_grounding=bool(flags.get("disable_component_grounding")),
                    disable_correction_memory=bool(flags.get("disable_correction_memory")),
                )
            )
    return plan


def _suite_command(plan: SuitePlan, simulator_mode: str) -> list[str]:
    command = [
        sys.executable,
        "-u",
        "scripts/run_suite.py",
        "--baseline",
        plan.baseline,
        "--model",
        plan.model,
        "--seed",
        str(plan.seed),
        "--results-root",
        plan.results_root,
        "--simulator-mode",
        simulator_mode,
        "--task-split",
        plan.task_split,
    ]
    if plan.disable_formula_guardrails:
        command.append("--disable-formula-guardrails")
    if plan.disable_component_grounding:
        command.append("--disable-component-grounding")
    if plan.disable_correction_memory:
        command.append("--disable-correction-memory")
    return command


def _drain_output(stream, queue: Queue[str]) -> None:
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            queue.put(line)
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _update_status_files(run_root: Path, payload: dict[str, Any]) -> None:
    (run_root / "status.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    progress_lines = [
        f"# Official Experiment Run Status",
        "",
        f"- run_name: `{payload['run_name']}`",
        f"- started_at_utc: `{payload['started_at_utc']}`",
        f"- updated_at_utc: `{payload['updated_at_utc']}`",
        f"- completed_suites: `{payload['completed_suites']}/{payload['total_suites']}`",
        f"- failed_suites: `{payload['failed_suites']}`",
        f"- run_state: `{payload.get('run_state', 'unknown')}`",
        f"- suite_progress: `{payload['suite_progress_bar']}`",
        f"- task_progress: `{payload['task_progress_bar']}`",
        "",
        f"## Current suite",
        "",
        f"- suite_id: `{payload.get('current_suite_id') or 'none'}`",
        f"- bucket: `{payload.get('current_bucket') or 'none'}`",
        f"- task_progress: `{payload.get('current_suite_tasks_done', 0)}/{payload.get('current_suite_task_total', 0)}`",
        f"- log: `{payload.get('current_suite_log') or 'none'}`",
        "",
        "## Buckets",
        "",
    ]
    for bucket_name, bucket_data in sorted(payload["bucket_status"].items()):
        progress_lines.append(
            f"- `{bucket_name}`: `{bucket_data['completed']}/{bucket_data['total']}` complete, analysis=`{bucket_data['analysis_dir']}`"
        )
    last_error = payload.get("last_error")
    if last_error:
        progress_lines.extend(
            [
                "",
                "## Last Error",
                "",
                "```text",
                last_error.rstrip(),
                "```",
            ]
        )
    (run_root / "progress.md").write_text("\n".join(progress_lines) + "\n", encoding="utf-8")


def _run_analysis(bucket_name: str, analysis_dir: Path, results_root: Path, master_log) -> None:
    suite_dirs = find_suite_dirs(results_root)
    if not suite_dirs:
        return
    outputs = write_analysis_outputs(suite_dirs=suite_dirs, output_dir=analysis_dir)
    print(f"[analysis] bucket={bucket_name} outputs={outputs}", file=master_log, flush=True)


def _suite_dir_is_compatible(plan: SuitePlan) -> bool:
    if not plan.suite_dir.exists() or not plan.summary_path.exists() or not plan.task_results_dir.exists():
        return False
    expected = _expected_task_snapshot(plan.task_split)
    result_files = sorted(plan.task_results_dir.glob("*.json"))
    if len(result_files) != len(expected):
        return False
    summary_mtime = plan.summary_path.stat().st_mtime
    latest_task_mtime = max((float(meta["mtime"]) for meta in expected.values()), default=0.0)
    if summary_mtime < latest_task_mtime:
        return False
    seen: set[str] = set()
    for result_file in result_files:
        result = load_json(result_file)
        task_id = str(result.get("task_id") or "")
        expected_meta = expected.get(task_id)
        if expected_meta is None:
            return False
        if str(result.get("difficulty_tier")) != str(expected_meta["difficulty_tier"]):
            return False
        seen.add(task_id)
    return seen == set(expected)


def _archive_stale_suite(plan: SuitePlan, master_log) -> None:
    if not plan.suite_dir.exists():
        return
    archive_root = Path(plan.results_root).parent / "stale_runs"
    archive_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = archive_root / f"{plan.suite_id}__stale_{timestamp}"
    shutil.move(str(plan.suite_dir), str(destination))
    print(f"[archive-stale-suite] suite_id={plan.suite_id} moved_to={destination}", file=master_log, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full PE-Bench official dev_v2 experiment plan locally.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--simulator-mode", default="auto")
    parser.add_argument("--run-name", default=f"official_dev_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--no-resume", dest="resume", action="store_false")
    parser.add_argument("--stop-on-error", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seeds = DEFAULT_SEEDS
    plan = _build_plan(model=args.model, seeds=seeds)
    run_root = RUN_CONTROL_ROOT / args.run_name
    suite_logs_root = run_root / "suite_logs"
    suite_logs_root.mkdir(parents=True, exist_ok=True)
    manifest_path = run_root / "manifest.json"
    manifest_path.write_text(json.dumps([asdict(item) | {"run_name": item.run_name, "suite_id": item.suite_id} for item in plan], indent=2), encoding="utf-8")

    total_tasks = sum(item.task_count for item in plan)
    bucket_status: dict[str, dict[str, Any]] = {}
    for item in plan:
        bucket_status.setdefault(
            item.bucket,
            {"completed": 0, "total": 0, "analysis_dir": item.analysis_dir, "results_root": item.results_root},
        )
        bucket_status[item.bucket]["total"] += 1

    master_log_path = run_root / "run.log"
    completed_suites = 0
    completed_tasks = 0
    failed_suites: list[str] = []
    started_at = _utc_now()
    run_state = "running"
    last_error: str | None = None

    with master_log_path.open("a", encoding="utf-8") as master_log:
        print(f"[run-start] run_name={args.run_name} started_at={started_at} total_suites={len(plan)} total_tasks={total_tasks}", file=master_log, flush=True)
        for item in plan:
            if item.suite_dir.exists() and not _suite_dir_is_compatible(item):
                _archive_stale_suite(item, master_log)
        try:
            for index, item in enumerate(plan, start=1):
                suite_log_path = suite_logs_root / f"{item.suite_id}.log"
                current_done = 0
                if args.resume and item.summary_path.exists() and _suite_dir_is_compatible(item):
                    completed_suites += 1
                    completed_tasks += item.task_count
                    bucket_status[item.bucket]["completed"] += 1
                    print(f"[skip-existing] {item.suite_id}", file=master_log, flush=True)
                    status_payload = {
                        "run_name": args.run_name,
                        "started_at_utc": started_at,
                        "updated_at_utc": _utc_now(),
                        "completed_suites": completed_suites,
                        "total_suites": len(plan),
                        "failed_suites": len(failed_suites),
                        "run_state": run_state,
                        "suite_progress_bar": _bar(completed_suites, len(plan)),
                        "completed_tasks_estimate": completed_tasks,
                        "total_tasks_estimate": total_tasks,
                        "task_progress_bar": _bar(completed_tasks, total_tasks),
                        "current_suite_id": item.suite_id,
                        "current_bucket": item.bucket,
                        "current_suite_tasks_done": item.task_count,
                        "current_suite_task_total": item.task_count,
                        "current_suite_log": str(suite_log_path),
                        "bucket_status": bucket_status,
                        "last_error": last_error,
                    }
                    _update_status_files(run_root, status_payload)
                    continue

                command = _suite_command(item, simulator_mode=args.simulator_mode)
                print(f"[suite-run] {index}/{len(plan)} {shlex.join(command)}", file=master_log, flush=True)
                with suite_log_path.open("w", encoding="utf-8") as suite_log:
                    suite_log.write(f"[suite-run] {shlex.join(command)}\n")
                    child_env = os.environ.copy()
                    child_env.setdefault("PYTHONUNBUFFERED", "1")
                    if args.simulator_mode in {"auto", "live", "mcp", "xmlrpc"}:
                        child_env["PEBENCH_ENABLE_LIVE_SIM"] = "1"

                    proc = subprocess.Popen(
                        command,
                        cwd=REPO_ROOT,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        env=child_env,
                    )
                    output_queue: Queue[str] = Queue()
                    reader = threading.Thread(target=_drain_output, args=(proc.stdout, output_queue), daemon=True)
                    reader.start()

                    last_status_emit = 0.0
                    while True:
                        while True:
                            try:
                                line = output_queue.get_nowait()
                            except Empty:
                                break
                            print(line, end="", file=suite_log, flush=True)
                            print(line, end="", file=master_log, flush=True)
                        if item.task_results_dir.exists():
                            current_done = len(list(item.task_results_dir.glob("*.json")))
                        now = time.time()
                        if now - last_status_emit >= args.poll_seconds:
                            suite_progress = current_done
                            total_progress = completed_tasks + suite_progress
                            progress_line = (
                                f"[progress] suites={completed_suites}/{len(plan)} { _bar(completed_suites, len(plan)) } "
                                f"| current={item.suite_id} tasks={suite_progress}/{item.task_count} "
                                f"{_bar(suite_progress, item.task_count)} | total_tasks={total_progress}/{total_tasks} "
                                f"{_bar(total_progress, total_tasks)}"
                            )
                            print(progress_line, file=master_log, flush=True)
                            status_payload = {
                                "run_name": args.run_name,
                                "started_at_utc": started_at,
                                "updated_at_utc": _utc_now(),
                                "completed_suites": completed_suites,
                                "total_suites": len(plan),
                                "failed_suites": len(failed_suites),
                                "run_state": run_state,
                                "suite_progress_bar": _bar(completed_suites, len(plan)),
                                "completed_tasks_estimate": total_progress,
                                "total_tasks_estimate": total_tasks,
                                "task_progress_bar": _bar(total_progress, total_tasks),
                                "current_suite_id": item.suite_id,
                                "current_bucket": item.bucket,
                                "current_suite_tasks_done": suite_progress,
                                "current_suite_task_total": item.task_count,
                                "current_suite_log": str(suite_log_path),
                                "bucket_status": bucket_status,
                                "last_error": last_error,
                            }
                            _update_status_files(run_root, status_payload)
                            last_status_emit = now
                        if proc.poll() is not None:
                            break
                        time.sleep(1.0)

                    while True:
                        try:
                            line = output_queue.get_nowait()
                        except Empty:
                            break
                        print(line, end="", file=suite_log, flush=True)
                        print(line, end="", file=master_log, flush=True)

                    return_code = proc.wait()
                    if item.task_results_dir.exists():
                        current_done = len(list(item.task_results_dir.glob("*.json")))

                if return_code != 0:
                    failed_suites.append(item.suite_id)
                    print(f"[suite-failed] suite_id={item.suite_id} return_code={return_code}", file=master_log, flush=True)
                    if args.stop_on_error:
                        raise RuntimeError(f"Suite failed: {item.suite_id}")
                else:
                    completed_suites += 1
                    completed_tasks += item.task_count
                    bucket_status[item.bucket]["completed"] += 1
                    print(f"[suite-ok] suite_id={item.suite_id}", file=master_log, flush=True)

                status_payload = {
                    "run_name": args.run_name,
                    "started_at_utc": started_at,
                    "updated_at_utc": _utc_now(),
                    "completed_suites": completed_suites,
                    "total_suites": len(plan),
                    "failed_suites": len(failed_suites),
                    "run_state": run_state,
                    "suite_progress_bar": _bar(completed_suites, len(plan)),
                    "completed_tasks_estimate": completed_tasks,
                    "total_tasks_estimate": total_tasks,
                    "task_progress_bar": _bar(completed_tasks, total_tasks),
                    "current_suite_id": item.suite_id,
                    "current_bucket": item.bucket,
                    "current_suite_tasks_done": current_done,
                    "current_suite_task_total": item.task_count,
                    "current_suite_log": str(suite_log_path),
                    "bucket_status": bucket_status,
                    "last_error": last_error,
                }
                _update_status_files(run_root, status_payload)
                _run_analysis(item.bucket, Path(item.analysis_dir), Path(item.results_root), master_log)
            run_state = "completed"
        except KeyboardInterrupt:
            run_state = "interrupted"
            last_error = "KeyboardInterrupt"
            print("[run-error] KeyboardInterrupt", file=master_log, flush=True)
            raise
        except Exception:
            run_state = "failed"
            last_error = traceback.format_exc()
            print("[run-error] orchestrator failed", file=master_log, flush=True)
            print(last_error, file=master_log, flush=True)
            raise

        finally:
            final_payload = {
                "run_name": args.run_name,
                "started_at_utc": started_at,
                "updated_at_utc": _utc_now(),
                "completed_suites": completed_suites,
                "total_suites": len(plan),
                "failed_suites": len(failed_suites),
                "failed_suite_ids": failed_suites,
                "run_state": run_state,
                "suite_progress_bar": _bar(completed_suites, len(plan)),
                "completed_tasks_estimate": completed_tasks,
                "total_tasks_estimate": total_tasks,
                "task_progress_bar": _bar(completed_tasks, total_tasks),
                "current_suite_id": None,
                "current_bucket": None,
                "current_suite_tasks_done": 0,
                "current_suite_task_total": 0,
                "current_suite_log": None,
                "bucket_status": bucket_status,
                "last_error": last_error,
            }
            _update_status_files(run_root, final_payload)
            print(f"[run-finish] completed_suites={completed_suites}/{len(plan)} failed={len(failed_suites)}", file=master_log, flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
