"""AURA MCP — read-only, path-safe report access.

Phase 1 exposes the contents of curated, report-like files under the
repository's ``reports/`` directory and NOTHING else.  All path resolution
goes through :func:`core.path_safety.safe_path`, which resolves the candidate
and asserts it is *contained* within the reports root — defeating ``..``
traversal, absolute-path escape, and symlinks that point outside the tree.

This module performs NO writes and never executes file contents.
"""
from __future__ import annotations

from pathlib import Path

import config
from core.path_safety import safe_path, MissionIdError

# Anchored at the repository's reports/ directory.  Functions read these as
# module globals at call time so tests may monkeypatch them onto a tmp dir.
REPORTS_ROOT: Path = Path(config.REPORT_DIR).resolve()
REPO_ROOT: Path = Path(config.BASE_DIR).resolve()

# Only these extensions are ever returned/listed.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".md", ".json", ".jsonl", ".txt"})

# Directory names whose entire subtree is skipped.
_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({
    "__pycache__", ".git", ".hg", ".svn", "node_modules", ".pytest_cache",
})

# Filename suffixes that are never report-like.
_EXCLUDED_SUFFIXES: frozenset[str] = frozenset({
    ".pyc", ".pyo", ".pyd", ".bak", ".tmp", ".swp", ".log", ".key", ".pem",
})

# Exact filenames treated as secrets / non-reports.
_EXCLUDED_NAMES: frozenset[str] = frozenset({
    ".env", ".env.example", ".env.local", "secrets.json", "credentials.json",
})


def _is_safe_report_file(path: Path, root: Path) -> bool:
    """Return True if *path* is a curated, report-like file under *root*."""
    name = path.name
    # Hidden files (dotfiles) and editor backups are excluded.
    if name.startswith("."):
        return False
    if name.endswith("~"):
        return False
    if name in _EXCLUDED_NAMES:
        return False
    if path.suffix.lower() in _EXCLUDED_SUFFIXES:
        return False
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return False
    # Reject any component that is an excluded directory or hidden dir.
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        return False
    for part in rel_parts[:-1]:
        if part in _EXCLUDED_DIR_NAMES or part.startswith("."):
            return False
    return True


def list_reports(limit: int = 1000) -> list[str]:
    """List safe, report-like files under the reports root.

    Returns POSIX-style paths *relative to the reports root*.  Never traverses
    outside it; excludes hidden files, backups, ``.pyc``/caches, and secrets.
    """
    root = REPORTS_ROOT
    if not root.exists():
        return []
    out: list[str] = []
    for p in sorted(root.rglob("*")):
        if len(out) >= limit:
            break
        try:
            if p.is_dir():
                continue
            # Skip symlinks entirely (defence-in-depth).
            if p.is_symlink():
                continue
            if not _is_safe_report_file(p, root):
                continue
            rel = p.relative_to(root).as_posix()
            out.append(rel)
        except (OSError, ValueError):
            continue
    return out


def _normalize_request(report_path: str) -> str:
    """Strip an optional leading ``reports/`` prefix so callers may pass either
    a path relative to the reports root (as returned by :func:`list_reports`)
    or a repo-relative ``reports/...`` path.
    """
    rp = report_path.strip().replace("\\", "/")
    for prefix in ("reports/", "./reports/"):
        if rp.lower().startswith(prefix):
            return rp[len(prefix):]
    return rp


def read_report(report_path: str, *, max_bytes: int = 5_000_000) -> tuple[str | None, str | None]:
    """Read an approved report file.  Returns ``(content, error)``.

    Safety: resolves under the reports root via ``safe_path`` (blocks ``..``,
    absolute escape, and symlink targets outside the tree), and only returns
    content for approved report-like extensions.
    """
    if not isinstance(report_path, str) or not report_path.strip():
        return None, "report_path must be a non-empty string."

    rel = _normalize_request(report_path)
    if not rel:
        return None, "report_path resolves to the reports root, not a file."

    try:
        # safe_path resolves + asserts containment within REPORTS_ROOT.
        candidate = safe_path(REPORTS_ROOT, rel)
    except MissionIdError as exc:
        return None, f"Path rejected: {exc}"
    except (ValueError, OSError) as exc:
        return None, f"Path rejected: {exc}"

    # Reject symlinks (even if their target happens to resolve inside).
    try:
        if candidate.is_symlink():
            return None, "Symlinked report files are not allowed."
    except OSError:
        return None, "Could not stat the requested path."

    if not candidate.exists() or not candidate.is_file():
        return None, "File not found under reports/."

    if not _is_safe_report_file(candidate, REPORTS_ROOT):
        return None, (
            "Not an approved report file (allowed: "
            f"{sorted(ALLOWED_EXTENSIONS)}; no hidden/backup/secret files)."
        )

    try:
        size = candidate.stat().st_size
        if size > max_bytes:
            return None, f"File too large ({size} bytes > {max_bytes})."
        return candidate.read_text(encoding="utf-8", errors="replace"), None
    except OSError as exc:
        return None, f"Could not read file: {exc}"
