"""
Safe folder scan (Section B).

Refuses to enumerate outside the chosen folder, normalises paths, skips
symlinks by default, and applies file-count / file-size limits.
"""
from __future__ import annotations

import os
from pathlib import Path

import config
from .models import DiscoveredFile, DiscoverySummary


# Defect 12: legacy formats are NOT in the supported set.  Without a real
# extraction backend they would always fail; counting them as "supported"
# was a lie.  They are still RECOGNISED below so the summary can surface
# them under ``unsupported_formats`` with a ``skip_reason="legacy_format"``
# message rather than the more generic "unsupported_format".
FIRST_CLASS_FORMATS: frozenset[str] = frozenset({".pdf", ".docx", ".txt", ".md"})
LEGACY_FORMATS: frozenset[str] = frozenset({".doc", ".rtf", ".odt"})
SUPPORTED_FORMATS: frozenset[str] = FIRST_CLASS_FORMATS

# Caps (overridable via env vars; safe defaults).
# Phase 3 (goal D): parsed via config.env_int so a malformed value (e.g.
# AURA_LOCAL_FOLDER_MAX_FILES=lots) falls back to the default instead of
# crashing this module's import.
MAX_FILES_DEFAULT: int = config.env_int("AURA_LOCAL_FOLDER_MAX_FILES", 200)
MAX_FILE_BYTES_DEFAULT: int = config.env_int("AURA_LOCAL_FOLDER_MAX_FILE_BYTES", 20000000)   # 20 MB
MAX_TOTAL_BYTES_DEFAULT: int = config.env_int("AURA_LOCAL_FOLDER_MAX_TOTAL_BYTES", 200000000)   # 200 MB


def _validate_folder(raw_path: str) -> tuple[Path | None, str]:
    """Return ``(folder, error)``.  Folder is None when validation fails."""
    if not raw_path or not isinstance(raw_path, str):
        return None, "folder_path is empty"
    try:
        folder = Path(raw_path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        return None, f"folder path normalisation failed: {exc}"
    if not folder.exists():
        return None, f"folder does not exist: {folder}"
    if not folder.is_dir():
        return None, f"path is not a directory: {folder}"
    if not os.access(folder, os.R_OK):
        return None, f"folder is not readable: {folder}"
    return folder, ""


def scan_folder(
    folder_path: str,
    *,
    max_files: int | None = None,
    max_file_bytes: int | None = None,
    max_total_bytes: int | None = None,
    follow_symlinks: bool = False,
    recursive: bool = True,
) -> DiscoverySummary:
    """Walk *folder_path* and return a structured DiscoverySummary.

    Files outside the resolved folder (symlinks pointing elsewhere) are
    skipped with ``skip_reason="symlink_outside_folder"`` unless
    ``follow_symlinks`` is explicitly enabled.

    File-size caps apply per-file AND across the total batch; oversized
    files are reported as skipped with reason ``size_limit``.
    """
    max_files = max_files or MAX_FILES_DEFAULT
    max_file_bytes = max_file_bytes or MAX_FILE_BYTES_DEFAULT
    max_total_bytes = max_total_bytes or MAX_TOTAL_BYTES_DEFAULT

    folder, err = _validate_folder(folder_path)
    if folder is None:
        return DiscoverySummary(folder_path=folder_path, validation_error=err)

    summary = DiscoverySummary(
        folder_path=str(folder),
        max_files_applied=max_files,
    )
    unsupported_exts: set[str] = set()
    total_bytes_accumulated = 0
    omitted_count = 0

    iterator = (
        folder.rglob("*") if recursive else folder.glob("*")
    )

    for raw_entry in iterator:
        # Defect 13: count files we WOULD have inspected but had to skip
        # because of the cap.  We stop early to keep memory bounded, but
        # before returning we set scan_truncated=True so the caller knows
        # the result is partial.
        if summary.files_discovered >= max_files:
            try:
                # Only count files (not directories) for the omitted_count.
                if raw_entry.is_file():
                    omitted_count += 1
            except OSError:
                pass
            summary.scan_truncated = True
            # Limit how many extra paths we walk just to count omissions —
            # a folder with millions of files should not block the scan.
            if omitted_count >= max_files * 4:
                break
            continue
        try:
            entry = raw_entry
            # Reject paths that escape the folder via symlinks.
            if entry.is_symlink() and not follow_symlinks:
                summary.discovered_files.append(DiscoveredFile(
                    path=str(entry), name=entry.name, ext=entry.suffix.lower(),
                    size_bytes=0, is_supported=False,
                    skip_reason="symlink_skipped",
                ))
                summary.files_discovered += 1
                summary.files_skipped += 1
                continue
            try:
                resolved = entry.resolve(strict=False)
            except (OSError, RuntimeError):
                continue
            try:
                resolved.relative_to(folder)
            except ValueError:
                summary.discovered_files.append(DiscoveredFile(
                    path=str(entry), name=entry.name, ext=entry.suffix.lower(),
                    size_bytes=0, is_supported=False,
                    skip_reason="symlink_outside_folder",
                ))
                summary.files_discovered += 1
                summary.files_skipped += 1
                continue
            if not entry.is_file():
                continue
        except OSError:
            continue

        summary.files_discovered += 1
        ext = entry.suffix.lower()
        try:
            size = entry.stat().st_size
        except OSError:
            size = 0

        if ext not in SUPPORTED_FORMATS:
            unsupported_exts.add(ext or "(no_ext)")
            summary.files_skipped += 1
            # Defect 12: legacy formats are explicitly distinguished from
            # other unsupported extensions so the summary can tell the user
            # we saw their .doc but cannot read it.
            reason = "legacy_format" if ext in LEGACY_FORMATS else "unsupported_format"
            summary.discovered_files.append(DiscoveredFile(
                path=str(entry), name=entry.name, ext=ext, size_bytes=size,
                is_supported=False, skip_reason=reason,
            ))
            continue

        if size > max_file_bytes:
            summary.files_skipped += 1
            summary.discovered_files.append(DiscoveredFile(
                path=str(entry), name=entry.name, ext=ext, size_bytes=size,
                is_supported=False, skip_reason="size_limit",
            ))
            continue

        if total_bytes_accumulated + size > max_total_bytes:
            summary.files_skipped += 1
            summary.discovered_files.append(DiscoveredFile(
                path=str(entry), name=entry.name, ext=ext, size_bytes=size,
                is_supported=False, skip_reason="total_size_limit",
            ))
            continue

        total_bytes_accumulated += size
        summary.files_supported += 1
        summary.discovered_files.append(DiscoveredFile(
            path=str(entry), name=entry.name, ext=ext, size_bytes=size,
            is_supported=True,
        ))

    summary.unsupported_formats = sorted(unsupported_exts)
    summary.omitted_count = omitted_count
    return summary
