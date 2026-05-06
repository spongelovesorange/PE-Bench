# Reproduced Paper Tables

This directory contains reviewer-readable Markdown tables generated from `artifacts/evidence/frozen_v1`.

Generation command:

```bash
python scripts/build_paper_tables.py --evidence artifacts/evidence/frozen_v1 --check
```

The source evidence kind is `frozen_manuscript_summary_records` and the source task total is `78`.

Generated tables:

- `ablation_summary.md`
- `backbone_robustness.md`
- `heldout_summary.md`
- `inverter_extension_summary.md`
- `leaderboard_summary.md`
- `retry_budget_summary.md`
- `simulation_check_gap.md`
- `task_accounting.md`
- `topology_slice_summary.md`
- `validation_summary.md`

For exact numeric assertions, run:

```bash
python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1
```
