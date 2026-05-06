from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_dataset_artifacts import CROISSANT_PATH, _validate_croissant_metadata


def main() -> int:
    if not CROISSANT_PATH.exists():
        print(f"Missing Croissant metadata: {CROISSANT_PATH}")
        return 1
    metadata = json.loads(CROISSANT_PATH.read_text(encoding="utf-8"))
    errors = _validate_croissant_metadata(metadata)
    if errors:
        print("Croissant/Responsible AI metadata validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Croissant/Responsible AI metadata validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
