"""Role-overlap registry — prevents task agents from duplicating existing AURA agents.

Before creating any task-scoped agent, AURA MUST check whether an existing
top-level agent already covers that role.  Broad responsibilities stay with
the built-in agents; only narrow helper subtasks may become task agents.
"""

from __future__ import annotations

import re
from typing import FrozenSet

# ---------------------------------------------------------------------------
# Existing agent capability keywords
# ---------------------------------------------------------------------------
_EXISTING_AGENT_CAPABILITIES: dict[str, frozenset[str]] = {
    "strategic_governor": frozenset({
        "routing", "task classification", "agent selection",
        "risk level", "autonomy level", "evidence requirement",
        "workflow sequence", "governor", "route to",
    }),
    "research_scout": frozenset({
        "literature search", "search the literature", "paper search",
        "search for papers", "ideation",
        "gap analysis", "trend monitoring", "deep research",
        "grant opportunity scan", "research evidence",
        "literature review", "paper discovery",
    }),
    "scientific_verifier": frozenset({
        "verify claims", "verify the", "fact check", "evidence adequacy",
        "unsupported claims", "route decision", "claim audit",
        "verifier", "verification", "verify these",
    }),
    "grant_architect": frozenset({
        "grant draft", "specific aims", "significance",
        "innovation", "proposal structure", "reviewer framing",
        "grant writing", "proposal",
    }),
    "china_grant_architect": frozenset({
        "china grant", "china proposal",
    }),
    "teaching_mentor": frozenset({
        "teaching material", "lesson plan", "quiz",
        "rubric", "explanation", "teaching",
    }),
    "lab_data_analyst": frozenset({
        "data analysis", "analyze data", "methods", "statistics",
        "plotting", "reproducibility checks", "experiment data",
        "analyze this", "data from",
    }),
    "influence_public_communication": frozenset({
        "public communication", "public summary",
        "social message", "lay explanation", "media message",
    }),
    "collaboration_operator": frozenset({
        "collaboration", "outreach draft", "agenda",
        "collaborator identification",
    }),
    "founder_innovation": frozenset({
        "commercialization", "startup idea", "market",
        "competitor", "validation experiment",
        "business hypothesis", "commercial",
    }),
    "patent_intelligence": frozenset({
        "patent landscape", "patent search",
        "prior art reconnaissance", "IP white space",
        "patent", "freedom to operate",
    }),
    "self_evolution_engine": frozenset({
        "memory proposal", "profile update", "update memory",
        "learning from session", "self-improvement proposal",
        "evolution", "memory update", "update profile",
        "lessons from this session",
    }),
}

# ---------------------------------------------------------------------------
# Allowed / forbidden task-agent roles
# ---------------------------------------------------------------------------
_ALLOWED_ROLES: frozenset[str] = frozenset({
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

_FORBIDDEN_ROLES: frozenset[str] = frozenset({
    "research_scout_clone",
    "verifier_clone",
    "grant_architect_clone",
    "patent_agent_clone",
    "founder_agent_clone",
    "self_evolution_agent",
    "memory_writer_agent",
    "profile_editor_agent",
    "github_writer_agent",
    "autonomous_coder_agent",
    "shell_executor_agent",
})


def find_existing_agent_for_task(
    requested_role: str, subtask: str
) -> str | None:
    """Return the name of an existing AURA agent if *subtask* overlaps its
    responsibility, or ``None`` if no overlap is detected.

    Matching is keyword-based (case-insensitive, word-boundary) against each
    agent's capability set.
    """
    combined = f"{requested_role} {subtask}".lower()
    for agent_name, keywords in _EXISTING_AGENT_CAPABILITIES.items():
        for kw in keywords:
            # Word-boundary match so "patent" doesn't match "propatent"
            pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
            if pattern.search(combined):
                return agent_name
    return None


def is_allowed_task_agent_role(role: str) -> bool:
    """Return True if *role* is in the pre-approved task-agent list."""
    return (role or "").strip().lower() in _ALLOWED_ROLES


def is_forbidden_task_agent_role(role: str) -> bool:
    """Return True if *role* is explicitly blocked."""
    return (role or "").strip().lower() in _FORBIDDEN_ROLES


def list_allowed_roles() -> list[str]:
    return sorted(_ALLOWED_ROLES)


def list_existing_agent_capabilities() -> dict[str, list[str]]:
    return {k: sorted(v) for k, v in _EXISTING_AGENT_CAPABILITIES.items()}
