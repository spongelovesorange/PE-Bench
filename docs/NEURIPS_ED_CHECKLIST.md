# NeurIPS E&D Alignment Checklist

This checklist maps the anonymous PE-Bench artifact to the NeurIPS 2026 Evaluations and Datasets track expectations.

| Requirement area | Artifact support |
| --- | --- |
| Double-blind review | Repository text uses anonymous author language; paper sources, personal local paths, private keys, and non-anonymous commit metadata are excluded from the public `main` branch. |
| Executable code | `scripts/reviewer_smoke_test.py` validates all task banks, reference candidates, release artifacts, dataset artifacts, paper-table artifacts, and public-anonymization checks without API access. |
| Clean-room verification | `docs/CLEANROOM_VERIFICATION.md` records validation from the exported anonymous zip in a fresh virtual environment. |
| Code availability | The anonymous GitHub artifact is code-first and runnable from `requirements.txt`. |
| Dataset/code documentation | `README.md`, `docs/ARTIFACT_OVERVIEW.md`, `docs/DATASET_CARD.md`, `artifacts/cards/benchmark_card.md`, and `artifacts/cards/evaluator_card.md`. |
| Croissant metadata | `croissant_metadata.json` includes Croissant core fields, file distributions, record sets, field source mappings, checksums, and `conformsTo`. Validate with `python scripts/validate_croissant_metadata.py`. |
| Responsible AI metadata | `croissant_metadata.json` includes minimal RAI fields; `docs/RESPONSIBLE_AI_METADATA.md` provides the human-readable RAI summary. |
| Responsible use and non-use | `docs/DATASET_CARD.md`, `docs/RESPONSIBLE_AI_METADATA.md`, `artifacts/evidence/REPRODUCIBILITY_CLAIMS.md`, and evaluator/benchmark cards. |
| Paper-table reproducibility | `artifacts/evidence/frozen_v1`, `scripts/reproduce_paper_tables.py`, and `scripts/build_paper_tables.py`. |
| Full-run auditability | `scripts/run_paper_main_raw_evidence.py`, `scripts/run_final78_experiments.py`, `scripts/freeze_api_run_records.py`, `scripts/promote_api_run_evidence.py`, `scripts/compare_api_evidence_to_paper.py`, and the sanitized complete rerun summary under `artifacts/evidence/api_rerun_gpt4omini_20260506`. |

The current anonymous artifact is hosted on GitHub for review. For a deanonymized or camera-ready release, a dedicated dataset-hosting mirror such as Hugging Face, OpenML, Dataverse, or Kaggle should be added while preserving the same Croissant metadata and checksums.
