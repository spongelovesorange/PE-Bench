"""The small public command line interface for PE-Bench."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path


def _invoke(module_name: str, arguments: list[str]) -> int:
    """Call an existing command without changing its experiment behavior."""
    module = importlib.import_module(f"pebench._commands.{module_name}")
    previous = sys.argv
    try:
        sys.argv = [f"python -m pebench._commands.{module_name}", *arguments]
        return int(module.main() or 0)
    finally:
        sys.argv = previous


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pebench",
        description="Check, run, and evaluate power-electronics design tasks.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Validate all 78 tasks and local release artifacts.")

    run = commands.add_parser("run", help="Run the reference suite or generate one candidate.")
    run.add_argument("--task", help="Task YAML; omit to run the released task banks.")
    run.add_argument("--baseline", default="reference_design")
    run.add_argument("--model", help="Defaults to reference-design, or heuristic-v0 for other baselines.")
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--simulator-mode", choices=["stub", "auto", "live", "mcp", "xmlrpc"], default="stub")
    run.add_argument("--output", help="Single candidate JSON path; requires --task.")
    run.add_argument("--output-root", default="results/pebench", help="Suite output directory.")
    run.add_argument("--track", choices=["all", "flyback", "topology_full", "three_phase_inverter"], default="all")
    run.add_argument("--topology", choices=["all", "buck", "boost", "buck_boost", "flyback", "three_phase_inverter"], default="all")
    run.add_argument("--task-limit", type=int, default=999, help="Maximum tasks per track.")
    run.add_argument("--difficulty-tier", action="append", default=[])
    run.add_argument("--task-split", default="all")
    for flag in ("formula-guardrails", "component-grounding", "correction-memory"):
        run.add_argument(f"--disable-{flag}", action="store_true")

    evaluate = commands.add_parser("evaluate", help="Evaluate a candidate JSON against its task.")
    evaluate.add_argument("--task", required=True)
    evaluate.add_argument("--candidate", required=True)
    evaluate.add_argument("--output", default="results/evaluation.json")
    evaluate.add_argument("--simulator-mode", choices=["stub", "auto", "live", "mcp", "xmlrpc"], default="stub")

    tables = commands.add_parser("tables", help="Check frozen summary records and rebuild paper tables.")
    tables.add_argument("--evidence", default="artifacts/evidence/frozen_v1")

    export = commands.add_parser("export", help="Check and export an anonymous reviewer ZIP.")
    export.add_argument("--output", help="Destination ZIP; defaults to dist/pebench_anonymous_artifact.zip.")
    return parser


def _run_one(args: argparse.Namespace) -> int:
    from pebench.baselines.reference import build_reference_candidate
    from pebench.tasks.schema import load_task
    from pebench.utils.io import dump_json

    task = load_task(args.task)
    if args.baseline == "reference_design":
        candidate = build_reference_candidate(
            task, model_name=args.model, seed=args.seed, simulator_mode=args.simulator_mode,
        )
    else:
        topology = task.get("topology") or task.get("reference_design", {}).get("topology")
        options = {
            "disable_formula_guardrails": args.disable_formula_guardrails,
            "disable_component_grounding": args.disable_component_grounding,
            "disable_correction_memory": args.disable_correction_memory,
        }
        if topology in {"buck", "boost", "buck_boost"}:
            from pebench.baselines.topology_scout import get_topology_scout_baseline

            baseline = get_topology_scout_baseline(args.baseline, **options)
            candidate = baseline.generate(task=task, model_name=args.model, seed=args.seed)
        elif topology == "three_phase_inverter":
            from pebench.baselines.inverter import get_inverter_baseline

            baseline = get_inverter_baseline(args.baseline, **options)
            candidate = baseline.generate(task=task, model_name=args.model, seed=args.seed)
        else:
            from pebench.adapters.registry import get_baseline
            from pebench._commands.run_suite import run_task_with_baseline

            baseline = get_baseline(args.baseline, **options)
            candidate, _, _ = run_task_with_baseline(
                baseline=baseline, task=task, model_name=args.model,
                seed=args.seed, simulator_mode=args.simulator_mode,
            )
    output = Path(args.output or "results/candidate.json")
    dump_json(candidate, output)
    print(f"Candidate: {output}")
    return 0


def _run(args: argparse.Namespace) -> int:
    args.model = args.model or ("reference-design" if args.baseline == "reference_design" else "heuristic-v0")
    if args.task:
        return _run_one(args)
    arguments = [
        "--baseline", args.baseline, "--model", args.model,
        "--seed", str(args.seed), "--simulator-mode", args.simulator_mode,
        "--output-root", args.output_root, "--track", args.track,
        "--topology", args.topology, "--task-limit", str(args.task_limit),
        "--task-split", args.task_split,
    ]
    for tier in args.difficulty_tier:
        arguments.extend(["--difficulty-tier", tier])
    for flag in ("formula_guardrails", "component_grounding", "correction_memory"):
        if getattr(args, f"disable_{flag}"):
            arguments.append(f"--disable-{flag.replace('_', '-')}")
    result = _invoke("run_pebench_suite", arguments)
    if result == 0:
        print(f"Suite results: {args.output_root}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "check":
        return _invoke("reviewer_smoke_test", [])
    if args.command == "run":
        if args.output and not args.task:
            parser.error("--output requires --task; use --output-root for a suite")
        if args.task_limit < 1:
            parser.error("--task-limit must be positive")
        return _run(args)
    if args.command == "evaluate":
        return _invoke("run_evaluator", [
            "--task", args.task, "--candidate", args.candidate,
            "--output", args.output, "--simulator-mode", args.simulator_mode,
        ])
    if args.command == "tables":
        arguments = ["--evidence", args.evidence]
        result = _invoke("reproduce_paper_tables", arguments)
        return result or _invoke("build_paper_tables", [*arguments, "--check"])
    if args.command == "export":
        arguments = ["--check"]
        if args.output:
            arguments.extend(["--output", args.output])
        return _invoke("export_anonymous_artifact", arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
