# PE-Bench Protocol

## Scope

PE-Bench evaluates AI-assisted power-electronics design artifacts. A valid candidate must expose a structured design package that can be checked across requirements, topology, equations, components, safety margins, metrics, reported claims, and review/escalation behavior.

## Task Banks

- Flyback: 30 tasks in `pebench/tasks/flyback/`
- Topology Full: 36 Buck/Boost/Buck-Boost tasks in `pebench/tasks/topology_full/`
- Three-phase inverter: 12 tasks in `pebench/tasks/inverter/`

Total: 78 released tasks.

## Task Schema

Every task records:

- `task_id`
- `natural_language_spec`
- `difficulty_tier`
- `benchmark_meta`
- `structured_spec`
- `evaluation_rubric`
- `reference_design`
- `known_failure_modes`

Topology Full and Three-phase inverter tasks also expose `schema_version`, `topology`, and `closure_gates`.

## Difficulty Tiers

- `easy`: comfortable margins and limited closure burden.
- `medium`: clean requirements with nontrivial closure.
- `hard`: stronger performance, power, ripple, or stress requirements.
- `boundary`: feasible but close to operating or safety margins.
- `stress`: conflicting objectives, ambiguity, or escalation-sensitive conditions.

## Evaluator Output

Every evaluator result must include:

- `pass_fail`
- `score_total`
- `sub_scores`
- `constraint_violations`
- `simulation_metrics`
- `failure_tags`
- `failure_groups`
- `aggregate_scores`
- `execution_log`
- `runtime_stats`

## Required Checks

- Schema and required-field closure.
- Requirement grounding.
- Topology feasibility.
- Equation and sizing consistency.
- Component grounding and derating margins.
- Efficiency, ripple, stress, startup, and protection checks.
- Reported-value consistency.
- Human-review or escalation behavior where the task is unsafe or underspecified.

## Reference Designs

Each task ships with a feasible reference design. The reference is a feasibility anchor, not a gold answer that candidates must exactly match.

## Release Invariants

`python scripts/reviewer_smoke_test.py` must pass before a release. The generated manifest under `artifacts/release/pebench_v1_manifest.json` is the machine-readable statement of the frozen task inventory and artifact contract.
