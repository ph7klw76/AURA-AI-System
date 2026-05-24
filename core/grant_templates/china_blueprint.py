"""China Grant Proposal Blueprint (template_id = CHINA_GRANT_PROPOSAL_BLUEPRINT_V1).

Persistent, user-adjustable template that the AURA China Grant Architect
uses as its drafting backbone.  Stored in three layers (Part 10 of the
spec):

    1. specific_call_requirements   (per-call override, strongest)
    2. user_override_preferences    (persisted per-user preference)
    3. china_grant_master_template  (this module — the default)
    4. universal_aura_grant_logic   (the general grant_architect — fallback)

The first three layers live in this module; the fourth is provided by
``agents/grant_architect.py`` and reached via the orchestrator.

This module never raises on bad user input — it returns the master
template (with a warning recorded) so the architect can still produce
a draft.  The contract that the resolved template MUST contain all 24
sections is enforced by ``core.aura_principles.CHINA_GRANT_PROPOSAL_SECTIONS``.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from core import memory as _memory
from core.aura_principles import CHINA_GRANT_PROPOSAL_SECTIONS


TEMPLATE_ID = "CHINA_GRANT_PROPOSAL_BLUEPRINT_V1"
TEMPLATE_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Master template (immutable defaults).  User edits NEVER mutate this dict
# in place — they accumulate in the override layers.
# ---------------------------------------------------------------------------

CHINA_GRANT_MASTER_TEMPLATE: dict[str, Any] = {
    "template_id": TEMPLATE_ID,
    "template_type": "grant_proposal_framework",
    "region_focus": "China",
    "status": "active",
    "user_adjustable": True,
    "version": "1.0",
    "schema_version": TEMPLATE_SCHEMA_VERSION,

    # --- The 24 main sections (Part 5 of the spec) -----------------------
    "sections": list(CHINA_GRANT_PROPOSAL_SECTIONS),

    # --- China-specific adjustable fields --------------------------------
    "fields": {
        "funding_body": "",
        "program_type": "",
        "discipline_code": "",
        "interdisciplinary_code": "",
        "title_language_requirement": "bilingual",       # zh + en
        "abstract_language_requirement": "bilingual",
        "keyword_language_requirement": "bilingual",
        "application_language": "zh",
        "grant_duration": "",
        "budget_mode": "category-based",
        "compliance_rules": [],
        "attachments_rules": [],
        "evaluation_rubric_override": {},
        "page_or_word_limits": {},
        "call_specific_section_order": [],
    },

    # --- Per-section drafting hints (used by the architect's prompt) -----
    # Each entry: short instruction for the section, optional must_include
    # bullet list, optional reviewer_traps to surface up-front.
    "section_hints": {
        "Project Title": {
            "instruction": "Produce formal, concise, and ambitious variants. "
                           "If application_language=zh, include a Chinese version.",
            "must_include": ["formal_title", "reviewer_friendly_title",
                             "ambitious_alternative"],
            "reviewer_traps": ["vague grandiosity", "too long", "buzzword salad"],
        },
        "Abstract": {
            "instruction": "Include problem, gap, hypothesis, objectives, "
                           "methods, innovation, expected contribution. "
                           "Provide a logic-audit table.",
            "must_include": ["full_technical_abstract", "concise_abstract"],
            "reviewer_traps": ["no quantified gap", "no falsifiable hypothesis"],
        },
        "Keywords": {
            "instruction": "Split into scientific keywords and funder-alignment "
                           "keywords. Flag too-broad and too-niche terms.",
            "must_include": ["scientific_keywords", "funder_alignment_keywords"],
            "reviewer_traps": ["only generic discipline terms",
                               "keywords absent from abstract"],
        },
        "Background and Scientific Significance": {
            "instruction": "Field status -> precise bottleneck -> unresolved gap "
                           "-> importance to fundamental science -> relevance to "
                           "funding scope -> why timely.",
            "reviewer_traps": ["unsupported 'breakthrough' claims",
                               "no contrast with state of the art"],
        },
        "Literature Review and Research Gap Map": {
            "instruction": "Produce a gap-map table: known | unresolved | "
                           "limitation | how addressed | evidence level | "
                           "reviewer vulnerability.",
        },
        "Central Scientific Question": {
            "instruction": "One main question + 2-4 sub-questions, all "
                           "answerable from the proposed experiments.",
        },
        "Central Hypothesis": {
            "instruction": "Primary hypothesis + alternatives + testable "
                           "predictions + falsification criteria.",
        },
        "Specific Objectives": {
            "instruction": "Overall objective + 3-5 measurable specific "
                           "objectives + objective-to-gap traceability table.",
        },
        "Research Content / Work Packages": {
            "instruction": "Each WP: title, objective, rationale, methods, "
                           "data expected, milestones, decision gate, risks, "
                           "mitigation, deliverable.",
        },
        "Methodology and Technical Route": {
            "instruction": "Per method: purpose, justification, procedure "
                           "logic, critical variables, controls, validation "
                           "method, expected evidence, failure modes, "
                           "backup plan.",
        },
        "Innovation": {
            "instruction": "Split conceptual / methodological / technical / "
                           "application. Each claim: what existed -> what is "
                           "new -> why it matters -> truly innovative vs "
                           "incremental.",
            "reviewer_traps": ["'first of its kind' without contrast",
                               "incremental framed as transformative"],
        },
        "Preliminary Basis / Research Foundation": {
            "instruction": "Research foundation narrative + team capability "
                           "narrative + evidence matrix (claim, support, "
                           "source, strength, weakness).",
        },
        "Feasibility": {
            "instruction": "Scientific / technical / timeline / personnel / "
                           "equipment feasibility, each with concrete "
                           "support.",
        },
        "Timeline and Milestones": {
            "instruction": "Year-by-year + optional quarter-by-quarter; "
                           "milestone table; stage outcomes; dependencies.",
        },
        "Expected Outputs": {
            "instruction": "Separate papers / datasets / methods / prototypes "
                           "/ training / collaboration / strategic. Do NOT "
                           "exaggerate publication counts.",
        },
        "Risk Register and Mitigation": {
            "instruction": "Per risk: probability, impact, early warning "
                           "signs, mitigation, fallback plan.",
        },
        "Budget Logic and Task-to-Budget Mapping": {
            "instruction": "Architecture + categories + justification + "
                           "task-to-budget mapping + reasonableness audit + "
                           "anticipated reviewer objections.",
        },
        "Ethics, Security, and Compliance": {
            "instruction": "Ethics review needs, human/animal involvement, "
                           "biosafety, sensitive data, S&T security, "
                           "institutional documentation, call-specific "
                           "certifications. Flag unsupported compliance "
                           "statements.",
        },
        "Required Attachments Checklist": {
            "instruction": "Mandatory / conditional / collaborator / CVs / "
                           "agreements / supporting materials. Output a "
                           "missing-item warning list.",
        },
    },

    # ------------------------------------------------------------------
    # Default presentation outline (A-P parts, items 1-36).
    # ------------------------------------------------------------------
    # This is the AURA default rendering style for the proposal markdown.
    # It groups the 24 underlying blueprint sections into 16 named PARTS
    # (A-P) carrying 36 numbered ITEMS, matching the user-supplied
    # rigorous outline.  The 24-section content contract still holds —
    # this layer only controls how that content is arranged on disk.
    #
    # Each item has:
    #   ``number`` : the 1-36 item number from the spec
    #   ``label``  : human-readable label that appears under the part
    #   ``source`` : where the renderer pulls content from.  One of
    #       - ``{"kind": "section",  "name": "<blueprint section name>"}``
    #         → pulls ``ChinaProposalSection.content`` for that section
    #       - ``{"kind": "titles",   "key":  "formal_en|reviewer_friendly_en|..."}``
    #         → pulls from ``out.titles[key]``
    #       - ``{"kind": "abstract", "key":  "full_en|concise_en|full_zh|logic_audit"}``
    #         → pulls from ``out.abstract[key]``
    #       - ``{"kind": "keywords"}``
    #         → renders all keyword categories
    #       - ``{"kind": "reviewer_simulation"}``
    #         → renders the 5 simulated reviewers
    #       - ``{"kind": "competitiveness"}``
    #         → renders the scorecard + band
    #       - ``{"kind": "weakness_repair"}``
    #         → renders the top-10 weakness repair plan
    #       - ``{"kind": "narrative", "text": "<placeholder text>"}``
    #         → renders the placeholder verbatim (used for items the
    #           24-section blueprint doesn't carry directly, e.g. the
    #           "Conceptual framework chain" in item 14).
    #
    # A user can override this whole outline (e.g. reorder, add parts,
    # change labels) by writing a patch via
    # ``agents.grant_architect.apply_china_template_patch({...})``.  The
    # 24-section content contract is enforced separately, so a malformed
    # outline patch can never strip evidence — the underlying draft
    # always exists.
    "presentation_outline": [
        {"letter": "A", "title": "Project Framing", "items": [
            {"number": 1, "label": "Three candidate project titles",
             "source": {"kind": "titles_triplet"}},
            {"number": 2, "label": "English title (+ optional Chinese title placeholder)",
             "source": {"kind": "titles_bilingual"}},
            {"number": 3, "label": "Full technical abstract",
             "source": {"kind": "abstract", "key": "full_en"}},
            {"number": 4, "label": "Concise abstract",
             "source": {"kind": "abstract", "key": "concise_en"}},
            {"number": 5, "label": "Keyword set",
             "source": {"kind": "keywords"}},
        ]},
        {"letter": "B", "title": "Scientific Rationale", "items": [
            {"number": 6, "label": "Background and significance",
             "source": {"kind": "section",
                        "name": "Background and Scientific Significance"}},
            {"number": 7, "label": "Literature-state summary",
             "source": {"kind": "section",
                        "name": "Literature Review and Research Gap Map"}},
            {"number": 8, "label": "Research gap map table",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 7)_"}},
        ]},
        {"letter": "C", "title": "Scientific Architecture", "items": [
            {"number": 9, "label": "Central question",
             "source": {"kind": "section",
                        "name": "Central Scientific Question"}},
            {"number": 10, "label": "Subquestions",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 9)_"}},
            {"number": 11, "label": "Central hypothesis",
             "source": {"kind": "section",
                        "name": "Central Hypothesis"}},
            {"number": 12, "label": "Specific objectives",
             "source": {"kind": "section",
                        "name": "Specific Objectives"}},
            {"number": 13, "label": "Objective-to-gap traceability matrix",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 12)_"}},
            {"number": 14, "label": "Conceptual framework chain",
             "source": {"kind": "narrative",
                        "text": "Molecular design → excited-state behavior "
                                "→ device architecture → optical output "
                                "→ photobiomodulation relevance."}},
        ]},
        {"letter": "D", "title": "Work Packages", "items": [
            {"number": 15, "label": "Design 4-5 work packages",
             "source": {"kind": "section",
                        "name": "Research Content / Work Packages"}},
            {"number": 16, "label": "Per-WP detail (objective, rationale, methods, "
                                    "outputs, risks, fallback, deliverables)",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 15)_"}},
        ]},
        {"letter": "E", "title": "Methodology", "items": [
            {"number": 17, "label": "Rigorous methodology",
             "source": {"kind": "section",
                        "name": "Methodology and Technical Route"}},
            {"number": 18, "label": "Missing methods or overclaims",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 17)_"}},
        ]},
        {"letter": "F", "title": "Innovation", "items": [
            {"number": 19, "label": "Innovation categories "
                                    "(conceptual / material / device / translational)",
             "source": {"kind": "section", "name": "Innovation"}},
            {"number": 20, "label": "Per-innovation strength (strong / moderate / weak)",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 19)_"}},
        ]},
        {"letter": "G", "title": "Preliminary Basis", "items": [
            {"number": 21, "label": "Research foundation (placeholders where "
                                    "user data is unavailable)",
             "source": {"kind": "section",
                        "name": "Preliminary Basis / Research Foundation"}},
            {"number": 22, "label": "Evidence matrix "
                                    "(claim → support → missing → evidence needed)",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 21)_"}},
        ]},
        {"letter": "H", "title": "Feasibility", "items": [
            {"number": 23, "label": "Scientific / technical / resource / "
                                    "timeline / applicant-fit feasibility",
             "source": {"kind": "section", "name": "Feasibility"}},
        ]},
        {"letter": "I", "title": "Timeline", "items": [
            {"number": 24, "label": "3-year timeline + milestones + critical "
                                    "dependencies + go/no-go points",
             "source": {"kind": "section",
                        "name": "Timeline and Milestones"}},
        ]},
        {"letter": "J", "title": "Expected Outcomes", "items": [
            {"number": 25, "label": "Realistic expected outputs",
             "source": {"kind": "section", "name": "Expected Outputs"}},
        ]},
        {"letter": "K", "title": "Risk Register", "items": [
            {"number": 26, "label": "Full risk table (risk, probability, impact, "
                                    "early warning, mitigation, contingency)",
             "source": {"kind": "section",
                        "name": "Risk Register and Mitigation"}},
        ]},
        {"letter": "L", "title": "Budget Logic", "items": [
            {"number": 27, "label": "Task-to-budget rationale (generic categories)",
             "source": {"kind": "section",
                        "name": "Budget Logic and Task-to-Budget Mapping"}},
            {"number": 28, "label": "No final numbers unless input is provided",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 27)_"}},
            {"number": 29, "label": "Reviewer vulnerabilities in the budget logic",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 27)_"}},
        ]},
        {"letter": "M", "title": "Compliance and Attachments", "items": [
            {"number": 30, "label": "China-grant compliance + attachments checklist",
             "source": {"kind": "section_pair",
                        "names": ["Ethics, Security, and Compliance",
                                  "Required Attachments Checklist"]}},
        ]},
        {"letter": "N", "title": "Reviewer Simulation", "items": [
            {"number": 31, "label": "At least five reviewers in canonical order",
             "source": {"kind": "reviewer_simulation"}},
            {"number": 32, "label": "Per reviewer: strengths, weaknesses, "
                                    "rejection concern, score, mandatory revision",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 31)_"}},
        ]},
        {"letter": "O", "title": "Competitiveness Score", "items": [
            {"number": 33, "label": "Proposal scored out of 100 across 10 axes",
             "source": {"kind": "competitiveness"}},
            {"number": 34, "label": "Decision band (competitive / promising / "
                                    "not submission-ready)",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 33)_"}},
        ]},
        {"letter": "P", "title": "Weakness Repair Plan", "items": [
            {"number": 35, "label": "Top 10 weaknesses",
             "source": {"kind": "weakness_repair"}},
            {"number": 36, "label": "Per weakness: why it matters, what to "
                                    "revise, evidence needed, how to rewrite",
             "source": {"kind": "narrative",
                        "text": "_(emitted inline within item 35)_"}},
        ]},
    ],

    # --- Reviewer simulation roster (Part 7 §20) ------------------------
    "reviewer_roster_notes": {
        "novelty": "Compare the proposed contribution to the state of the "
                   "art; flag every uncontrasted novelty claim.",
        "methods": "Challenge each method's controls, variables, validation "
                   "and failure modes.",
        "feasibility": "Attack timeline realism, equipment access, personnel "
                       "FTE, and dependency risk.",
        "china_funder_fit": "Read against the specific China call: theme "
                            "alignment, discipline code, language and "
                            "compliance, strategic priorities.",
        "budget_compliance": "Attack budget reasonableness, task-to-budget "
                             "mapping, attachments completeness, ethics and "
                             "security compliance.",
    },
}


# ---------------------------------------------------------------------------
# Persisted overrides
# ---------------------------------------------------------------------------

_USER_OVERRIDE_KIND = "china_grant_user_override"
_CALL_OVERRIDE_KIND = "china_grant_call_override"


def _load_latest_override(kind: str, scope: str = "") -> dict | None:
    """Return the most recent override of this kind, optionally filtered by scope.

    Overrides are JSONL-appended to the memory store so we can audit
    every user edit. ``scope`` lets callers store one per call (e.g.
    ``scope='NSFC_2026_general'``) or one per user (``scope='user'``).
    """
    try:
        records = _memory.read_jsonl(_memory.config.MEMORY_PATH, limit=200)
    except Exception:
        return None
    matches: list[dict] = []
    for rec in records:
        if rec.get("kind") != kind:
            continue
        meta = rec.get("metadata") or {}
        if scope and meta.get("scope") != scope:
            continue
        if meta.get("template_id") != TEMPLATE_ID:
            continue
        matches.append(rec)
    if not matches:
        return None
    # Most recent wins.
    latest = matches[-1]
    try:
        return json.loads(latest.get("content", "{}"))
    except json.JSONDecodeError:
        return None


def save_user_override(overrides: dict, *, scope: str = "user") -> None:
    """Persist a user-level override patch (Part 10).

    The patch is stored as a memory record so historical overrides are
    auditable.  Repeated calls do NOT overwrite past records — newer
    records take effect on next resolution.
    """
    payload = {
        "template_id": TEMPLATE_ID,
        "scope": scope,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "patch": overrides,
    }
    _memory.save_memory(
        kind=_USER_OVERRIDE_KIND,
        content=json.dumps({"patch": overrides}),
        metadata={
            "template_id": TEMPLATE_ID,
            "scope": scope,
            "schema_version": TEMPLATE_SCHEMA_VERSION,
        },
    )


def save_call_override(overrides: dict, *, scope: str) -> None:
    """Persist a per-call override patch (Part 10 priority 1)."""
    if not scope:
        raise ValueError("save_call_override requires a non-empty scope.")
    _memory.save_memory(
        kind=_CALL_OVERRIDE_KIND,
        content=json.dumps({"patch": overrides}),
        metadata={
            "template_id": TEMPLATE_ID,
            "scope": scope,
            "schema_version": TEMPLATE_SCHEMA_VERSION,
        },
    )


def _deep_merge(dst: dict, patch: dict) -> dict:
    """Recursive dict merge: patch overrides dst; lists in patch replace
    lists in dst (no concatenation, to keep override semantics
    predictable for the user)."""
    if not isinstance(patch, dict):
        return dst
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            dst[k] = _deep_merge(dst[k], v)
        else:
            dst[k] = copy.deepcopy(v)
    return dst


def resolve_template(
    *,
    call_scope: str = "",
    user_scope: str = "user",
) -> dict:
    """Resolve the effective template using the Part-10 priority order.

    Lower-numbered layers override higher-numbered ones:
      1. specific_call_requirements  (memory: china_grant_call_override)
      2. user_override_preferences   (memory: china_grant_user_override)
      3. china_grant_master_template (this module)
      4. universal_aura_grant_logic  (general grant_architect — used
         downstream, not merged into the template).
    """
    effective = copy.deepcopy(CHINA_GRANT_MASTER_TEMPLATE)

    user_patch = _load_latest_override(_USER_OVERRIDE_KIND, scope=user_scope)
    if isinstance(user_patch, dict):
        _deep_merge(effective, user_patch.get("patch", user_patch))

    if call_scope:
        call_patch = _load_latest_override(_CALL_OVERRIDE_KIND, scope=call_scope)
        if isinstance(call_patch, dict):
            _deep_merge(effective, call_patch.get("patch", call_patch))

    # Defensive: the contract requires all 24 master sections to remain
    # present even after overrides — drops here would corrupt the
    # architect's drafting loop.  We re-add any missing entries at the
    # end of the section list so a deliberate user reorder is preserved
    # but accidental deletion is healed.
    sections = effective.get("sections")
    if not isinstance(sections, list):
        effective["sections"] = list(CHINA_GRANT_PROPOSAL_SECTIONS)
    else:
        present = set(sections)
        for canonical in CHINA_GRANT_PROPOSAL_SECTIONS:
            if canonical not in present:
                sections.append(canonical)
        effective["sections"] = sections

    return effective


def list_active_overrides() -> dict:
    """Return a summary of which override layers are currently in effect.

    Lets the user see what they've patched without having to grep the
    memory store.  Useful from a /show-china-template slash command.
    """
    return {
        "template_id": TEMPLATE_ID,
        "user_override":
            _load_latest_override(_USER_OVERRIDE_KIND, scope="user"),
        "call_override_keys_seen": [
            rec.get("metadata", {}).get("scope", "")
            for rec in _memory.read_jsonl(_memory.config.MEMORY_PATH, limit=200)
            if rec.get("kind") == _CALL_OVERRIDE_KIND
        ],
    }


__all__ = [
    "TEMPLATE_ID",
    "TEMPLATE_SCHEMA_VERSION",
    "CHINA_GRANT_MASTER_TEMPLATE",
    "resolve_template",
    "save_user_override",
    "save_call_override",
    "list_active_overrides",
]
