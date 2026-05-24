from __future__ import annotations

import json
import logging

from core.llm import ask_json
from core.memory import save_memory, save_reflection, append_jsonl
from core.schemas import ReflectionRecord

logger = logging.getLogger(__name__)

# 12-type failure taxonomy
FAILURE_TAXONOMY = [
    "query_too_broad",
    "query_too_narrow",
    "overclaimed_novelty",
    "insufficient_evidence",
    "methodology_gap",
    "citation_missing",
    "scope_mismatch",
    "verifier_reject",
    "verifier_human_review",
    "partial_execution",
    "low_confidence",
    "profile_mismatch",
]

SYSTEM_PROMPT = """\
You are the AURA Learning Governor — the self-evolution engine for an AI research assistant.
Your role: extract durable, reusable lessons from this session and propose governed improvements.

CRITICAL RULES:
- Only save lessons that are non-obvious, reusable across sessions, and backed by evidence.
- Do NOT store private chain-of-thought, ephemeral details, or trivial observations.
- Profile update proposals are DRAFTS ONLY — never applied automatically.
- For each lesson, assign: confidence (0.0-1.0), scope (session|topic|domain|global),
  evidence_basis (what from this session supports it), risk_if_applied (low|medium|high),
  save_decision (save_now|needs_review|discard).

save_now criteria: confidence >= 0.75 AND risk_if_applied == "low" AND scope != "session"
discard criteria: confidence < 0.4 OR purely session-specific OR too vague to act on
needs_review: everything else

Failure taxonomy labels (use ONLY these):
query_too_broad, query_too_narrow, overclaimed_novelty, insufficient_evidence,
methodology_gap, citation_missing, scope_mismatch, verifier_reject,
verifier_human_review, partial_execution, low_confidence, profile_mismatch

Return strict JSON with EXACTLY this schema — no additional keys:
{
  "session_assessment": "One sentence on overall session quality.",
  "failure_modes": ["taxonomy label"],
  "lesson_details": [
    {
      "lesson": "Specific, reusable lesson text.",
      "failure_type": "taxonomy label or empty string",
      "confidence": 0.0,
      "scope": "session|topic|domain|global",
      "evidence_basis": "What from this session supports this.",
      "risk_if_applied": "low|medium|high",
      "save_decision": "save_now|needs_review|discard",
      "applies_to_modes": ["ideation"]
    }
  ],
  "memory_update_proposals": ["Specific memory entry to save."],
  "workflow_update_proposals": ["Workflow improvement."],
  "rubric_update_proposals": ["Rubric change."],
  "profile_update_proposals": [
    {
      "field_path": "research_topics",
      "current_value": "current value summary",
      "proposed_value": "proposed value summary",
      "rationale": "Why change this.",
      "requires_human_approval": true
    }
  ],
  "next_experiments": [
    {
      "description": "What to do next.",
      "motivation": "Why this matters.",
      "expected_outcome": "What success looks like.",
      "agent_mode": "literature_scan",
      "priority": "high"
    }
  ],
  "human_approval_required": false,
  "do_not_learn": ["Things that should NOT be generalized from this session."],
  "what_worked": ["Flat string — backward compat."],
  "what_failed_or_was_weak": ["Flat string — backward compat."],
  "reusable_lessons": ["Top 3 save_now lesson texts — backward compat."],
  "memory_updates": ["Top 3 memory_update_proposals — backward compat."],
  "workflow_improvements": ["Top 3 workflow_update_proposals — backward compat."],
  "suggested_profile_updates": ["Top 3 profile_update_proposals as strings — backward compat."]
}"""


def _extract_session_content(all_outputs: dict) -> dict:
    """Structured Python-level extraction of session signals — no blind truncation."""
    governor = all_outputs.get("strategic_governor") or {}
    scout = all_outputs.get("research_scout") or {}
    verifier = all_outputs.get("scientific_verifier") or {}
    errors = all_outputs.get("errors") or []

    claim_checks = verifier.get("claim_checks", []) if isinstance(verifier, dict) else []
    sev_counts: dict[str, int] = {}
    for c in claim_checks:
        if isinstance(c, dict):
            sev = c.get("severity", "low")
            sev_counts[sev] = sev_counts.get(sev, 0) + 1

    return {
        "governor": {
            "task_type": governor.get("task_type", ""),
            "risk_level": governor.get("risk_level", "low"),
            "scout_mode": governor.get("research_scout_mode", ""),
        },
        "scout": {
            "mode": scout.get("mode", ""),
            "confidence": scout.get("confidence", "medium"),
            "evidence_quality": scout.get("evidence_quality", "moderate"),
            "partial_results": scout.get("partial_results", False),
            "failed_stage": scout.get("failed_stage", ""),
            "top_paper_count": len(scout.get("top_papers", [])),
            "gap_candidate_count": len(scout.get("research_gap_candidates", [])),
            "literature_scan_used": scout.get("literature_scan_used", False),
        },
        "verifier": {
            "route": verifier.get("route", "") if isinstance(verifier, dict) else "",
            "overall_assessment": verifier.get("overall_assessment", "") if isinstance(verifier, dict) else "",
            "claim_count": len(claim_checks),
            "claim_severity_counts": sev_counts,
            "revision_instruction_count": len(verifier.get("revision_instructions", [])) if isinstance(verifier, dict) else 0,
            "human_approvals_required": (verifier.get("required_human_approvals", []) if isinstance(verifier, dict) else [])[:3],
            "revision_instructions": (verifier.get("revision_instructions", []) if isinstance(verifier, dict) else [])[:5],
        },
        "pipeline_errors": [
            {"agent": e.get("agent", ""), "error": e.get("error", "")}
            for e in errors[:5]
            if isinstance(e, dict)
        ],
    }


