"""Memory candidate review pipeline.

Runs after candidate extraction.  Applies policy, writes pending candidates
to local JSONL, and (in approved_only mode) commits approved memories to the
LangGraph Memory Service.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .audit import (
    log_candidate_blocked,
    log_candidate_extracted,
    log_candidate_pending_review,
    log_service_unavailable,
)
from .client import propose_memory, commit_approved_memory, memory_service_available
from .config import MemoryServiceConfig, load_memory_service_config
from .policy import classify_memory_candidate, validate_memory_write
from .schemas import MemoryCandidate, MemoryWriteDecisionResult


def review_memory_candidates(
    candidates: list[MemoryCandidate],
    session_result: dict,
    *,
    config: MemoryServiceConfig | None = None,
    session_id: str = "",
) -> list[MemoryWriteDecisionResult]:
    """Review a batch of memory candidates from a completed session.

    1. Classify each candidate (block secrets, set requirements).
    2. Validate each candidate against write policy.
    3. Write pending candidates to local JSONL.
    4. Commit approved candidates to LangGraph Memory Service (if available).

    Returns one decision per candidate.
    """
    cfg = config or load_memory_service_config()
    decisions: list[MemoryWriteDecisionResult] = []

    for c in candidates:
        # ── 1. Classify ──
        c = classify_memory_candidate(c, config=cfg)
        log_candidate_extracted(
            session_id, c.candidate_id, c.memory_type,
            source_agent=c.source_agent,
            requires_verifier=c.requires_verifier,
            requires_human_review=c.requires_human_review,
        )

        # ── 2. Validate ──
        decision = validate_memory_write(c, config=cfg)

        if decision.decision == "blocked":
            log_candidate_blocked(
                session_id, c.candidate_id, decision.reason,
                memory_type=c.memory_type,
            )
            decisions.append(decision)
            continue

        # ── 3. Write pending candidate to local JSONL ──
        if decision.decision in ("needs_human_review", "needs_verifier"):
            _write_pending_candidate(c, decision, cfg)
            log_candidate_pending_review(
                session_id, c.candidate_id, c.memory_type,
            )
            decisions.append(decision)
            continue

        # ── 4. Commit to LangGraph Memory Service ──
        if decision.decision == "approve" and decision.approved:
            if memory_service_available(cfg):
                record = _candidate_to_record(c)
                commit_result = commit_approved_memory(record, config=cfg)
                if commit_result.get("ok"):
                    decision.committed = True
                    decision.memory_id = commit_result.get("memory_id", "")
                else:
                    # Commit failed — fall back to pending
                    decision.decision = "needs_human_review"
                    decision.approved = False
                    decision.reason = (
                        f"Commit failed: {commit_result.get('error', 'unknown')}"
                    )
                    _write_pending_candidate(c, decision, cfg)
            else:
                log_service_unavailable(session_id, "Cannot commit — service unavailable.")
                decision.decision = "needs_human_review"
                decision.approved = False
                decision.reason = "Service unavailable — pending review."
                _write_pending_candidate(c, decision, cfg)

        decisions.append(decision)

    return decisions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_pending_candidate(
    candidate: MemoryCandidate,
    decision: MemoryWriteDecisionResult,
    config: MemoryServiceConfig,
) -> None:
    """Append a pending candidate to the local JSONL file."""
    try:
        p = Path(config.pending_file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "candidate_id": candidate.candidate_id,
            "memory_type": candidate.memory_type,
            "decision": decision.decision,
            "reason": decision.reason,
            "content": candidate.content,
            "proposed_namespace": candidate.proposed_namespace,
            "requires_verifier": candidate.requires_verifier,
            "requires_human_review": candidate.requires_human_review,
            "source_session_id": candidate.source_session_id,
        }
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass  # File write failure must not crash AURA


def _candidate_to_record(candidate: MemoryCandidate) -> dict:
    """Convert a MemoryCandidate to a dict for the LangGraph Memory Service."""
    return {
        "memory_type": candidate.memory_type,
        "namespace": candidate.proposed_namespace,
        "key": candidate.proposed_key,
        "content": candidate.content,
        "source_session_id": candidate.source_session_id,
        "source_agent": candidate.source_agent,
        "confidence": candidate.confidence,
        "evidence_status": candidate.evidence_status,
        "verifier_route": candidate.verifier_route,
        "requires_verifier": candidate.requires_verifier,
        "requires_human_review": candidate.requires_human_review,
        "tags": [],
        "limitations": [],
    }
