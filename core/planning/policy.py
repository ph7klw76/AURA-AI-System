"""Policy validation for LLM-proposed agent plans.

Every plan the LLM proposes MUST pass this validator before the orchestrator
may act on it.  The validator enforces hard safety constraints — no plan,
however confident, can weaken AURA's integrity invariants.
"""

from __future__ import annotations

import os
from typing import Tuple

from .schemas import (
    AgentPlan,
    PLANNABLE_AGENTS,
    PLANNABLE_HELPER_TEMPLATES,
    PLANNABLE_MCP_PROVIDERS,
    PlanningContext,
    ValidatedAgentPlan,
)

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------
def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def _is_planner_enabled() -> bool:
    return _env_bool("AURA_LLM_PLANNER_ENABLED", False)


def _allow_external_mcp() -> bool:
    return _env_bool("AURA_LLM_PLANNER_ALLOW_EXTERNAL_MCP", False)


def _allow_task_agents() -> bool:
    return _env_bool("AURA_LLM_PLANNER_ALLOW_TASK_AGENTS", False)


def _require_policy() -> bool:
    return _env_bool("AURA_LLM_PLANNER_REQUIRE_POLICY", True)


def _require_verifier() -> bool:
    return _env_bool("AURA_LLM_PLANNER_REQUIRE_VERIFIER", True)


# ---------------------------------------------------------------------------
# High-risk / scientific / public-comms keyword sets (from schemas)
# ---------------------------------------------------------------------------
_HIGH_RISK = (
    "patent", "file patent", "legal advice", "medical diagnosis",
    "clinical trial", "drug", "therapy recommendation", "freedom to operate",
    "regulatory", "FDA", "EMA", "liability",
)
_SCIENTIFIC = (
    "hypothesis", "claim", "mechanism", "pathway", "evidence",
    "experiment", "result", "finding", "significance",
    "p value", "statistical", "correlation", "causation",
    "grant proposal", "manuscript", "paper submission",
    "peer review", "publication",
)
_EXTERNAL_ACTION_KEYWORDS = (
    "send", "email", "submit", "publish", "post", "tweet",
    "share", "export", "delete",
)
# Actions that must always be blocked (no planner override).
ALWAYS_BLOCKED: frozenset[str] = frozenset({
    "submit_grant",
    "file_patent",
    "send_email",
    "publish_content",        # noqa: S105 — blocked action, not a secret
    "github_write",
    "github_merge",
    "github_delete",
    "github_release",
    "memory_write",
    "profile_write",
    "self_evolution_approve",
    "shell_exec",
    "delete_file",
    "delete_folder",
})

# Tasks that always require human review irrespective of planner confidence.
_FORCE_HUMAN_REVIEW_KEYWORDS = (
    "patent", "legal", "regulatory", "FDA", "EMA",
    "clinical", "medical", "safety", "compliance",
)


def _task_has_scientific_claims(prompt: str, plan: AgentPlan) -> bool:
    combined = f"{prompt} {plan.task_type} {plan.rationale}".lower()
    return any(kw in combined for kw in _SCIENTIFIC)


def _task_is_high_risk(prompt: str, plan: AgentPlan) -> bool:
    combined = f"{prompt} {plan.task_type} {plan.rationale}".lower()
    if plan.risk_level == "high":
        return True
    return any(kw in combined for kw in _HIGH_RISK)


def _task_has_external_actions(prompt: str, plan: AgentPlan) -> bool:
    combined = f"{prompt} {plan.task_type}".lower()
    return any(kw in combined for kw in _EXTERNAL_ACTION_KEYWORDS)


def _task_needs_human_review(prompt: str, plan: AgentPlan) -> bool:
    combined = f"{prompt} {plan.task_type} {plan.rationale}".lower()
    return any(kw in combined for kw in _FORCE_HUMAN_REVIEW_KEYWORDS)


