"""Audit logging for LLM Agent Planner decisions.

Logs to ``data/llm_agent_plans.jsonl``.  Never logs secrets, API keys,
tokens, or raw private documents.
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
    "llm_agent_plans.jsonl",
)
_lock = threading.Lock()


def _hash(text: str) -> str:
    """SHA-256 truncated hash for prompt/plan fingerprinting."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(record: dict[str, Any]) -> None:
    """Thread-safe append of a JSON line to the audit log."""
    with _lock:
        os.makedirs(os.path.dirname(_LOGFILE), exist_ok=True)
        with open(_LOGFILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")


def log_planner_disabled(session_id: str | None, reason: str = "") -> None:
    """Log that the planner was not used because it is disabled."""
    try:
        _write({
            "timestamp": _now(),
            "session_id": session_id,
            "event": "planner_disabled",
            "reason": reason or "AURA_LLM_PLANNER_ENABLED != 1",
        })
    except Exception:
        pass


def log_planner_requested(session_id: str | None, prompt_hash: str) -> None:
    """Log that the planner was invoked."""
    try:
        _write({
            "timestamp": _now(),
            "session_id": session_id,
            "event": "planner_requested",
            "prompt_hash": prompt_hash,
        })
    except Exception:
        pass


def log_planner_succeeded(
    session_id: str | None,
    plan_id: str,
    raw_plan_hash: str,
    plan: Any,  # AgentPlan
) -> None:
    """Log a successful LLM plan proposal."""
    try:
        _write({
            "timestamp": _now(),
            "session_id": session_id,
            "event": "planner_succeeded",
            "plan_id": plan_id,
            "raw_plan_hash": raw_plan_hash,
            "primary_agent": plan.primary_agent,
            "secondary_agents": plan.secondary_agents,
            "helper_agents": plan.helper_agents,
            "external_mcp": plan.external_mcp,
            "risk_level": plan.risk_level,
            "confidence": plan.confidence,
            "requires_verifier": plan.requires_verifier,
            "requires_human_review": plan.requires_human_review,
        })
    except Exception:
        pass


def log_planner_failed(
    session_id: str | None, error: str, raw_plan_hash: str | None = None
) -> None:
    """Log a failed LLM plan proposal (error is hashed, never stored in plaintext)."""
    try:
        _write({
            "timestamp": _now(),
            "session_id": session_id,
            "event": "planner_failed",
            "error_hash": _hash(error[:300]),
            "raw_plan_hash": raw_plan_hash,
        })
    except Exception:
        pass


def log_plan_validated(
    session_id: str | None,
    plan_id: str,
    ok: bool,
    errors: list[str],
    warnings: list[str],
    fallback_used: bool,
) -> None:
    """Log a policy validation result."""
    try:
        _write({
            "timestamp": _now(),
            "session_id": session_id,
            "event": "plan_validated" if ok else "plan_rejected",
            "plan_id": plan_id,
            "ok": ok,
            "errors": errors[:10],
            "warnings": warnings[:10],
            "fallback_used": fallback_used,
        })
    except Exception:
        pass


def log_fallback_used(
    session_id: str | None, reason: str, selected_agents: list[str]
) -> None:
    """Log that fallback routing was used."""
    try:
        _write({
            "timestamp": _now(),
            "session_id": session_id,
            "event": "fallback_used",
            "reason": reason[:300],
            "selected_agents": selected_agents,
        })
    except Exception:
        pass
