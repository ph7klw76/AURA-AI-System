"""Append-only audit log for outbound MCP calls.

Every outbound call is recorded as one JSONL row.  Arguments and raw results
are HASHED (sha256) — raw payloads (which may contain secrets) are never
written.  Enough metadata is captured for reproducibility.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import McpOutboundConfig, load_config


def hash_obj(obj: Any) -> str:
    """Stable sha256 of any JSON-serializable object (or its repr)."""
    try:
        blob = json.dumps(obj, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = repr(obj)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_audit_record(
    *,
    session_id: str | None,
    server: str,
    tool: str,
    arguments: dict | None,
    raw_result: Any,
    ok: bool,
    error_type: str | None,
    duration_seconds: float,
    normalized_evidence_type: str | None,
    verified_by_aura: bool = False,
    mock_mode: bool = False,
) -> dict:
    """Build the canonical audit record (hashed args/results, no raw secrets)."""
    return {
        "timestamp": utc_now(),
        "session_id": session_id,
        "direction": "outbound",
        "server": server,
        "tool": tool,
        "arguments_hash": hash_obj(arguments or {}),
        "result_hash": hash_obj(raw_result),
        "ok": bool(ok),
        "error_type": error_type,
        "duration_seconds": round(float(duration_seconds), 4),
        "normalized_evidence_type": normalized_evidence_type,
        "verified_by_aura": bool(verified_by_aura),
        "mock_mode": bool(mock_mode),
    }


def log_call(record: dict, *, config: McpOutboundConfig | None = None) -> bool:
    """Append one audit record to the JSONL audit log.  Never raises."""
    cfg = config or load_config()
    try:
        path: Path = cfg.audit_log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return True
    except Exception:  # noqa: BLE001 — auditing must never crash a call
        return False
