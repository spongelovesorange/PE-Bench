# PE-Bench Dataset Card

## Summary

PE-Bench is a 78-task executable benchmark for evaluating AI-assisted power-electronics design systems. It contains task cards, bounded component catalogs, feasible reference designs, evaluator schemas, and frozen manuscript evidence records.

## Composition

- Flyback: 30 tasks
- Buck/Boost/Buck-Boost topology-full bank: 36 tasks
- Three-phase inverter: 12 tasks
- Total: 78 tasks

## Primary Use

PE-Bench measures whether submitted design candidates satisfy requirement interpretation, topology suitability, equation consistency, component feasibility, safety margins, reported-value support, and human-review decisions. The primary metric is verifiable task success rate (VTSR).

## Non-Use

PE-Bench is not a hardware certification tool, regulatory approval workflow, production sign-off process, automated procurement system, or substitute for qualified engineering review.

## Files

- `artifacts/dataset/task_records.jsonl`: normalized 78-task dataset records.
- `artifacts/dataset/task_records.csv`: tabular task metadata.
- `artifacts/release/task_inventory.csv`: release inventory used by the artifact manifest.
- `croissant_metadata.json`: Croissant metadata for dataset-indexing and ED-track review.
- `docs/RESPONSIBLE_AI_METADATA.md`: human-readable Responsible AI metadata.

## Licensing

Software is MIT licensed. Task cards, documentation, and generated artifacts are released as CC BY 4.0 unless otherwise noted.
