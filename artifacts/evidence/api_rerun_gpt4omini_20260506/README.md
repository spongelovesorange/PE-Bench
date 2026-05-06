# Independent API Rerun Summary

This directory contains a sanitized summary of one complete OpenAI-compatible API rerun of the PE-Bench 78-task suite using `gpt-4o-mini`.

It is included as secondary pipeline evidence:

- `integrity_report.json` reports `33/33` completed jobs and `2574` task-result records.
- `task_results.csv` provides task-level frozen result records.
- `leaderboard_summary.csv`, `track_summary.csv`, and `ablation_summary.csv` summarize the rerun.
- Raw API request/response logs are not included in this anonymous artifact.
- No API credentials, local run roots, or local machine paths are included.

These results are not used as the manuscript leaderboard source because the model/provider setting differs from the frozen manuscript records in `artifacts/evidence/frozen_v1`.
