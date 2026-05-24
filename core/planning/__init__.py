"""AURA Advisory LLM Agent Planner.

The planner is an optional, advisory layer that proposes agent execution
plans for tasks outside hard-coded routing.  It is **advisory only**:

    LLM proposes → policy validates → orchestrator executes → verifier judges

The planner is disabled by default (``AURA_LLM_PLANNER_ENABLED=0``).
When disabled, AURA behaviour is unchanged.

Public API — Stage 1 (standalone, no orchestrator integration):
    :func:`propose_agent_plan`   — call the LLM to propose a plan
    :func:`validate_agent_plan`  — policy-validate a proposed plan
    :func:`safe_fallback_plan`   — deterministic conservative fallback
    :func:`is_planner_enabled`   — check feature flag
"""

from __future__ import annotations

from .audit import (
    log_fallback_used,
    log_plan_validated,
    log_planner_disabled,
    log_planner_failed,
    log_planner_requested,
    log_planner_succeeded,
)
from .fallback import safe_fallback_plan
from .llm_agent_planner import propose_agent_plan
from .policy import is_planner_enabled, validate_agent_plan
from .schemas import (
    AgentPlan,
    PLANNABLE_AGENTS,
    PLANNABLE_HELPER_TEMPLATES,
    PLANNABLE_MCP_PROVIDERS,
    PlannerDecisionRecord,
    PlanningContext,
    ValidatedAgentPlan,
)

__all__ = [
    # schemas
    "AgentPlan",
    "ValidatedAgentPlan",
    "PlanningContext",
    "PlannerDecisionRecord",
    "PLANNABLE_AGENTS",
    "PLANNABLE_HELPER_TEMPLATES",
    "PLANNABLE_MCP_PROVIDERS",
    # core API
    "propose_agent_plan",
    "validate_agent_plan",
    "safe_fallback_plan",
    "is_planner_enabled",
    # audit
    "log_planner_disabled",
    "log_planner_requested",
    "log_planner_succeeded",
    "log_planner_failed",
    "log_plan_validated",
    "log_fallback_used",
]
