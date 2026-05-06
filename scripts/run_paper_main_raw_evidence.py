from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx
from openai import OpenAI


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_ROOT = REPO_ROOT / "results" / "paper_main_raw_runs"
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run, freeze, promote, and compare PE-Bench paper-main raw evidence.")
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--run-root", default=None)
    parser.add_argument("--model", default=os.getenv("PEBENCH_PAPER_MAIN_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=os.getenv("PEBENCH_LLM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument(
        "--profile",
        choices=["main", "main_plus_ablations", "backbone"],
        default="main_plus_ablations",
    )
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    parser.add_argument("--simulator-mode", default="stub")
    parser.add_argument("--env-file", default=None, help="Optional local env file outside the repo containing API settings.")
    parser.add_argument("--skip-model-preflight", action="store_true")
    parser.add_argument("--background", action="store_true", help="Launch this orchestration in a detached background process.")
    parser.add_argument("--fail-on-paper-mismatch", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_file:
        _load_env_file(Path(args.env_file))
        if args.base_url == DEFAULT_BASE_URL and os.getenv("PEBENCH_LLM_BASE_URL"):
            args.base_url = str(os.getenv("PEBENCH_LLM_BASE_URL"))
        if args.model == DEFAULT_MODEL and os.getenv("PEBENCH_PAPER_MAIN_MODEL"):
            args.model = str(os.getenv("PEBENCH_PAPER_MAIN_MODEL"))
    if not os.getenv("PEBENCH_LLM_API_KEY"):
        print("Missing PEBENCH_LLM_API_KEY in the environment.")
        print("Set it locally before launching; the key is never written to the run directory.")
        return 2

    if not args.skip_model_preflight:
        preflight = _preflight_model(args.model, args.base_url, args.timeout_sec)
        if preflight:
            print(preflight)
            return 3

    run_root = _run_root(args)
    if args.background:
        return _launch_background(args, run_root)

    run_root.mkdir(parents=True, exist_ok=True)
    _write_launch_manifest(args, run_root)
    run_cmd = [
        sys.executable,
        "scripts/run_final78_experiments.py",
        "--run-root",
        str(run_root),
        "--model",
        args.model,
        "--base-url",
        args.base_url,
        "--seeds",
        *[str(seed) for seed in args.seeds],
        "--profile",
        args.profile,
        "--temperature",
        str(args.temperature),
        "--timeout-sec",
        str(args.timeout_sec),
        "--simulator-mode",
        args.simulator_mode,
    ]
    if subprocess.run(run_cmd, cwd=REPO_ROOT, check=False).returncode != 0:
        return 1

    promoted = REPO_ROOT / "artifacts" / "evidence" / f"paper_main_raw_{run_root.name}"
    promote_cmd = [
        sys.executable,
        "scripts/promote_api_run_evidence.py",
        "--run-root",
        str(run_root),
        "--output-dir",
        str(promoted),
        "--label",
        "paper_main_raw_api_evidence",
    ]
    if args.profile != "backbone":
        promote_cmd.append("--used-for-main-paper-tables")
    if subprocess.run(promote_cmd, cwd=REPO_ROOT, check=False).returncode != 0:
        return 1

    compare_cmd = [
        sys.executable,
        "scripts/compare_api_evidence_to_paper.py",
        "--actual",
        str(promoted / "leaderboard_summary.csv"),
        "--output",
        str(promoted / "paper_alignment_report.json"),
        "--tolerance",
        "0.035",
    ]
    if args.fail_on_paper_mismatch:
        compare_cmd.append("--fail-on-mismatch")
    return subprocess.run(compare_cmd, cwd=REPO_ROOT, check=False).returncode


def _launch_background(args: argparse.Namespace, run_root: Path) -> int:
    run_root.mkdir(parents=True, exist_ok=True)
    log_path = run_root / "paper_main_raw_evidence.log"
    cmd = [
        sys.executable,
        "scripts/run_paper_main_raw_evidence.py",
        "--run-root",
        str(run_root),
        "--model",
        args.model,
        "--base-url",
        args.base_url,
        "--seeds",
        *[str(seed) for seed in args.seeds],
        "--profile",
        args.profile,
        "--temperature",
        str(args.temperature),
        "--timeout-sec",
        str(args.timeout_sec),
        "--simulator-mode",
        args.simulator_mode,
    ]
    if args.env_file:
        cmd.extend(["--env-file", args.env_file])
    if args.fail_on_paper_mismatch:
        cmd.append("--fail-on-paper-mismatch")
    if args.skip_model_preflight:
        cmd.append("--skip-model-preflight")
    env = os.environ.copy()
    with log_path.open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    (run_root / "launcher.pid").write_text(str(process.pid) + "\n", encoding="utf-8")
    print(f"Launched background paper-main raw-evidence run.")
    print(f"run_root: {run_root}")
    print(f"pid: {process.pid}")
    print(f"log: {log_path}")
    return 0


def _run_root(args: argparse.Namespace) -> Path:
    if args.run_root:
        return Path(args.run_root).resolve()
    run_name = args.run_name or f"paper_main_mid_general_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return DEFAULT_RUNS_ROOT / _sanitize(run_name)


def _write_launch_manifest(args: argparse.Namespace, run_root: Path) -> None:
    payload = {
        "api_key_recorded": False,
        "base_url": _normalize_base_url(args.base_url),
        "env_file_used": bool(args.env_file),
        "model": args.model,
        "profile": args.profile,
        "run_name": run_root.name,
        "runner": "scripts/run_paper_main_raw_evidence.py",
        "seeds": args.seeds,
        "simulator_mode": args.simulator_mode,
        "temperature": args.temperature,
        "timeout_sec": args.timeout_sec,
    }
    (run_root / "paper_main_launch_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_base_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")]
    if not normalized.endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


def _preflight_model(model: str, base_url: str, timeout_sec: float) -> str | None:
    if model == "auto":
        return None
    try:
        client = OpenAI(
            api_key=str(os.environ["PEBENCH_LLM_API_KEY"]),
            base_url=_normalize_base_url(base_url),
            timeout=timeout_sec,
            http_client=httpx.Client(timeout=timeout_sec, trust_env=False, http2=False),
        )
        model_ids = sorted(str(item.id) for item in client.models.list().data)
    except Exception:
        return None
    if model in model_ids:
        return None
    close = [item for item in model_ids if model.lower() in item.lower() or "gpt-4.1" in item.lower() or "gpt-4o" in item.lower()]
    suggestions = close[:12] or model_ids[:12]
    return (
        f"Requested model `{model}` was not returned by the provider model list. "
        f"Use one of these model ids or rerun with --model auto: {suggestions}"
    )


def _sanitize(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "run"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Missing env file: {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key in {"PEBENCH_LLM_API_KEY", "PEBENCH_LLM_BASE_URL", "PEBENCH_PAPER_MAIN_MODEL"}:
            os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
