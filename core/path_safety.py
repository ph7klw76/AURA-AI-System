"""Path-safety helpers — fail-closed validation for filesystem keys.

A ``mission_id`` (and similar identifiers) frequently controls a
filesystem read/write path (``reports/deep_research/<mission_id>_report.md``).
If that value is attacker- or LLM-influenced, an unvalidated id enables
**path traversal** (``../../etc/passwd``), absolute-path escape
(``/etc/shadow``), or separator injection.

This module provides:
  * :func:`validate_mission_id` — strict allowlist + length cap; raises
    ``MissionIdError`` on anything suspicious.
  * :func:`is_valid_mission_id` — boolean variant for callers that prefer
    to branch.
  * :func:`safe_path` — join + resolve a filename under a base directory
    and assert the resolved path is CONTAINED within that base (defends
    against symlink / ``..`` escape even after validation).

Policy: FAIL CLOSED.  An invalid id raises rather than silently
sanitising, so a caller can never proceed with a half-trusted path.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Conservative allowlist: alphanumerics, underscore, hyphen.  No dots
# (blocks ``..`` and hidden files), no separators, no whitespace.
_MISSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
MISSION_ID_MAX_LEN = 64


class MissionIdError(ValueError):
    """Raised when a mission_id (or similar fs key) fails validation."""


def validate_mission_id(mission_id: object, *, field: str = "mission_id") -> str:
    """Return ``mission_id`` if it is a safe filesystem key, else raise.

    Accepts only ``[A-Za-z0-9_-]`` up to :data:`MISSION_ID_MAX_LEN`
    characters.  Rejects empty strings, non-strings, anything containing
    a path separator, ``..``, a leading dot, a drive/absolute marker,
    NUL bytes, or whitespace.

    Raises:
        MissionIdError: on any invalid input (fail closed).
    """
    if not isinstance(mission_id, str):
        raise MissionIdError(
            f"{field} must be a string, got {type(mission_id).__name__}"
        )
    s = mission_id.strip()
    if not s:
        raise MissionIdError(f"{field} must not be empty")
    if len(s) > MISSION_ID_MAX_LEN:
        raise MissionIdError(
            f"{field} exceeds max length {MISSION_ID_MAX_LEN} (got {len(s)})"
        )
    # Explicit traversal / separator guards (defence-in-depth; the regex
    # already excludes these, but be explicit for clear error messages).
    if "\x00" in s:
        raise MissionIdError(f"{field} contains a NUL byte")
    if "/" in s or "\\" in s:
        raise MissionIdError(f"{field} must not contain path separators")
    if ".." in s:
        raise MissionIdError(f"{field} must not contain '..'")
    if not _MISSION_ID_RE.match(s):
        raise MissionIdError(
            f"{field} contains illegal characters; allowed: [A-Za-z0-9_-]"
        )
    return s


def is_valid_mission_id(mission_id: object) -> bool:
    """Boolean form of :func:`validate_mission_id` (never raises)."""
    try:
        validate_mission_id(mission_id)
        return True
    except MissionIdError:
        return False


def safe_path(base_dir: Path | str, *parts: str) -> Path:
    """Join ``parts`` under ``base_dir`` and assert containment.

    Resolves the final path and verifies it is inside the resolved
    ``base_dir`` — defending against ``..`` segments or symlinks that
    would otherwise escape.  Returns the resolved, contained path.

    Raises:
        MissionIdError: if the resolved path escapes ``base_dir``.
    """
    base = Path(base_dir).resolve()
    candidate = base.joinpath(*parts).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise MissionIdError(
            f"resolved path {candidate} escapes base directory {base}"
        )
    return candidate


def safe_mission_path(
    base_dir: Path | str,
    mission_id: object,
    suffix: str,
    *,
    field: str = "mission_id",
) -> Path:
    """Validate ``mission_id`` and return a contained ``<id><suffix>`` path.

    Convenience wrapper combining :func:`validate_mission_id` and
    :func:`safe_path` for the common ``<base>/<mission_id><suffix>``
    pattern (e.g. suffix=``"_report.md"``).
    """
    valid = validate_mission_id(mission_id, field=field)
    return safe_path(base_dir, f"{valid}{suffix}")


def unique_filename_stamp(*, utc: bool = False) -> str:
    """Return a collision-resistant timestamp token for filenames.

    Phase 2 (goal F): second-resolution timestamps (``%Y-%m-%d_%H%M%S``)
    and same-day-only names (``%Y-%m-%d``) silently OVERWRITE each other
    when two artefacts are produced in the same second / day.  This helper
    appends microseconds **and** a short random UUID suffix so two writes
    in rapid succession can never collide:

        2026-05-21_143002_417213_a1b2c3d4

    The leading ``%Y-%m-%d_%H%M%S`` keeps the names lexically sortable.
    """
    now = datetime.now(timezone.utc) if utc else datetime.now()
    return now.strftime("%Y-%m-%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:8]


__all__ = [
    "MissionIdError",
    "MISSION_ID_MAX_LEN",
    "validate_mission_id",
    "is_valid_mission_id",
    "safe_path",
    "safe_mission_path",
    "unique_filename_stamp",
]
