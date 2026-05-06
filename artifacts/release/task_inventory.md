# PE-Bench v1 Task Inventory

Release: `pebench-v1.0-78task`

Total tasks: **78**

## Topology Counts

| Topology | Count |
| --- | ---: |
| boost | 12 |
| buck | 12 |
| buck_boost | 12 |
| flyback | 30 |
| three_phase_inverter | 12 |

## Difficulty Counts

| Difficulty | Count |
| --- | ---: |
| boundary | 7 |
| easy | 21 |
| hard | 15 |
| medium | 26 |
| stress | 9 |

## Task Rows

| Task ID | Bank | Topology | Difficulty | Split | Path |
| --- | --- | --- | --- | --- | --- |
| `boundary_acdc_15v1a_tight_margin` | flyback | flyback | boundary | public_dev | `pebench/tasks/flyback/boundary_acdc_15v1a_tight_margin.yaml` |
| `boundary_acdc_24v1a_high_eff` | flyback | flyback | boundary | public_dev | `pebench/tasks/flyback/boundary_acdc_24v1a_high_eff.yaml` |
| `boundary_dcdc_12v3a_narrow_duty` | flyback | flyback | boundary | public_dev | `pebench/tasks/flyback/boundary_dcdc_12v3a_narrow_duty.yaml` |
| `boundary_dcdc_28v0p9a_low_stress` | flyback | flyback | boundary | private_holdout | `pebench/tasks/flyback/boundary_dcdc_28v0p9a_low_stress.yaml` |
| `easy_acdc_12v1a` | flyback | flyback | easy | public_dev | `pebench/tasks/flyback/easy_acdc_12v1a.yaml` |
| `easy_acdc_5v1a` | flyback | flyback | easy | public_dev | `pebench/tasks/flyback/easy_acdc_5v1a.yaml` |
| `easy_dcdc_12v0p5a` | flyback | flyback | easy | public_dev | `pebench/tasks/flyback/easy_dcdc_12v0p5a.yaml` |
| `easy_dcdc_15v0p8a` | flyback | flyback | easy | public_dev | `pebench/tasks/flyback/easy_dcdc_15v0p8a.yaml` |
| `easy_dcdc_24v0p5a` | flyback | flyback | easy | private_holdout | `pebench/tasks/flyback/easy_dcdc_24v0p5a.yaml` |
| `easy_dcdc_5v2a` | flyback | flyback | easy | public_dev | `pebench/tasks/flyback/easy_dcdc_5v2a.yaml` |
| `hard_acdc_12v2p2a_lowripple` | flyback | flyback | hard | public_dev | `pebench/tasks/flyback/hard_acdc_12v2p2a_lowripple.yaml` |
| `hard_acdc_19v1p5a_compact` | flyback | flyback | hard | private_holdout | `pebench/tasks/flyback/hard_acdc_19v1p5a_compact.yaml` |
| `hard_acdc_24v1p2a_eff89` | flyback | flyback | hard | public_dev | `pebench/tasks/flyback/hard_acdc_24v1p2a_eff89.yaml` |
| `hard_dcdc_12v2p5a_lowripple` | flyback | flyback | hard | public_dev | `pebench/tasks/flyback/hard_dcdc_12v2p5a_lowripple.yaml` |
| `hard_dcdc_24v1p8a_eff89` | flyback | flyback | hard | public_dev | `pebench/tasks/flyback/hard_dcdc_24v1p8a_eff89.yaml` |
| `hard_dcdc_48v0p8a_highline` | flyback | flyback | hard | private_holdout | `pebench/tasks/flyback/hard_dcdc_48v0p8a_highline.yaml` |
| `easy_acdc_18v0p6a` | flyback | flyback | medium | public_dev | `pebench/tasks/flyback/easy_acdc_18v0p6a.yaml` |
| `easy_acdc_9v0p7a` | flyback | flyback | medium | public_dev | `pebench/tasks/flyback/easy_acdc_9v0p7a.yaml` |
| `medium_acdc_12v2a` | flyback | flyback | medium | public_dev | `pebench/tasks/flyback/medium_acdc_12v2a.yaml` |
| `medium_acdc_15v1p5a` | flyback | flyback | medium | public_dev | `pebench/tasks/flyback/medium_acdc_15v1p5a.yaml` |
| `medium_acdc_24v0p8a` | flyback | flyback | medium | public_dev | `pebench/tasks/flyback/medium_acdc_24v0p8a.yaml` |
| `medium_acdc_5v3a` | flyback | flyback | medium | public_dev | `pebench/tasks/flyback/medium_acdc_5v3a.yaml` |
| `medium_dcdc_12v1p8a` | flyback | flyback | medium | public_dev | `pebench/tasks/flyback/medium_dcdc_12v1p8a.yaml` |
| `medium_dcdc_15v1p6a` | flyback | flyback | medium | public_dev | `pebench/tasks/flyback/medium_dcdc_15v1p6a.yaml` |
| `medium_dcdc_24v1a` | flyback | flyback | medium | public_dev | `pebench/tasks/flyback/medium_dcdc_24v1a.yaml` |
| `medium_dcdc_24v1p4a` | flyback | flyback | medium | private_holdout | `pebench/tasks/flyback/medium_dcdc_24v1p4a.yaml` |
| `stress_acdc_12v2a_ambiguous_bom` | flyback | flyback | stress | public_dev | `pebench/tasks/flyback/stress_acdc_12v2a_ambiguous_bom.yaml` |
| `stress_acdc_24v1p3a_smallsize` | flyback | flyback | stress | private_holdout | `pebench/tasks/flyback/stress_acdc_24v1p3a_smallsize.yaml` |
| `stress_acdc_5v3a_conflicting_cost_size` | flyback | flyback | stress | public_dev | `pebench/tasks/flyback/stress_acdc_5v3a_conflicting_cost_size.yaml` |
| `stress_dcdc_12v3a_conflicting_targets` | flyback | flyback | stress | public_dev | `pebench/tasks/flyback/stress_dcdc_12v3a_conflicting_targets.yaml` |
| `inverter_3ph_easy_grid_400v_20kw` | three_phase_inverter | three_phase_inverter | easy | extension | `pebench/tasks/inverter/inverter_3ph_easy_grid_400v_20kw.yaml` |
| `inverter_3ph_easy_grid_480v_50kw` | three_phase_inverter | three_phase_inverter | easy | extension | `pebench/tasks/inverter/inverter_3ph_easy_grid_480v_50kw.yaml` |
| `inverter_3ph_easy_traction_380v_30kw` | three_phase_inverter | three_phase_inverter | easy | extension | `pebench/tasks/inverter/inverter_3ph_easy_traction_380v_30kw.yaml` |
| `inverter_3ph_hard_grid_800v_100kw` | three_phase_inverter | three_phase_inverter | hard | extension | `pebench/tasks/inverter/inverter_3ph_hard_grid_800v_100kw.yaml` |
| `inverter_3ph_hard_islanding_480v_40kw` | three_phase_inverter | three_phase_inverter | hard | extension | `pebench/tasks/inverter/inverter_3ph_hard_islanding_480v_40kw.yaml` |
| `inverter_3ph_hard_traction_650v_120kw` | three_phase_inverter | three_phase_inverter | hard | extension | `pebench/tasks/inverter/inverter_3ph_hard_traction_650v_120kw.yaml` |
| `inverter_3ph_medium_grid_480v_100kw` | three_phase_inverter | three_phase_inverter | medium | extension | `pebench/tasks/inverter/inverter_3ph_medium_grid_480v_100kw.yaml` |
| `inverter_3ph_medium_microgrid_480v_25kw` | three_phase_inverter | three_phase_inverter | medium | extension | `pebench/tasks/inverter/inverter_3ph_medium_microgrid_480v_25kw.yaml` |
| `inverter_3ph_medium_traction_380v_60kw` | three_phase_inverter | three_phase_inverter | medium | extension | `pebench/tasks/inverter/inverter_3ph_medium_traction_380v_60kw.yaml` |
| `inverter_3ph_medium_ups_208v_15kw` | three_phase_inverter | three_phase_inverter | medium | extension | `pebench/tasks/inverter/inverter_3ph_medium_ups_208v_15kw.yaml` |
| `inverter_3ph_stress_high_current_400v_200kw` | three_phase_inverter | three_phase_inverter | stress | extension | `pebench/tasks/inverter/inverter_3ph_stress_high_current_400v_200kw.yaml` |
| `inverter_3ph_stress_low_dc_link_208v_60kw` | three_phase_inverter | three_phase_inverter | stress | extension | `pebench/tasks/inverter/inverter_3ph_stress_low_dc_link_208v_60kw.yaml` |
| `topology_boost_boundary_24v1p2a` | topology_full | boost | boundary | public_dev | `pebench/tasks/topology_full/topology_boost_boundary_24v1p2a.yaml` |
| `topology_boost_easy_12v1a` | topology_full | boost | easy | public_dev | `pebench/tasks/topology_full/topology_boost_easy_12v1a.yaml` |
| `topology_boost_easy_24v0p5a` | topology_full | boost | easy | public_dev | `pebench/tasks/topology_full/topology_boost_easy_24v0p5a.yaml` |
| `topology_boost_easy_24v0p7a` | topology_full | boost | easy | public_dev | `pebench/tasks/topology_full/topology_boost_easy_24v0p7a.yaml` |
| `topology_boost_easy_9v1a` | topology_full | boost | easy | public_dev | `pebench/tasks/topology_full/topology_boost_easy_9v1a.yaml` |
| `topology_boost_hard_36v1p3a` | topology_full | boost | hard | public_dev | `pebench/tasks/topology_full/topology_boost_hard_36v1p3a.yaml` |
| `topology_boost_hard_48v0p8a` | topology_full | boost | hard | public_dev | `pebench/tasks/topology_full/topology_boost_hard_48v0p8a.yaml` |
| `topology_boost_medium_28v1a` | topology_full | boost | medium | public_dev | `pebench/tasks/topology_full/topology_boost_medium_28v1a.yaml` |
| `topology_boost_medium_36v1a` | topology_full | boost | medium | public_dev | `pebench/tasks/topology_full/topology_boost_medium_36v1a.yaml` |
| `topology_boost_medium_48v0p6a` | topology_full | boost | medium | public_dev | `pebench/tasks/topology_full/topology_boost_medium_48v0p6a.yaml` |
| `topology_boost_medium_60v0p5a` | topology_full | boost | medium | public_dev | `pebench/tasks/topology_full/topology_boost_medium_60v0p5a.yaml` |
| `topology_boost_stress_36v1p5a` | topology_full | boost | stress | public_dev | `pebench/tasks/topology_full/topology_boost_stress_36v1p5a.yaml` |
| `topology_buck_boundary_12v3a` | topology_full | buck | boundary | public_dev | `pebench/tasks/topology_full/topology_buck_boundary_12v3a.yaml` |
| `topology_buck_easy_12v2a` | topology_full | buck | easy | public_dev | `pebench/tasks/topology_full/topology_buck_easy_12v2a.yaml` |
| `topology_buck_easy_24v1p2a` | topology_full | buck | easy | public_dev | `pebench/tasks/topology_full/topology_buck_easy_24v1p2a.yaml` |
| `topology_buck_easy_3p3v4a` | topology_full | buck | easy | public_dev | `pebench/tasks/topology_full/topology_buck_easy_3p3v4a.yaml` |
| `topology_buck_easy_5v3a` | topology_full | buck | easy | public_dev | `pebench/tasks/topology_full/topology_buck_easy_5v3a.yaml` |
| `topology_buck_hard_12v5a` | topology_full | buck | hard | public_dev | `pebench/tasks/topology_full/topology_buck_hard_12v5a.yaml` |
| `topology_buck_hard_5v8a` | topology_full | buck | hard | public_dev | `pebench/tasks/topology_full/topology_buck_hard_5v8a.yaml` |
| `topology_buck_medium_15v2p5a` | topology_full | buck | medium | public_dev | `pebench/tasks/topology_full/topology_buck_medium_15v2p5a.yaml` |
| `topology_buck_medium_18v3a` | topology_full | buck | medium | public_dev | `pebench/tasks/topology_full/topology_buck_medium_18v3a.yaml` |
| `topology_buck_medium_5v6a` | topology_full | buck | medium | public_dev | `pebench/tasks/topology_full/topology_buck_medium_5v6a.yaml` |
| `topology_buck_medium_9v4a` | topology_full | buck | medium | public_dev | `pebench/tasks/topology_full/topology_buck_medium_9v4a.yaml` |
| `topology_buck_stress_1p8v10a` | topology_full | buck | stress | public_dev | `pebench/tasks/topology_full/topology_buck_stress_1p8v10a.yaml` |
| `topology_buck_boost_boundary_12v3a` | topology_full | buck_boost | boundary | public_dev | `pebench/tasks/topology_full/topology_buck_boost_boundary_12v3a.yaml` |
| `topology_buck_boost_easy_12v1p5a` | topology_full | buck_boost | easy | public_dev | `pebench/tasks/topology_full/topology_buck_boost_easy_12v1p5a.yaml` |
| `topology_buck_boost_easy_15v1p5a` | topology_full | buck_boost | easy | public_dev | `pebench/tasks/topology_full/topology_buck_boost_easy_15v1p5a.yaml` |
| `topology_buck_boost_easy_24v1a` | topology_full | buck_boost | easy | public_dev | `pebench/tasks/topology_full/topology_buck_boost_easy_24v1a.yaml` |
| `topology_buck_boost_easy_9v2a` | topology_full | buck_boost | easy | public_dev | `pebench/tasks/topology_full/topology_buck_boost_easy_9v2a.yaml` |
| `topology_buck_boost_hard_18v2p5a` | topology_full | buck_boost | hard | public_dev | `pebench/tasks/topology_full/topology_buck_boost_hard_18v2p5a.yaml` |
| `topology_buck_boost_hard_24v2a` | topology_full | buck_boost | hard | public_dev | `pebench/tasks/topology_full/topology_buck_boost_hard_24v2a.yaml` |
| `topology_buck_boost_medium_12v2a` | topology_full | buck_boost | medium | public_dev | `pebench/tasks/topology_full/topology_buck_boost_medium_12v2a.yaml` |
| `topology_buck_boost_medium_18v1p5a` | topology_full | buck_boost | medium | public_dev | `pebench/tasks/topology_full/topology_buck_boost_medium_18v1p5a.yaml` |
| `topology_buck_boost_medium_24v1p2a` | topology_full | buck_boost | medium | public_dev | `pebench/tasks/topology_full/topology_buck_boost_medium_24v1p2a.yaml` |
| `topology_buck_boost_medium_36v1a` | topology_full | buck_boost | medium | public_dev | `pebench/tasks/topology_full/topology_buck_boost_medium_36v1a.yaml` |
| `topology_buck_boost_stress_24v3a` | topology_full | buck_boost | stress | public_dev | `pebench/tasks/topology_full/topology_buck_boost_stress_24v3a.yaml` |
