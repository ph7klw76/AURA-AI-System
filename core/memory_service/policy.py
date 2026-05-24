"""Memory candidate classification and validation policy.

Applies all safety rules: secret blocking, verifier requirements,
human-review requirements, per-type policy gates.

Memory helps AURA remember.  Scientific Verifier decides trust.
Human review controls behavior-changing memory.  Policy controls what can be written.
"""
from __future__ import annotations

import re

from .config import MemoryServiceConfig, load_memory_service_config
from .schemas import MemoryCandidate, MemoryWriteDecisionResult


# ---------------------------------------------------------------------------
# Block-list patterns — these must NEVER be stored
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, str]] = [
    (r'sk-[a-zA-Z0-9_-]{20,}', "OpenAI-style API key"),
    (r'api[_-]?key\s*[:=]\s*["\']?\w{8,}["\']?', "API key assignment"),
    (r'Bearer\s+[A-Za-z0-9_\-\.]{20,}', "Bearer token"),
    (r'password\s*[:=]\s*["\']?\S+["\']?', "Password in content"),
    (r'token\s*[:=]\s*["\']?\S{12,}["\']?', "Token assignment"),
    (r'secret\s*[:=]\s*["\']?\S{8,}["\']?', "Secret assignment"),
    (r'-----BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE KEY-----', "Private key block"),
    (r'ghp_[A-Za-z0-9]{20,}', "GitHub personal access token"),
    (r'gho_[A-Za-z0-9]{20,}', "GitHub OAuth token"),
    (r'github_pat_[A-Za-z0-9_]{20,}', "GitHub fine-grained PAT"),
    (r'AKIA[0-9A-Z]{12,}', "AWS access key"),
    (r'AURA_MEMORY_SERVICE_URL\s*=\s*http', ".env content — AURA_MEMORY_SERVICE_URL"),
    (r'AURA_LLM_MCP_KEY\s*=', ".env content — LLM key"),
    (r'OPENAI_API_KEY\s*=', ".env content — OpenAI key"),
]

_COMBINED_SECRET_RE = re.compile(
    "|".join(f"(?P<p{i}>{p})" for i, (p, _) in enumerate(_SECRET_PATTERNS)),
    re.IGNORECASE,
)


def _contains_secret(text: str) -> tuple[bool, str]:
    """Check whether text contains any blocked secret pattern."""
    m = _COMBINED_SECRET_RE.search(text)
    if m:
        for i in range(len(_SECRET_PATTERNS)):
            if m.group(f"p{i}"):
                return True, _SECRET_PATTERNS[i][1]
    return False, ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_memory_candidate(
    candidate: MemoryCandidate,
    config: MemoryServiceConfig | None = None,
) -> MemoryCandidate:
    """Classify and enrich a memory candidate with policy metadata.

    This is a pure function — it marks the candidate but does not write.
    """
    # 1. Check for secrets / blocked content in the serialized candidate
    raw = str(candidate.content)
    is_secret, reason = _contains_secret(raw)
    if is_secret:
        candidate.blocked = True
        candidate.block_reason = f"Blocked: {reason}"
        return candidate

    # 2. Type-specific rules
    mt = candidate.memory_type

    if mt == "procedural_memory":
        candidate.requires_human_review = True

    elif mt == "evidence_memory":
        candidate.requires_verifier = True

    elif mt == "planner_memory":
        candidate.requires_human_review = True  # Routing changes need review
        candidate.confidence = "low"

    elif mt == "task_agent_memory":
        # Task agents cannot grant permissions
        content_str = str(candidate.content).lower()
        if any(kw in content_str for kw in (
            "permission", "sudo", "admin", "root", "token", "key",
            "bypass", "override", "grant access", "shell",
        )):
            candidate.blocked = True
            candidate.block_reason = (
                "Task-agent memory cannot grant permissions or access."
            )
        candidate.requires_human_review = True

    elif mt == "mcp_tool_memory":
        # MCP output is NOT truth
        candidate.confidence = "low"
        candidate.requires_verifier = True

    return candidate


