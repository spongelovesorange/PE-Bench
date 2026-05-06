# Release Checklist

- [ ] `python scripts/reviewer_smoke_test.py`
- [ ] `python scripts/build_release_artifacts.py --check`
- [ ] `python scripts/validate_tasks.py`
- [ ] `python scripts/validate_topology_full_tasks.py`
- [ ] `python scripts/validate_inverter_tasks.py`
- [ ] `python scripts/validate_reference_designs.py`
- [ ] `python scripts/reproduce_paper_tables.py --evidence artifacts/evidence/frozen_v1`
- [ ] `pytest`
- [ ] Confirm `paper/` is absent from the repository.
- [ ] Confirm `.env` is absent and caches/virtualenvs are ignored by `.gitignore`.
- [ ] Confirm `artifacts/release/pebench_v1_manifest.json` reports 78 tasks.
- [ ] Confirm non-use statement is visible in `docs/NON_USE_STATEMENT.md` and generated artifact cards.