# ---------------------------------------------------------------------------
# Core validator
# ---------------------------------------------------------------------------
def validate_agent_plan(
    plan: AgentPlan, context: PlanningContext | None = None
) -> ValidatedAgentPlan:
    """Validate an LLM-proposed plan against all safety policy rules.

    Returns a ``ValidatedAgentPlan`` with ``ok=True`` only when the plan
    passes every rule.  Validation errors are structured — never raises.
    """
    errors: list[str] = []
    warnings: list[str] = []

    prompt = context.user_prompt if context else ""
    selected: list[str] = []
    helpers: list[str] = []
    mcp: list[str] = []
    verifier_required = plan.requires_verifier
    human_review_required = plan.requires_human_review
    risk_level = plan.risk_level
    blocked = sorted(set(plan.blocked_actions + list(ALWAYS_BLOCKED)))

    # ── Rule 1: unknown agents blocked ──
    if plan.primary_agent and plan.primary_agent not in PLANNABLE_AGENTS:
        errors.append(f"Primary agent '{plan.primary_agent}' is not a known AURA agent.")
    elif plan.primary_agent:
        selected.append(plan.primary_agent)

    for agent in plan.secondary_agents:
        if agent not in PLANNABLE_AGENTS:
            errors.append(f"Secondary agent '{agent}' is not a known AURA agent.")
        elif agent not in selected:
            selected.append(agent)

    # ── Rule 2: strategic_governor cannot be a downstream execution agent ──
    if "strategic_governor" in selected:
        errors.append("strategic_governor cannot be selected as a downstream execution agent.")
        selected = [a for a in selected if a != "strategic_governor"]

    # ── Rule 3: verifier cannot be disabled for scientific/evidence tasks ──
    if _task_has_scientific_claims(prompt, plan):
        if not verifier_required:
            errors.append(
                "Scientific claims detected — requires_verifier forced to True."
            )
            verifier_required = True
        if not plan.requires_verifier:
            warnings.append(
                "Planner set requires_verifier=False for a task with scientific claims; "
                "policy forced it to True."
            )

    if plan.external_mcp and not verifier_required:
        errors.append("External MCP evidence requires verifier.")
        verifier_required = True

    if plan.helper_agents and not verifier_required:
        errors.append("Task-agent helpers require verifier.")
        verifier_required = True

    if risk_level in ("medium", "high") and not verifier_required:
        errors.append(f"Risk level '{risk_level}' requires verifier.")
        verifier_required = True

    # ── Rule 4: high-risk → human review ──
    if _task_is_high_risk(prompt, plan) and not human_review_required:
        errors.append("High-risk task requires human review.")
        human_review_required = True

    if _task_needs_human_review(prompt, plan) and not human_review_required:
        errors.append("Patent/legal/regulatory/medical task requires human review.")
        human_review_required = True

    # ── Rule 5: external actions blocked ──
    if _task_has_external_actions(prompt, plan):
        for action in ("send_email", "submit_grant", "publish_content"):
            if action not in blocked:
                blocked.append(action)
        warnings.append(
            "Task involves external actions — submit/send/publish blocked."
        )

    # ── Rule 6: external MCP blocked unless explicitly enabled ──
    if plan.external_mcp:
        if not _allow_external_mcp():
            warnings.append(
                f"External MCP suggestions blocked (AURA_LLM_PLANNER_ALLOW_EXTERNAL_MCP=0): "
                f"{plan.external_mcp}"
            )
            mcp = []
        else:
            mcp = [
                p for p in plan.external_mcp if p in PLANNABLE_MCP_PROVIDERS
            ]
            unknown_mcp = [p for p in plan.external_mcp if p not in PLANNABLE_MCP_PROVIDERS]
            if unknown_mcp:
                warnings.append(f"Unknown MCP providers stripped: {unknown_mcp}")

    # ── Rule 7: task agents blocked unless explicitly enabled ──
    if plan.helper_agents:
        if not _allow_task_agents():
            warnings.append(
                f"Task-agent suggestions blocked (AURA_LLM_PLANNER_ALLOW_TASK_AGENTS=0): "
                f"{plan.helper_agents}"
            )
            helpers = []
        else:
            helpers = [
                h for h in plan.helper_agents if h in PLANNABLE_HELPER_TEMPLATES
            ]
            unknown_helpers = [
                h for h in plan.helper_agents
                if h not in PLANNABLE_HELPER_TEMPLATES
            ]
            if unknown_helpers:
                warnings.append(f"Unknown helper agents stripped: {unknown_helpers}")

    # ── Rules 8–13: always‑blocked actions ──
    for ba in ALWAYS_BLOCKED:
        if ba in plan.blocked_actions:
            continue  # already listed
        # Check if the plan implicitly needs this block
        if ba == "submit_grant" and "grant" in plan.task_type.lower():
            if ba not in blocked:
                blocked.append(ba)

    # ── Rule 14: low confidence → warning ──
    if plan.confidence == "low":
        warnings.append(
            "Planner confidence is low — fallback or human review preferred."
        )
        if not human_review_required and risk_level != "low":
            warnings.append("Low confidence + elevated risk — consider human review.")

    # ── Rule 15: verifier unconditional when global flag set ──
    if _require_verifier() and not verifier_required:
        warnings.append("Global AURA_LLM_PLANNER_REQUIRE_VERIFIER=1 forces verifier.")
        verifier_required = True

    # ── Always ensure scientific_verifier is appended if required ──
    if verifier_required and "scientific_verifier" not in selected:
        selected.append("scientific_verifier")

    # ── Normalise risk_level ──
    if risk_level not in ("low", "medium", "high"):
        risk_level = "low"

    ok = len(errors) == 0
    return ValidatedAgentPlan(
        ok=ok,
        plan=plan if ok else None,
        selected_agents=selected,
        helper_agents=helpers,
        external_mcp=mcp,
        evidence_requirement=plan.evidence_requirement,
        risk_level=risk_level,
        requires_verifier=verifier_required,
        requires_human_review=human_review_required,
        blocked_actions=blocked,
        validation_errors=errors,
        validation_warnings=warnings,
        fallback_used=False,
    )


# Public convenience
is_planner_enabled = _is_planner_enabled
allow_external_mcp = _allow_external_mcp
allow_task_agents = _allow_task_agents
