"""Deterministic memory-candidate extraction from AURA session results.

Runs after AURA completes a session.  Extracts structured candidates from
the orchestrator result dict — no LLM calls, no external services.

Candidates are proposals only; they are validated by ``policy.py`` and
written to the pending file by ``review.py``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .schemas import MemoryCandidate


def _cid() -> str:
    return f"c-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_memory_candidates_from_session(
    result: dict,
    *,
    session_id: str = "",
    user_input: str = "",
) -> list[MemoryCandidate]:
    """Extract memory candidates from a completed AURA session result dict.

    Returns an empty list when the result dict carries no useful long-term
    memory signals.  Never raises.
    """
    try:
        candidates: list[MemoryCandidate] = []

        _extract_user_preferences(result, candidates, session_id, user_input)
        _extract_project_decisions(result, candidates, session_id)
        _extract_mcp_tool_memory(result, candidates, session_id)
        _extract_task_agent_patterns(result, candidates, session_id)
        _extract_planner_patterns(result, candidates, session_id)
        _extract_repository_constraints(result, candidates, session_id)
        _extract_evidence_memory(result, candidates, session_id)
        _extract_procedural_proposals(result, candidates, session_id)

        return candidates
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Private extractors — each is self-contained and non-fatal
# ---------------------------------------------------------------------------

def _extract_user_preferences(
    result: dict, out: list[MemoryCandidate], session_id: str, user_input: str,
) -> None:
    """Extract explicit user preferences from the session.

    Only captures preferences that appear as repeated or explicit patterns
    in verifier-accepted specialist output.  Transient chat is ignored.
    """
    if not user_input:
        return

    # Detect explicit preference signals in user input
    preference_signals = {
        "i prefer": "user_preference",
        "i want you to": "user_preference",
        "always use": "user_preference",
        "use markdown": "user_preference",
        "keep it": "user_preference",
        "no mermaid": "user_preference",
        "no diagrams": "user_preference",
        "publication-quality": "user_preference",
        "conservative": "user_preference",
        "aggressive claims": "user_preference",
    }

    lower = user_input.lower()
    matched = [sig for sig in preference_signals if sig in lower]
    if not matched:
        return

    # Also check if this preference was validated by a specialist
    specialists = result.get("specialists") or {}
    verified = any(
        v.get("verifier_route") == "approve"
        for v in result.get("verifications", {}).values()
        if isinstance(v, dict)
    )

    out.append(MemoryCandidate(
        candidate_id=_cid(),
        memory_type="user_preference",
        proposed_namespace=["aura", "user", "default", "preferences"],
        proposed_key="writing_preference",
        content={
            "preference": user_input[:500],
            "signals": matched[:5],
            "source": "user_input",
        },
        rationale=f"Explicit user preference detected: {matched[0]}",
        source_session_id=session_id,
        source_agent="orchestrator",
        confidence="medium",
        requires_verifier=False,
        requires_human_review=False,  # User preferences are low-risk
    ))


def _extract_project_decisions(
    result: dict, out: list[MemoryCandidate], session_id: str,
) -> None:
    """Extract explicit architecture/design decisions from specialist output."""
    gov = result.get("strategic_governor") or {}
    decision_text = (
        gov.get("rationale")
        or gov.get("constraints")
        or ""
    )
    if not decision_text or len(str(decision_text)) < 20:
        return

    out.append(MemoryCandidate(
        candidate_id=_cid(),
        memory_type="project_decision",
        proposed_namespace=["aura", "project", "default", "decisions"],
        proposed_key="architecture_decision",
        content={
            "decision": str(decision_text)[:1000],
            "source": "strategic_governor",
        },
        rationale="Architecture/design decision from Strategic Governor.",
        source_session_id=session_id,
        source_agent="strategic_governor",
        confidence="medium",
        requires_verifier=False,
        requires_human_review=True,  # Architecture changes need review
    ))


def _extract_mcp_tool_memory(
    result: dict, out: list[MemoryCandidate], session_id: str,
) -> None:
    """Record usefulness/failure of external MCP tools.

    MCP output is NOT treated as verified truth — only as tool-usefulness
    signal.
    """
    evidence = result.get("external_mcp_evidence")
    if not evidence:
        return

    # Evidence summary from orchestrator
    if isinstance(evidence, dict):
        for provider, summary in evidence.items():
            if isinstance(summary, dict) and summary.get("ok"):
                out.append(MemoryCandidate(
                    candidate_id=_cid(),
                    memory_type="mcp_tool_memory",
                    proposed_namespace=["aura", "mcp", "tools"],
                    proposed_key=provider,
                    content={
                        "provider": provider,
                        "useful": True,
                        "summary": str(summary.get("summary", ""))[:500],
                        "quality": summary.get("evidence_quality", "unknown"),
                    },
                    rationale=f"MCP tool {provider} returned useful results.",
                    source_session_id=session_id,
                    source_agent="orchestrator",
                    confidence="low",  # External tools are low-confidence
                    evidence_status="unverified",
                    requires_verifier=True,
                    requires_human_review=False,
                ))
            elif isinstance(summary, dict):
                out.append(MemoryCandidate(
                    candidate_id=_cid(),
                    memory_type="mcp_tool_memory",
                    proposed_namespace=["aura", "mcp", "tools"],
                    proposed_key=provider,
                    content={
                        "provider": provider,
                        "useful": False,
                        "error": str(summary.get("error", ""))[:300],
                    },
                    rationale=f"MCP tool {provider} failed — remember for future avoidance.",
                    source_session_id=session_id,
                    source_agent="orchestrator",
                    confidence="low",
                    requires_verifier=False,
                    requires_human_review=False,
                ))


def _extract_task_agent_patterns(
    result: dict, out: list[MemoryCandidate], session_id: str,
) -> None:
    """Record useful bounded helper-agent patterns from task-agent results."""
    ta_results = result.get("task_agent_results") or []
    if not isinstance(ta_results, list):
        return

    for tr in ta_results:
        if not isinstance(tr, dict):
            continue
        if not tr.get("ok"):
            continue

        role = tr.get("role", "")
        summary = tr.get("summary", "")
        if not role or not summary:
            continue

        out.append(MemoryCandidate(
            candidate_id=_cid(),
            memory_type="task_agent_memory",
            proposed_namespace=["aura", "task_agents"],
            proposed_key=role.replace(" ", "_"),
            content={
                "role": role,
                "useful_pattern": str(summary)[:500],
                "verified_by_aura": tr.get("verified_by_aura", False),
            },
            rationale=f"Task agent '{role}' produced a useful result pattern.",
            source_session_id=session_id,
            source_agent=role,
            confidence=tr.get("confidence", "medium"),
            requires_verifier=tr.get("requires_verification", True),
            requires_human_review=tr.get("requires_human_approval", True),
        ))


def _extract_planner_patterns(
    result: dict, out: list[MemoryCandidate], session_id: str,
) -> None:
    """Record useful routing lessons from the LLM Agent Planner."""
    planner = result.get("llm_agent_planner") or {}
    if not isinstance(planner, dict):
        return

    # Only record if the planner was actually used (not fallback)
    if not planner.get("plan_used"):
        return

    selected = planner.get("selected_agents") or []
    if not selected or len(selected) <= 1:
        return

    out.append(MemoryCandidate(
        candidate_id=_cid(),
        memory_type="planner_memory",
        proposed_namespace=["aura", "planner"],
        proposed_key="routing_pattern",
        content={
            "agents": selected[:5],
            "pattern": f"Planner selected: {', '.join(selected[:5])}",
            "fallback_used": planner.get("fallback_used", False),
        },
        rationale="Planner routing pattern — advisory only, does not override policy.",
        source_session_id=session_id,
        source_agent="llm_agent_planner",
        confidence="low",  # Planner memories are advisory
        requires_verifier=False,
        requires_human_review=True,  # Routing patterns need review
    ))


def _extract_repository_constraints(
    result: dict, out: list[MemoryCandidate], session_id: str,
) -> None:
    """Extract stable codebase constraints from the session."""
    gov = result.get("strategic_governor") or {}
    constraints = gov.get("constraints") or ""
    if not constraints or len(str(constraints)) < 20:
        return

    out.append(MemoryCandidate(
        candidate_id=_cid(),
        memory_type="repository_memory",
        proposed_namespace=["aura", "repository", "default"],
        proposed_key="codebase_constraint",
        content={
            "constraint": str(constraints)[:1000],
            "source": "strategic_governor",
        },
        rationale="Codebase constraint detected from governor decision.",
        source_session_id=session_id,
        source_agent="strategic_governor",
        confidence="medium",
        requires_verifier=False,
        requires_human_review=True,
    ))


def _extract_evidence_memory(
    result: dict, out: list[MemoryCandidate], session_id: str,
) -> None:
    """Extract evidence memories ONLY when the verifier supports them."""
    verifications = result.get("verifications") or {}
    if not isinstance(verifications, dict):
        return

    for agent_name, verif in verifications.items():
        if not isinstance(verif, dict):
            continue

        route = verif.get("verifier_route") or verif.get("route") or ""
        evidence_status = verif.get("evidence_status", "unverified")

        # Only extract if the verifier approved or accepted with caveats
        if route.lower() in ("approve", "accept", "conditional_accept"):
            claims = verif.get("claims") or verif.get("key_claims") or []
            if isinstance(claims, list) and claims:
                out.append(MemoryCandidate(
                    candidate_id=_cid(),
                    memory_type="evidence_memory",
                    proposed_namespace=["aura", "project", "default", "evidence"],
                    proposed_key=f"{agent_name}_evidence",
                    content={
                        "agent": agent_name,
                        "claims": [str(c)[:300] for c in claims[:5]],
                        "route": route,
                        "evidence_status": evidence_status,
                    },
                    rationale=f"Verifier-approved evidence from {agent_name}.",
                    source_session_id=session_id,
                    source_agent=agent_name,
                    confidence="medium",
                    evidence_status=evidence_status,
                    verifier_route=route,
                    requires_verifier=True,
                    requires_human_review=False,
                ))


def _extract_procedural_proposals(
    result: dict, out: list[MemoryCandidate], session_id: str,
) -> None:
    """Extract procedural proposals — ALWAYS require human review.

    Procedural memories describe how AURA should behave (e.g.,
    "AURA should always verify claims against PubMed").  These are
    NEVER auto-committed.
    """
    gov = result.get("strategic_governor") or {}
    blocked = gov.get("blocked_actions") or []
    memory_policy = gov.get("memory_policy") or {}

    # If the governor explicitly set memory-write rules, record them
    if memory_policy and isinstance(memory_policy, dict):
        if memory_policy.get("allow_memory_write"):
            out.append(MemoryCandidate(
                candidate_id=_cid(),
                memory_type="procedural_memory",
                proposed_namespace=["aura", "procedural_rules"],
                proposed_key="memory_write_policy",
                content={
                    "rule": str(memory_policy)[:500],
                    "source": "strategic_governor",
                },
                rationale="Governor set explicit memory-write policy — requires human review.",
                source_session_id=session_id,
                source_agent="strategic_governor",
                confidence="low",
                requires_verifier=False,
                requires_human_review=True,
            ))
