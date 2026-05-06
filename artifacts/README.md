# PE-Bench Artifacts

This directory contains reviewer-facing files generated from the source task banks and evaluator contracts.

Regenerate everything with:

```bash
python scripts/build_release_artifacts.py --check
python scripts/build_dataset_artifacts.py --check
python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check
python scripts/validate_public_artifact.py
```

Generated artifact groups:

- `release/`: manifest, task inventory, and checksums.
- `schema/`: candidate and evaluator-result JSON schemas.
- `cards/`: benchmark and evaluator cards.
- `quickstart/`: no-API reviewer smoke-test instructions.
- `dataset/`: normalized 78-task JSONL/CSV exports and dataset summary.
- `evidence/`: frozen manuscript records, evidence matrix, reproducibility claims, and sanitized API rerun summaries.
- `reproduced_tables/`: Markdown tables generated from frozen manuscript records.

The source of truth remains `pebench/`, `assets/`, `docs/`, and `scripts/`.
