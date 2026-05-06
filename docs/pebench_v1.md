# PE-Bench v1 Snapshot

The canonical machine-readable snapshot is generated at:

- `artifacts/release/pebench_v1_manifest.json`
- `artifacts/release/task_inventory.csv`
- `artifacts/release/task_inventory.md`

Regenerate it with:

```bash
python scripts/build_release_artifacts.py --check
```

Task accounting is fixed at 78 released tasks across Buck, Boost, Buck-Boost, Flyback, and Three-phase inverter families.
