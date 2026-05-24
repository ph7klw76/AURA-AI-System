"""
AURA Influence / Public Communication — Wave 2 specialist.

Drafts public-facing communication (LinkedIn posts, lay summaries, podcast
angles) WITHOUT publishing. Always carries an explicit publishing-approval
flag. Always reviewed by the Scientific Verifier.

Public surface:
    run(user_input, context) -> dict (validates against InfluencePublicCommunicationOutput)
    influence_public_communication = run   # alias matching reference signature
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from core.llm import ask_json
from core.memory import retrieve_relevant_memory
from core.schemas import InfluencePublicCommunicationOutput


SYSTEM_PROMPT = """\
You are the AURA Influence / Public Communication specialist.

Your job is to convert research ideas and outputs into RESPONSIBLE public-facing
communication drafts. You are useful for LinkedIn posts, lay summaries, podcast
angles, science storytelling, and industry-facing narratives.

Hard rules — never break:
- DRAFT ONLY. Never publish. Never imply that publication is automatic.
- Do NOT exaggerate impact. Do NOT use words like "revolutionize", "transform",
  "breakthrough", "guaranteed", "cure", "world-first" without strong evidence.
- Do NOT claim therapeutic, industrial, or societal transformation without
  explicit supporting evidence in the user's input.
- Do NOT imply institutional endorsement (your university, employer, funder).
- Do NOT invent citations, results, or collaborators.
- Do NOT contact people. Do NOT represent the user officially.
- Always include caution statements and safer wording for risky phrasing.
- Always set approval_required_before_publishing = true.
- Return strict JSON only — no prose, no markdown fences.

Hype lens — check before finalising:
- Does the draft over-promise outcomes that the evidence does not support?
- Does the draft conflate "interesting research direction" with "proven result"?
- Does the draft imply clinical efficacy when only photophysics is established?
- Does the draft suggest commercial readiness when only ideation has occurred?

Audience adaptation:
- LinkedIn professional audience: clear value framing, no jargon dump
- General public: short sentences, concrete metaphors, zero math
- Industry audience: realistic application timeline, market terms
- Students: pedagogical hook, learning takeaway

