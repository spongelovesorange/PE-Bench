# PE-Bench Evidence Matrix

This matrix maps paper-facing claims to the reviewer-visible artifact files that support them.

| Paper-facing claim | Primary evidence | Reproduction command | API required | Evidence status |
| --- | --- | --- | --- | --- |
| PE-Bench v1 contains 78 released tasks across Flyback, Buck, Boost, Buck-Boost, and Three-phase inverter families. | `artifacts/release/task_inventory.csv`, `artifacts/evidence/frozen_v1/task_accounting.csv`, `artifacts/dataset/task_records.jsonl` | `python scripts/reviewer_smoke_test.py` | No | Executable task cards plus frozen manuscript records |
| Main 78-task leaderboard and VTSR values match the manuscript. | `artifacts/evidence/frozen_v1/leaderboard_summary.csv` | `python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1` | No | Frozen manuscript summary records |
| Reported validator and evaluator-quality checks are fixed and auditable. | `artifacts/evidence/frozen_v1/validation_summary.csv`, `artifacts/schema/result.schema.json`, `artifacts/cards/evaluator_card.md` | `python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1` | No | Frozen manuscript summary records plus executable schemas |
| Simulation-only success overstates full PE-Bench success. | `artifacts/evidence/frozen_v1/simulation_check_gap.csv` | `python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check` | No | Frozen manuscript summary records |
| Ablations isolate the value of component checks, margin checks, reported-value audits, and human-review gates. | `artifacts/evidence/frozen_v1/ablation_summary.csv` | `python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check` | No | Frozen manuscript summary records |
| Results are robustly summarized across backbone classes and task slices. | `artifacts/evidence/frozen_v1/backbone_robustness.csv`, `artifacts/evidence/frozen_v1/topology_slice_summary.csv`, `artifacts/evidence/frozen_v1/heldout_summary.csv` | `python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check` | No | Frozen manuscript summary records |
| Retry-budget and inverter-extension claims are explicitly separated. | `artifacts/evidence/frozen_v1/retry_budget_summary.csv`, `artifacts/evidence/frozen_v1/inverter_extension_summary.csv` | `python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check` | No | Frozen manuscript summary records |
| The long-run API pipeline can execute the 78-task suite end to end. | `artifacts/evidence/api_rerun_gpt4omini_20260506/integrity_report.json`, `artifacts/evidence/api_rerun_gpt4omini_20260506/task_results.csv`, `artifacts/evidence/paper_main_raw_*/integrity_report.json` | `python scripts/freeze_api_run_records.py --run-root results/final78_api_runs/<run_name>` | Yes, for new reruns | Sanitized complete rerun summaries, not used for manuscript leaderboard unless promotion gate passes |
| Paper-main raw API evidence is not accepted blindly. | `artifacts/evidence/paper_main_raw_*/promotion_decision.json`, `artifacts/evidence/paper_main_raw_*/paper_alignment_report.json`, `scripts/promote_api_run_evidence.py` | `python scripts/promote_api_run_evidence.py --run-root results/paper_main_raw_runs/<run_name> --used-for-main-paper-tables` | No for checking completed records; Yes for generating new records | Automatic gate keeps mismatched reruns as independent audit evidence |
| PLECS-backed live simulation is optional and machine-specific. | `docs/protocol/PLECS_BACKEND.md`, `scripts/doctor_plecs_backend.py`, `pebench/evaluator/simulator.py` | `python scripts/doctor_plecs_backend.py` | No for public checks; Yes for live PLECS reruns | Public artifact remains runnable without PLECS; live backend readiness is explicit |

## Evidence Levels

- `frozen_manuscript_summary_records`: summary CSV/JSON records reconstructed from the manuscript, TeX source, and experiment notes. These are the source of paper-table reproduction.
- `frozen_actual_api_run_records`: summary records produced by a completed API run. The included `gpt-4o-mini` rerun is secondary pipeline evidence.

The artifact deliberately separates these evidence levels so reviewers can check the paper numbers without credentials and independently inspect end-to-end API rerun summaries without confusing them for the manuscript leaderboard source. Completed reruns are promoted to main-table raw evidence only when the alignment gate passes; otherwise they remain independent rerun evidence.
