# Evaluator Card: PE-Bench v1

## Evaluator goal
Verify cross-representation consistency for PE design artifacts. The evaluator checks topology/mode feasibility, theory constraints, component grounding, derating margins, claim consistency, and escalation behavior.

## Inputs
- Task definition (YAML)
- Candidate artifact (JSON)
- Component catalogs (YAML)
- Simulator mode (stub/auto/live/mcp/xmlrpc)

## Outputs (required)
- pass_fail
- score_total
- sub_scores
- constraint_violations
- simulation_metrics
- failure_tags
- failure_groups
- aggregate_scores
- execution_log
- runtime_stats

## Failure taxonomy
- Spec Parsing Failure
- Infeasible Theory Failure
- Invalid or Unsafe BOM
- Simulation Execution Failure
- Optimistic but Unrealistic Claim
- Efficiency Miss
- Ripple / Regulation Miss
- Current Quality Miss
- Stress Violation / Escalation Required
- Protection Missing

## Limitations
- Does not replace hardware validation, thermal layout, EMI/EMC, or certification
- Catalog coverage limits apply
- Simulator simplifications remain an abstraction

## Safety and escalation
- Escalation is treated as correct when specifications are ambiguous or unsafe
- Passing requires both simulator/metric consistency and component safety margins
