"""AURA Principles — in-system immutable contracts.

This module is AURA's own "constitution".  It declares contracts that
the rest of the system MUST honour, plus runtime assertion helpers that
verify those contracts at the point of execution.

Why this module exists
----------------------
Rules that live only in human-readable docs (README, CLAUDE.md) drift
silently as the code evolves.  Rules expressed as Python constants and
``assert_*`` helpers cannot drift — every deep_research run executes
them, and any code change that violates the contract fails fast.

If you are about to modify a constant here, STOP.  These represent
explicit user agreements.  Re-confirm with the user first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final


# ===========================================================================
# Deep Research — 16-section structured report (IMMUTABLE)
# ===========================================================================
#
# Source of truth: user spec, 2026-05-18.
# See also: ``qwen_evolver/deep_research/rigor.py`` and
#           ``qwen_evolver/deep_research/orchestrator.py``.
#
# Every successful ``run_research(mission)`` MUST write exactly ONE
# markdown file at ``reports/deep_research/<mission_id>_report.md``
# containing all 16 numbered sections below, in this exact order, with
# the spec's exact titles.  Empty sections MUST be emitted with the
# literal placeholder ``_(not derivable from current evidence)_`` —
# never skipped.

# ===========================================================================
# Canonical specialist execution order (SINGLE SOURCE OF TRUTH)
# ===========================================================================
#
# Both the Strategic Governor (which reorders ``selected_agents`` for
# display + consistency) and the orchestrator (which actually executes
# the workflow) MUST derive their ordering from THIS tuple, so the
# control plane (what the Governor reports) and the data plane (what the
# orchestrator runs) can never silently disagree (review finding 6).
#
# Order is DEPENDENCY-DRIVEN: evidence producers (research_scout,
# patent_intelligence) run before the consumers that cite their output
# (grant_architect, china_grant_architect, founder_innovation, ...).
# china_grant_architect sits immediately after grant_architect — it is
# a mutually-exclusive sibling, never both in one run (review finding 7).
#
# Special agents (memory_retriever, scientific_verifier,
# self_evolution_engine, human_approval_governor) are NOT specialists
# and are orchestration-owned — they are appended by each consumer as
# needed, NOT listed here.
CANONICAL_AGENT_ORDER: Final[tuple[str, ...]] = (
    "research_scout",
    "patent_intelligence",
    "grant_architect",
    "china_grant_architect",
    "lab_data_analyst",
    "teaching_mentor",
    "influence_public_communication",
    "collaboration_operator",
    "founder_innovation",
)


DEEP_RESEARCH_REPORT_SECTIONS: Final[tuple[str, ...]] = (
    "Title",
    "Executive Summary",
    "Research Objective",
    "Scope and Assumptions",
    "Methodology",
    "Background and Context",
    "Core Research Questions",
    "Key Findings",
    "Deep Analysis",
    "Competing Interpretations",
    "Risks, Limitations, and Uncertainties",
    "Synthesis",
    "Conclusion",
    "Recommendations or Strategic Implications",
    "References",
    "Appendix",
)
assert len(DEEP_RESEARCH_REPORT_SECTIONS) == 16, (
    "DEEP_RESEARCH_REPORT_SECTIONS must contain exactly 16 sections — "
    "this is an immutable user-agreed contract."
)

DEEP_RESEARCH_EMPTY_PLACEHOLDER: Final[str] = (
    "_(not derivable from current evidence)_"
)

# The canonical filename for the unified deep_research report.  There
# is exactly ONE markdown file per mission — the rigorous 16-section
# format IS the report.  No ``_rigorous_report.md`` companion file.
DEEP_RESEARCH_REPORT_FILENAME_TEMPLATE: Final[str] = "{mission_id}_report.md"


@dataclass(frozen=True)
class DeepResearchContract:
    """Immutable record of the deep_research output contract."""
    sections: tuple[str, ...] = DEEP_RESEARCH_REPORT_SECTIONS
    empty_placeholder: str = DEEP_RESEARCH_EMPTY_PLACEHOLDER
    filename_template: str = DEEP_RESEARCH_REPORT_FILENAME_TEMPLATE
    rationale: tuple[str, ...] = field(default_factory=lambda: (
        "16-section layout is the user's explicit spec.",
        "Exactly ONE report file per mission (no _rigorous_report.md "
        "companion). Two files caused user confusion.",
        "Empty sections use a placeholder so structural contract holds.",
        "No silent opt-out: AURA_DEEP_RESEARCH_RIGOR=0 is a degraded "
        "test-mode toggle only — the file is still written.",
        "Pipeline failures degrade to a placeholder report; they never "
        "skip the file.",
        "Additive only: never mutates verifier / memory / persistence.",
        "Confidence is evidence-driven, not LLM-driven.",
        "Seven-gate final check is mandatory and surfaced explicitly.",
    ))


DEEP_RESEARCH_CONTRACT: Final[DeepResearchContract] = DeepResearchContract()


# ---------------------------------------------------------------------------
# Runtime assertion helpers
# ---------------------------------------------------------------------------

class DeepResearchContractViolation(RuntimeError):
    """Raised when the 16-section deep_research contract is breached."""


def assert_deep_research_report_layout(markdown_text: str) -> None:
    """Verify a rendered markdown report honours the 16-section contract.

    Every section heading from ``DEEP_RESEARCH_REPORT_SECTIONS`` MUST
    appear as a ``## <n>. <title>`` line (case-sensitive on the
    section number; the title is matched as a prefix to tolerate
    suffix annotations like '(per-source quality)').

    Raises:
        DeepResearchContractViolation: if any section is missing or
        out-of-order.
    """
    last_index = -1
    for i, name in enumerate(DEEP_RESEARCH_REPORT_SECTIONS, start=1):
        needle = f"## {i}. {name}"
        idx = markdown_text.find(needle)
        if idx < 0:
            raise DeepResearchContractViolation(
                f"Section {i} ('{name}') missing from rendered report. "
                f"This is an immutable contract — see "
                f"core/aura_principles.py."
            )
        if idx < last_index:
            raise DeepResearchContractViolation(
                f"Section {i} ('{name}') appears out of order in the "
                f"rendered report. See core/aura_principles.py."
            )
        last_index = idx


def assert_single_report_file(reports_dir: Path, mission_id: str) -> None:
    """Verify exactly ONE report markdown file exists for a mission.

    The unified contract forbids a ``_rigorous_report.md`` companion
    file: two files caused user confusion in production.
    """
    main = reports_dir / DEEP_RESEARCH_REPORT_FILENAME_TEMPLATE.format(
        mission_id=mission_id,
    )
    companion = reports_dir / f"{mission_id}_rigorous_report.md"
    if companion.exists():
        raise DeepResearchContractViolation(
            f"Companion file {companion.name} exists. The deep_research "
            f"contract requires exactly ONE report file per mission. "
            f"Delete {companion.name} or fix the orchestrator. See "
            f"core/aura_principles.py."
        )
    if not main.exists():
        raise DeepResearchContractViolation(
            f"Expected report {main.name} not written. See "
            f"core/aura_principles.py."
        )


def render_contract_summary() -> str:
    """Return a human-readable summary of the contract (for `aura --info`)."""
    lines = ["AURA Deep Research — 16-section report contract", "=" * 60]
    for i, name in enumerate(DEEP_RESEARCH_REPORT_SECTIONS, start=1):
        lines.append(f"  {i:>2}. {name}")
    lines.append("")
    lines.append("Rationale:")
    for r in DEEP_RESEARCH_CONTRACT.rationale:
        lines.append(f"  - {r}")
    return "\n".join(lines)


# ===========================================================================
# China Grant Proposal Architect — IMMUTABLE invariants
# ===========================================================================
#
# Source of truth: user spec, 2026-05-18 (Parts 1, 4, 7, 8, 9, 10, 13).
# See ``agents/china_grant_architect.py`` and
#     ``core/grant_templates/china_blueprint.py``.
#
# The China Grant Architect is a SPECIALISED submodule of the general
# Grant Architect.  It MUST NOT replace, weaken, or bypass any existing
# AURA capability.  It is modular, bounded, and additive.

CHINA_GRANT_PROPOSAL_SECTIONS: Final[tuple[str, ...]] = (
    "Call Metadata",
    "Applicant and Team Profile",
    "Project Title",
    "Abstract",
    "Keywords",
    "Background and Scientific Significance",
    "Literature Review and Research Gap Map",
    "Central Scientific Question",
    "Central Hypothesis",
    "Specific Objectives",
    "Research Content / Work Packages",
    "Methodology and Technical Route",
    "Innovation",
    "Preliminary Basis / Research Foundation",
    "Feasibility",
    "Timeline and Milestones",
    "Expected Outputs",
    "Risk Register and Mitigation",
    "Budget Logic and Task-to-Budget Mapping",
    "Ethics, Security, and Compliance",
    "Required Attachments Checklist",
    "Reviewer Simulation",
    "Submission-Readiness Score",
    "Final Weakness-Repair Plan",
)
assert len(CHINA_GRANT_PROPOSAL_SECTIONS) == 24, (
    "CHINA_GRANT_PROPOSAL_SECTIONS must contain exactly 24 sections — "
    "this is an immutable user-agreed contract."
)


# Reviewer-simulation roster (Part 7 §20).  Five reviewer personas, in
# this canonical order.
CHINA_GRANT_REVIEWER_ROSTER: Final[tuple[str, ...]] = (
    "novelty",
    "methods",
    "feasibility",
    "china_funder_fit",
    "budget_compliance",
)


# Competitiveness-score rubric (Part 7 §21).  Weights MUST sum to 100.
CHINA_GRANT_SCORE_RUBRIC: Final[dict[str, int]] = {
    "call_alignment": 15,
    "scientific_significance": 15,
    "originality_innovation": 15,
    "hypothesis_clarity": 10,
    "methodological_rigor": 15,
    "feasibility": 10,
    "research_foundation": 8,
    "budget_logic": 4,
    "risk_mitigation": 4,
    "compliance_completeness": 4,
}
assert sum(CHINA_GRANT_SCORE_RUBRIC.values()) == 100, (
    "CHINA_GRANT_SCORE_RUBRIC weights must sum to 100 — "
    "Part 7 §21 of the user spec."
)


# Submission-readiness decision bands (Part 7 §21).
CHINA_GRANT_DECISION_BANDS: Final[tuple[tuple[int, str], ...]] = (
    (90, "competitive / strong submission candidate"),
    (80, "promising but needs targeted strengthening"),
    (70, "vulnerable proposal"),
    (0,  "not submission-ready"),
)


# Forbidden actions (Part 1 §5, Part 8).  The module MUST refuse these
# even if the user prompt implies them.
CHINA_GRANT_FORBIDDEN_ACTIONS: Final[tuple[str, ...]] = (
    "submit grant to a funder",
    "fabricate citation",
    "fabricate preliminary data",
    "fabricate collaborator commitment",
    "fabricate institutional commitment",
    "fabricate eligibility approval",
    "misrepresent funder rule",
    "alter official file without user approval",
    "represent the user institutionally",
)

# Compact intent-patterns used by the RUNTIME guard to catch a forbidden
# action regardless of the exact phrasing an LLM emits.  The list above
# is the human-readable contract; this list is the matching surface.
# Each entry is a lowercase substring — if ANY appears in a recommended
# action's description, the action is blocked.  Kept deliberately broad
# (e.g. "submit grant" catches "submit the grant to the funder",
# "submit grant to funder", "submit grant immediately", etc.).
CHINA_GRANT_FORBIDDEN_INTENT_PATTERNS: Final[tuple[str, ...]] = (
    "submit grant", "submit the grant", "submit proposal",
    "submit the proposal", "submit to the funder", "submit to funder",
    "submit application", "submit the application",
    "fabricate", "invent citation", "invent a citation",
    "fake citation", "fabricated data", "invent data", "invent results",
    "make up data", "make up results", "fabricate preliminary",
    "invent collaborator", "fake collaborator", "invent institutional",
    "misrepresent", "falsify", "forge",
    "alter official", "modify official file", "edit official file",
    "change official file",
    "represent the user", "act on behalf of the user",
    "impersonate the user", "act as the applicant",
)


# Template-override priority order (Part 10).  Lower-numbered layers win.
CHINA_GRANT_OVERRIDE_PRIORITY: Final[tuple[str, ...]] = (
    "specific_call_requirements",   # 1 — strongest
    "user_override_preferences",    # 2
    "china_grant_master_template",  # 3
    "universal_aura_grant_logic",   # 4 — weakest fallback
)


@dataclass(frozen=True)
class ChinaGrantContract:
    """Immutable record of the China Grant Architect contract."""
    sections: tuple[str, ...] = CHINA_GRANT_PROPOSAL_SECTIONS
    reviewer_roster: tuple[str, ...] = CHINA_GRANT_REVIEWER_ROSTER
    score_rubric: dict[str, int] = field(
        default_factory=lambda: dict(CHINA_GRANT_SCORE_RUBRIC),
    )
    decision_bands: tuple[tuple[int, str], ...] = CHINA_GRANT_DECISION_BANDS
    forbidden_actions: tuple[str, ...] = CHINA_GRANT_FORBIDDEN_ACTIONS
    override_priority: tuple[str, ...] = CHINA_GRANT_OVERRIDE_PRIORITY
    rationale: tuple[str, ...] = field(default_factory=lambda: (
        "24-section China proposal blueprint reflects user spec Part 5.",
        "Five-reviewer simulation reflects user spec Part 7 §20.",
        "Score weights sum to 100 per Part 7 §21 — must not be edited "
        "to imply different significance.",
        "Module is ADDITIVE: never replaces general Grant Architect, "
        "Scientific Verifier, Strategic Governor, Memory, or Self-"
        "Evolution Engine.",
        "Module always returns approval_level='draft_only' — it can "
        "draft, critique, simulate, score; it can NEVER submit.",
        "All forbidden actions hard-blocked (Part 8).",
        "User overrides are stored as layered template, never as a "
        "destructive replacement of the master blueprint (Part 10).",
    ))


CHINA_GRANT_CONTRACT: Final[ChinaGrantContract] = ChinaGrantContract()


# ---------------------------------------------------------------------------
# Runtime assertion helpers — China Grant Architect
# ---------------------------------------------------------------------------

class ChinaGrantContractViolation(RuntimeError):
    """Raised when the China-grant architect contract is breached."""


def classify_competitiveness(score: int | float) -> str:
    """Return the decision-band label for a 0-100 competitiveness score."""
    try:
        s = int(round(float(score)))
    except (TypeError, ValueError):
        return "not submission-ready"
    for floor, label in CHINA_GRANT_DECISION_BANDS:
        if s >= floor:
            return label
    return "not submission-ready"


def assert_china_grant_draft_contract(draft: dict) -> None:
    """Verify a ChinaGrantArchitectOutput-shaped dict honours the contract.

    Validation is *structural and fail-closed where present*.  A partial /
    fallback draft may legitimately omit the reviewer simulation or
    competitiveness score (those bypass this gate via ``_china_fallback``),
    so this helper does NOT require their PRESENCE — but when they ARE
    present it validates them strictly, because the assembled draft path
    always emits publication-grade structures.

    Enforces:
      * approval_level == 'draft_only' (Part 1 §5 — never submits).
      * Reviewer simulation, WHEN PRESENT, is exactly the five canonical
        personas in canonical roster order (Part 7 §20).
      * Competitiveness sub-scores, WHEN PRESENT, cover EXACTLY the rubric
        axes (no missing, no extra), each within its rubric weight bound,
        with a ``total`` in 0..100 (Part 7 §21).
      * No forbidden action label appears in recommended_actions.

    Raises:
        ChinaGrantContractViolation on any breach.
    """
    if not isinstance(draft, dict):
        raise ChinaGrantContractViolation(
            "China grant draft must be a dict (model_dump())."
        )
    approval = draft.get("approval_level")
    if approval != "draft_only":
        raise ChinaGrantContractViolation(
            f"approval_level must be 'draft_only', got {approval!r}. "
            "The China Grant Architect can never escalate to "
            "human_approval_required — it drafts, never submits."
        )
    reviewers = draft.get("reviewer_simulation") or []
    if reviewers:
        got = [str(r.get("reviewer_kind", "")).strip().lower()
               for r in reviewers if isinstance(r, dict)]
        if tuple(got) != CHINA_GRANT_REVIEWER_ROSTER:
            raise ChinaGrantContractViolation(
                f"Reviewer roster must be the five canonical personas in "
                f"canonical order {CHINA_GRANT_REVIEWER_ROSTER}, got "
                f"{tuple(got)}."
            )
    score = draft.get("competitiveness_score") or {}
    if isinstance(score, dict) and score.get("subscores"):
        sub = score["subscores"]
        if isinstance(sub, dict):
            rubric_axes = set(CHINA_GRANT_SCORE_RUBRIC)
            present_axes = set(sub)
            extra = present_axes - rubric_axes
            missing = rubric_axes - present_axes
            if extra or missing:
                raise ChinaGrantContractViolation(
                    "Competitiveness sub-scores must cover EXACTLY the "
                    f"rubric axes (Part 7 §21). extra={sorted(extra)} "
                    f"missing={sorted(missing)}."
                )
            # Each axis value must lie within [0, its rubric weight].
            for axis, weight in CHINA_GRANT_SCORE_RUBRIC.items():
                try:
                    val = float(sub[axis])
                except (TypeError, ValueError):
                    raise ChinaGrantContractViolation(
                        f"Competitiveness sub-score for {axis!r} is "
                        f"non-numeric: {sub[axis]!r}."
                    )
                if val < 0 or val > weight:
                    raise ChinaGrantContractViolation(
                        f"Competitiveness sub-score for {axis!r} = {val} is "
                        f"outside its rubric bound [0, {weight}] (Part 7 §21)."
                    )
        # Total, when present, must be a valid 0..100 score.
        if "total" in score:
            try:
                total_val = float(score["total"])
            except (TypeError, ValueError):
                raise ChinaGrantContractViolation(
                    f"Competitiveness total is non-numeric: {score['total']!r}."
                )
            if total_val < 0 or total_val > 100:
                raise ChinaGrantContractViolation(
                    f"Competitiveness total {total_val} is outside 0..100."
                )
    actions = draft.get("recommended_actions") or []
    for act in actions:
        if not isinstance(act, dict):
            continue
        desc = (act.get("description") or "").lower()
        # Match against the broad intent-patterns (robust to phrasing)
        # AND the exact human-readable contract strings (belt-and-braces).
        for pattern in (CHINA_GRANT_FORBIDDEN_INTENT_PATTERNS
                        + CHINA_GRANT_FORBIDDEN_ACTIONS):
            if pattern in desc:
                raise ChinaGrantContractViolation(
                    f"recommended_action would perform forbidden "
                    f"behaviour (matched pattern {pattern!r}): "
                    f"{desc[:120]!r}."
                )


def render_china_grant_contract_summary() -> str:
    """Return a human-readable summary (for `aura --info`)."""
    lines = [
        "AURA China Grant Architect — contract", "=" * 60,
        "24 proposal sections:",
    ]
    for i, name in enumerate(CHINA_GRANT_PROPOSAL_SECTIONS, start=1):
        lines.append(f"  {i:>2}. {name}")
    lines.append("")
    lines.append("5 simulated reviewers (canonical order):")
    for r in CHINA_GRANT_REVIEWER_ROSTER:
        lines.append(f"  - {r}")
    lines.append("")
    lines.append("Score rubric (sums to 100):")
    for axis, w in CHINA_GRANT_SCORE_RUBRIC.items():
        lines.append(f"  - {axis:<26} {w:>3}")
    lines.append("")
    lines.append("Decision bands:")
    for floor, label in CHINA_GRANT_DECISION_BANDS:
        lines.append(f"  - >= {floor:>3} : {label}")
    lines.append("")
    lines.append("Forbidden actions (hard-blocked):")
    for f in CHINA_GRANT_FORBIDDEN_ACTIONS:
        lines.append(f"  - {f}")
    lines.append("")
    lines.append("Template override priority (1 wins over 4):")
    for i, layer in enumerate(CHINA_GRANT_OVERRIDE_PRIORITY, start=1):
        lines.append(f"  {i}. {layer}")
    lines.append("")
    lines.append("Rationale:")
    for r in CHINA_GRANT_CONTRACT.rationale:
        lines.append(f"  - {r}")
    return "\n".join(lines)


__all__ = [
    # Deep research
    "DEEP_RESEARCH_REPORT_SECTIONS",
    "DEEP_RESEARCH_EMPTY_PLACEHOLDER",
    "DEEP_RESEARCH_REPORT_FILENAME_TEMPLATE",
    "DEEP_RESEARCH_CONTRACT",
    "DeepResearchContract",
    "DeepResearchContractViolation",
    "assert_deep_research_report_layout",
    "assert_single_report_file",
    "render_contract_summary",
    # China grant architect
    "CHINA_GRANT_PROPOSAL_SECTIONS",
    "CHINA_GRANT_REVIEWER_ROSTER",
    "CHINA_GRANT_SCORE_RUBRIC",
    "CHINA_GRANT_DECISION_BANDS",
    "CHINA_GRANT_FORBIDDEN_ACTIONS",
    "CHINA_GRANT_FORBIDDEN_INTENT_PATTERNS",
    "CHINA_GRANT_OVERRIDE_PRIORITY",
    "CHINA_GRANT_CONTRACT",
    "ChinaGrantContract",
    "ChinaGrantContractViolation",
    "classify_competitiveness",
    "assert_china_grant_draft_contract",
    "render_china_grant_contract_summary",
]