def _check_verifier_quality(verifier_report: dict | None) -> list[str]:
    """Extract actionable criticisms from the verifier report."""
    if not verifier_report or not isinstance(verifier_report, dict):
        return []

    criticisms: list[str] = []
    route = verifier_report.get("route", "")
    if route == "reject":
        criticisms.append(
            f"Verifier REJECTED outputs: {verifier_report.get('final_recommendation', '')}"
        )
    elif route == "human_review":
        criticisms.append(
            "Verifier required HUMAN REVIEW — risk level too high for automated acceptance."
        )

    for c in verifier_report.get("claim_checks", [])[:5]:
        if isinstance(c, dict) and c.get("severity") in ("high", "critical"):
            criticisms.append(
                f"[{c.get('severity','?').upper()}] Claim '{c.get('claim','')[:80]}'"
                f" — status: {c.get('support_status','?')}"
                f" — correction: {c.get('correction','')[:120]}"
            )

    for inst in verifier_report.get("revision_instructions", [])[:3]:
        if inst:
            criticisms.append(f"Revision required: {inst[:150]}")

    return criticisms


def _classify_failure_modes(session_content: dict) -> list[str]:
    """Pre-classify failure taxonomy labels from session signals (no LLM required)."""
    failures: list[str] = []
    scout = session_content.get("scout", {})
    verifier = session_content.get("verifier", {})
    errors = session_content.get("pipeline_errors", [])

    if scout.get("partial_results"):
        failures.append("partial_execution")
    if scout.get("confidence") == "low":
        failures.append("low_confidence")
    if verifier.get("route") == "reject":
        failures.append("verifier_reject")
    elif verifier.get("route") == "human_review":
        failures.append("verifier_human_review")

    sev = verifier.get("claim_severity_counts", {})
    if sev.get("critical", 0) + sev.get("high", 0) > 0:
        failures.append("overclaimed_novelty")
    if verifier.get("human_approvals_required"):
        failures.append("insufficient_evidence")
    if errors:
        # Any pipeline error implies some execution failure
        if not any(f in failures for f in ("partial_execution",)):
            failures.append("partial_execution")

    return failures


# Defect 9: explicit safe-route allowlist.  Durable lessons may only be saved
# when the verifier *affirmatively* reported one of these routes.  Any other
# value — missing, empty, failure marker, reject, human_review, or even
# retrieve_more_evidence — must NOT allow learning to persist.
SAFE_LEARN_ROUTES: frozenset[str] = frozenset({"approve", "revise"})


