"""
AURA Teaching Mentor — Wave 1 specialist.

Converts research ideas, papers, and scientific concepts into accurate,
learner-aware teaching material. Reviewed by the Scientific Verifier when the
output contains technical scientific claims.

Public surface:
    run(user_input, context) -> dict (validates against TeachingMentorOutput)
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from core.llm import ask_json
from core.memory import retrieve_relevant_memory
from core.schemas import TeachingMentorOutput


SYSTEM_PROMPT = """\
You are the AURA Teaching Mentor.

Your job is to convert research into clear, accurate, learner-aware teaching
material for OLED / TADF / photophysics / organic electronics topics.

Hard rules — never break:
- Do NOT oversimplify into false statements.
- Do NOT hide scientific uncertainty — mark uncertain claims as uncertain.
- Match the chosen learner_level: do not give graduate-level depth to general public,
  and do not flatten subtle physics for graduate / researcher audiences.
- Always include common misconceptions for the topic.
- Always include misconception-aware Socratic questions.
- Quiz questions must align with stated learning_outcomes.
- Include technical_cautions for every claim that could be misread as established fact.
- Return strict JSON only — no prose, no markdown fences.

Learner level definitions:
- general_public:   no chemistry/physics background; analogies, no equations
- undergraduate:    basic chemistry/photophysics; energy diagrams allowed
- graduate:         comfortable with kinetics, rates, photophysical pathways
- researcher:       full scientific depth; cite mechanisms by name
- mixed:            stratified by section (label what is for whom)

Misconception lens — check for these common errors before finalising:
- treating TADF as identical to phosphorescence
- claiming triplets are "harvested" without explaining RISC
- conflating PLQY with EQE
- conflating delayed fluorescence with long-lived phosphorescence
- assuming red/NIR emitters are inherently safer for biomedical use
- treating EQE as a material property rather than a device property

