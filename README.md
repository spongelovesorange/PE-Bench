# PE-Bench

PE-Bench is a reviewer-facing benchmark and evaluator artifact for AI-assisted power-electronics design. It checks whether generated design packages are consistent across requirements, converter topology, equations, component ratings, derating margins, simulation or formula-backed metrics, reported claims, and human-review decisions.

This repository is now code-first. Paper sources are maintained externally in Overleaf and are intentionally not part of the repo.

## What Is Included

- `pebench/`: primary Python package.
- `flybackbench/`: legacy import shim for old notebooks and scripts.
- `pebench/tasks/flyback/`: 30 Flyback tasks.
- `pebench/tasks/topology_full/`: 36 Buck/Boost/Buck-Boost tasks.
- `pebench/tasks/inverter/`: 12 Three-phase inverter tasks.
- `pebench/evaluator/`: family-aware evaluators and shared result contract.
- `pebench/baselines/`: baseline adapters plus `reference_design` feasibility anchors.
- `assets/catalogs/`: bounded component catalogs used by deterministic checks.
- `artifacts/`: generated release manifest, task inventory, schemas, cards, and reviewer quickstart.
- `artifacts/dataset/`: normalized 78-task dataset exports.
- `artifacts/evidence/`: frozen manuscript records, evidence matrix, and sanitized rerun summaries.
- `croissant_metadata.json`: Croissant dataset metadata with Responsible AI fields for E&D review.
- `docs/`: protocol cards, scope, non-use statement, and reproducibility notes.
- `docs/CLEANROOM_VERIFICATION.md`: recorded clean-room anonymous zip verification.

External PE system roots, when present in a local workspace, are treated as optional baseline assets and are excluded from the anonymous reviewer artifact.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/reviewer_smoke_test.py
```

The smoke test validates all released task banks, builds the release artifacts, validates checksums and metadata, and evaluates reference candidates for every released task in stub mode.
It also rebuilds dataset/Croissant artifacts and reviewer-readable paper tables without API access.

## Clean Anonymous Artifact Verification

These commands verify the anonymous artifact from a fresh directory without API keys, PLECS, author-local paths, or paper sources:

```bash
rm -rf /tmp/pebench_clean_verify
mkdir -p /tmp/pebench_clean_verify
cd /tmp/pebench_clean_verify
unzip /path/to/pebench_anonymous_artifact.zip
cd pebench_anonymous_artifact

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/validate_public_artifact.py
python scripts/validate_croissant_metadata.py
python scripts/validate_tasks.py
python scripts/validate_topology_full_tasks.py
python scripts/validate_inverter_tasks.py
python scripts/validate_reference_designs.py
python scripts/run_pebench_suite.py \
  --track all \
  --baseline reference_design \
  --model reference-design \
  --seed 0 \
  --simulator-mode stub \
  --output-root results/clean_reference_smoke
