# Clean-Room Anonymous Artifact Verification

This release was checked from the exported anonymous zip in a fresh temporary directory with a new virtual environment and no API keys or PLECS backend.

## Environment

- Python: 3.9 virtual environment
- Install command: `pip install -r requirements.txt`
- Artifact source: `dist/pebench_anonymous_artifact.zip`
- API credentials: none
- Live simulator: none

## Commands

```bash
python scripts/validate_public_artifact.py
python scripts/validate_croissant_metadata.py
python scripts/validate_tasks.py
python scripts/validate_topology_full_tasks.py
python scripts/validate_inverter_tasks.py
python scripts/validate_reference_designs.py
python scripts/run_pebench_suite.py \
  --track all \
  --baseline reference_design \
  --model reference-design \
  --seed 0 \
  --simulator-mode stub \
  --output-root results/clean_reference_smoke
python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1
python scripts/reviewer_smoke_test.py
```

## Result

All commands completed successfully. The clean-room run validated the anonymous-public scan, Croissant/Responsible AI metadata, all 78 task schemas, 78 feasible reference designs, a no-API offline reference suite, and frozen-record paper-table reproduction.
