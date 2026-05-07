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
| The long-run API pipeline can execute the 78-task suite end to end. | `artifacts/evidence/evidence_run_index.csv`, `artifacts/evidence/paper_main_raw_paper_main_vapi_gpt41mini_sleep_20260507/`, `artifacts/evidence/paper_main_raw_paper_main_vapi_gpt4o_sleep_20260507/`, `artifacts/evidence/paper_main_raw_paper_main_vapi_o3mini_sleep_20260507/` | `python scripts/freeze_api_run_records.py --run-root results/paper_main_raw_runs/<run_name>` | Yes, for new reruns | Three complete 78-task, 3-seed main-profile rerun summaries; all have `failed_jobs=0` and raw task JSONL summaries |
| Paper-main raw API evidence is not accepted blindly. | `artifacts/evidence/paper_main_raw_*/promotion_decision.json`, `artifacts/evidence/paper_main_raw_*/paper_alignment_report.json`, `scripts/promote_api_run_evidence.py` | `python scripts/promote_api_run_evidence.py --run-root results/paper_main_raw_runs/<run_name> --used-for-main-paper-tables` | No for checking completed records; Yes for generating new records | Automatic gate keeps mismatched reruns as independent audit evidence |
| PLECS-backed live simulation is optional and machine-specific. | `docs/protocol/PLECS_BACKEND.md`, `scripts/doctor_plecs_backend.py`, `pebench/evaluator/simulator.py` | `python scripts/doctor_plecs_backend.py` | No for public checks; Yes for live PLECS reruns | Public artifact remains runnable without PLECS; live backend readiness is explicit |

## Evidence Levels

- `frozen_manuscript_summary_records`: summary CSV/JSON records reconstructed from the manuscript, TeX source, and experiment notes. These are the source of paper-table reproduction.
- `independent_api_rerun_summary`: sanitized summaries and raw JSONL records from completed OpenAI-compatible API reruns. These validate the executable pipeline and are not used as paper-main leaderboard sources unless the promotion gate passes.
- `frozen_actual_api_run_records`: legacy name used by the earlier complete `gpt-4o-mini` rerun; it has the same reviewer role as independent rerun evidence.

The artifact deliberately separates these evidence levels so reviewers can check the paper numbers without credentials and independently inspect end-to-end API rerun summaries without confusing them for the manuscript leaderboard source. Completed reruns are promoted to main-table raw evidence only when the alignment gate passes; otherwise they remain independent rerun evidence.

## Current Rerun Evidence

`artifacts/evidence/evidence_run_index.csv` and `artifacts/evidence/evidence_run_index.json` enumerate every included evidence bundle, including completeness, model, profile, job count, task-result count, promotion status, and alignment decision.

The strongest included rerun evidence consists of three completed 78-task main-profile reruns:

- `artifacts/evidence/paper_main_raw_paper_main_vapi_gpt41mini_sleep_20260507`
- `artifacts/evidence/paper_main_raw_paper_main_vapi_gpt4o_sleep_20260507`
- `artifacts/evidence/paper_main_raw_paper_main_vapi_o3mini_sleep_20260507`

Each completed with 24/24 jobs, 1872 task-level records, and zero failed jobs. Their alignment reports intentionally keep them as independent rerun evidence because their leaderboard summaries differ from the frozen manuscript records beyond the configured tolerance. This is the intended guardrail against stochastic/provider drift.