python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1
```

The last command checks the frozen records used for the paper-facing main leaderboard and supporting tables. Reviewer-readable outputs are in `artifacts/reproduced_tables/`.

## Build Reviewer Artifacts

```bash
python scripts/build_release_artifacts.py --check
python scripts/build_dataset_artifacts.py --check
python scripts/validate_croissant_metadata.py
python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check
python scripts/validate_public_artifact.py --check-git-history
```

Generated files:

- `artifacts/release/pebench_v1_manifest.json`
- `artifacts/release/task_inventory.csv`
- `artifacts/release/task_inventory.md`
- `artifacts/release/checksums.sha256`
- `artifacts/schema/candidate.schema.json`
- `artifacts/schema/result.schema.json`
- `artifacts/cards/benchmark_card.md`
- `artifacts/cards/evaluator_card.md`
- `artifacts/quickstart/REVIEWER_SMOKE_TEST.md`
- `artifacts/dataset/task_records.jsonl`
- `artifacts/dataset/task_records.csv`
- `artifacts/dataset/dataset_summary.json`
- `croissant_metadata.json`
- `docs/DATASET_CARD.md`
- `docs/RESPONSIBLE_AI_METADATA.md`
- `artifacts/reproduced_tables/*.md`

## Reproduce Paper Tables Without API

```bash
python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1
```

This verifies the frozen manuscript summary records against the paper-facing task accounting, leaderboard, validation, ablation, held-out, and robustness numbers.

Reviewer-readable generated tables are written under `artifacts/reproduced_tables/`. The evidence-to-claim map is in `artifacts/evidence/EVIDENCE_MATRIX.md`.

## Evidence Levels

- `artifacts/evidence/frozen_v1`: frozen manuscript summary records used to reproduce the paper-facing tables.
- `artifacts/evidence/evidence_run_index.csv`: machine-readable index of all included evidence bundles.
- `artifacts/evidence/paper_main_raw_paper_main_vapi_gpt41mini_sleep_20260507`: complete 78-task `gpt-4.1-mini` main-profile API rerun summary.
- `artifacts/evidence/paper_main_raw_paper_main_vapi_gpt4o_sleep_20260507`: complete 78-task `gpt-4o` main-profile API rerun summary.
- `artifacts/evidence/paper_main_raw_paper_main_vapi_o3mini_sleep_20260507`: complete 78-task `o3-mini` main-profile API rerun summary.
- `artifacts/evidence/api_rerun_gpt4omini_20260506`: complete `gpt-4o-mini` API rerun summary used as secondary pipeline evidence.

The artifact separates summary manuscript evidence from actual rerun summaries so reviewers can audit what each file is allowed to support. Current API reruns completed without failed jobs and include sanitized task-level JSONL summaries, but their paper-alignment gates did not pass, so they remain independent rerun evidence and do not replace `frozen_v1`.

## Run and Freeze Full API Evidence

The default reviewer path does not require PLECS. Live PLECS execution is optional and documented in `docs/protocol/PLECS_BACKEND.md`; use `scripts/doctor_plecs_backend.py` to check local port/backend readiness before live reruns.

```bash
export PEBENCH_LLM_API_KEY=<your_openai_compatible_key>
export PEBENCH_LLM_BASE_URL=https://api.openai.com/v1

python scripts/run_paper_main_raw_evidence.py \
  --model gpt-4.1-mini \
  --profile main_plus_ablations \
  --background
```

To let a helper process launch without exposing secrets in shell history, put the variables in a local file outside the repo and pass only the path:

```bash
python scripts/run_paper_main_raw_evidence.py \
  --env-file /tmp/pebench_api.env \
  --model gpt-4.1-mini \
  --profile main_plus_ablations \
  --background
```

This is the preferred long-run path for paper-main raw evidence. It runs the final 78-task suite, freezes the completed run, promotes sanitized task-level JSONL evidence into `artifacts/evidence/paper_main_raw_<run_name>`, and compares the raw leaderboard against `artifacts/evidence/frozen_v1`.

The promotion step has a guardrail: a completed rerun is marked as `paper_main_raw_api_evidence` only if its leaderboard aligns with the frozen manuscript records within tolerance. Otherwise it is kept as `independent_api_rerun_summary`, with the decision recorded in `promotion_decision.json`, so rerun drift cannot silently replace the paper-facing numbers.

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
  --run-root results/final78_api_runs/<run_name> \
  --used-for-main-paper-tables
```

The runner records raw candidate JSON, task-result JSON, per-job logs, queue state, and checksums without writing API credentials. The freeze step converts those raw records into auditable CSV/JSON evidence that can supplement `artifacts/evidence/frozen_v1`; it replaces paper-main evidence only when the promotion gate passes.

## Export Anonymous Submission Zip

```bash
python scripts/export_anonymous_artifact.py --check
```

The zip excludes local runtime state, external baseline roots, raw sources, historical results, and any paper source files. It is the safer file to upload for double-blind review.

## Validate Task Banks

```bash
python scripts/validate_tasks.py
python scripts/validate_topology_full_tasks.py
python scripts/validate_inverter_tasks.py
python scripts/validate_reference_designs.py
```

## Run a Small Candidate Check

```bash
python scripts/run_baseline.py \
  --baseline direct_prompting \
  --model heuristic-v0 \
  --task pebench/tasks/flyback/easy_acdc_5v1a.yaml \
  --simulator-mode stub \
  --output results/examples/direct_prompting_candidate.json

python scripts/run_evaluator.py \
  --task pebench/tasks/flyback/easy_acdc_5v1a.yaml \
  --candidate results/examples/direct_prompting_candidate.json \
  --simulator-mode stub \
  --output results/examples/direct_prompting_eval.json
```

Emit 78-task reference feasibility records without LLM or live simulator dependencies:

```bash
python scripts/run_pebench_suite.py \
  --track all \
  --baseline reference_design \
  --model reference-design \
  --seed 0 \
  --simulator-mode stub \
  --output-root results/pebench_reference_smoke
```

Optional local PLECS readiness check:

```bash
python scripts/doctor_plecs_backend.py
```

## Scope

Current task accounting is fixed at 78 released tasks across five families: Buck, Boost, Buck-Boost, Flyback, and Three-phase inverter. The artifact includes a no-API smoke path plus frozen manuscript summary records for paper-table reproduction; full API reruns can replace those summaries without changing the task contract.

PE-Bench is not a hardware certification tool, production sign-off workflow, automated procurement system, or replacement for qualified engineering review.