Return JSON with EXACTLY this schema (no extra keys):
{
  "agent_name": "teaching_mentor",
  "summary": "...",
  "findings": ["..."],
  "assumptions": ["..."],
  "risks": ["..."],
  "recommended_actions": ["..."],
  "claims_for_verification": ["..."],
  "evidence_level": "none|weak|moderate|strong",
  "confidence": "low|medium|high",
  "approval_level": "none|draft_only|human_approval_required",
  "target_audience": "...",
  "learner_level": "general_public|undergraduate|graduate|researcher|mixed",
  "learning_outcomes": ["..."],
  "conceptual_explanation": "...",
  "socratic_questions": ["..."],
  "common_misconceptions": ["..."],
  "quiz_questions": ["..."],
  "assessment_rubric": ["..."],
  "teaching_activity": "...",
  "technical_cautions": ["..."]
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


_LEVEL_KEYWORDS: list[tuple[str, list[str]]] = [
    ("general_public", ["public", "lay audience", "general audience", "outreach", "podcast", "non-scientist"]),
    ("undergraduate",  ["undergraduate", "undergrad", "bachelor", "first-year", "second-year", "third-year"]),
    ("graduate",       ["graduate", "master's", "masters", "phd student", "ph.d. student", "grad student"]),
    ("researcher",     ["researcher", "expert", "postdoc", "faculty", "advanced researcher"]),
]


def _infer_learner_level(user_input: str) -> str:
    text = (user_input or "").lower()
    for level, keywords in _LEVEL_KEYWORDS:
        if any(k in text for k in keywords):
            return level
    return "undergraduate"   # safe default


def _scout_excerpt(scout_output: dict) -> str:
    if not isinstance(scout_output, dict):
        return "{}"
    excerpt = {
        "summary": scout_output.get("summary", "")[:600],
        "findings": list(scout_output.get("findings", []))[:5],
        "claims_for_verification": list(scout_output.get("claims_for_verification", []))[:5],
        "research_gap_candidate": scout_output.get("research_gap_candidate", "")[:300],
        "evidence_quality": scout_output.get("evidence_quality", ""),
        "literature_scan_used": scout_output.get("literature_scan_used", False),
    }
    return _safe_context(excerpt, max_chars=1800)


def _fallback_output(error: Exception | str, learner_level: str = "undergraduate") -> dict:
    """Conservative fallback when validation or the LLM call fails."""
    message = str(error)
    return TeachingMentorOutput(
        summary="Teaching Mentor could not produce a fully validated teaching module.",
        findings=["Manual review is needed before using this teaching material."],
        assumptions=["The learner level may need clarification."],
        risks=[
            "Scientific explanation may be incomplete without expert review.",
            f"Internal error or validation issue: {message[:300]}",
        ],
        recommended_actions=[
            "Clarify learner level with the user before classroom use.",
            "Run Scientific Verifier on any technical claims.",
            "Review explanation against a textbook before teaching.",
        ],
        claims_for_verification=[],
        evidence_level="weak",
        confidence="low",
        approval_level="draft_only",
        partial_results=True,
        failed_stage="llm_teaching_module",
        target_audience="students (level uncertain)",
        learner_level=learner_level if learner_level in (
            "general_public", "undergraduate", "graduate", "researcher", "mixed"
        ) else "undergraduate",
        learning_outcomes=[],
        conceptual_explanation="Teaching explanation requires manual refinement.",
        socratic_questions=[],
        common_misconceptions=[
            "TADF is sometimes confused with phosphorescence — clarify before use.",
        ],
        quiz_questions=[],
        assessment_rubric=[],
        teaching_activity=(
            "Ask students to identify what evidence is needed to support each "
            "scientific claim before treating it as established fact."
        ),
        technical_cautions=[
            "Do not present uncertain research claims as established facts.",
        ],
    ).model_dump()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(user_input: str, context: dict | None = None) -> dict:
    """Generate teaching material for the user's chosen topic and audience."""
    ctx = context or {}
    learner_level = _infer_learner_level(user_input)

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

    user_prompt = (
        "User request:\n"
        f"{user_input}\n\n"
        f"Inferred learner level (from keywords): {learner_level}\n\n"
        "Research Scout excerpt (use only if it helps explain the topic):\n"
        f"{_scout_excerpt(scout_output)}\n\n"
        "Grant Architect summary (optional context, ignore if unrelated):\n"
        f"{_safe_context({'summary': grant_output.get('summary',''), 'central_hypothesis': grant_output.get('central_hypothesis','')}, max_chars=400)}\n\n"
        "Relevant AURA memory:\n"
        f"{_safe_context(memory_records[:8], max_chars=1500)}\n\n"
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
        "Task: build a teaching module matching the JSON schema. "
        "Match learner level. Include misconceptions and Socratic questions. "
        "Include technical_cautions for any claim that could be over-stated. "
        "Return strict JSON only."
    )

    try:
        raw = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.2)
    except Exception as exc:
        return _fallback_output(exc, learner_level=learner_level)

    if not isinstance(raw, dict):
        return _fallback_output("LLM returned non-dict output.", learner_level=learner_level)

    # Sanity check — if the LLM returned no substantive teaching fields, fall back.
    _SUBSTANTIVE = (
        "summary", "conceptual_explanation", "learning_outcomes",
        "socratic_questions", "common_misconceptions", "quiz_questions",
        "teaching_activity",
    )
    if not any(raw.get(f) for f in _SUBSTANTIVE):
        return _fallback_output(
            "LLM response contained no substantive teaching fields.",
            learner_level=learner_level,
        )

    # Force agent_name (Literal-locked) and clamp learner_level if obviously wrong
    raw["agent_name"] = "teaching_mentor"
    if raw.get("learner_level") not in (
        "general_public", "undergraduate", "graduate", "researcher", "mixed"
    ):
        raw["learner_level"] = learner_level

    # Teaching material that contains technical claims should not auto-publish.
    # Force draft_only when the module contains any technical_cautions or risks.
    if raw.get("technical_cautions") or raw.get("risks"):
        if raw.get("approval_level") == "human_approval_required":
            raw["approval_level"] = "draft_only"

    try:
        validated = TeachingMentorOutput.model_validate(raw)
    except ValidationError as exc:
        return _fallback_output(exc, learner_level=learner_level)

    return validated.model_dump()
