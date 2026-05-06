# Responsible AI Metadata

## Dataset Type

PE-Bench is a synthetic benchmark dataset and executable evaluator artifact for AI-assisted power-electronics design.

## Intended Use

- Evaluate whether AI-assisted design systems produce auditable converter-design candidates.
- Compare systems under the PE-Bench task schema, component-grounding checks, safety-margin checks, reported-value checks, and human-review/escalation rules.
- Reproduce paper-facing tables from frozen manuscript records without requiring API keys or live simulator access.

## Out-of-Scope Use

- Hardware certification, production sign-off, regulatory approval, procurement automation, or safety-critical deployment.
- Claims about broad electrical-engineering competence beyond the included task families and evaluator contract.

## Data Collection

The task cards are synthetic, author-curated engineering specifications with feasible reference-design anchors and bounded component-catalog slices. The artifact does not contain personal data.

## Biases And Limitations

- Coverage is limited to the released Buck, Boost, Buck-Boost, Flyback, and three-phase inverter task families.
- The public reviewer path uses deterministic stub/formula checks; PLECS-backed live simulation is optional and machine-specific.
- Model-provider outputs may drift over time; raw reruns are gated before they can replace frozen manuscript records.

## Human Oversight

PE-Bench is designed to evaluate auditability, not to automate final engineering decisions. Qualified engineering review remains required for any physical design or deployment.

## Metadata Files

- `croissant_metadata.json`: machine-readable Croissant core and Responsible AI metadata.
- `docs/DATASET_CARD.md`: dataset-card summary.
- `artifacts/evidence/EVIDENCE_MATRIX.md`: claim-to-evidence mapping.
