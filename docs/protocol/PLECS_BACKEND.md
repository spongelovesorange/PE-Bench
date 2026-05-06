# Optional PLECS Backend

PE-Bench does not require PLECS for the default reviewer path. The no-API smoke tests, task validators, frozen manuscript table reproduction, and anonymous artifact export all run with deterministic `stub` or formula-backed evaluator modes.

PLECS is an optional live-simulation backend for rerunning experiments in environments that already have a licensed local PLECS installation and the reference-agent PLECS bridge configured. Because PLECS setup is machine-specific, live reruns are documented as an optional backend rather than a hard package dependency.

## When To Use Each Simulator Mode

| Mode | Use case | Requires PLECS | Reviewer expectation |
| --- | --- | --- | --- |
| `stub` | CI, smoke tests, frozen artifact validation, table reproduction | No | Required path |
| `auto` | Try live backend when configured, otherwise record fallback to stub | Optional | Optional rerun convenience |
| `live` | Require a live backend attempt | Yes | Optional deep rerun |
| `xmlrpc` | Use the PLECS XML-RPC bridge | Yes | Optional deep rerun |
| `mcp` | Use the reference-agent PLECS MCP bridge | Yes | Optional deep rerun |

Every result records `backend_requested`, `backend_used`, `fallback_used`, and `fallback_reason` in `runtime_stats` or `simulation_metrics`, so a run cannot silently pretend to have used PLECS when it fell back.

## Default No-PLECS Reviewer Path

```bash
python scripts/reviewer_smoke_test.py
python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1
python scripts/build_dataset_artifacts.py --check
python scripts/validate_public_artifact.py
```

Reference feasibility without live simulation:

```bash
python scripts/run_pebench_suite.py \
  --track all \
  --baseline reference_design \
  --model reference-design \
  --seed 0 \
  --simulator-mode stub \
  --output-root results/pebench_reference_smoke
```

## Local PLECS XML-RPC Setup

Start PLECS locally and enable its XML-RPC server. The default PE-Bench probe expects:

```bash
export PEBENCH_PLECS_XMLRPC_HOST=127.0.0.1
export PEBENCH_PLECS_XMLRPC_PORT=1080
```

If your local PLECS bridge listens on a different port, set `PEBENCH_PLECS_XMLRPC_PORT` to that value before running PE-Bench. The legacy aliases `PLECS_XMLRPC_HOST` and `PLECS_XMLRPC_PORT` are also accepted.

Check readiness:

```bash
python scripts/doctor_plecs_backend.py
python scripts/doctor_plecs_backend.py --json
```

Require readiness in a local run script:

```bash
python scripts/doctor_plecs_backend.py --fail-if-unavailable
```

## Live Flyback Rerun Example

```bash
export PEBENCH_ENABLE_LIVE_SIM=1
export PEBENCH_PLECS_XMLRPC_HOST=127.0.0.1
export PEBENCH_PLECS_XMLRPC_PORT=1080

python scripts/run_pebench_suite.py \
  --track flyback \
  --baseline reference_agent \
  --model gpt-4.1-mini \
  --seed 1 \
  --simulator-mode xmlrpc \
  --task-limit 30 \
  --output-root results/live_plecs_flyback
```

For full API reruns, combine the usual API environment variables with the simulator mode:

```bash
export PEBENCH_LLM_API_KEY=<your_openai_compatible_key>
export PEBENCH_LLM_BASE_URL=<openai_compatible_base_url>
export PEBENCH_ENABLE_LIVE_SIM=1
export PEBENCH_PLECS_XMLRPC_PORT=1080

python scripts/run_final78_experiments.py \
  --profile main_plus_ablations \
  --model gpt-4.1-mini \
  --seeds 1 2 3 \
  --simulator-mode xmlrpc \
  --run-root results/final78_live_plecs_runs/<run_name>
```

## Troubleshooting

- If `doctor_plecs_backend.py` reports `port_open=false`, confirm PLECS is running and the XML-RPC server is enabled on the same host/port.
- If `module_available=false`, the anonymous artifact does not contain your private reference-agent PLECS bridge. Use `stub` for public validation, or install the bridge locally before live reruns.
- If `auto` falls back to `stub`, inspect each result's `fallback_reason`; fallback is recorded as part of the run evidence.
- Do not commit PLECS-generated local workspaces, raw logs, API keys, or machine-specific paths. Promote completed runs with `scripts/promote_api_run_evidence.py`, which sanitizes reviewer-facing evidence.

## Artifact Claim

The submitted artifact claims reproducible task/evaluator/table validation without PLECS. PLECS-backed reruns are optional execution evidence for labs with the same proprietary simulator setup. This separation is intentional: it makes the public artifact runnable by reviewers while still documenting how live-simulation runs were configured.
