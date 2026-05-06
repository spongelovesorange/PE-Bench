from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_ROOT = REPO_ROOT / "results" / "final78_api_runs"
BASELINES = (
    "direct_prompting",
    "structured_output_only",
    "text_only_self_refine",
    "single_agent_same_tools",
    "single_agent_retry",
    "generic_two_role_mas",
    "pe_gpt_style",
    "reference_agent",
)
ABLATION_FLAGS = (
    ("reference_agent__wo_formula_guardrails", ["--disable-formula-guardrails"]),
    ("reference_agent__wo_component_grounding", ["--disable-component-grounding"]),
    ("reference_agent__wo_correction_memory", ["--disable-correction-memory"]),
)
MODEL_PRIORITY = (
    "gpt-4.1-mini",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",
    "gemini-1.5-flash",
    "claude-3-5-haiku",
    "claude-3-haiku",
    "gpt-4o-mini",
)


@dataclass(frozen=True)
class Job:
    job_id: str
    kind: str
    baseline: str
    model: str
    seed: int
    extra_args: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run long PE-Bench final 78-task API experiments with resumable records.")
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--run-root", default=None)
    parser.add_argument("--model", default="auto")
    parser.add_argument("--base-url", default=os.getenv("PEBENCH_LLM_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument(
        "--profile",
        choices=["main", "main_plus_ablations", "backbone", "smoke"],
        default="main_plus_ablations",
    )
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--simulator-mode", default="stub")
    parser.add_argument("--task-limit", type=int, default=999)
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    parser.add_argument("--stop-on-failure", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _require_api_key(args.model)
    os.environ["PEBENCH_LLM_BASE_URL"] = _normalize_base_url(args.base_url)
    os.environ["PEBENCH_LLM_TEMPERATURE"] = str(args.temperature)
    os.environ["PEBENCH_LLM_TIMEOUT_SEC"] = str(args.timeout_sec)

    model = _select_model(args.model, os.environ["PEBENCH_LLM_BASE_URL"], args.timeout_sec)
    run_root = _run_root(args)
    raw_root = run_root / "raw_records"
    logs_root = run_root / "logs"
    jobs_root = run_root / "jobs"
    for path in (raw_root, logs_root, jobs_root):
        path.mkdir(parents=True, exist_ok=True)

    jobs = _build_jobs(profile=args.profile, seeds=tuple(args.seeds), model=model)
    _write_manifest(run_root, args, model, jobs)
    _write_queue(run_root / "queue.csv", jobs)
    failures = 0
    started_at = _utc_now()
    for index, job in enumerate(jobs, start=1):
        done_marker = jobs_root / f"{job.job_id}.done.json"
        fail_marker = jobs_root / f"{job.job_id}.failed.json"
        if done_marker.exists():
            _write_status(
                run_root,
                jobs,
                current=None,
                index=index - 1,
                failures=failures,
                state="running",
                started_at=started_at,
            )
            continue
        log_path = logs_root / f"{job.job_id}.log"
        _write_status(
            run_root,
            jobs,
            current=job,
            index=index - 1,
            failures=failures,
            state="running",
            log_path=log_path,
            started_at=started_at,
        )
        command = _job_command(job, raw_root, args)
        start = time.time()
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n===== {job.job_id} start {_utc_now()} =====\n")
            log.write("command: " + " ".join(_redact_command(command)) + "\n")
            log.flush()
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=os.environ.copy(),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            log.write(f"===== {job.job_id} end {_utc_now()} returncode={completed.returncode} =====\n")
        payload = {
            "job": asdict(job),
            "started_at_utc": datetime.fromtimestamp(start, timezone.utc).isoformat(),
            "finished_at_utc": _utc_now(),
            "runtime_seconds": round(time.time() - start, 3),
            "returncode": completed.returncode,
            "log_path": str(log_path.relative_to(run_root)),
            "raw_records_root": str(raw_root.relative_to(run_root)),
        }
        if completed.returncode == 0:
            done_marker.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            failures += 1
            fail_marker.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if args.stop_on_failure:
                _write_status(
                    run_root,
                    jobs,
                    current=None,
                    index=index,
                    failures=failures,
                    state="failed",
                    started_at=started_at,
                )
                return completed.returncode
        _write_status(
            run_root,
            jobs,
            current=None,
            index=index,
            failures=failures,
            state="running",
            started_at=started_at,
        )

    _write_checksums(run_root)
    final_state = "completed" if failures == 0 else "completed_with_failures"
    _write_status(run_root, jobs, current=None, index=len(jobs), failures=failures, state=final_state, started_at=started_at)
    return 0 if failures == 0 else 1


def _build_jobs(*, profile: str, seeds: tuple[int, ...], model: str) -> list[Job]:
    jobs: list[Job] = []
    if profile == "smoke":
        seeds = seeds[:1]
        baselines = ("direct_prompting", "reference_agent")
    elif profile == "backbone":
        baselines = ("direct_prompting", "reference_agent")
    else:
        baselines = BASELINES
    for seed in seeds:
        for baseline in baselines:
            jobs.append(
                Job(
                    job_id=_sanitize(f"main78__{baseline}__{model}__seed{seed}"),
                    kind="main78",
                    baseline=baseline,
                    model=model,
                    seed=seed,
                    extra_args=(),
                )
            )
    if profile == "main_plus_ablations":
        for seed in seeds:
            for label, flags in ABLATION_FLAGS:
                jobs.append(
                    Job(
                        job_id=_sanitize(f"ablation78__{label}__{model}__seed{seed}"),
                        kind="ablation78",
                        baseline="reference_agent",
                        model=model,
                        seed=seed,
                        extra_args=tuple(flags),
                    )
                )
    return jobs


def _job_command(job: Job, raw_root: Path, args: argparse.Namespace) -> list[str]:
    return [
        sys.executable,
        "-u",
        "scripts/run_pebench_suite.py",
        "--track",
        "all",
        "--topology",
        "all",
        "--baseline",
        job.baseline,
        "--model",
        job.model,
        "--seed",
        str(job.seed),
        "--temperature",
        str(args.temperature),
        "--api-base",
        os.environ["PEBENCH_LLM_BASE_URL"],
        "--api-key-env",
        "PEBENCH_LLM_API_KEY",
        "--simulator-mode",
        args.simulator_mode,
        "--task-limit",
        str(args.task_limit),
        "--output-root",
        str(raw_root),
        *job.extra_args,
    ]


def _select_model(requested: str, base_url: str, timeout_sec: float) -> str:
    if requested != "auto":
        return requested
    key = os.environ["PEBENCH_LLM_API_KEY"]
    try:
        client = OpenAI(
            api_key=key,
            base_url=base_url,
            timeout=timeout_sec,
            http_client=httpx.Client(timeout=timeout_sec, trust_env=False, http2=False),
        )
        model_ids = {str(item.id) for item in client.models.list().data}
    except Exception:
        return "gpt-4o-mini"
    for candidate in MODEL_PRIORITY:
        if candidate in model_ids:
            return candidate
    lowered = {model.lower(): model for model in model_ids}
    for candidate in MODEL_PRIORITY:
        for lowered_id, original_id in lowered.items():
            if candidate.lower() in lowered_id:
                return original_id
    if model_ids:
        return sorted(model_ids)[0]
    return "gpt-4o-mini"


def _write_manifest(run_root: Path, args: argparse.Namespace, model: str, jobs: list[Job]) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_name": run_root.name,
        "created_at_utc": _utc_now(),
        "task_total_per_main_job": 78,
        "model": model,
        "base_url": os.environ["PEBENCH_LLM_BASE_URL"],
        "api_key_recorded": False,
        "profile": args.profile,
        "seeds": args.seeds,
        "job_count": len(jobs),
        "raw_records_root": "raw_records",
        "logs_root": "logs",
        "runner": "scripts/run_final78_experiments.py",
    }
    (run_root / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_queue(path: Path, jobs: list[Job]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["job_id", "kind", "baseline", "model", "seed", "extra_args"])
        writer.writeheader()
        for job in jobs:
            writer.writerow({**asdict(job), "extra_args": " ".join(job.extra_args)})


def _write_status(
    run_root: Path,
    jobs: list[Job],
    *,
    current: Job | None,
    index: int,
    failures: int,
    state: str,
    log_path: Path | None = None,
    started_at: str | None = None,
) -> None:
    done = len(list((run_root / "jobs").glob("*.done.json"))) if (run_root / "jobs").exists() else 0
    failed = len(list((run_root / "jobs").glob("*.failed.json"))) if (run_root / "jobs").exists() else failures
    payload = {
        "run_name": run_root.name,
        "state": state,
        "updated_at_utc": _utc_now(),
        "started_at_utc": started_at,
        "completed_jobs": done,
        "failed_jobs": failed,
        "total_jobs": len(jobs),
        "current_job": asdict(current) if current else None,
        "current_log": str(log_path.relative_to(run_root)) if log_path else None,
        "progress_percent": round(100.0 * done / max(1, len(jobs)), 2),
    }
    (run_root / "status.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Final 78-Task API Run Status",
        "",
        f"- state: `{payload['state']}`",
        f"- updated_at_utc: `{payload['updated_at_utc']}`",
        f"- completed_jobs: `{done}/{len(jobs)}`",
        f"- failed_jobs: `{failed}`",
        f"- progress_percent: `{payload['progress_percent']}`",
        f"- current_job: `{current.job_id if current else 'none'}`",
        f"- current_log: `{payload['current_log'] or 'none'}`",
        "",
        "API key is used from the local process environment and is not written to this run directory.",
        "",
    ]
    (run_root / "RUN_STATUS.md").write_text("\n".join(lines), encoding="utf-8")


def _write_checksums(run_root: Path) -> None:
    lines: list[str] = []
    for path in sorted((run_root / "raw_records").rglob("*")):
        if path.is_file():
            lines.append(f"{_sha256(path)}  {path.relative_to(run_root)}")
    (run_root / "raw_record_checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _require_api_key(model: str) -> None:
    if model in {"", "heuristic", "heuristic-v0", "none", "stub"}:
        return
    if not os.getenv("PEBENCH_LLM_API_KEY"):
        raise SystemExit("Missing PEBENCH_LLM_API_KEY in environment.")


def _run_root(args: argparse.Namespace) -> Path:
    if args.run_root:
        return Path(args.run_root).resolve()
    run_name = args.run_name or f"final78_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return DEFAULT_RUNS_ROOT / _sanitize(run_name)


def _normalize_base_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")]
    if not normalized.endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


def _redact_command(command: list[str]) -> list[str]:
    redacted = []
    skip_next = False
    for part in command:
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
            continue
        redacted.append(part)
        if part == "--api-key-env":
            skip_next = True
    return redacted


def _sanitize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "run"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
