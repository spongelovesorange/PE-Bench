# Evaluator Card: PE-Bench v1

Inputs: task YAML, candidate JSON, bounded component catalog slice, simulator configuration, and run metadata.

Checks: schema closure, requirement grounding, topology equations, component grounding, derating margins, reported-value consistency, simulator/formula metrics, protection behavior where applicable, and human-review or escalation behavior.

Outputs: pass/fail, score_total, sub_scores, constraint_violations, simulation_metrics, failure_tags, failure_groups, aggregate_scores, execution_log, and runtime_stats.

Known abstractions: formula stubs are CI-safe approximations; full live simulation requires a local circuit-simulation backend.
