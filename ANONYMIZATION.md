# Anonymous Submission Notes

This repository can be exported as an anonymous PE-Bench artifact with:

```bash
python scripts/export_anonymous_artifact.py --check
```

The export excludes local and non-anonymous workspace material:

- optional external baseline roots
- `results/`
- `sources/`
- `.chainlit/`
- `.files/`
- `.reference_agent_runtime/`
- `.vscode/`
- local caches, virtual environments, logs, notebooks, and archives

The anonymous artifact contains only the benchmark package, task cards, catalogs, reviewer scripts, tests, generated release metadata, and documentation needed to inspect and run the code artifact.

The legacy package name `flybackbench` is kept only as an import shim and does not identify the authors.
