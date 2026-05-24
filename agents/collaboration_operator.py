"""
AURA Collaboration Operator — Wave 3 specialist.

Identifies, evaluates, and PREPARES collaboration outreach. Drafts emails,
meeting agendas, and questions. Never sends, never schedules, never implies
institutional commitment. Always reviewed by the Scientific Verifier.

Public surface:
    run(user_input, context) -> dict (validates against CollaborationOperatorOutput)
    collaboration_operator = run   # alias matching reference signature
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from core.llm import ask_json
from core.memory import retrieve_relevant_memory
from core.schemas import CollaborationOperatorOutput


SYSTEM_PROMPT = """\
You are the AURA Collaboration Operator.

Your job is to help identify, evaluate, and PREPARE collaboration opportunities
for the user (a photophysics / OLED / TADF / organic electronics researcher).

You may:
- suggest possible collaborators (only when context supports them)
- explain why a collaboration may fit
- draft an email subject and body
- draft a meeting agenda
- prepare questions to ask
- identify risks and missing information

Hard rules — never break:
- DRAFT ONLY. Never send messages. Never schedule meetings.
- Never imply institutional commitment from the user's employer or funder.
- Never promise resources, funding, authorship, or formal partnership.
- Never represent the user or institution officially.
- NEVER invent collaborator names, papers, claims, or affiliations not present
  in the supplied context. If the user did not name a collaborator, return
  archetypes (e.g. "an OLED device-physics group with calibrated EQE setup")
  and explicitly mark them as suggestions.
- Always set approval_required_before_contacting = true.
- Be evidence-aware. Separate evidence from assumptions.
- Identify missing_information so the user knows what to verify.
- Include institutional_risk_notes (do not imply formal partnership, etc.).
- Return strict JSON only — no prose, no markdown fences.

Return JSON with EXACTLY this schema (no extra keys):
{
  "agent_name": "collaboration_operator",
  "summary": "...",
  "findings": ["..."],
  "assumptions": ["..."],
  "risks": ["..."],
  "recommended_actions": ["..."],
  "claims_for_verification": ["..."],
  "evidence_level": "none|weak|moderate|strong",
  "confidence": "low|medium|high",
  "approval_level": "none|draft_only|human_approval_required",

  "collaboration_goal": "...",
  "suggested_collaboration_type": "research_discussion|grant_collaboration|industry_partnership|student_exchange|technical_consultation|invited_talk|unknown",
  "possible_collaborators": ["..."],
  "collaborator_rationale": ["..."],
  "evidence_for_fit": ["..."],
  "missing_information": ["..."],

  "draft_email_subject": "...",
  "draft_email_body": "...",

  "meeting_agenda": ["..."],
  "questions_to_ask": ["..."],

  "approval_required_before_contacting": true,
  "institutional_risk_notes": ["..."]
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_context(value: Any, max_chars: int = 3000) -> str:
    try:
        text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]"
    return text


_TYPE_HINTS: list[tuple[str, list[str]]] = [
    ("grant_collaboration",   ["grant", "proposal", "funding", "co-pi", "co-investigator"]),
    ("industry_partnership",  ["company", "industry", "industrial partner", "corporate"]),
    ("student_exchange",      ["student exchange", "phd exchange", "student visit", "intern"]),
    ("technical_consultation", ["technical consultation", "consult", "advisory", "advisor"]),
    ("invited_talk",          ["invite speaker", "invited talk", "seminar", "webinar speaker", "guest lecture"]),
    ("research_discussion",   ["research discussion", "research collaborator", "co-author", "scientific partner"]),
]


def _infer_collaboration_type(user_input: str) -> str:
    text = (user_input or "").lower()
    for label, keywords in _TYPE_HINTS:
        if any(k in text for k in keywords):
            return label
    if "collaborat" in text or "partner" in text:
        return "research_discussion"
    return "unknown"


_CONTACT_INTENT_KEYWORDS: tuple[str, ...] = (
    "send email", "send the email", "send an email", "send it to",
    "send this to", "send out",
    "contact author", "contact collaborator", "contact researcher",
    "contact professor", "contact company",
    "contact the author", "contact the collaborator", "contact the researcher",
    "contact the partner",
    "schedule meeting", "schedule a meeting",
    "send invitation", "invite them",
    "reach out and", "reach out to",
)


def _detects_contact_intent(user_input: str) -> bool:
    text = (user_input or "").lower()
    return any(k in text for k in _CONTACT_INTENT_KEYWORDS)


