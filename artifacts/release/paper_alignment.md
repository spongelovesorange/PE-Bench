# Paper Alignment Checklist

This file maps the main paper-facing artifact claims to concrete files and commands.

| Paper-facing claim | Artifact support | Status |
| --- | --- | --- |
| 78 executable tasks | `artifacts/release/task_inventory.csv`; topology counts `{'boost': 12, 'buck': 12, 'buck_boost': 12, 'flyback': 30, 'three_phase_inverter': 12}` | Supported |
| 12 Buck, 12 Boost, 12 Buck-Boost, 30 Flyback, 12 Three-phase inverter | `artifacts/release/pebench_v1_manifest.json` | Supported |
| Required-field checks 78/78 | `python scripts/reviewer_smoke_test.py`; `python scripts/validate_tasks.py`; `python scripts/validate_topology_full_tasks.py`; `python scripts/validate_inverter_tasks.py` | Supported |
| Feasible-reference checks 78/78 | `python scripts/validate_reference_designs.py` | Supported |
| Candidate/result schema is machine-readable | `artifacts/schema/candidate.schema.json`; `artifacts/schema/result.schema.json` | Supported |
| Dataset metadata is indexable | `croissant_metadata.json`; `docs/DATASET_CARD.md`; `artifacts/dataset/task_records.jsonl` | Supported |
| Anonymous release | `python scripts/export_anonymous_artifact.py --check` | Supported |
| Frozen final leaderboard and figure reproduction | `python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1`; `python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check` | Summary records included |
| Faulty-design, independent-valid-design, leakage, and held-out validation logs | `artifacts/evidence/frozen_v1/validation_summary.csv` | Summary records included; raw trace export should replace before camera-ready if available |
| Completed API rerun pipeline evidence | `artifacts/evidence/api_rerun_gpt4omini_20260506/integrity_report.json` | Secondary evidence included; not used for manuscript leaderboard |

The code artifact is sufficient for task/evaluator/release-contract inspection. The frozen evidence bundle is summary-level and intentionally anonymous; replace it with raw sanitized run records after a full rerun when time permits.
