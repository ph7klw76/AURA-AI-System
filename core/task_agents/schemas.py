"""Pydantic v2 schemas for task-scoped agents.

AURA task agents are temporary, bounded helpers created by the orchestrator
to handle narrow subtasks.  They are NOT autonomous agents — they are limited
in scope, tools, steps, and cannot approve their own outputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class TaskAgentRequest(BaseModel):
    """A request to create (or route) a task-scoped agent."""

    parent_session_id: str
    parent_agent: str
    requested_role: str
    subtask: str
    context: dict[str, Any] = Field(default_factory=dict)
    desired_output_schema: dict[str, Any] | None = None
    requested_tools: list[str] = Field(default_factory=list)
    risk_level: str | None = None


class AgentSpec(BaseModel):
    """Immutable specification of a task-scoped agent.

    Every field that grants capability defaults to ``False`` — safe by default.
    """

    agent_id: str
    name: str
    purpose: str
    parent_session_id: str
    parent_agent: str
    parent_task: str
    subtask: str
    created_by: str

    # --- tool surface ---
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_mcp_servers: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)

    # --- schemas ---
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)

    # --- governance ---
    evidence_requirement: str = "low"
    risk_level: Literal["low", "medium", "high"] = "low"
    max_steps: int = 5
    timeout_seconds: int = 120
    verifier_required: bool = True
    human_review_required: bool = False

    # --- capabilities (ALL default False) ---
    can_write_files: bool = False
    can_modify_memory: bool = False
    can_modify_profile: bool = False
    can_call_external_mcp: bool = False
    can_spawn_agents: bool = False
    persistence_allowed: bool = False

    # --- lifecycle ---
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    expires_at: str | None = None


class AgentCreationDecision(BaseModel):
    """Result of attempting to propose a task agent."""

    create_agent: bool
    reason: str
    use_existing_agent: str | None = None
    proposed_spec: AgentSpec | None = None
    warnings: list[str] = Field(default_factory=list)


class TaskAgentResult(BaseModel):
    """Output produced by a task-scoped agent.

    ALL outputs are marked ``verified_by_aura=False`` and
    ``requires_verification=True``.  The Scientific Verifier is the sole
    authority that can approve an output for final use.
    """

    agent_id: str
    ok: bool
    subtask: str
    summary: str = ""
    findings: list[str] = Field(default_factory=list)
    evidence_records: list[dict[str, Any]] = Field(default_factory=list)
    claims_for_verification: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"
    requires_verification: bool = True
    verified_by_aura: bool = False
    route: str | None = None
