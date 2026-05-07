# Reproducibility Claims

## What Reviewers Can Reproduce Without API Access

- Parse and validate all 78 released task cards.
- Build release manifests, schemas, cards, task inventory, dataset exports, and Croissant metadata.
- Evaluate all feasible reference candidates in stub simulator mode.
- Verify frozen paper-facing task accounting, leaderboard, validation, ablation, split, topology, retry, and inverter-extension tables.
- Regenerate reviewer-readable Markdown tables under `artifacts/reproduced_tables`.

Commands:

```bash
python scripts/reviewer_smoke_test.py
python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1
python scripts/build_dataset_artifacts.py --check
python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check
```

## What Requires API Access

Full LLM-agent reruns require an OpenAI-compatible endpoint and a user-provided API key:

```bash
export PEBENCH_LLM_API_KEY=<your_openai_compatible_key>
export PEBENCH_LLM_BASE_URL=<openai_compatible_base_url>

python scripts/run_paper_main_raw_evidence.py \
  --model gpt-4.1-mini \
  --profile main_plus_ablations \
  --background
```

For secret hygiene, the same command can read API settings from a local file outside the repository:

```bash
python scripts/run_paper_main_raw_evidence.py \
  --env-file /tmp/pebench_api.env \
  --model gpt-4.1-mini \
  --profile main_plus_ablations \
  --background
```

This long-run orchestration writes resumable records under `results/paper_main_raw_runs/`, freezes the completed run, promotes sanitized raw JSONL evidence under `artifacts/evidence/paper_main_raw_<run_name>`, and writes a paper-alignment comparison report.

Main-table raw-evidence promotion is gated. If a rerun is requested as paper-main evidence, `scripts/promote_api_run_evidence.py` compares the promoted leaderboard against `artifacts/evidence/frozen_v1/leaderboard_summary.csv` before marking it as `paper_main_raw_api_evidence`. If the rerun differs beyond the configured tolerance or is missing manuscript baselines, it remains `independent_api_rerun_summary` and records the reason in `promotion_decision.json`. This prevents stochastic model/provider drift from silently replacing the frozen manuscript records.

The lower-level runner remains available:

```bash
python scripts/run_final78_experiments.py \
  --profile main_plus_ablations \
  --model <model_name> \
  --base-url "$PEBENCH_LLM_BASE_URL" \
  --seeds 1 2 3 \
  --simulator-mode stub \
  --run-root results/final78_api_runs/<run_name>
```

The runner writes raw records under `results/`, which is intentionally excluded from the anonymous source artifact. A completed run can be frozen into reviewer-facing summaries with:

```bash
python scripts/freeze_api_run_records.py --run-root results/final78_api_runs/<run_name>
python scripts/promote_api_run_evidence.py --run-root results/final78_api_runs/<run_name>
```

## Current Included Reruns

`artifacts/evidence/evidence_run_index.csv` and `artifacts/evidence/evidence_run_index.json` are the reviewer-facing index for all included evidence bundles.

The included complete API reruns are:

| Evidence directory | Model | Profile | Jobs | Task-level records | Failed jobs | Paper-main source |
| --- | --- | --- | --- | --- | --- | --- |
| `artifacts/evidence/paper_main_raw_paper_main_vapi_gpt41mini_sleep_20260507` | `gpt-4.1-mini` | main | 24/24 | 1872 | 0 | No |
| `artifacts/evidence/paper_main_raw_paper_main_vapi_gpt4o_sleep_20260507` | `gpt-4o` | main | 24/24 | 1872 | 0 | No |
| `artifacts/evidence/paper_main_raw_paper_main_vapi_o3mini_sleep_20260507` | `o3-mini` | main | 24/24 | 1872 | 0 | No |
| `artifacts/evidence/paper_main_raw_backbone_vapi_gpt41_sleep_20260507` | `gpt-4.1` | backbone | 6/6 | 468 | 0 | No |
| `artifacts/evidence/paper_main_raw_backbone_vapi_o4mini_sleep_20260507` | `o4-mini` | backbone | 6/6 | 468 | 0 | No |
| `artifacts/evidence/api_rerun_gpt4omini_20260506` | `gpt-4o-mini` | main plus ablations | 33/33 | 2574 | 0 | No |

These runs validate the long-run experiment pipeline and provide task-level audit records, but they are not the source for the manuscript leaderboard. Their promotion gates record model/provider drift relative to `artifacts/evidence/frozen_v1`; therefore they remain `independent_api_rerun_summary` evidence. Reviewers should read each directory's `manifest.json`, `promotion_decision.json`, and `paper_alignment_report.json` before using a rerun for any paper-facing claim.

## Explicit Limitations

- `artifacts/evidence/frozen_v1` is summary-level manuscript evidence, not raw API logs.
- No API keys, local filesystem paths, or raw provider logs are included.
- Model-provider outputs can vary over time; exact rerun equality is not claimed unless the same model snapshot, provider behavior, prompts, seeds, and simulator/evaluator versions are frozen.
- PE-Bench is an evaluation benchmark, not a hardware-certification or production sign-off workflow.
