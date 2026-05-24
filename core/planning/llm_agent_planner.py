"""LLM-based agent planner — proposes agent plans for unhandled tasks.

The planner is ADVISORY only.  It proposes a plan; policy validates it;
the orchestrator executes only validated plans.  The planner never executes
anything directly.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .schemas import AgentPlan, PLANNABLE_AGENTS, PLANNABLE_HELPER_TEMPLATES, PLANNABLE_MCP_PROVIDERS, PlanningContext

logger = logging.getLogger(__name__)

_PLANNER_SYSTEM_PROMPT = """\
You are an advisory agent router for the AURA research assistant system.
Your role is to propose which AURA agents should handle a user's request.

**IMPORTANT: You are ADVISORY ONLY.** You propose. AURA policy validates.
The orchestrator executes. The Scientific Verifier judges. You do NOT
execute anything, call tools, or make final decisions.

You may only select agents from this list:
  {planable_agents}

You may only suggest helper agents from this list:
  {helper_templates}

You may only suggest external MCP evidence providers from this list:
  {mcp_providers}

You MUST NOT invent agents, tools, or providers not in these lists.

Respond with STRICT JSON matching this schema:
{{
  "task_type": "string — concise classification",
  "primary_agent": "string or null — the main agent to run first",
  "secondary_agents": ["list of additional existing agents"],
  "helper_agents": ["list of task-scoped helper suggestions"],
  "external_mcp": ["list of MCP evidence providers"],
  "evidence_requirement": "one of: low, basic, source_level_evidence",
  "risk_level": "low | medium | high",
  "requires_verifier": true,
  "requires_human_review": false,
  "blocked_actions": [],
  "rationale": "string — WHY you selected these agents",
  "confidence": "low | medium | high",
  "warnings": []
}}

Rules:
- ALWAYS set requires_verifier=true when evidence, claims, grants, patents,
  medical, or scientific analysis is involved.
- Set requires_human_review=true for patent, legal, medical, clinical, or
  regulatory tasks.
- blocked_actions should list actions that MUST be prevented (e.g. submit_grant,
  file_patent, send_email, github_write, memory_write, profile_write,
  self_evolution_approve).
- If you are unsure, prefer lower risk and more verification.
- Your rationale should briefly explain the agent selection logic.
"""


def propose_agent_plan(context: PlanningContext) -> AgentPlan:
    """Call the AURA LLM to propose an agent plan for the given context.

    Returns an ``AgentPlan``.  On any failure (LLM error, bad JSON, timeout)
    returns a plan with ``confidence="low"`` and a warning so the fallback
    can take over.
    """
    try:
        from core.llm import ask_json
    except ImportError:
        logger.warning("core.llm not available — returning low-confidence empty plan")
        return AgentPlan(
            confidence="low",
            warnings=["LLM module not available — planner cannot propose."],
        )

    user_prompt = _build_user_prompt(context)
    system_prompt = _PLANNER_SYSTEM_PROMPT.format(
        planable_agents=", ".join(sorted(PLANNABLE_AGENTS)),
        helper_templates=", ".join(sorted(PLANNABLE_HELPER_TEMPLATES)),
        mcp_providers=", ".join(sorted(PLANNABLE_MCP_PROVIDERS)),
    )

    try:
        raw_result = ask_json(system_prompt, user_prompt, temperature=0.1)
    except Exception as exc:
        logger.warning(f"LLM planner call failed: {exc}")
        return AgentPlan(
            confidence="low",
            warnings=[f"LLM call failed: {exc}"],
        )

    if not isinstance(raw_result, dict):
        return AgentPlan(
            confidence="low",
            warnings=[f"LLM returned non-dict: {type(raw_result).__name__}"],
        )

    try:
        plan = AgentPlan(**raw_result)
    except Exception as exc:
        logger.warning(f"Failed to parse LLM plan into AgentPlan: {exc}")
        plan = AgentPlan(
            confidence="low",
            warnings=[f"Plan parsing failed: {exc}"],
            rationale=str(raw_result)[:500] if raw_result else "",
        )
        # Try to salvage any agent names from the raw output
        for key in ("primary_agent", "secondary_agents"):
            val = raw_result.get(key)
            if isinstance(val, str) and val in PLANNABLE_AGENTS:
                plan.primary_agent = val
            elif isinstance(val, list):
                plan.secondary_agents = [v for v in val if v in PLANNABLE_AGENTS]

    return plan


def _build_user_prompt(context: PlanningContext) -> str:
    """Build the user-facing prompt for the planner LLM."""
    parts: list[str] = [
        f"USER REQUEST: {context.user_prompt}",
        "",
        f"Available agents: {', '.join(context.available_agents)}",
    ]

    if context.available_task_agent_templates:
        parts.append(
            f"Available helper templates: "
            f"{', '.join(context.available_task_agent_templates)}"
        )
    if context.available_mcp_providers:
        parts.append(
            f"Available MCP providers: "
            f"{', '.join(context.available_mcp_providers)}"
        )

    if context.governor_decision:
        gov = context.governor_decision
        gov_agents = gov.get("selected_agents") or []
        if gov_agents:
            parts.append(f"Governor suggests: {', '.join(gov_agents)}")
        gov_risk = gov.get("risk_level", "")
        if gov_risk:
            parts.append(f"Governor risk level: {gov_risk}")

    if context.risk_hints:
        parts.append(f"Risk hints: {'; '.join(context.risk_hints)}")
    if context.policy_hints:
        parts.append(f"Policy hints: {'; '.join(context.policy_hints)}")

    parts.append("\nPropose an agent execution plan as strict JSON.")
    return "\n".join(parts)
