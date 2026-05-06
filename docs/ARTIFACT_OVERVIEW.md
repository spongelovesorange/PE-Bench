# Artifact Overview

PE-Bench v1 is a 78-task benchmark and evaluator artifact for AI-assisted power-electronics design.

The code artifact is organized around five reviewer questions:

1. Do the task cards exist and parse across the released converter families?
2. Does the evaluator expose a stable, machine-readable result contract?
3. Can a reviewer run no-API checks without live simulator or LLM credentials?
4. Are intended use, non-use, task inventory, schemas, and checksums explicit?
5. Can the paper-facing tables be reproduced from frozen manuscript summary records without API access?
6. Are dataset metadata, Croissant/RAI fields, and evidence levels explicit for E&D review?

The answer to each is encoded in `scripts/reviewer_smoke_test.py` and the generated `artifacts/` directory.

## Task Accounting

- Buck: 12 tasks
- Boost: 12 tasks
- Buck-Boost: 12 tasks
- Flyback: 30 tasks
- Three-phase inverter: 12 tasks

## Generated Artifact Entry Points

- `artifacts/release/pebench_v1_manifest.json`
- `artifacts/release/task_inventory.md`
- `artifacts/schema/candidate.schema.json`
- `artifacts/schema/result.schema.json`
- `artifacts/cards/benchmark_card.md`
- `artifacts/cards/evaluator_card.md`
- `artifacts/quickstart/REVIEWER_SMOKE_TEST.md`
- `artifacts/evidence/frozen_v1/manifest.json`
- `artifacts/evidence/EVIDENCE_MATRIX.md`
- `artifacts/evidence/REPRODUCIBILITY_CLAIMS.md`
- `artifacts/evidence/api_rerun_gpt4omini_20260506/manifest.json`
- `artifacts/dataset/dataset_summary.json`
- `artifacts/reproduced_tables/manifest.json`
- `croissant_metadata.json`
- `docs/DATASET_CARD.md`
- `docs/NEURIPS_ED_CHECKLIST.md`

## Evidence Levels

- Frozen manuscript records in `artifacts/evidence/frozen_v1` reproduce the paper-facing numbers without API access.
- The sanitized `gpt-4o-mini` rerun in `artifacts/evidence/api_rerun_gpt4omini_20260506` demonstrates that the long-run API pipeline completed a 78-task experiment. It is secondary evidence and is not used as the manuscript leaderboard source.