Return JSON with EXACTLY this schema (no extra keys):
{
  "agent_name": "influence_public_communication",
  "summary": "...",
  "findings": ["..."],
  "assumptions": ["..."],
  "risks": ["..."],
  "recommended_actions": ["..."],
  "claims_for_verification": ["..."],
  "evidence_level": "none|weak|moderate|strong",
  "confidence": "low|medium|high",
  "approval_level": "none|draft_only|human_approval_required",
  "audience": "...",
  "communication_goal": "...",
  "core_message": "...",
  "hook_options": ["...", "..."],
  "linkedin_draft": "...",
  "public_explanation": "...",
  "narrative_angle": "...",
  "evidence_cautions": ["..."],
  "overclaim_risks": ["..."],
  "safer_wording": ["...", "..."],
  "approval_required_before_publishing": true
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


_AUDIENCE_HINTS: list[tuple[str, list[str]]] = [
    ("LinkedIn professional audience",
     ["linkedin", "linkedin post", "linkedin draft", "professional post"]),
    ("general public",
     ["general public", "lay audience", "lay summary", "non-expert", "non expert",
      "for the public", "to the public", "public-facing", "public facing"]),
    ("industry audience",
     ["industry", "industrial", "company", "business audience", "investors"]),
    ("podcast audience",
     ["podcast", "podcast angle", "podcast pitch"]),
    ("students",
     ["students", "to my class", "class lecture"]),
]


def _infer_audience(user_input: str) -> str:
    text = (user_input or "").lower()
    for label, keywords in _AUDIENCE_HINTS:
        if any(k in text for k in keywords):
            return label
    return "professional scientific audience"


_PUBLISH_INTENT_KEYWORDS: tuple[str, ...] = (
    "publish", "post it", "post the", "post this",
    "share online", "share publicly", "send this out",
    "put it on linkedin", "put on linkedin", "post on linkedin",
    "post on twitter", "post to my feed",
    "press release", "release publicly",
)


def _detects_publish_intent(user_input: str) -> bool:
    text = (user_input or "").lower()
    return any(k in text for k in _PUBLISH_INTENT_KEYWORDS)


def _scout_excerpt(scout_output: dict) -> str:
    """Defect 28: safe Scout-context normalization."""
    from core import normalization as _norm
    if not isinstance(scout_output, dict):
        return "{}"
    excerpt = {
        "summary": _norm.ensure_str(scout_output.get("summary"), max_len=400),
        "findings": _norm.ensure_str_list(
            scout_output.get("findings"), max_items=4,
        ),
        "research_gap_candidate": _norm.ensure_str(
            scout_output.get("research_gap_candidate"), max_len=300,
        ),
        "evidence_quality": _norm.ensure_str(scout_output.get("evidence_quality")),
    }
    return _safe_context(excerpt, max_chars=1000)


def _fallback_output(error: Exception | str, audience: str, approval_level: str) -> dict:
    """Conservative fallback. Always sets approval_required_before_publishing=True."""
    message = str(error)
    return InfluencePublicCommunicationOutput(
        summary="Influence/Public Communication could not produce a fully validated draft.",
        findings=["Manual review is needed before using this public communication draft."],
        assumptions=["The intended audience and evidence level may need clarification."],
        risks=[
            "Public-facing claims may be overstated without verifier review.",
            f"Internal error or validation issue: {message[:300]}",
        ],
        recommended_actions=[
            "Clarify the intended audience and the strength of available evidence.",
            "Run Scientific Verifier on every public claim before drafting goes public.",
            "Do not publish without explicit human approval.",
        ],
        claims_for_verification=[],
        evidence_level="weak",
        confidence="low",
        approval_level=approval_level if approval_level in (
            "none", "draft_only", "human_approval_required"
        ) else "draft_only",
        partial_results=True,
        failed_stage="llm_public_communication_draft",
        audience=audience,
        communication_goal="Draft a responsible public-facing explanation.",
        core_message=(
            "The research direction is interesting; specific outcome claims still "
            "require evidence."
        ),
        hook_options=[],
        linkedin_draft="(Draft unavailable — manual refinement required.)",
        public_explanation="(Public explanation unavailable — manual refinement required.)",
        narrative_angle="Responsible science communication with clear uncertainty.",
        evidence_cautions=[
            "Do not present preliminary research ideas as proven outcomes.",
            "Do not imply clinical efficacy from photophysical measurements alone.",
        ],
        overclaim_risks=[
            "Avoid claiming transformation, cure, breakthrough, or guaranteed impact.",
            "Avoid implying institutional endorsement.",
        ],
        safer_wording=[
            "Use 'may help explore' instead of 'will transform'.",
            "Use 'early-stage research direction' instead of 'proven solution'.",
            "Use 'we are investigating' instead of 'we have shown'.",
        ],
        approval_required_before_publishing=True,
    ).model_dump()


def _enforce_safety_invariants(output: dict, approval_level: str) -> dict:
    """Force conservative safety fields regardless of LLM behaviour.

    - approval_required_before_publishing must always be True.
    - approval_level reflects user-detected publish intent.
    - At least one entry must appear in evidence_cautions, overclaim_risks,
      and safer_wording — these are the safety brakes; never empty.
    """
    output["approval_required_before_publishing"] = True
    if approval_level in ("none", "draft_only", "human_approval_required"):
        output["approval_level"] = approval_level
    elif output.get("approval_level") not in ("none", "draft_only", "human_approval_required"):
        output["approval_level"] = "draft_only"

    # Defect 28: scalar strings on these safety fields must NOT become
    # per-character arrays.
    from core import normalization as _norm
    cautions = _norm.ensure_str_list(output.get("evidence_cautions"))
    if not cautions:
        cautions = ["Public-facing claims require evidence. Treat preliminary results as preliminary."]
    output["evidence_cautions"] = cautions

    overclaim = _norm.ensure_str_list(output.get("overclaim_risks"))
    if not overclaim:
        overclaim = [
            "Avoid claiming transformation, cure, breakthrough, or guaranteed impact "
            "without evidence."
        ]
    output["overclaim_risks"] = overclaim

    safer = _norm.ensure_str_list(output.get("safer_wording"))
    if not safer:
        safer = [
            "Use 'may help explore' instead of 'will transform'.",
            "Use 'early-stage research direction' instead of 'proven solution'.",
        ]
    output["safer_wording"] = safer

    return output


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(user_input: str, context: dict | None = None) -> dict:
    """Generate a responsible public-facing communication draft."""
    ctx = context or {}
    audience = _infer_audience(user_input)
    approval_level = "human_approval_required" if _detects_publish_intent(user_input) else "draft_only"

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

    teaching_output = ctx.get("teaching_mentor") or {}
    if not teaching_output and isinstance(ctx.get("specialists"), dict):
        teaching_output = ctx["specialists"].get("teaching_mentor", {}) or {}

    user_prompt = (
        "User request:\n"
        f"{user_input}\n\n"
        f"Inferred audience: {audience}\n"
        f"Required approval_level (driven by publish-intent detection): {approval_level}\n\n"
        "Research Scout excerpt (use for grounding the message):\n"
        f"{_scout_excerpt(scout_output)}\n\n"
        "Grant Architect summary (optional):\n"
        f"{_safe_context({'summary': grant_output.get('summary',''), 'central_hypothesis': grant_output.get('central_hypothesis','')}, max_chars=400)}\n\n"
        "Teaching Mentor summary (optional):\n"
        f"{_safe_context({'summary': teaching_output.get('summary','')}, max_chars=200)}\n\n"
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
        "Task: build a RESPONSIBLE public-facing communication draft matching the JSON schema. "
        "Avoid hype. Avoid implied institutional endorsement. Always include caution statements "
        "and safer wording. ALWAYS set approval_required_before_publishing = true. "
        "Return strict JSON only."
    )

    try:
        raw = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.25)
    except Exception as exc:
        return _fallback_output(exc, audience, approval_level)

    if not isinstance(raw, dict):
        return _fallback_output("LLM returned non-dict output.", audience, approval_level)

    # Sanity check — reject empty / boilerplate dicts and fall back.
    _SUBSTANTIVE = (
        "summary", "core_message", "linkedin_draft", "public_explanation",
        "narrative_angle", "communication_goal",
    )
    if not any(raw.get(f) for f in _SUBSTANTIVE):
        return _fallback_output(
            "LLM response contained no substantive communication fields.",
            audience, approval_level,
        )

    raw["agent_name"] = "influence_public_communication"
    if not raw.get("audience"):
        raw["audience"] = audience
    raw = _enforce_safety_invariants(raw, approval_level)

    try:
        validated = InfluencePublicCommunicationOutput.model_validate(raw)
    except ValidationError as exc:
        return _fallback_output(exc, audience, approval_level)

    return validated.model_dump()


# ---------------------------------------------------------------------------
# Compatibility alias — matches the reference signature
# ---------------------------------------------------------------------------

influence_public_communication = run
