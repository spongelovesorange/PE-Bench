# Benchmark Card: PE-Bench v1

## Summary

PE-Bench evaluates whether AI-assisted power-electronics design outputs are auditable and internally consistent. A candidate passes only when requirements, topology, equations, component choices, derating margins, simulator or formula-backed metrics, reported claims, and review/escalation behavior agree.

## Task Coverage

- 78 tasks across five families: Buck, Boost, Buck-Boost, Flyback, and Three-phase inverter.
- Difficulty tiers: easy, medium, hard, boundary, stress.
- Splits: 60 public development tasks, 6 private holdout tasks, and 12 extension tasks.

## Intended Use

- Benchmarking and debugging AI systems that generate PE design artifacts.
- Studying failure modes in engineering-agent design closure.
- Reproducing evaluator-contract checks without requiring LLM or live-simulator access.

## Not Intended For

- Hardware certification or regulatory approval.
- Production sign-off or automated procurement.
- Replacement of qualified PE engineer review.

## Release Metadata

Run `python scripts/build_release_artifacts.py --check` to regenerate task inventory, schemas, cards, and checksums under `artifacts/`.