def validate_memory_write(
    candidate: MemoryCandidate,
    config: MemoryServiceConfig | None = None,
) -> MemoryWriteDecisionResult:
    """Decide whether a memory candidate may be written.

    Returns a structured decision — never raises.
    """
    cfg = config or load_memory_service_config()

    # Already blocked by classifier
    if candidate.blocked:
        return MemoryWriteDecisionResult(
            candidate_id=candidate.candidate_id,
            approved=False,
            decision="blocked",
            reason=candidate.block_reason or "Blocked by policy.",
        )

    # Writes disabled
    if cfg.write_disabled:
        return MemoryWriteDecisionResult(
            candidate_id=candidate.candidate_id,
            approved=False,
            decision="blocked",
            reason="Memory writes are disabled.",
        )

    mt = candidate.memory_type

    # ── Procedural memory — ALWAYS requires human review ──
    if mt == "procedural_memory":
        if cfg.require_review_for_procedural:
            return MemoryWriteDecisionResult(
                candidate_id=candidate.candidate_id,
                approved=False,
                decision="needs_human_review",
                reason="Procedural memories always require human review.",
            )
        return MemoryWriteDecisionResult(
            candidate_id=candidate.candidate_id,
            approved=True,
            decision="approve",
            reason="Procedural memory approved (review requirement disabled).",
        )

    # ── Evidence memory — requires verifier ──
    if mt == "evidence_memory":
        if cfg.require_verifier_for_evidence:
            route = (candidate.verifier_route or "").lower()
            if route in ("reject", "human_review"):
                return MemoryWriteDecisionResult(
                    candidate_id=candidate.candidate_id,
                    approved=False,
                    decision="blocked",
                    reason=f"Evidence memory rejected: verifier route={route}.",
                )
            if route in ("approve", "accept", "conditional_accept"):
                if cfg.approved_only:
                    return MemoryWriteDecisionResult(
                        candidate_id=candidate.candidate_id,
                        approved=True,
                        decision="approve",
                        reason="Evidence memory — verifier approved.",
                    )
                else:
                    return MemoryWriteDecisionResult(
                        candidate_id=candidate.candidate_id,
                        approved=False,
                        decision="needs_human_review",
                        reason="Evidence memory requires human review in propose_only mode.",
                    )
            return MemoryWriteDecisionResult(
                candidate_id=candidate.candidate_id,
                approved=False,
                decision="needs_verifier",
                reason="Evidence memory needs verifier approval first.",
            )
        return MemoryWriteDecisionResult(
            candidate_id=candidate.candidate_id,
            approved=True,
            decision="approve",
            reason="Evidence memory (verifier requirement disabled).",
        )

    # ── MCP tool memory ──
    if mt == "mcp_tool_memory":
        if cfg.propose_only:
            return MemoryWriteDecisionResult(
                candidate_id=candidate.candidate_id,
                approved=False,
                decision="needs_human_review",
                reason="MCP tool memory — propose_only mode.",
            )
        return MemoryWriteDecisionResult(
            candidate_id=candidate.candidate_id,
            approved=True,
            decision="approve",
            reason="MCP tool memory — approved.",
        )

    # ── Planner memory — advisory, needs review ──
    if mt == "planner_memory":
        return MemoryWriteDecisionResult(
            candidate_id=candidate.candidate_id,
            approved=False,
            decision="needs_human_review",
            reason="Planner routing memory requires human review.",
        )

    # ── Task-agent memory ──
    if mt == "task_agent_memory":
        if cfg.propose_only:
            return MemoryWriteDecisionResult(
                candidate_id=candidate.candidate_id,
                approved=False,
                decision="needs_human_review",
                reason="Task-agent memory — propose_only mode.",
            )
        return MemoryWriteDecisionResult(
            candidate_id=candidate.candidate_id,
            approved=True,
            decision="approve",
            reason="Task-agent memory — approved.",
        )

    # ── Repository / project decision memory ──
    if mt in ("repository_memory", "project_decision"):
        candidate.requires_human_review = True
        return MemoryWriteDecisionResult(
            candidate_id=candidate.candidate_id,
            approved=False,
            decision="needs_human_review",
            reason=f"{mt} requires human/maintainer review.",
        )

    # ── User preference / research profile / project_memory ──
    # These are low-risk and can be auto-approved
    if mt in ("user_preference", "research_profile", "project_memory"):
        if cfg.approved_only:
            return MemoryWriteDecisionResult(
                candidate_id=candidate.candidate_id,
                approved=True,
                decision="approve",
                reason=f"{mt} — auto-approved.",
            )
        return MemoryWriteDecisionResult(
            candidate_id=candidate.candidate_id,
            approved=False,
            decision="needs_human_review",
            reason=f"{mt} — pending review in propose_only mode.",
        )

    # ── Unknown ──
    return MemoryWriteDecisionResult(
        candidate_id=candidate.candidate_id,
        approved=False,
        decision="blocked",
        reason=f"Unknown memory type: {mt}.",
    )
