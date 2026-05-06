# Ablation Summary

Strong-baseline component ablations.

Source: `artifacts/evidence/frozen_v1/ablation_summary.csv`

| variant | vtsr_78task | inverter_vtsr | unsupported_values_percent | invalid_bom_percent | unsafe_false_pass_percent | evidence_level |
| --- | --- | --- | --- | --- | --- | --- |
| Full Strong Baseline | 0.684 | 0.565 | 8.2 | 4.5 | 0.0 | frozen_manuscript_summary_record |
| without_component_database_checks | 0.452 | 0.31 | 12.5 | 46.8 | 1.2 | frozen_manuscript_summary_record |
| without_equation_checks | 0.188 | 0.085 | 45.0 | 28.5 | 3.5 | frozen_manuscript_summary_record |
| without_reported_value_checker | 0.545 | 0.42 | 68.4 | 8.2 | 2.1 | frozen_manuscript_summary_record |
| without_human_review_rule | 0.612 | 0.49 | 10.5 | 5.0 | 12.8 | frozen_manuscript_summary_record |

