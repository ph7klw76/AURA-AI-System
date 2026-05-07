"""
AURA Scientific Verifier — claim-level, evidence-aware, routing verifier.

Pipeline:
    prior_outputs
        -> _extract_structured_content()   (Python-level, no LLM)
        -> _build_prompt()
        -> ask_json()                      (Qwen3:8b, temperature=0.0)
        -> _safe_parse_report()
        -> [repair pass if parse fails]
        -> _backfill_compat_fields()
        -> _add_audit_metadata()
        -> return VerificationReport dict
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import config
from core.llm import ask_json, ask_llm
from core.schemas import ClaimCheck, VerificationReport

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the AURA Scientific Verifier — a strict, evidence-based reviewer whose job is to
protect the user from harm, not to encourage them.

You must protect the user from:
- unsupported scientific claims
- exaggerated or undemonstrated novelty
- invented, absent, or misrepresented citations
- implausible mechanisms or device physics
- unrealistic experimental or fabrication claims
- grant framing stronger than the evidence supports
- premature commercialisation or biomedical translation claims
- unsafe autonomous actions (emailing, submitting, spending, publishing)
- collaboration suggestions that require human approval

You simulate seven reviewer lenses simultaneously:
1. Skeptical materials scientist — are material properties stated accurately?
2. OLED device physicist — are EQE, luminance, lifetime, voltage claims realistic?
3. Photophysics/chemistry reviewer — are TADF mechanisms, rates, yield claims defensible?
4. Grant panel reviewer — is the problem clearly defined and the evidence grant-level compelling?
5. Industry feasibility reviewer — OLEDWorks/Samsung/LG standards for device reliability?
6. Biomedical translation skeptic — for photobiomodulation: wavelength, dose, encapsulation, safety?
7. Methodology and reproducibility reviewer — can the proposed experiments actually be done?

For EVERY major claim in the input, you must produce a ClaimCheck entry containing:
  - claim: the exact claim text (quote directly when possible)
  - claim_type: one of mechanism | novelty | grant | method | action | collaboration | citation
  - support_status: supported | partially_supported | unsupported | contradicted | unverifiable
  - severity: low | medium | high | critical
  - confidence: float 0.0–1.0 (your confidence in this assessment)
  - evidence_needed: list of 1–3 specific missing pieces of evidence
  - correction: one concrete, actionable correction

Additional outputs:
  - methodology_risks: experimental/computational approach risks
  - novelty_risks: where novelty appears overstated or insufficiently differentiated
  - citation_risks: papers that may not exist, be misrepresented, or be out of scope
  - grant_risks: grant framing that outpaces the evidence
  - action_governance_risks: any action the system should NOT take autonomously
  - required_human_approvals: explicit list of actions needing user sign-off
  - revision_instructions: ordered, specific steps to fix the output before use
  - final_recommendation: approve | revise | reject | needs_more_evidence
  - route: approve | revise | retrieve_more_evidence | human_review | reject
  - overall_assessment: weak | acceptable | strong | incomplete

Severity guide:
  - critical: would mislead a grant reviewer, editor, or industry partner
  - high: significant overstatement requiring correction before any use
  - medium: potentially misleading; should be qualified
  - low: minor imprecision acceptable in early-stage ideation

Rules you must never break:
- Do NOT invent papers, data, mechanisms, experimental results, or reviewer objections.
- If evidence is absent, state that it is absent — do not assume it is implied.
- If a recommendation involves emailing, submitting, spending, deleting, or representing
  the user officially, mark it in required_human_approvals and action_governance_risks.
- A parse failure or insufficient evidence must yield overall_assessment = "incomplete".
- Return strict JSON only. No prose outside the JSON object.

Return JSON matching this exact schema:
{
  "overall_assessment": "weak | acceptable | strong | incomplete",
  "claim_checks": [
    {
      "claim": "...",
      "claim_type": "mechanism | novelty | grant | method | action | collaboration | citation",
      "support_status": "supported | partially_supported | unsupported | contradicted | unverifiable",
      "severity": "low | medium | high | critical",
      "confidence": 0.0,
      "evidence_needed": ["..."],
      "correction": "..."
    }
  ],
  "methodology_risks": ["..."],
  "novelty_risks": ["..."],
  "citation_risks": ["..."],
  "grant_risks": ["..."],
  "action_governance_risks": ["..."],
  "required_human_approvals": ["..."],
  "revision_instructions": ["..."],
  "final_recommendation": "approve | revise | reject | needs_more_evidence",
  "route": "approve | revise | retrieve_more_evidence | human_review | reject"
}"""

