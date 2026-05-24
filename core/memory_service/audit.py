"""JSONL audit logging for the optional LangGraph Memory Service adapter.

All memory-related events (retrieval, write, commit, rejection) are written to
``data/memory_service.jsonl`` as structured JSON records.  Secrets, keys, and
private data are NEVER logged — only content hashes.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import load_memory_service_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOG_PATH: Path | None = None


def _log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        cfg = load_memory_service_config()
        _LOG_PATH = Path(cfg.audit_log_path)
    return _LOG_PATH


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


def _ensure_log_file() -> None:
    p = _log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.touch()


def _append(event: dict[str, object]) -> None:
    _ensure_log_file()
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    with open(_log_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")


# ---------------------------------------------------------------------------
# Public audit events
# ---------------------------------------------------------------------------

def log_retrieval_requested(
    session_id: str,
    prompt: str,
    agent_name: str | None = None,
    memory_types: list[str] | None = None,
) -> None:
    _append({
        "event": "retrieval_requested",
        "session_id": session_id,
        "prompt_hash": _sha256_hex(prompt),
        "agent_name": agent_name or "",
        "memory_types": memory_types or [],
    })


def log_retrieval_succeeded(session_id: str, count: int) -> None:
    _append({
        "event": "retrieval_succeeded",
        "session_id": session_id,
        "retrieved_count": count,
        "ok": True,
    })


def log_retrieval_failed(session_id: str, errors: list[str]) -> None:
    _append({
        "event": "retrieval_failed",
        "session_id": session_id,
        "errors": errors,
        "ok": False,
    })


def log_candidate_extracted(
    session_id: str,
    candidate_id: str,
    memory_type: str,
    source_agent: str = "",
    requires_verifier: bool = False,
    requires_human_review: bool = False,
) -> None:
    _append({
        "event": "candidate_extracted",
        "session_id": session_id,
        "candidate_id": candidate_id,
        "memory_type": memory_type,
        "source_agent": source_agent,
        "requires_verifier": requires_verifier,
        "requires_human_review": requires_human_review,
        "ok": True,
    })


def log_candidate_blocked(
    session_id: str,
    candidate_id: str,
    reason: str,
    memory_type: str = "",
) -> None:
    _append({
        "event": "candidate_blocked",
        "session_id": session_id,
        "candidate_id": candidate_id,
        "memory_type": memory_type,
        "reason": reason,
        "ok": False,
    })


def log_candidate_pending_review(
    session_id: str,
    candidate_id: str,
    memory_type: str,
) -> None:
    _append({
        "event": "candidate_pending_review",
        "session_id": session_id,
        "candidate_id": candidate_id,
        "memory_type": memory_type,
        "requires_human_review": True,
        "ok": True,
    })


def log_service_unavailable(session_id: str, reason: str) -> None:
    _append({
        "event": "service_unavailable",
        "session_id": session_id,
        "reason": reason,
        "ok": False,
    })
