# PE-Bench Release Bundle Mapping

This directory describes how to export a submission bundle without copying or rewriting the repository.

Suggested bundle layout:
- tasks/ -> pebench/tasks/
- catalogs/ -> assets/catalogs/
- evaluator/ -> pebench/evaluator/
- baselines/ -> pebench/baselines/
- analysis/ -> pebench/analysis/
- docs/ -> docs/
- scripts/ -> scripts/

Use symlinks or a packaging script to avoid content drift.