def _scout_excerpt(scout_output: dict) -> str:
    """Defect 25: normalize Scout fields before iteration to avoid
    AttributeError when ``top_papers`` is a string / dict / None."""
    from core import normalization as _norm
    if not isinstance(scout_output, dict):
        return "{}"
    top_papers_raw = _norm.ensure_dict_list(
        scout_output.get("top_papers"), max_items=5,
    )
    top_papers = []
    for p in top_papers_raw:
        authors_raw = p.get("authors")
        authors = (
            authors_raw[:4] if isinstance(authors_raw, list) else []
        )
        top_papers.append({
            "title": _norm.ensure_str(p.get("title")),
            "source": _norm.ensure_str(p.get("source")),
            "authors": authors,
        })
    excerpt = {
        "summary": _norm.ensure_str(scout_output.get("summary"), max_len=400),
        "findings": _norm.ensure_str_list(
            scout_output.get("findings"), max_items=4,
        ),
        "top_papers": top_papers,
        "literature_scan_used": bool(scout_output.get("literature_scan_used", False)),
    }
    return _safe_context(excerpt, max_chars=1500)


def _fallback_output(error: Exception | str, collaboration_type: str, approval_level: str) -> dict:
    """Conservative fallback. Always sets approval_required_before_contacting=True
    and includes institutional risk notes."""
    message = str(error)
    return CollaborationOperatorOutput(
        summary="Collaboration Operator could not produce a fully validated collaboration plan.",
        findings=["Manual review is needed before using this collaboration output."],
        assumptions=["The collaborator fit may be incomplete without stronger evidence."],
        risks=[
            "Contacting people without approval could create reputational or institutional risk.",
            f"Internal error or validation issue: {message[:300]}",
        ],
        recommended_actions=[
            "Review the collaboration rationale before any contact.",
            "Verify collaborator identity and relevance independently.",
            "Do not send any message without explicit human approval.",
        ],
        claims_for_verification=[],
        evidence_level="weak",
        confidence="low",
        approval_level=approval_level if approval_level in (
            "none", "draft_only", "human_approval_required"
        ) else "draft_only",
        partial_results=True,
        failed_stage="llm_collaboration_plan",
        collaboration_goal="Draft a possible collaboration pathway (manual review required).",
        suggested_collaboration_type=collaboration_type if collaboration_type in (
            "research_discussion", "grant_collaboration", "industry_partnership",
            "student_exchange", "technical_consultation", "invited_talk", "unknown",
        ) else "unknown",
        possible_collaborators=[],
        collaborator_rationale=[],
        evidence_for_fit=[],
        missing_information=[
            "Verified collaborator expertise.",
            "Recent publications or projects relevant to the topic.",
            "Mutual benefit and time availability.",
        ],
        draft_email_subject="Draft collaboration inquiry — manual review required",
        draft_email_body=(
            "Dear [Name],\n\n"
            "I am exploring a possible research discussion related to [topic]. "
            "Before contacting you, I will review the fit and obtain approval.\n\n"
            "Best regards,\n[Your name — REVIEW BEFORE SENDING]"
        ),
        meeting_agenda=[],
        questions_to_ask=[],
        approval_required_before_contacting=True,
        institutional_risk_notes=[
            "Do not imply formal institutional support or endorsement.",
            "Do not promise funding, authorship, resources, or formal partnership.",
            "Verify identity and affiliation before any external contact.",
        ],
    ).model_dump()


