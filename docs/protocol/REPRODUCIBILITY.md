# Reproducibility

## Minimal Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Required No-API Checks

```bash
python scripts/reviewer_smoke_test.py
python scripts/build_release_artifacts.py --check
pytest
```

## Task Validators

```bash
python scripts/validate_tasks.py
python scripts/validate_topology_full_tasks.py
python scripts/validate_reference_designs.py
```

## Simulator Modes

- `stub`: deterministic, CI-safe evaluator path.
- `auto`: try live backend and log fallback.
- `live`, `mcp`, `xmlrpc`: backend-specific live execution modes.

Every run must record `backend_requested`, `backend_used`, `fallback_used`, and `fallback_reason` where applicable.

PLECS is optional and not required for the public artifact checks. For local live-simulation reruns, see `docs/protocol/PLECS_BACKEND.md` and run:

```bash
python scripts/doctor_plecs_backend.py
```

## Reference Feasibility Suite

```bash
python scripts/run_pebench_suite.py \
  --track all \
  --baseline reference_design \
  --model reference-design \
  --seed 0 \
  --simulator-mode stub \
  --output-root results/pebench_reference_smoke
```

This is a reproducibility smoke path, not a model-performance result.
