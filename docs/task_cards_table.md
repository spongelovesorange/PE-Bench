# Task Cards Table

The task-card table is generated from source YAML files during artifact build.

Use:

```bash
python scripts/build_release_artifacts.py --check
```

Then inspect:

- `artifacts/release/task_inventory.csv`
- `artifacts/release/task_inventory.md`