def _enforce_safety_invariants(output: dict, approval_level: str) -> dict:
    """Force conservative safety fields regardless of LLM behaviour."""
    output["approval_required_before_contacting"] = True

    if approval_level in ("none", "draft_only", "human_approval_required"):
        output["approval_level"] = approval_level
    elif output.get("approval_level") not in ("none", "draft_only", "human_approval_required"):
        output["approval_level"] = "draft_only"

    # Always carry institutional risk notes.
    # Defect 28: a scalar string risk note must NOT become a per-character list.
    from core import normalization as _norm
    notes = _norm.ensure_str_list(output.get("institutional_risk_notes"))
    text = " ".join(notes).lower()
    if "institutional" not in text and "endorsement" not in text and "formal" not in text:
        notes.append(
            "Do not imply formal institutional support or endorsement on the user's behalf."
        )
    if "funding" not in text and "authorship" not in text and "partnership" not in text:
        notes.append(
            "Do not promise funding, authorship, resources, or formal partnership."
        )
    output["institutional_risk_notes"] = notes

    return output


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(user_input: str, context: dict | None = None) -> dict:
    """Generate a draft-only collaboration plan and outreach material."""
    ctx = context or {}
    collaboration_type = _infer_collaboration_type(user_input)
    approval_level = "human_approval_required" if _detects_contact_intent(user_input) else "draft_only"

    try:
        memory_records = retrieve_relevant_memory(user_input, limit=8) or []
    except Exception:
        memory_records = []

    scout_output = ctx.get("research_scout") or {}
    if not scout_output and isinstance(ctx.get("specialists"), dict):
        scout_output = ctx["specialists"].get("research_scout", {}) or {}

    grant_output = ctx.get("grant_architect") or {}
    if not grant_output and isinstance(ctx.get("specialists"), dict):
        grant_output = ctx["specialists"].get("grant_architect", {}) or {}

    influence_output = ctx.get("influence_public_communication") or {}
    if not influence_output and isinstance(ctx.get("specialists"), dict):
        influence_output = ctx["specialists"].get("influence_public_communication", {}) or {}

    user_prompt = (
        "User request:\n"
        f"{user_input}\n\n"
        f"Inferred collaboration type (from keywords): {collaboration_type}\n"
        f"Required approval_level (from contact-intent detection): {approval_level}\n\n"
        "Research Scout excerpt (use only collaborators / authors that actually appear here):\n"
        f"{_scout_excerpt(scout_output)}\n\n"
        "Grant Architect summary (optional):\n"
        f"{_safe_context({'summary': grant_output.get('summary',''), 'central_hypothesis': grant_output.get('central_hypothesis','')}, max_chars=400)}\n\n"
        "Influence/Public Communication summary (optional):\n"
        f"{_safe_context({'summary': influence_output.get('summary','')}, max_chars=200)}\n\n"
        "Relevant AURA memory:\n"
        f"{_safe_context(memory_records[:8], max_chars=1200)}\n\n"
    )

    # --- Inject verifier revision instructions if present (retry context) ---
    verifier_instructions = ctx.get("verifier_revision_instructions")
    if verifier_instructions and isinstance(verifier_instructions, list):
        user_prompt += (
            "Verifier Revision Instructions (address each before finalising):\n"
            + "\n".join(f"  - {v}" for v in verifier_instructions[:8])
            + "\n\n"
        )
    verifier_corrections = ctx.get("verifier_corrections")
    if verifier_corrections and isinstance(verifier_corrections, list):
        user_prompt += (
            "Verifier Corrections (mandatory fixes):\n"
            + "\n".join(f"  * {c}" for c in verifier_corrections[:5])
            + "\n\n"
        )
    verifier_risks = ctx.get("verifier_risks")
    if verifier_risks and isinstance(verifier_risks, list):
        user_prompt += (
            "Verifier Risks to Mitigate:\n"
            + "\n".join(f"  ! {r}" for r in verifier_risks[:5])
            + "\n\n"
        )

    user_prompt += (
        "Task: produce a DRAFT-ONLY collaboration plan matching the JSON schema. "
        "Do not invent collaborators not in the context. Always include "
        "institutional_risk_notes. Always set approval_required_before_contacting = true. "
        "Return strict JSON only."
    )

    try:
        raw = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.18)
    except Exception as exc:
        return _fallback_output(exc, collaboration_type, approval_level)

    if not isinstance(raw, dict):
        return _fallback_output("LLM returned non-dict output.", collaboration_type, approval_level)

    # Sanity check — reject empty / boilerplate dicts and fall back.
    _SUBSTANTIVE = (
        "summary", "collaboration_goal", "draft_email_subject", "draft_email_body",
        "possible_collaborators", "meeting_agenda", "questions_to_ask",
    )
    if not any(raw.get(f) for f in _SUBSTANTIVE):
        return _fallback_output(
            "LLM response contained no substantive collaboration fields.",
            collaboration_type, approval_level,
        )

    raw["agent_name"] = "collaboration_operator"
    raw = _enforce_safety_invariants(raw, approval_level)

    try:
        validated = CollaborationOperatorOutput.model_validate(raw)
    except ValidationError as exc:
        return _fallback_output(exc, collaboration_type, approval_level)

    return validated.model_dump()


# ---------------------------------------------------------------------------
# Compatibility alias — matches the reference signature
# ---------------------------------------------------------------------------

collaboration_operator = run
