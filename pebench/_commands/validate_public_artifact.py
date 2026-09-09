from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

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
    ".example",
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
    endpoint = (
        r"(?i)(?:[\"']?(?:base_url|api_base|api_endpoint)[\"']?\s*[:=]\s*[\"']?)"
        r"https?://(?!(?:api\.openai\.com|localhost|127\.0\.0\.1|example\.(?:com|org|invalid))(?=[:/\s\"']|$))"
        r"[^\s\"']+"
    )
    return [
        ("API key-like token", re.compile(r"sk-[A-Za-z0-9]{20,}")),
        ("absolute user path", re.compile(r"/(?:Users|home)/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+")),
        ("credential-bearing URL", re.compile(r"https?://[^\s/@:]+:[^\s/@]+@")),
        ("private provider endpoint", re.compile(endpoint)),
        ("legacy task-count wording", re.compile(r"\b66[- ]tasks?\b|\b66 released\b", re.IGNORECASE)),
        ("old public benchmark name", re.compile(r"pebench[-_]scout", re.IGNORECASE)),
        ("old public split name", re.compile(r"public[-_]scout", re.IGNORECASE)),
        ("old public task family", re.compile(r"multitopology[-_]scout", re.IGNORECASE)),
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


def _is_anonymous_identity(name: str) -> bool:
    return bool(re.fullmatch(
        r"Anonymous(?: [A-Za-z0-9_.-]+)*"
        r"|(?:[A-Za-z0-9_.-]+ )?Artifact (?:Maintainers?|Authors?)"
        r"|[A-Za-z0-9_.-]+\[bot\]",
        name.strip(),
        re.IGNORECASE,
    ))


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
        for index in (1, 3):
            if len(fields) > index and not _is_anonymous_identity(fields[index]):
                findings.append(f"non-anonymous author or committer: git commit metadata {commit}")
                break
        for label, pattern in patterns:
            if pattern.search(metadata):
                findings.append(f"{label}: git commit metadata {commit}")
    return findings


if __name__ == "__main__":
    raise SystemExit(main())
