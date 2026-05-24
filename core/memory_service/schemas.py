"""Pydantic v2 schemas for the LangGraph Memory Service adapter.

These models define the shape of memory records, retrieval requests/results,
candidates, and write decisions.  They are deliberately separate from
``core/schemas.py`` (which handles AURA-internal memory) and do NOT replace
``MemoryRecord``, ``ReflectionRecord``, or any existing schema.
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Allowed memory types
# ---------------------------------------------------------------------------
ALLOWED_MEMORY_TYPES: tuple[str, ...] = (
    "user_preference",
    "research_profile",
    "project_decision",
    "project_memory",
    "evidence_memory",
    "procedural_memory",
    "mcp_tool_memory",
    "task_agent_memory",
    "planner_memory",
    "repository_memory",
    "unknown",
)
MemoryType = Literal[
    "user_preference",
    "research_profile",
    "project_decision",
    "project_memory",
    "evidence_memory",
    "procedural_memory",
    "mcp_tool_memory",
    "task_agent_memory",
    "planner_memory",
    "repository_memory",
    "unknown",
]
Confidence = Literal["low", "medium", "high"]
WriteDecision = Literal["approve", "reject", "revise", "needs_verifier", "needs_human_review", "blocked"]
WriteMode = Literal["disabled", "propose_only", "approved_only"]


# ---------------------------------------------------------------------------
# Core records
# ---------------------------------------------------------------------------

class AURAMemoryRecord(BaseModel):
    """A single memory record stored in LangGraph Memory Service."""
    memory_id: str = ""
    memory_type: MemoryType = "unknown"
    namespace: list[str] = Field(default_factory=list)
    key: str = ""
    content: dict[str, object] = Field(default_factory=dict)
    source_session_id: str = ""
    source_agent: str = ""
    confidence: Confidence = "medium"
    evidence_status: str = "unverified"
    verifier_route: str = ""
    requires_verifier: bool = False
    requires_human_review: bool = False
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class MemoryCandidate(BaseModel):
    """A proposed memory record — NOT yet written to the service."""
    candidate_id: str
    memory_type: MemoryType = "unknown"
    proposed_namespace: list[str] = Field(default_factory=list)
    proposed_key: str = ""
    content: dict[str, object] = Field(default_factory=dict)
    rationale: str = ""
    source_session_id: str = ""
    source_agent: str = ""
    confidence: Confidence = "medium"
    evidence_status: str = "unverified"
    verifier_route: str = ""
    requires_verifier: bool = False
    requires_human_review: bool = False
    blocked: bool = False
    block_reason: str = ""


class MemoryRetrievalRequest(BaseModel):
    """Request to retrieve memories from the service."""
    user_id: str = ""
    project_id: str = ""
    session_id: str = ""
    prompt: str
    agent_name: str = ""
    memory_types: list[MemoryType] = Field(default_factory=list)
    max_results: int = 8


class MemoryRetrievalResult(BaseModel):
    """Structured result from memory retrieval."""
    ok: bool = True
    memories: list[AURAMemoryRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    degraded: bool = False
    # Compact context string for agent consumption
    compact_context: str = ""


class MemoryWriteDecisionResult(BaseModel):
    """Decision on whether a memory candidate was committed."""
    candidate_id: str
    approved: bool = False
    decision: WriteDecision = "blocked"
    reason: str = ""
    reviewer: str = ""
    committed: bool = False
    memory_id: str = ""