REPAIR_SYSTEM_PROMPT = """\
You are a JSON repair assistant. The text below is malformed or incomplete JSON that was
produced by a scientific verifier. Your only job is to return valid JSON that matches the
required schema as closely as possible, preserving all the original content.

Required top-level keys:
overall_assessment, claim_checks, methodology_risks, novelty_risks, citation_risks,
grant_risks, action_governance_risks, required_human_approvals, revision_instructions,
final_recommendation, route.

Return ONLY the repaired JSON object. No explanation, no prose."""


# ---------------------------------------------------------------------------
# Structured content extraction (Python-level, no LLM)
# ---------------------------------------------------------------------------

def _extract_structured_content(prior_outputs: dict) -> tuple[dict, bool]:
    """
    Extract verifiable content from prior agent outputs into a compact structured dict.
    Returns (structured_content, was_truncated).

    This replaces blind string truncation. The verifier sees a curated view instead of
    raw JSON that may bury the most important claims past a character limit.
    """
    scout: dict = prior_outputs.get("research_scout") or {}
    gov: dict = prior_outputs.get("strategic_governor") or {}

    claims: list[str] = []

    # Governor rationale as a claim source
    rationale = gov.get("rationale", "").strip()
    if rationale and len(rationale) > 15:
        claims.append(f"[governor] {rationale}")

    # Scout summary — split into sentences to surface individual claims
    summary = scout.get("summary", "")
    for sentence in summary.split("."):
        s = sentence.strip()
        if len(s) > 25:
            claims.append(f"[summary] {s}.")

    # Each finding is a discrete verifiable claim
    for f in scout.get("findings", []):
        if f and len(f) > 10:
            claims.append(f"[finding] {f}")

    # Research gap candidate is a high-stakes novelty claim
    gap = scout.get("research_gap_candidate", "").strip()
    if gap:
        claims.append(f"[gap_claim] {gap}")

    # Recommended actions are governance-relevant
    recommended_actions: list[str] = scout.get("recommended_actions", [])

    # Top papers: title + recommended_action + commentary are verifiable assertions
    cited_papers: list[dict] = []
    for p in scout.get("top_papers", [])[:8]:
        cited_papers.append({
            "title": p.get("title", ""),
            "source": p.get("source", ""),
            "score": round(float(p.get("total_score", 0.0)), 2),
            "recommended_action": p.get("recommended_action", ""),
            "commentary": (p.get("commentary", "") or "")[:200],
            "evidence_gaps": p.get("evidence_gaps", [])[:3],
        })

    structured = {
        "task_type": gov.get("task_type", ""),
        "risk_level": gov.get("risk_level", "low"),
        "scout_mode": scout.get("mode", ""),
        "scout_confidence": scout.get("confidence", ""),
        "requires_approval_flagged_by_governor": gov.get("requires_approval", False),
        "claims": claims[:20],   # cap to keep prompt tractable
        "cited_papers": cited_papers,
        "recommended_actions": recommended_actions,
        "research_gap_candidate": gap,
        "risks_from_scout": scout.get("risks", [])[:8],
        "literature_scan_used": scout.get("literature_scan_used", False),
    }

    original_size = len(json.dumps(prior_outputs, default=str))
    truncated = original_size > 8000
    return structured, truncated


def _build_evidence_summary(evidence_pack: dict | None) -> str:
    if not evidence_pack:
        return "No external evidence pack provided."
    lines = []
    topics = evidence_pack.get("profile_topics", [])
    if topics:
        lines.append(f"Profile topics: {', '.join(topics[:8])}")
    sources = evidence_pack.get("sources_used", [])
    if sources:
        lines.append(f"Sources searched: {', '.join(sources)}")
    top = evidence_pack.get("top_papers", [])
    if top:
        lines.append(f"Papers in evidence pack: {len(top)}")
        for i, p in enumerate(top[:5], 1):
            lines.append(
                f"  {i}. [{p.get('source', '?')}] {p.get('title', 'Untitled')[:80]}"
                f" (score={p.get('total_score', 0):.2f})"
            )
    if not lines:
        return "Evidence pack present but empty."
    return "\n".join(lines)


