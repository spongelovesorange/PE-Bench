# Workspace Layout

PE-Bench is organized around one benchmark codebase plus optional external baseline repositories.

## Source Code

- `pebench/`
  Core benchmark package: tasks, evaluator, baselines, adapters, analysis, integrations.
- `scripts/`
  CLI entrypoints for runs, audits, task validation, analysis, and literature ingestion.
- `tests/`
  Benchmark-facing tests for evaluator behavior, baseline adapters, provenance generation, and task validation.
- `assets/`
  Static benchmark assets such as catalogs, reference designs, and task templates.

## External Baselines

Optional external PE system roots may be present in a local development workspace. They are treated as upstream baseline assets, not as the main benchmark package, and are excluded from the anonymous reviewer artifact.

## Generated Outputs

- `results/archive/`
  Frozen old result bundles.
- `results/audits/`
  Audit artifacts such as easy-tier calibration.
- `results/canonical/`
  Canonical benchmark runs and holdout runs.
- `results/ablations/`
  Ablation-only experiment outputs.
- `results/repeatability/`
  Multi-seed repeatability outputs.
- `sources/flyback_literature_20260408_massive/`
  Raw and curated literature harvest.
- `sources/provenance/`
  Task provenance, coverage summaries, and holdout candidate exports.

## Practical Rule

If a directory is needed to import Python modules, define tasks, run evaluators, or reproduce official benchmark experiments, it stays in place.

If a directory only contains caches, local virtual environments, browser profiles, compiled artifacts, or transient runtime state, it should stay out of the workspace view and out of version control.
