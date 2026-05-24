"""Audit logging for task-scoped agent events.

Writes structured JSONL records to ``data/task_agents.jsonl``.
Never logs secrets.  Hashes long context payloads.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

_LOGFILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "task_agents.jsonl",
)
_lock = threading.Lock()


def _hash_payload(data: Any) -> str:
    """SHA-256 hash of a JSON-serialised payload (deterministic)."""
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _write(record: dict[str, Any]) -> None:
    """Thread-safe append of a JSON line to the audit log."""
    with _lock:
        os.makedirs(os.path.dirname(_LOGFILE), exist_ok=True)
        with open(_LOGFILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")


def log_created(
    spec: Any,  # AgentSpec (imported lazily to avoid circular deps)
    session_id: str,
) -> None:
    """Log a task-agent creation event."""
    try:
        _write({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event": "created",
            "agent_id": spec.agent_id,
            "name": spec.name,
            "parent_agent": spec.parent_agent,
            "subtask_hash": _hash_payload(spec.subtask),
            "allowed_tools": spec.allowed_tools,
            "risk_level": spec.risk_level,
            "verifier_required": spec.verifier_required,
            "human_review_required": spec.human_review_required,
            "ok": True,
        })
    except Exception:
        pass  # audit failure must never break the pipeline


def log_blocked(
    requested_role: str,
    subtask: str,
    reason: str,
    session_id: str,
    existing_agent: str | None = None,
) -> None:
    """Log a blocked task-agent creation."""
    try:
        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event": "blocked",
            "name": requested_role,
            "subtask_hash": _hash_payload(subtask),
            "reason": reason[:500],
            "ok": False,
        }
        if existing_agent:
            record["routed_to"] = existing_agent
        _write(record)
    except Exception:
        pass


def log_executed(
    result: Any,  # TaskAgentResult
    session_id: str,
) -> None:
    """Log a task-agent execution event."""
    try:
        _write({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event": "executed",
            "agent_id": result.agent_id,
            "subtask_hash": _hash_payload(result.subtask),
            "ok": result.ok,
            "confidence": result.confidence,
            "findings_count": len(result.findings) if result.findings else 0,
            "claims_count": len(result.claims_for_verification) if result.claims_for_verification else 0,
            "errors": result.errors,
            "requires_verification": result.requires_verification,
            "verified_by_aura": result.verified_by_aura,
        })
    except Exception:
        pass


def log_failed(
    agent_id: str,
    subtask: str,
    errors: list[str],
    session_id: str,
) -> None:
    """Log a task-agent failure event."""
    try:
        _write({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event": "failed",
            "agent_id": agent_id,
            "subtask_hash": _hash_payload(subtask),
            "ok": False,
            "errors": errors,
        })
    except Exception:
        pass
