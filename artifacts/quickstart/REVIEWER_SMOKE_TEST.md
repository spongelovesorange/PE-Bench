# Reviewer Smoke Test

This smoke test validates the task bank, evaluator contracts, package imports, and release manifest without running expensive LLM or live simulator experiments.

```bash
python scripts/reviewer_smoke_test.py
```

Expected checks:

- 30 Flyback tasks parse.
- 36 Buck/Boost/Buck-Boost Topology Full tasks parse.
- 12 Three-phase inverter tasks parse.
- Release artifacts build and validate.
- Dataset exports and Croissant metadata build and validate.
- Reproduced Markdown paper tables build and validate.
- Public artifact anonymization and secret-leak checks pass.
- Reference feasibility candidates evaluate on every released task.
- Frozen manuscript summary records reproduce the paper-facing tables without API access.
