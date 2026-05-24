"""Deterministic fallback routing when the LLM planner fails or is disabled.

Fallback is conservative — it never selects more agents than needed and
always requires the Scientific Verifier for evidence-bearing tasks.
"""

from __future__ import annotations

import re

from .schemas import AgentPlan, ValidatedAgentPlan

# ---------------------------------------------------------------------------
# Keyword → agent mapping (conservative — one primary + verifier when needed)
# ---------------------------------------------------------------------------
_TASK_PATTERNS: list[tuple[str, str, bool]] = [
    # (regex pattern, primary_agent, needs_verifier)
    # NOTE: ordering matters — more-specific patterns must come first.
    (r"\b(?:china\s+grant|NSFC|MOST|国家自然科学基金)\b", "china_grant_architect", True),
    (r"\b(?:grant|proposal|funding|ERC|NIH|NSF|Horizon)\b", "grant_architect", True),
    (r"\b(?:patent|IP\s+landscape|prior\s+art|freedom\s+to\s+operate)\b",
     "patent_intelligence", True),
    (r"\b(?:commerciali[sz]|startup|market|product|business\s+model)\b",
     "founder_innovation", True),
    (r"\b(?:teach|lesson|quiz|rubric|explain\s+(?:this|the|a))\b",
     "teaching_mentor", False),
    (r"\b(?:data\s+(?:anal|from)|qPCR|statistic|plot|reproducib|experiment)\b",
     "lab_data_analyst", True),
    (r"\b(?:collaborat|outreach|agenda)\b",
     "collaboration_operator", False),
    (r"\b(?:public\s+commu|press\s+release|lay\s+summary|social\s+media)\b",
     "influence_public_communication", False),
    (r"\b(?:literature|paper|search|research\s+(?:on|about)|ideation|gap\s+anal)\b",
     "research_scout", True),
]

# Evidence-bearing task keywords that always force the verifier.
_EVIDENCE_KEYWORDS: tuple[str, ...] = (
    "grant", "proposal", "patent", "hypothesis", "claim",
    "experiment", "result", "finding", "clinical", "medical",
    "scientific", "research", "evidence", "mechanism",
)


def _task_is_evidence_bearing(prompt: str) -> bool:
    lower = prompt.lower()
    return any(kw in lower for kw in _EVIDENCE_KEYWORDS)


def safe_fallback_plan(
    prompt: str,
    governor_decision: dict | None = None,
) -> ValidatedAgentPlan:
    """Build a conservative, deterministic fallback plan.

    1. If a valid Governor decision exists with ``selected_agents``, use it.
    2. Otherwise, match keyword patterns → primary agent.
    3. Always append ``scientific_verifier`` for evidence-bearing tasks.
    4. Block all external actions.
    """
    # Prefer existing Governor output if it has selected_agents.
    if isinstance(governor_decision, dict):
        gov_agents = governor_decision.get("selected_agents") or []
        if gov_agents:
            selected = list(dict.fromkeys([a for a in gov_agents if a]))
            return ValidatedAgentPlan(
                ok=True,
                selected_agents=selected,
                helper_agents=[],
                external_mcp=[],
                evidence_requirement=governor_decision.get("evidence_requirement", "low"),
                risk_level=governor_decision.get("risk_level", "low") or "low",
                requires_verifier="scientific_verifier" in selected,
                requires_human_review=governor_decision.get("requires_human_review", False),
                blocked_actions=sorted(
                    set(governor_decision.get("blocked_actions", []))
                ),
                validation_warnings=[],
                fallback_used=True,
            )

    # Keyword-based fallback.
    primary: str | None = None
    needs_verifier = _task_is_evidence_bearing(prompt)

    for pattern, agent, verifier_needed in _TASK_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            primary = agent
            needs_verifier = needs_verifier or verifier_needed
            break

    if primary is None:
        # Unclear task → safest route: research_scout + verifier + human_review
        primary = "research_scout"
        needs_verifier = True

    selected = [primary]
    if needs_verifier and "scientific_verifier" not in selected:
        selected.append("scientific_verifier")

    is_high_risk = any(
        kw in prompt.lower()
        for kw in ("patent", "legal", "clinical", "medical", "regulatory")
    )

    return ValidatedAgentPlan(
        ok=True,
        plan=AgentPlan(
            task_type="unknown",
            primary_agent=primary,
            secondary_agents=selected[1:],
            rationale=f"Fallback plan — keyword-matched from prompt.",
            evidence_requirement="source_level_evidence" if needs_verifier else "low",
            risk_level="high" if is_high_risk else "medium" if needs_verifier else "low",
            requires_verifier=needs_verifier,
            requires_human_review=is_high_risk,
            blocked_actions=sorted({
                "submit_grant", "file_patent", "send_email",
                "github_write", "memory_write", "profile_write",
                "self_evolution_approve",
            }),
            confidence="medium",
        ),
        selected_agents=selected,
        helper_agents=[],
        external_mcp=[],
        evidence_requirement="source_level_evidence" if needs_verifier else "low",
        risk_level="high" if is_high_risk else "medium" if needs_verifier else "low",
        requires_verifier=needs_verifier,
        requires_human_review=is_high_risk,
        blocked_actions=sorted({
            "submit_grant", "file_patent", "send_email",
            "github_write", "memory_write", "profile_write",
            "self_evolution_approve",
        }),
        validation_warnings=["Plan generated by deterministic fallback (conservative)."],
        fallback_used=True,
    )
