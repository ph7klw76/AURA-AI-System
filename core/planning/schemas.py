"""Pydantic v2 schemas for the advisory LLM Agent Planner.

The planner proposes — policy validates — orchestrator executes — verifier judges.
All planner outputs are advisory and policy-gated.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Environment-based defaults (lazy — evaluated at runtime, not import time)
# ---------------------------------------------------------------------------
def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


# Pre-approved agent names — the planner may ONLY select from this set.
# strategic_governor is intentionally excluded (it controls, not executes).
PLANNABLE_AGENTS: frozenset[str] = frozenset({
    "research_scout",
    "grant_architect",
    "china_grant_architect",
    "teaching_mentor",
    "lab_data_analyst",
    "influence_public_communication",
    "collaboration_operator",
    "founder_innovation",
    "patent_intelligence",
    "scientific_verifier",
    "self_evolution_engine",
})

# Task-agent helper templates the planner may suggest (only if enabled).
PLANNABLE_HELPER_TEMPLATES: frozenset[str] = frozenset({
    "claim_extractor",
    "evidence_table_formatter",
    "query_variant_generator",
    "mcp_result_normalizer",
    "repo_issue_classifier",
    "competitor_name_extractor",
    "reviewer_objection_mapper",
    "risk_register_builder",
    "test_case_suggester",
    "local_document_excerpt_summarizer",
})

# MCP evidence providers the planner may suggest (only if enabled).
PLANNABLE_MCP_PROVIDERS: frozenset[str] = frozenset({
    "local_deep_research",
    "idea_reality",
    "github",
    "tooluniverse",
    "paper_qa",
    "jupyter_mcp_server",
})

# High-risk / safety-critical task keywords that force verifier + human review.
_HIGH_RISK_KEYWORDS: tuple[str, ...] = (
    "patent", "file patent", "legal advice", "medical diagnosis",
    "clinical trial", "drug", "therapy recommendation", "freedom to operate",
    "regulatory", "FDA", "EMA", "liability",
)
_SCIENTIFIC_KEYWORDS: tuple[str, ...] = (
    "hypothesis", "claim", "mechanism", "pathway", "evidence",
    "experiment", "result", "finding", "significance",
    "p value", "statistical", "correlation", "causation",
    "grant proposal", "manuscript", "paper submission",
    "peer review", "publication",
)
_PUBLIC_COMMS_KEYWORDS: tuple[str, ...] = (
    "publish", "tweet", "post", "blog", "press release",
    "linkedin", "twitter",
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class AgentPlan(BaseModel):
    """Raw LLM-proposed plan — advisory, not authoritative."""

    plan_id: str = Field(default_factory=lambda: f"plan-{os.urandom(4).hex()}")
    task_type: str = ""
    primary_agent: str | None = None
    secondary_agents: list[str] = Field(default_factory=list)
    helper_agents: list[str] = Field(default_factory=list)
    external_mcp: list[str] = Field(default_factory=list)
    evidence_requirement: str = "low"
    risk_level: Literal["low", "medium", "high"] = "low"
    requires_verifier: bool = True
    requires_human_review: bool = False
    blocked_actions: list[str] = Field(default_factory=list)
    rationale: str = ""
    confidence: Literal["low", "medium", "high"] = "medium"
    warnings: list[str] = Field(default_factory=list)


class ValidatedAgentPlan(BaseModel):
    """Policy-validated plan — safe for orchestrator consumption."""

    ok: bool
    plan: AgentPlan | None = None
    selected_agents: list[str] = Field(default_factory=list)
    helper_agents: list[str] = Field(default_factory=list)
    external_mcp: list[str] = Field(default_factory=list)
    evidence_requirement: str = "low"
    risk_level: Literal["low", "medium", "high"] = "low"
    requires_verifier: bool = True
    requires_human_review: bool = False
    blocked_actions: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    fallback_used: bool = False


class PlanningContext(BaseModel):
    """Context passed to the planner — describes the situation, not the decision."""

    user_prompt: str
    session_id: str | None = None
    governor_decision: dict[str, Any] | None = None
    available_agents: list[str] = Field(default_factory=lambda: sorted(PLANNABLE_AGENTS))
    available_task_agent_templates: list[str] = Field(
        default_factory=lambda: sorted(PLANNABLE_HELPER_TEMPLATES)
    )
    available_mcp_providers: list[str] = Field(
        default_factory=lambda: sorted(PLANNABLE_MCP_PROVIDERS)
    )
    risk_hints: list[str] = Field(default_factory=list)
    policy_hints: list[str] = Field(default_factory=list)


class PlannerDecisionRecord(BaseModel):
    """Audit record for planner decisions."""

    timestamp: str = ""
    session_id: str | None = None
    plan_id: str | None = None
    planner_enabled: bool = False
    raw_plan_hash: str | None = None
    validated: bool = False
    fallback_used: bool = False
    selected_agents: list[str] = Field(default_factory=list)
    helper_agents: list[str] = Field(default_factory=list)
    external_mcp: list[str] = Field(default_factory=list)
    risk_level: str | None = None
    requires_verifier: bool = True
    requires_human_review: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
