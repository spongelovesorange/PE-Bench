# Evidence Directory

This directory separates manuscript-table evidence from independent rerun evidence.

## Primary Paper Evidence

`frozen_v1/` contains the frozen manuscript summary records used by:

```bash
python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1
```

These records support the paper-facing tables without API credentials. They are summary-level manuscript records, not raw provider logs.

## Independent API Rerun Evidence

`paper_main_raw_*` directories contain sanitized evidence promoted from completed OpenAI-compatible API reruns. The strongest included reruns are:

| Evidence directory | Model | Profile | Jobs | Task records | Failed jobs | Used for paper main tables |
| --- | --- | --- | --- | --- | --- | --- |
| `paper_main_raw_paper_main_vapi_gpt41mini_sleep_20260507` | `gpt-4.1-mini` | main | 24/24 | 1872 | 0 | No |
| `paper_main_raw_paper_main_vapi_gpt4o_sleep_20260507` | `gpt-4o` | main | 24/24 | 1872 | 0 | No |
| `paper_main_raw_paper_main_vapi_o3mini_sleep_20260507` | `o3-mini` | main | 24/24 | 1872 | 0 | No |
| `paper_main_raw_backbone_vapi_gpt41_sleep_20260507` | `gpt-4.1` | backbone | 6/6 | 468 | 0 | No |
| `paper_main_raw_backbone_vapi_o4mini_sleep_20260507` | `o4-mini` | backbone | 6/6 | 468 | 0 | No |

Each rerun directory includes `manifest.json`, `integrity_report.json`, `leaderboard_summary.csv`, `task_results.csv`, `raw_suite_records.jsonl`, `raw_task_records.jsonl`, `promotion_decision.json`, and `paper_alignment_report.json`.

The promotion gate intentionally keeps these reruns as independent evidence when stochastic/provider drift makes them diverge from `frozen_v1`. This prevents rerun drift from silently replacing the manuscript numbers.

## Index Files

- `evidence_run_index.csv`
- `evidence_run_index.json`

These files summarize every evidence bundle in this directory, including completeness, model, profile, raw-record availability, promotion status, and alignment result.
