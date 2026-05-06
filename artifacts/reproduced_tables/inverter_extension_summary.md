# Inverter Extension Summary

Three-phase inverter extension slice.

Source: `artifacts/evidence/frozen_v1/inverter_extension_summary.csv`

| method | vtsr | partial | pass_at_3 | unsupported_values_percent | dominant_failure_group | task_count | evidence_level |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LLM-only | 0.083 | 0.35 | 0.125 | 92.5 | Theory / Data Integrity | 12 | frozen_manuscript_summary_record |
| Structured-output only | 0.083 | 0.38 | 0.125 | 90.0 | Theory / Data Integrity | 12 | frozen_manuscript_summary_record |
| LLM+Tools | 0.105 | 0.41 | 0.15 | 85.0 | Component database checks | 12 | frozen_manuscript_summary_record |
| Single-Agent+Retry | 0.125 | 0.42 | 0.16 | 82.0 | Component database checks | 12 | frozen_manuscript_summary_record |
| Generic Two-Role MAS | 0.167 | 0.505 | 0.208 | 75.5 | Performance Requirement | 12 | frozen_manuscript_summary_record |
| PE-GPT-style | 0.167 | 0.525 | 0.22 | 70.0 | Simulation Execution Failure | 12 | frozen_manuscript_summary_record |
| Strong Baseline | 0.583 | 0.81 | 0.667 | 12.5 | Safety / Human review | 12 | frozen_manuscript_summary_record |

