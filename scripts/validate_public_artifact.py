from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "results",
}

TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".csv",
    ".ini",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan the public PE-Bench artifact for anonymization and secret leaks.")
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root to scan.")
    parser.add_argument("--check-git-history", action="store_true", help="Also scan commit author/committer metadata when .git is present.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    errors = validate_public_artifact(root, check_git_history=args.check_git_history)
    if errors:
        print("Public artifact validation failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Public artifact validation passed.")
    return 0


def validate_public_artifact(root: Path = REPO_ROOT, *, check_git_history: bool = False) -> list[str]:
    findings: list[str] = []
    patterns = _patterns()
    for path in _iter_text_files(root):
        text = _read_text(path)
        if text is None:
            continue
        for label, pattern in patterns:
            if pattern.search(text):
                findings.append(f"{label}: {_rel(path, root)}")
    if check_git_history and (root / ".git").exists():
        findings.extend(_scan_git_history(root, patterns))
    return findings


def _patterns() -> list[tuple[str, re.Pattern[str]]]:
    legacy_count = "6" + "6"
    return [
        ("API key-like token", re.compile(r"sk-[A-Za-z0-9]{20,}")),
        ("absolute user path", re.compile(re.escape("/" + "Users" + "/"))),
        ("local username", re.compile("beau" + "locanana", re.IGNORECASE)),
        ("local source path", re.compile(re.escape("Downloads/" + "FlybackBench"))),
        ("legacy task-count wording", re.compile(rf"\b{legacy_count}[- ]tasks?\b|\b{legacy_count} released\b", re.IGNORECASE)),
        ("non-anonymous author name", re.compile("Shi" + r"\s+" + "Qiu", re.IGNORECASE)),
        ("non-anonymous author name", re.compile("邱" + "释")),
        ("old public benchmark name", re.compile("pebench" + r"[-_]" + "scout", re.IGNORECASE)),
        ("old public split name", re.compile("public" + r"[-_]" + "scout", re.IGNORECASE)),
        ("old public task family", re.compile("multitopology" + r"[-_]" + "scout", re.IGNORECASE)),
    ]


def _iter_text_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            paths.append(path)
    return sorted(paths)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _rel(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _scan_git_history(root: Path, patterns: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    completed = subprocess.run(
        ["git", "log", "--format=%H%x09%an%x09%ae%x09%cn%x09%ce"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return ["git history scan failed"]
    findings: list[str] = []
    for line in completed.stdout.splitlines():
        fields = line.split("\t")
        commit = fields[0][:12] if fields else "unknown"
        metadata = "\t".join(fields[1:])
        for label, pattern in patterns:
            if pattern.search(metadata):
                findings.append(f"{label}: git commit metadata {commit}")
    return findings


if __name__ == "__main__":
    raise SystemExit(main())