def _make_input_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# JSON repair pass
# ---------------------------------------------------------------------------

def _repair_json(raw_text: str) -> dict:
    """Ask the model to repair malformed JSON. Returns parsed dict or raises."""
    user_prompt = f"Repair this JSON:\n\n{raw_text[:3000]}"
    repaired_text = ask_llm(REPAIR_SYSTEM_PROMPT, user_prompt, temperature=0.0, json_mode=True)
    from core.llm import extract_json
    return extract_json(repaired_text)


# ---------------------------------------------------------------------------
# Schema validation and backfill
# ---------------------------------------------------------------------------

_VALID_ASSESSMENTS = {"weak", "acceptable", "strong", "incomplete"}
_VALID_ROUTES = {"approve", "revise", "retrieve_more_evidence", "human_review", "reject"}
_VALID_RECOMMENDATIONS = {"approve", "revise", "reject", "needs_more_evidence"}
_VALID_CLAIM_TYPES = {"mechanism", "novelty", "grant", "method", "action", "collaboration", "citation"}
_VALID_SUPPORT = {"supported", "partially_supported", "unsupported", "contradicted", "unverifiable"}
_VALID_SEVERITY = {"low", "medium", "high", "critical"}


def _coerce_claim_check(raw: Any) -> ClaimCheck:
    if not isinstance(raw, dict):
        return ClaimCheck(claim=str(raw), support_status="unverifiable", severity="medium")
    claim_type = raw.get("claim_type", "mechanism")
    if claim_type not in _VALID_CLAIM_TYPES:
        claim_type = "mechanism"
    support = raw.get("support_status", "unverifiable")
    if support not in _VALID_SUPPORT:
        support = "unverifiable"
    severity = raw.get("severity", "low")
    if severity not in _VALID_SEVERITY:
        severity = "low"
    try:
        confidence = float(raw.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.5
    evidence_needed = raw.get("evidence_needed", [])
    if not isinstance(evidence_needed, list):
        evidence_needed = [str(evidence_needed)]
    return ClaimCheck(
        claim=str(raw.get("claim", ""))[:500],
        claim_type=claim_type,
        support_status=support,
        severity=severity,
        confidence=round(confidence, 2),
        evidence_needed=[str(e)[:200] for e in evidence_needed[:4]],
        correction=str(raw.get("correction", ""))[:400],
    )


def _safe_parse_report(raw: dict, truncated: bool) -> VerificationReport:
    """Parse and coerce the LLM output into a VerificationReport, fixing minor issues."""
    assessment = raw.get("overall_assessment", "incomplete")
    if assessment not in _VALID_ASSESSMENTS:
        assessment = "incomplete"

    claim_checks_raw = raw.get("claim_checks", [])
    if not isinstance(claim_checks_raw, list):
        claim_checks_raw = []
    claim_checks = [_coerce_claim_check(c) for c in claim_checks_raw[:15]]

    route = raw.get("route", "revise")
    if route not in _VALID_ROUTES:
        route = "revise"

    final_rec = raw.get("final_recommendation", "needs_more_evidence")
    if final_rec not in _VALID_RECOMMENDATIONS:
        final_rec = "needs_more_evidence"

    def _strlist(key: str) -> list[str]:
        v = raw.get(key, [])
        if not isinstance(v, list):
            return [str(v)] if v else []
        return [str(x)[:400] for x in v[:10]]

    # Derive flat backward-compat fields from claim_checks
    unsupported = [
        c.claim for c in claim_checks
        if c.support_status in ("unsupported", "contradicted")
    ]
    high_severity_corrections = [
        c.correction for c in claim_checks
        if c.correction and c.severity in ("high", "critical")
    ]
    all_risks = (
        _strlist("methodology_risks")
        + _strlist("novelty_risks")
        + _strlist("grant_risks")
        + _strlist("action_governance_risks")
    )

    return VerificationReport(
        overall_assessment=assessment,
        claim_checks=claim_checks,
        methodology_risks=_strlist("methodology_risks"),
        novelty_risks=_strlist("novelty_risks"),
        citation_risks=_strlist("citation_risks"),
        grant_risks=_strlist("grant_risks"),
        action_governance_risks=_strlist("action_governance_risks"),
        required_human_approvals=_strlist("required_human_approvals"),
        revision_instructions=_strlist("revision_instructions"),
        final_recommendation=final_rec,
        route=route,
        truncated=truncated,
        # Backward-compat flat fields
        unsupported_claims=unsupported[:10],
        assumptions=_strlist("assumptions") or [],
        risks=all_risks[:10],
        corrections=high_severity_corrections[:8],
    )


def _add_audit_metadata(report: VerificationReport, input_hash: str, sources: list[str]) -> None:
    report.verified_at = datetime.now(timezone.utc).isoformat()
    report.model_used = config.MODEL_NAME
    report.evidence_sources_checked = sources


def _incomplete_fallback(reason: str) -> VerificationReport:
    """Safe fallback that does NOT silently pass a failed verification."""
    return VerificationReport(
        overall_assessment="incomplete",
        route="human_review",
        final_recommendation="needs_more_evidence",
        methodology_risks=[f"Verifier could not complete: {reason}"],
        revision_instructions=[
            "Do not use prior outputs until manually reviewed.",
            "Re-run the verifier or perform a manual scientific check.",
        ],
        risks=[f"Verification incomplete: {reason}"],
        corrections=["Manual review required before any downstream use."],
        verified_at=datetime.now(timezone.utc).isoformat(),
        model_used=config.MODEL_NAME,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    user_input: str,
    prior_outputs: dict,
    evidence_pack: dict | None = None,
    approval_context: dict | None = None,
) -> dict:
    """
    Run the AURA Scientific Verifier.

    Args:
        user_input:       Original user request.
        prior_outputs:    Dict containing strategic_governor and research_scout outputs.
        evidence_pack:    Optional dict with top_papers, profile_topics, sources_used.
        approval_context: Optional dict with governance context (not yet used in Phase 1).

    Returns:
        VerificationReport as a dict.
    """
    # Step 1: structured extraction — no LLM, no truncation risk
    structured, truncated = _extract_structured_content(prior_outputs)
    evidence_summary = _build_evidence_summary(evidence_pack)

    # Identify what sources were actually checked
    sources_checked: list[str] = []
    if evidence_pack:
        sources_checked = evidence_pack.get("sources_used", [])
    if structured.get("literature_scan_used"):
        for p in structured.get("cited_papers", []):
            src = p.get("source", "")
            if src and src not in sources_checked:
                sources_checked.append(src)

    # Build audit hash from deterministic content
    input_hash = _make_input_hash(user_input + json.dumps(structured, sort_keys=True))

    # Step 2: build verifier prompt
    prompt_content = json.dumps(structured, indent=2)
    user_prompt = (
        f"ORIGINAL USER REQUEST:\n{user_input}\n\n"
        f"STRUCTURED CONTENT TO VERIFY:\n{prompt_content}\n\n"
        f"EVIDENCE PACK:\n{evidence_summary}\n\n"
        f"TRUNCATION NOTE: {'Prior outputs were large and compressed.' if truncated else 'No truncation.'}\n\n"
        "Verify the above content and return strict JSON matching the required schema."
    )

    # Step 3: first LLM call
    raw: dict = {}
    parse_error: str = ""
    try:
        raw = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.0)
    except Exception as exc:
        parse_error = str(exc)

    # Step 4: repair pass if first call failed or returned unusable output
    if parse_error or not isinstance(raw, dict) or "overall_assessment" not in raw:
        try:
            raw = _repair_json(str(raw) if raw else parse_error)
        except Exception as repair_exc:
            report = _incomplete_fallback(f"Parse failed: {parse_error}; Repair failed: {repair_exc}")
            _add_audit_metadata(report, input_hash, sources_checked)
            return report.model_dump()

    # Step 5: coerce into schema
    try:
        report = _safe_parse_report(raw, truncated)
    except Exception as exc:
        report = _incomplete_fallback(f"Schema coercion failed: {exc}")

    _add_audit_metadata(report, input_hash, sources_checked)
    return report.model_dump()
