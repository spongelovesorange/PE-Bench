# Leaderboard Policy

The code scaffold supports PE-Bench suite execution and includes frozen manuscript summary records for paper-table reproduction. Full raw API reruns can replace the summary bundle when available.

## Valid Leaderboard Run

A run is leaderboard-valid only if:

- the task inventory matches the frozen 78-task manifest,
- all evaluator outputs validate against the result contract,
- seeds, model labels, simulator mode, fallback behavior, and run checksums are recorded,
- unsupported claims, unsafe components, and escalation behavior are reported through failure tags.

## Reporting Fields

Every leaderboard row should report:

- `baseline_name`
- `model_name`
- `seed`
- `num_tasks`
- `vtsr`
- `mean_score`
- `pass_at_k` when available
- unsupported-value rate
- invalid or unsafe component rate
- simulator-call count
- fallback rate

## Non-Leaderboard Runs

The following should not be mixed with final leaderboard claims:

- `reference_design` feasibility runs,
- stub-only smoke tests,
- prompt-tuning sweeps,
- partially wired baseline tracks,
- runs without frozen candidate/result records.
