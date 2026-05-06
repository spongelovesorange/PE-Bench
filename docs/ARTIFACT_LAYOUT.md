# Artifact Layout

PE-Bench separates source code, task banks, generated release metadata, and optional experiment records.

## Source of Truth

- `pebench/tasks/flyback/`: 30 Flyback tasks.
- `pebench/tasks/topology_full/`: 36 Buck/Boost/Buck-Boost tasks.
- `pebench/evaluator/`: family-aware evaluator implementations.
- `pebench/baselines/`: model/baseline adapters and reference feasibility anchors.
- `assets/catalogs/`: bounded component catalogs.
- `docs/protocol/`: benchmark and evaluator contracts.

## Generated Reviewer Artifacts

- `artifacts/release/pebench_v1_manifest.json`
- `artifacts/release/task_inventory.csv`
- `artifacts/release/task_inventory.md`
- `artifacts/release/checksums.sha256`
- `artifacts/schema/candidate.schema.json`
- `artifacts/schema/result.schema.json`
- `artifacts/cards/benchmark_card.md`
- `artifacts/cards/evaluator_card.md`
- `artifacts/quickstart/REVIEWER_SMOKE_TEST.md`

Regenerate them with:

```bash
python scripts/build_release_artifacts.py --check
```

The repository intentionally does not contain paper source files.
