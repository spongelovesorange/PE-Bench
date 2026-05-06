# Validation Summary

Evaluator validation, robustness, leakage, and simulation-consistency checks.

Source: `artifacts/evidence/frozen_v1/validation_summary.csv`

| validation_family | cases | parsed_or_accepted | pass_rate_percent | notes | evidence_level | rejection_rate_percent | detection_rate_percent | unsafe_false_pass_percent | run_record_match_percent | accepted | rejected | evaluator_false_negatives | false_negative_rate_percent | strong_baseline_heldout_vtsr | public_dev_vtsr | baseline_heldout_vtsr_min | baseline_heldout_vtsr_max | decision_agreement_percent | median_efficiency_error_percent | median_ripple_error_percent | median_stress_margin_error_percent | leakage_flags | max_tolerant_guess_rate_percent | strong_baseline_vtsr | strongest_non_specialized_vtsr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| required_field_checks | 78 | 78 | 100.0 | 78/78 task files parse and expose required fields across all five families | frozen_manuscript_summary_record |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| feasible_reference_checks | 78 | 78 | 100.0 | Feasible reference designs pass converter-specific checks | frozen_manuscript_summary_record |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| malformed_output_tests | 500+ |  |  | Malformed candidates rejected by required-format checks | frozen_manuscript_summary_record | 100.0 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| faulty_design_tests | 800 |  |  | Injected PE design faults | frozen_manuscript_summary_record |  | 99.2 | 0.0 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| run_record_check | all_reported_runs |  |  | simulation setup, seed, model, fallback, evaluator version, checksum | frozen_manuscript_summary_record |  |  |  | 100.0 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| independent_valid_design_check | 100 |  |  | Alternative valid designs across five families | frozen_manuscript_summary_record |  |  |  |  | 94 | 6 | 2 | 2.0 |  |  |  |  |  |  |  |  |  |  |  |  |
| heldout_robustness_split | 24 |  |  | Held-out robustness split | frozen_manuscript_summary_record |  |  |  |  |  |  |  |  | 0.652 | 0.684 | 0.158 | 0.218 |  |  |  |  |  |  |  |  |
| simulation_setup_consistency | 60 |  |  | Stability across simulation setup variants | frozen_manuscript_summary_record |  |  |  |  |  |  |  |  |  |  |  |  | 95.0 | 1.3 | 3.9 | 4.8 |  |  |  |  |
| data_leakage_slot_guessing | 1000 |  |  | No leakage flags in hidden slots | frozen_manuscript_summary_record |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0 | 6.5 |  |  |
| synchronous_buck_minitrack | 8 |  |  | Extensibility mini-track outside 78-task mean | frozen_manuscript_summary_record |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  | 0.625 | 0.250 |