def _save_approved_lessons(
    lesson_details: list[dict],
    verifier_report: dict | None = None,
) -> int:
    """Auto-save lessons that meet ALL of:
        - save_decision == "save_now"
        - risk_if_applied == "low"
        - confidence >= 0.75
        - scope != "session"
        - verifier route is in SAFE_LEARN_ROUTES (affirmative only)
        - verifier did NOT report a `failed` flag
        - verifier did NOT flag any critical/high-severity claims

    Any lesson failing any of these gates is silently skipped — the user can
    still approve it manually from the reflection record on disk.
    """
    # Defect 9: fail closed unless verifier explicitly affirmed via a safe route.
    if not isinstance(verifier_report, dict):
        logger.info(
            "Self-evolution: skipping lesson save — no verifier report provided.",
        )
        return 0
    if verifier_report.get("failed") is True:
        logger.info(
            "Self-evolution: skipping lesson save — verifier reported failure: %s",
            verifier_report.get("failure_reason", "(no reason)"),
        )
        return 0
    route = (verifier_report.get("route") or "").strip().lower()
    if route not in SAFE_LEARN_ROUTES:
        logger.info(
            "Self-evolution: skipping lesson save — verifier route '%s' is not "
            "in the safe-learn allowlist %s.",
            route or "(missing)",
            sorted(SAFE_LEARN_ROUTES),
        )
        return 0

    # Severity veto: any critical/high claim issue blocks learning.
    checks = verifier_report.get("claim_checks", []) or []
    sev_counts: dict[str, int] = {}
    for c in checks:
        if isinstance(c, dict):
            sev = c.get("severity", "low")
            sev_counts[sev] = sev_counts.get(sev, 0) + 1
    if sev_counts.get("critical", 0) + sev_counts.get("high", 0) > 0:
        logger.info(
            "Self-evolution: skipping lesson save — verifier flagged "
            "critical/high-severity claims (%d critical, %d high).",
            sev_counts.get("critical", 0),
            sev_counts.get("high", 0),
        )
        return 0

    _VALID_SCOPES = {"session", "topic", "domain", "global"}
    saved = 0
    for lesson in lesson_details:
        if not isinstance(lesson, dict):
            continue
        # Phase 1 (goal E): a lesson with an INVALID scope must never be
        # durably saved.  Coerce unknown scopes to "session" (the
        # narrowest), which the ``scope != "session"`` gate below then
        # excludes — so a malformed/over-broad scope cannot reach memory.
        raw_scope = str(lesson.get("scope", "session") or "").strip().lower()
        scope = raw_scope if raw_scope in _VALID_SCOPES else "session"
        if (
            lesson.get("save_decision") == "save_now"
            and lesson.get("risk_if_applied", "high") == "low"
            and float(lesson.get("confidence", 0.0)) >= 0.75
            and scope != "session"
        ):
            content = lesson.get("lesson", "")
            if len(content) > 10:
                try:
                    save_memory("lesson", content, {
                        "source": "self_evolution_engine",
                        "failure_type": lesson.get("failure_type", ""),
                        "scope": scope,
                        "confidence": lesson.get("confidence", 0.5),
                    })
                    saved += 1
                except Exception as exc:
                    logger.warning("Failed to save lesson to memory: %s", exc)
    return saved


def _build_llm_prompt(
    user_input: str,
    session_content: dict,
    verifier_criticisms: list[str],
    pre_classified: list[str],
    user_feedback: str | None,
) -> str:
    parts = [
        f"Session user input:\n{user_input}\n",
        f"Session content summary:\n{json.dumps(session_content, indent=2, default=str)}\n",
    ]
    if verifier_criticisms:
        parts.append(
            "Verifier criticisms to learn from:\n"
            + "\n".join(f"  - {c}" for c in verifier_criticisms)
        )
    if pre_classified:
        parts.append(f"Pre-classified failure modes: {', '.join(pre_classified)}")
    if user_feedback:
        parts.append(f"User feedback for this session:\n{user_feedback}")
    parts.append("\nExtract durable lessons and return as strict JSON.")
    return "\n\n".join(parts)


def run(
    user_input: str,
    all_outputs: dict,
    verifier_report: dict | None = None,
    user_feedback: str | None = None,
) -> dict:
    # Step 1: Structured extraction — no blind truncation
    session_content = _extract_session_content(all_outputs)

    # Step 2: Extract verifier criticisms
    verifier_criticisms = _check_verifier_quality(verifier_report)

    # Step 3: Pre-classify failures without LLM
    pre_classified = _classify_failure_modes(session_content)

    # Step 4: Build LLM prompt
    user_prompt = _build_llm_prompt(
        user_input, session_content, verifier_criticisms, pre_classified, user_feedback
    )

    # Step 5: LLM call
    try:
        raw = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.15)
        record = ReflectionRecord(**raw)
        output = record.model_dump()
    except Exception as exc:
        logger.error("Self-evolution LLM parse error: %s", exc)
        output = ReflectionRecord(
            session_assessment=f"Evolution parse error: {exc}",
            failure_modes=pre_classified,
            what_failed_or_was_weak=[f"Self-evolution parse error: {exc}"],
        ).model_dump()

    # Merge pre-classified failures with any the LLM identified
    merged = list({*output.get("failure_modes", []), *pre_classified})
    output["failure_modes"] = merged

    # Step 6: Save reflection record
    try:
        save_reflection(output)
    except Exception as exc:
        logger.warning("Failed to save reflection: %s", exc)

    # Step 7: Save only approved lessons (verifier route can veto the whole batch)
    lesson_details = output.get("lesson_details", [])
    saved_count = _save_approved_lessons(lesson_details, verifier_report=verifier_report)
    if saved_count:
        logger.info("Self-evolution: saved %d approved lesson(s) to memory.", saved_count)

    # Step 8: Append performance log entry
    try:
        import config
        perf_entry = {
            "session_assessment": output.get("session_assessment", ""),
            "failure_modes": output.get("failure_modes", []),
            "lessons_saved": saved_count,
            "verifier_route": session_content.get("verifier", {}).get("route", ""),
            "scout_mode": session_content.get("scout", {}).get("mode", ""),
            "user_input_snippet": user_input[:80],
        }
        append_jsonl(config.PERFORMANCE_LOG_PATH, perf_entry)
    except Exception as exc:
        logger.warning("Failed to write performance log: %s", exc)

    return output
