# Reviewer Quickstart

## Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## No-API Smoke Test

```bash
python scripts/reviewer_smoke_test.py
```

This validates all 78 released task cards, builds the release manifest/schemas/cards, checks task-file checksums, and evaluates reference feasibility candidates for every released task in stub mode.
It also rebuilds dataset/Croissant artifacts and generated Markdown paper tables.

## Individual Validators

```bash
python scripts/validate_tasks.py
python scripts/validate_topology_full_tasks.py
python scripts/validate_inverter_tasks.py
python scripts/validate_reference_designs.py
python scripts/build_release_artifacts.py --check
python scripts/build_dataset_artifacts.py --check
python scripts/validate_croissant_metadata.py
python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check
python scripts/validate_public_artifact.py
```

For the linked GitHub repository, additionally run:

```bash
python scripts/validate_public_artifact.py --check-git-history
```

## No-API Paper Table Reproduction

```bash
python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1
```

This checks the frozen manuscript summary records against the paper-facing task accounting, leaderboard, validation, ablation, held-out, and robustness numbers. It does not call any API.

The generated Markdown tables are in `artifacts/reproduced_tables/`, and the evidence-to-claim map is in `artifacts/evidence/EVIDENCE_MATRIX.md`.

## Optional Full API Rerun

PLECS is not required for the commands above. If you have a local PLECS installation and want live-simulation reruns, first follow `docs/protocol/PLECS_BACKEND.md` and check readiness with:

```bash
python scripts/doctor_plecs_backend.py
```

```bash
export PEBENCH_LLM_API_KEY=<your_openai_compatible_key>
export PEBENCH_LLM_BASE_URL=https://api.openai.com/v1

python scripts/run_paper_main_raw_evidence.py \
  --model gpt-4.1-mini \
  --profile main_plus_ablations \
  --background
```

For local secret hygiene, pass an env file outside the repository instead of exporting a key in the current shell:

```bash
python scripts/run_paper_main_raw_evidence.py \
  --env-file /tmp/pebench_api.env \
  --model gpt-4.1-mini \
  --profile main_plus_ablations \
  --background
```

The paper-main wrapper launches a resumable long run, freezes the completed records, promotes sanitized JSONL evidence, and writes a comparison report against the frozen manuscript table records. If the rerun does not align with the frozen manuscript leaderboard within tolerance, it is retained as independent rerun evidence instead of being marked as paper-main raw evidence.

Lower-level runner:

```bash
python scripts/run_final78_experiments.py \
  --profile main_plus_ablations \
  --model gpt-4.1-mini \
  --base-url "$PEBENCH_LLM_BASE_URL" \
  --seeds 1 2 3 \
  --simulator-mode stub \
  --run-root results/final78_api_runs/<run_name>

python scripts/freeze_api_run_records.py \
  --run-root results/final78_api_runs/<run_name>

python scripts/promote_api_run_evidence.py \
  --run-root results/final78_api_runs/<run_name>
```

The API rerun writes raw candidate JSON, task-result JSON, per-job logs, queue state, and checksums under the run directory. The freeze step creates reviewer-facing CSV/JSON summaries without storing API credentials. For promoted reruns, `manifest.json`, `promotion_decision.json`, and `paper_alignment_report.json` state whether the run supports the manuscript main tables or only audits the execution pipeline.

The included `artifacts/evidence/api_rerun_gpt4omini_20260506` directory is a sanitized complete rerun summary used only as secondary pipeline evidence.

## Optional Reference Suite

```bash
python scripts/run_pebench_suite.py \
  --track all \
  --baseline reference_design \
  --model reference-design \
  --seed 0 \
  --simulator-mode stub \
  --output-root results/pebench_reference_smoke
```

This is a feasibility check, not a leaderboard experiment.
