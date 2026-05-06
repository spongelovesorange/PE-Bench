from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.artifacts.release import validate_release_artifacts, write_release_artifacts


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "dist" / "pebench_anonymous_artifact.zip"
PACKAGE_ROOT_NAME = "pebench_anonymous_artifact"
EXTERNAL_AGENT_ROOT = "PE" + "-MAS"
PEGPT_ROOT = "PE" + "-GPT"

INCLUDE_ROOTS = [
    ".env.example",
    ".gitignore",
    "ANONYMIZATION.md",
    "DATA_LICENSE.md",
    "LICENSE",
    "README.md",
    "artifacts",
    "assets",
    "croissant_metadata.json",
    "docs",
    "flybackbench",
    "pebench",
    "pyproject.toml",
    "requirements.txt",
    "scripts",
    "tests",
]

EXCLUDE_PATTERNS = [
    "*/__pycache__/*",
    "*/.pytest_cache/*",
    "*/.DS_Store",
    "*.pyc",
    "*.pyo",
    "*.zip",
    "*.db",
    "*.sqlite",
    "*.log",
    "*.aux",
    "*.bbl",
    "*.blg",
    "*.out",
    "*.pdf",
    "*.docx",
    "*.pptx",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.ipynb",
    ".env",
    ".venv/*",
    ".vscode/*",
    ".chainlit/*",
    ".files/*",
    ".reference_agent_runtime/*",
    f"{EXTERNAL_AGENT_ROOT}/*",
    f"{PEGPT_ROOT}/*",
    "paper/*",
    "results/*",
    "sources/*",
    "dist/*",
    "scripts/build_topology_scout_tasks.py",
    "scripts/run_topology_scout_suite.py",
    "scripts/summarize_topology_scout_results.py",
    "scripts/validate_topology_scout.py",
]

FORBIDDEN_TEXT_PATTERNS = [
    "beaulo" + "canana",
    "/" + "Users/",
    "Documents/" + "New project",
    "Downloads/" + "FlybackBench",
    "Shi " + "Qiu",
    "Shi_" + "QIU",
    "邱" + "释",
    "PE" + "-MAS",
    "pe" + "_mas",
    "pe" + "_mas_full",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a double-blind PE-Bench artifact zip.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--check", action="store_true", help="Run smoke test and anonymity checks before writing.")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip reviewer smoke test even when --check is set.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output).resolve()

    write_release_artifacts()
    errors = validate_release_artifacts()
    if errors:
        _print_errors("Release artifact validation failed", errors)
        return 1

    if args.check and not args.skip_smoke:
        completed = subprocess.run(
            [sys.executable, "scripts/reviewer_smoke_test.py"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            print(completed.stdout)
            return completed.returncode

    files = _included_files()
    errors = _anonymity_errors(files)
    if errors:
        _print_errors("Anonymous artifact check failed", errors)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative in files:
            archive.write(REPO_ROOT / relative, Path(PACKAGE_ROOT_NAME) / relative)

    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"Wrote {output}")
    print(f"Files: {len(files)}")
    print(f"Size: {size_mb:.2f} MB")
    return 0


def _included_files() -> list[Path]:
    files: list[Path] = []
    for root in INCLUDE_ROOTS:
        path = REPO_ROOT / root
        if path.is_file():
            relative = Path(root)
            if not _excluded(relative):
                files.append(relative)
            continue
        if not path.exists():
            continue
        for current_root, dirnames, filenames in os.walk(path):
            current = Path(current_root)
            dirnames[:] = [
                dirname for dirname in dirnames if not _excluded((current / dirname).relative_to(REPO_ROOT))
            ]
            for filename in filenames:
                relative = (current / filename).relative_to(REPO_ROOT)
                if not _excluded(relative):
                    files.append(relative)
    return sorted(set(files))


def _excluded(relative: Path) -> bool:
    value = relative.as_posix()
    return any(fnmatch.fnmatch(value, pattern) for pattern in EXCLUDE_PATTERNS)


def _anonymity_errors(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for relative in files:
        if relative.parts and relative.parts[0] in {EXTERNAL_AGENT_ROOT, PEGPT_ROOT, "results", "sources", "paper"}:
            errors.append(f"Excluded root leaked into artifact: {relative}")
        path = REPO_ROOT / relative
        if path.suffix.lower() not in {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json", ".csv", ".sh", ".example"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in FORBIDDEN_TEXT_PATTERNS:
            if pattern in text:
                errors.append(f"Forbidden text pattern '{pattern}' found in {relative}")
    return errors


def _print_errors(title: str, errors: list[str]) -> None:
    print(title + ":")
    for error in errors:
        print(f"  - {error}")


if __name__ == "__main__":
    raise SystemExit(main())
