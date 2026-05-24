"""Task-agent factory — deterministic proposal logic (no LLM).

Decides whether to create a task agent, route to an existing agent, or
block the request.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from .registry import (
    find_existing_agent_for_task,
    is_allowed_task_agent_role,
    is_forbidden_task_agent_role,
)
from .policy import is_task_agents_enabled, validate_agent_spec
from .schemas import AgentCreationDecision, AgentSpec, TaskAgentRequest


def propose_task_agent(request: TaskAgentRequest) -> AgentCreationDecision:
    """Determine whether a task-scoped agent should be created.

    Returns an ``AgentCreationDecision`` that either:
      * routes the task to an **existing** AURA agent (overlap detected),
      * **blocks** the request (forbidden role / disabled / policy fail), or
      * **proposes** a new ``AgentSpec`` (narrow allowed subtask).
    """
    warnings: list[str] = []

    # --- gate 0: globally disabled ---
    if not is_task_agents_enabled():
        return AgentCreationDecision(
            create_agent=False,
            reason="Task agents are disabled (AURA_TASK_AGENTS_ENABLED != 1).",
            warnings=warnings,
        )

    role = request.requested_role.strip().lower()

    # --- gate 1: forbidden role ---
    if is_forbidden_task_agent_role(role):
        return AgentCreationDecision(
            create_agent=False,
            reason=f"Role '{request.requested_role}' is explicitly forbidden.",
            warnings=warnings,
        )

    # --- gate 2: overlap with existing AURA agent (MUST precede allowed-role
    #     gate so broad tasks like "draft a grant" reliably route to existing
    #     agents even when the requested_role is generic like "helper"). ---
    existing = find_existing_agent_for_task(
        request.requested_role, request.subtask
    )
    if existing:
        return AgentCreationDecision(
            create_agent=False,
            reason=(
                f"Subtask '{request.subtask}' overlaps with existing AURA agent "
                f"'{existing}'.  Use the existing agent instead."
            ),
            use_existing_agent=existing,
            warnings=warnings,
        )

    # --- gate 3: not an allowed narrow task-agent role ---
    if not is_allowed_task_agent_role(role):
        return AgentCreationDecision(
            create_agent=False,
            reason=(
                f"Role '{request.requested_role}' is not in the pre-approved "
                "task-agent role list."
            ),
            warnings=warnings,
        )

    # --- gate 4: build and validate spec ---
    risk = _resolve_risk(request.risk_level)
    agent_id = f"task-{role}-{uuid.uuid4().hex[:8]}"
    spec = AgentSpec(
        agent_id=agent_id,
        name=role,
        purpose=f"Narrow helper: {request.subtask}",
        parent_session_id=request.parent_session_id,
        parent_agent=request.parent_agent,
        parent_task=request.subtask,
        subtask=request.subtask,
        created_by=request.parent_agent,
        allowed_tools=_resolve_tools(role),
        allowed_mcp_servers=[],
        forbidden_tools=[],
        risk_level=risk,
        max_steps=5,
        timeout_seconds=120,
        verifier_required=True,
        human_review_required=(risk == "high"),
        can_write_files=False,
        can_modify_memory=False,
        can_modify_profile=False,
        can_call_external_mcp=False,
        can_spawn_agents=False,
        persistence_allowed=False,
        created_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
    )

    ok, errors = validate_agent_spec(spec)
    if not ok:
        warnings.extend(errors)
        return AgentCreationDecision(
            create_agent=False,
            reason=f"Policy validation failed: {'; '.join(errors)}",
            warnings=warnings,
        )

    return AgentCreationDecision(
        create_agent=True,
        reason=f"Narrow subtask approved for task agent '{role}'.",
        proposed_spec=spec,
        warnings=warnings,
    )


def _resolve_risk(user_risk: str | None) -> str:
    risk = (user_risk or "low").strip().lower()
    if risk in ("high", "medium"):
        return risk
    return "low"


def _resolve_tools(role: str) -> list[str]:
    """Map each allowed role to its safe internal tool set."""
    role_map: dict[str, list[str]] = {
        "claim_extractor": ["aura.internal.claim_extract"],
        "evidence_table_formatter": ["aura.internal.evidence_format"],
        "query_variant_generator": ["aura.internal.query_generate"],
        "mcp_result_normalizer": ["aura.internal.mcp_normalize"],
        "repo_issue_classifier": ["aura.internal.issue_classify"],
        "competitor_name_extractor": ["aura.internal.competitor_extract"],
        "reviewer_objection_mapper": ["aura.internal.objection_map"],
        "risk_register_builder": ["aura.internal.risk_register"],
        "test_case_suggester": ["aura.internal.test_suggest"],
        "local_document_excerpt_summarizer": ["aura.internal.doc_summarize"],
    }
    return role_map.get(role, [])
