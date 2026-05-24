"""
AURA Scientific Verifier — claim-level, evidence-aware, routing verifier.

Pipeline:
    prior_outputs
        -> _extract_structured_content()   (Python-level, no LLM)
        -> _build_prompt()
        -> ask_llm()                       (Qwen3:8b, temperature=0.0)
        -> _safe_parse_report()
        -> [repair pass if parse fails]
        -> _backfill_compat_fields()
        -> _add_audit_metadata()
        -> return VerificationReport dict

Failure-closed guarantees (Phase 1):
    * Every code path returns a schema-valid VerificationReport-compatible
      dict — no callers ever see a partial dict, list, string, or None.
    * `_safe_parse_report` rejects non-dict JSON (arrays, scalars, null).
    * `evidence_pack` fields (sources, top_papers, profile_topics, scout
      mode/confidence, evidence_quality) are consumed, not silently dropped.
    * Crashed-scout markers (partial_results + failed_stage in known crash
      stages) force evidence_quality down to "none".
    * Missing/invalid scout evidence_quality defaults to "weak", not
      "moderate" — a fallback default must never read as moderate evidence.
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
# Structured extraction (Python, no LLM)
# ---------------------------------------------------------------------------

_REAL_SCOUT_MODES = {
    "literature_scan", "ideation", "gap_analysis", "grant_opportunity",
}
_EV_LEVELS = {"none": 0, "weak": 1, "moderate": 2, "strong": 3}
_ROUTE_PRIORITY = {
    "reject": 5,
    "human_review": 4,
    "retrieve_more_evidence": 3,
    "revise": 2,
    "approve": 1,
}

# Stages indicating the scout crashed or returned a placeholder rather than
# a real analysis — verifier must NEVER infer moderate evidence from these.
_SCOUT_CRASH_STAGES = {
    "unhandled_exception",
    "agent_run",
    "not_implemented",
    "crash",
}

# Safe routes that downstream code (orchestrator persistence,
# self-evolution learning) may treat as affirmative.  Defined here so the
# verifier's failure-state output never accidentally matches.
SAFE_VERIFIER_ROUTES: frozenset[str] = frozenset({"approve", "revise"})


def _resolve_evidence_quality(scout: dict, evidence_pack: dict | None) -> str:
    """Decide the evidence_quality string the verifier should see.

    Priority:
        1. ``evidence_pack["evidence_quality"]`` if explicitly set.
        2. ``scout["evidence_quality"]`` if a valid level.
        3. Default ``"weak"`` (NOT ``"moderate"``) — defect 10.

    Then, if the scout reports ``partial_results=True`` with a crash-marker
    failed_stage, force the result to ``"none"`` regardless.
    """
    raw: Any = None
    if isinstance(evidence_pack, dict):
        raw = evidence_pack.get("evidence_quality")
    if not isinstance(raw, str) or raw not in _EV_LEVELS:
        raw = scout.get("evidence_quality") if isinstance(scout, dict) else None
    if not isinstance(raw, str) or raw not in _EV_LEVELS:
        raw = "weak"  # defect 10: fallback default is weak, not moderate

    # Crash override.
    if isinstance(scout, dict) and scout.get("partial_results"):
        stage = (scout.get("failed_stage") or "").strip()
        if stage in _SCOUT_CRASH_STAGES:
            return "none"
        # Other partial states are downgraded if currently > weak.
        if _EV_LEVELS.get(raw, 0) > 1:
            return "weak"

    return raw


def _extract_structured_content(
    all_outputs: dict,
    evidence_pack: dict | None = None,
) -> dict:
    """Aggregate claims, risks, and evidence from the full session state.

    Collects from research_scout and every specialist present in the
    `specialists` dict, so the verifier sees a unified view of the whole
    multi-agent workflow.  Evidence-pack fields take precedence over scout
    fields when both are provided (defect 5).
    """
    gov = all_outputs.get("strategic_governor") or {}
    scout = all_outputs.get("research_scout") or {}
    if not isinstance(scout, dict):
        scout = {}
    specialists = all_outputs.get("specialists") or {}
    if not isinstance(specialists, dict):
        specialists = {}
    if not isinstance(evidence_pack, dict):
        evidence_pack = {}

    # --- claims ---------------------------------------------------------------
    # Defect 26: a scalar string MUST become ["string"], not character items.
    from core import normalization as _norm
    claims_raw = _norm.ensure_str_list(
        scout.get("claims_for_verification"), max_items=20,
    )
    # Specialists may also have claims; include them so reject-vs-approve
    # logic at the holistic level sees every claim.
    for name, spec_out in specialists.items():
        if isinstance(spec_out, dict):
            spec_claims = _norm.ensure_str_list(
                spec_out.get("claims_for_verification"), max_items=8,
            )
            for c in spec_claims:
                claims_raw.append(f"[{name}] {c}")

    # --- findings -------------------------------------------------------------
    findings = _norm.ensure_str_list(scout.get("findings"), max_items=10)

    # --- risks ----------------------------------------------------------------
    risks: list[dict] = []
    scout_risks = scout.get("risks", [])
    for item in scout_risks:
        if isinstance(item, str):
            risks.append({"agent": "research_scout", "description": item})
        elif isinstance(item, dict) and "description" in item:
            item.setdefault("agent", "research_scout")
            risks.append(item)
    for name, spec_out in specialists.items():
        if not isinstance(spec_out, dict):
            continue
        spec_risks = spec_out.get("risks", [])
        for item in spec_risks:
            if isinstance(item, str):
                risks.append({"agent": name, "description": item})
            elif isinstance(item, dict) and "description" in item:
                item.setdefault("agent", name)
                risks.append(item)

    # --- assumptions ----------------------------------------------------------
    # Defect 26: protect against scalar-string assumptions.
    assumptions = _norm.ensure_str_list(scout.get("assumptions"), max_items=8)
    for name, spec_out in specialists.items():
        if isinstance(spec_out, dict):
            assumptions.extend(
                _norm.ensure_str_list(spec_out.get("assumptions"), max_items=4)
            )

    # --- evidence quality strings (defect 5 + defect 10) ---------------------
    evidence_quality = _resolve_evidence_quality(scout, evidence_pack)

    # Scout confidence: evidence_pack override (defect 5) → scout → default.
    scout_confidence = (
        evidence_pack.get("scout_confidence")
        or scout.get("confidence", "medium")
    )

    # --- paper count ----------------------------------------------------------
    # Defect 27 (verifier side): top_papers may be malformed — coerce safely.
    top_papers_pack = _norm.ensure_dict_list(evidence_pack.get("top_papers"))
    if top_papers_pack:
        top_papers = top_papers_pack
    else:
        top_papers = _norm.ensure_dict_list(scout.get("top_papers"))
    if scout.get("literature_scan_used") or evidence_pack.get("top_papers"):
        paper_count = len(top_papers)
    else:
        paper_count = 0

    # --- recommended actions --------------------------------------------------
    # Defect 26: a scalar string here was being expanded to per-character
    # audit items.  Normalize first, then promote string/dict shapes.
    recs: list[str] = []

    def _coerce_action(item) -> str:
        if isinstance(item, str):
            s = item.strip()
            return s
        if isinstance(item, dict):
            return _norm.ensure_str(item.get("description"))
        return ""

    scout_recs = scout.get("recommended_actions")
    if isinstance(scout_recs, str):
        scout_recs = [scout_recs]
    elif not isinstance(scout_recs, list):
        scout_recs = []
    for item in scout_recs[:10]:
        s = _coerce_action(item)
        if s:
            recs.append(s)
    for name, spec_out in specialists.items():
        if not isinstance(spec_out, dict):
            continue
        sp_recs = spec_out.get("recommended_actions")
        if isinstance(sp_recs, str):
            sp_recs = [sp_recs]
        elif not isinstance(sp_recs, list):
            sp_recs = []
        for item in sp_recs[:5]:
            s = _coerce_action(item)
            if s:
                recs.append(f"[{name}] {s}")

    # --- grants / gaps -------------------------------------------------------
    grant_angles = _norm.ensure_str_list(scout.get("grant_angles"), max_items=4)
    gap_text = (scout.get("research_gap_candidate") or "")[:400]

    # --- mode and evidence flags ---------------------------------------------
    # Evidence-pack scout_mode takes precedence (defect 5).
    mode = evidence_pack.get("scout_mode") or scout.get("mode", "")
    literature_scan_used = bool(
        scout.get("literature_scan_used") or evidence_pack.get("top_papers")
    )

    # --- evidence-pack-only fields the verifier should see ------------------
    profile_topics = list(evidence_pack.get("profile_topics", []))[:10]
    sources_used = list(evidence_pack.get("sources_used", []))

    # Phase 2 Defect 7: lift local-document evidence + ingestion summaries
    # out of the evidence_pack so the verifier prompt can audit them.
    local_literature_evidence = list(evidence_pack.get("local_literature_evidence", []) or [])[:8]
    local_patent_evidence = list(evidence_pack.get("local_patent_evidence", []) or [])[:8]
    local_lit_summary = evidence_pack.get("local_literature_ingestion_summary") or {}
    local_pat_summary = evidence_pack.get("local_patent_ingestion_summary") or {}

    return {
        "claims": [str(c).strip() for c in claims_raw if str(c).strip()],
        "findings": [str(f).strip() for f in findings if str(f).strip()],
        "risks": [
            {
                "agent": r.get("agent", "unknown"),
                "description": r.get("description", str(r)),
            }
            for r in risks
            if isinstance(r, dict)
        ],
        "assumptions": [str(a).strip() for a in assumptions if str(a).strip()],
        "recommended_actions": [str(a).strip() for a in recs if str(a).strip()],
        "grant_angles": grant_angles,
        "gap_candidate": gap_text,
        "evidence_quality": evidence_quality,
        "scout_confidence": scout_confidence,
        "paper_count": paper_count,
        "mode": mode,
        "literature_scan_used": literature_scan_used,
        # Evidence-pack-derived:
        "profile_topics": profile_topics,
        "sources_used": sources_used,
        "top_papers": top_papers[:10],
        # Crash markers from scout — surfaced so the verifier prompt can see them.
        "scout_partial_results": bool(scout.get("partial_results")),
        "scout_failed_stage": (scout.get("failed_stage") or "")[:80],
        # Phase 2 Defect 7: local-document evidence for verifier reasoning.
        "local_literature_evidence":         local_literature_evidence,
        "local_patent_evidence":             local_patent_evidence,
        "local_literature_ingestion_summary": local_lit_summary,
        "local_patent_ingestion_summary":    local_pat_summary,
    }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are the AURA Scientific Verifier — a strict, evidence-aware peer reviewer
for a photophysics / OLED / TADF research group.

You receive a structured **Verification Context** (claims, risks, evidence
quality, reported findings, assumptions, recommended actions, gap candidate,
profile topics, sources, and crash markers). Your task is to produce a
**demanding, high-rigor verification report** in strict JSON.

Rules (never break):
- Over-claiming is the cardinal sin.  Flag it aggressively.
- Evaluate claims against the evidence quality reported *by the agents*.
  Do NOT treat a claim as verified simply because an agent asserted it.
- Use the **claims** list as your primary truth-audit surface.
- Consider **risks**, **assumptions**, and **recommended actions** only
  for context — they do NOT count as scientific evidence.
- Separate methodology concerns, novelty concerns, citation concerns,
  grant-framing concerns, and action-governance concerns.
- Clearly mark which outputs require human approval before use.
- When evidence is insufficient for a claim, assign an appropriate severity:
  critical, high, medium, or low.
- If the Scout crashed (partial_results=true with a crash-marker stage), do
  NOT approve. Route to human_review or reject.
- The final route MUST be one of:
  approve | revise | retrieve_more_evidence | human_review | reject.
"""

_USER_PROMPT_TEMPLATE = """\
=== VERIFICATION CONTEXT ===

Claims (audit these):
{claims}

Findings (reported by scout):
{findings}

Risks (aggregated from all agents):
{risks}

Assumptions:
{assumptions}

Recommended actions:
{recommended_actions}

Grant angles:
{grant_angles}

Gap candidate:
{gap_candidate}

Scout metadata:
- Evidence quality: {evidence_quality}
- Scout confidence: {scout_confidence}
- Paper count: {paper_count}
- Mode: {mode}
- Literature scan used: {literature_scan_used}
- Scout partial_results: {scout_partial_results}
- Scout failed_stage: {scout_failed_stage}

Evidence pack (consumed):
- Profile topics: {profile_topics}
- Sources used: {sources_used}
- Top papers: {top_papers_brief}

Local literature evidence (user-supplied folder; UNVERIFIED):
- Ingestion summary: {local_literature_ingestion_summary}
{local_literature_evidence_block}

Local patent evidence (user-supplied folder; UNVERIFIED, NOT legally verified prior art):
- Ingestion summary: {local_patent_ingestion_summary}
{local_patent_evidence_block}

User request:
{user_input}

=== TASK ===
Produce the VerificationReport as strict JSON with claim_checks array and route.

CRITICAL FORMAT REQUIREMENT for claim_checks:
- The array MUST have exactly one entry per claim in the **Claims** list above,
  in the same order.
- Each entry MUST include a "claim" field containing the VERBATIM claim text
  from the Claims list. Do NOT paraphrase, truncate, or leave it empty.
- Required fields per entry: claim (string, verbatim), claim_type, support_status,
  severity, confidence (0.0-1.0), evidence_needed (list), correction (string).
- If evidence is insufficient to verify a claim, set support_status="unverifiable"
  and explain what is missing in evidence_needed — but still echo the claim text.
"""


# ---------------------------------------------------------------------------
# Safe parsing, repair, backfill
# ---------------------------------------------------------------------------

def _safe_parse_report(text: str) -> dict:
    """Parse LLM output to a dict.

    Defect 6: must reject arrays, strings, integers, booleans, null.
    Returns ``{}`` for any non-dict JSON or parse failure.
    """
    if not isinstance(text, str):
        return {}
    text = text.strip()
    if not text:
        return {}

    # Strip optional ``` ```json ... ``` fence.
    import re
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        text = match.group(1).strip()

    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}
    # Defect 6: reject any non-dict JSON value.
    if not isinstance(obj, dict):
        return {}
    return obj


def _failure_safe_report(reason: str, *, route: str = "human_review") -> dict:
    """Return a fully schema-valid VerificationReport-shaped dict.

    Used by every failure path so callers never receive a partial dict.
    The route defaults to ``human_review`` so the failure cannot accidentally
    pass downstream allowlists like ``SAFE_VERIFIER_ROUTES``.
    """
    base = VerificationReport(
        route=route,
        overall_assessment="incomplete",
        final_recommendation="needs_more_evidence",
        novelty_risks=[],
        methodology_risks=[],
        citation_risks=[],
        grant_risks=[],
        action_governance_risks=[f"Verifier failure: {reason[:160]}"],
        revision_instructions=[
            "Verification could not complete — re-run the verifier or "
            "supply more evidence before relying on this output.",
        ],
    ).model_dump()
    # Backward-compat keys read by orchestrator + self-evolution.
    base["risks"] = [f"Verifier failure: {reason[:160]}"]
    base["contradictions"] = []
    base["unsupported_claims"] = []
    base["corrections"] = []
    base["assumptions"] = []
    base["failure_reason"] = reason[:240]
    base["failed"] = True
    return base


def _backfill_compat_fields(report: dict) -> dict:
    """Ensure every VerificationReport field plus orchestrator/self-evolution
    backward-compat keys are present.

    Also DEFENSIVELY coerces a small set of string-typed fields to real
    strings.  Some LLMs (deepseek-v4-flash in particular) occasionally
    return a structured object for ``overall_assessment`` / ``route`` /
    ``final_recommendation`` instead of the documented short string —
    and the downstream rich-formatter crashes with
    ``TypeError: unhashable type: 'dict'`` when that happens.  Coerce
    here so the bug is fixed at the source, not just papered over in
    the CLI.
    """
    schema_defaults = VerificationReport().model_dump()
    for key, default in schema_defaults.items():
        if key not in report:
            report[key] = default
    # Backward-compat keys used by callers (orchestrator, self-evolution).
    report.setdefault("risks", [])
    report.setdefault("contradictions", [])
    report.setdefault("unsupported_claims", [])
    report.setdefault("corrections", [])
    report.setdefault("assumptions", [])

    # Coerce known string-typed fields (and the route/recommendation
    # downstream consumers .get() into).  We deliberately do NOT try to
    # invent a sensible value from a dict — just stringify so the
    # downstream code stops crashing; the verifier's _safe_parse_report
    # / repair pass should also reject this shape in future runs.
    _coerce_str_field(report, "overall_assessment", "incomplete")
    # Fail closed: a non-string / missing route escalates to human_review,
    # never silently to a routine "revise".
    _coerce_str_field(report, "route", "human_review")
    _coerce_str_field(report, "final_recommendation", "needs_more_evidence")
    return report


def _coerce_str_field(report: dict, key: str, default: str) -> None:
    """Force ``report[key]`` to a string.  Lists/dicts get JSON-serialized;
    None / missing → ``default``."""
    v = report.get(key)
    if isinstance(v, str):
        return
    if v is None:
        report[key] = default
        return
    if isinstance(v, (int, float, bool)):
        report[key] = str(v)
        return
    try:
        import json
        report[key] = json.dumps(v, default=str)[:200] or default
    except Exception:
        report[key] = default


def _add_audit_metadata(report: dict, input_hash: str, sources: list[str]) -> None:
    report["verified_at"] = datetime.now(timezone.utc).isoformat()
    report["model_used"] = config.get_model_name()
    report["evidence_sources_checked"] = sources


# ---------------------------------------------------------------------------
# Enum normalisation + derived-field population (safety-critical)
# ---------------------------------------------------------------------------
# The verifier output drives persistence / retry / approval gates, which key
# off ``route``, ``support_status``, ``severity`` etc.  An LLM that emits an
# UNKNOWN enum value (e.g. route="unknown_route") must NOT pass through raw —
# it is coerced to the conservative (fail-closed) default so a malformed
# verdict can never bypass a gate.  This restores behaviour that a prior
# refactor dropped.

_VALID_OVERALL = {"strong", "acceptable", "weak", "incomplete"}
_VALID_ROUTE = {
    "approve", "revise", "retrieve_more_evidence", "human_review", "reject",
}
_VALID_RECOMMENDATION = {
    "submit_ready", "revise", "needs_more_evidence", "do_not_submit", "reject",
}
_VALID_CLAIM_TYPE = {
    "novelty", "mechanism", "methodology", "performance", "grant",
    "application", "citation", "other",
}
_VALID_SUPPORT_STATUS = {
    "supported", "partially_supported", "unsupported", "contradicted",
    "unverifiable",
}
# "critical" is a first-class severity the prompt instructs the LLM to use
# for the most serious problems; it MUST be preserved (never normalised to
# "low"), and it participates in the approve-downgrade safety check.
_VALID_SEVERITY = {"low", "medium", "high", "critical"}
# Severities that, when attached to an unsupported/unverifiable claim,
# forbid an ``approve`` verdict.
_BLOCKING_SEVERITIES = {"high", "critical"}
# Statuses that mean the verifier could NOT stand behind the claim.
_UNBACKED_STATUSES = {"unsupported", "contradicted", "unverifiable"}


def _coerce_enum(value, allowed: set[str], default: str) -> str:
    s = str(value or "").strip().lower()
    return s if s in allowed else default


def _normalize_and_derive(report: dict) -> dict:
    """Coerce invalid enums to fail-closed defaults, clamp confidence to
    [0, 1], and DERIVE ``unsupported_claims`` + ``corrections`` from the
    per-claim checks.  Idempotent.

    Fail-closed routing:
      * a MISSING or INVALID route becomes ``human_review`` (NOT
        ``revise``) — an unparseable verdict must escalate to a human,
        not silently downgrade to a routine revision.
    """
    # Top-level enums.  overall/final default conservatively; route fails
    # CLOSED to human_review on missing/invalid (safety > convenience).
    report["overall_assessment"] = _coerce_enum(
        report.get("overall_assessment"), _VALID_OVERALL, "incomplete")
    report["route"] = _coerce_enum(
        report.get("route"), _VALID_ROUTE, "human_review")
    report["final_recommendation"] = _coerce_enum(
        report.get("final_recommendation"), _VALID_RECOMMENDATION,
        "needs_more_evidence")

    # Per-claim enums + confidence clamp.
    checks = report.get("claim_checks") or []
    derived_unsupported: list[str] = []
    derived_corrections: list[str] = []
    for c in checks:
        if not isinstance(c, dict):
            continue
        c["claim_type"] = _coerce_enum(
            c.get("claim_type"), _VALID_CLAIM_TYPE, "mechanism")
        c["support_status"] = _coerce_enum(
            c.get("support_status"), _VALID_SUPPORT_STATUS, "unverifiable")
        # NOTE: default is "low" for a missing/garbage severity, but a
        # genuine "critical" is in the allowed set and preserved as-is.
        c["severity"] = _coerce_enum(
            c.get("severity"), _VALID_SEVERITY, "low")
        try:
            conf = float(c.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        c["confidence"] = max(0.0, min(1.0, conf))

        # Derive: claims the verifier could not support.
        if c["support_status"] in ("unsupported", "contradicted"):
            claim_text = (c.get("claim") or "").strip()
            if claim_text:
                derived_unsupported.append(claim_text)
        # Derive: high/critical-severity corrections surfaced as a flat list.
        if c["severity"] in _BLOCKING_SEVERITIES:
            corr = (c.get("correction") or "").strip()
            if corr:
                derived_corrections.append(corr)

    # Only populate derived fields when the LLM did not already provide
    # them, so an explicit LLM-supplied list is never clobbered.
    if not report.get("unsupported_claims"):
        report["unsupported_claims"] = derived_unsupported
    if not report.get("corrections"):
        report["corrections"] = derived_corrections
    return report


def _enforce_semantic_consistency(
    report: dict,
    source_claim_count: int,
    *,
    real_check_count: int | None = None,
) -> dict:
    """Fail-closed semantic-consistency pass run AFTER normalisation.

    Catches verdicts that are individually well-formed but jointly
    contradictory or unsafe:

      1. Source claims exist but the verifier produced NO real
         claim_checks (only padded placeholders, or none) → it did not
         actually evaluate the claims → escalate to human_review.
      2. ``approve`` while a high/critical-severity claim is
         unsupported / contradicted / unverifiable → an approve cannot
         stand on a serious unbacked claim → downgrade to human_review.
      3. ``approve`` while a placeholder ``unverifiable`` claim_check was
         injected (the LLM skipped a claim) → the verifier did not
         actually verify that claim → downgrade to human_review.

    ``real_check_count`` is the number of LLM-produced checks BEFORE
    placeholder padding; when omitted it falls back to the current count.
    All downgrades are recorded as risks for auditability.
    """
    checks = report.get("claim_checks") or []
    if real_check_count is None:
        real_check_count = len(checks)
    risks = list(report.get("risks") or [])

    # (1) Claims existed but the verifier checked nothing real → fail closed.
    if source_claim_count > 0 and real_check_count == 0:
        if report.get("route") not in ("human_review", "reject"):
            risks.append(
                "Semantic-consistency: source claims were present but the "
                "verifier produced no real claim_checks — escalating to "
                "human_review (fail closed)."
            )
            report["route"] = "human_review"
            report["overall_assessment"] = "incomplete"
            report["final_recommendation"] = "needs_more_evidence"

    # (2) + (3) approve on serious unbacked / placeholder claims.
    if report.get("route") == "approve":
        serious_unbacked = [
            c for c in checks
            if isinstance(c, dict)
            and c.get("support_status") in _UNBACKED_STATUSES
            and c.get("severity") in _BLOCKING_SEVERITIES
        ]
        placeholder_injected = any(
            isinstance(c, dict)
            and c.get("support_status") == "unverifiable"
            and "Verifier omitted this claim" in " ".join(
                str(x) for x in (c.get("evidence_needed") or [])
            )
            for c in checks
        )
        if serious_unbacked or placeholder_injected:
            reason = (
                "high/critical unsupported or unverifiable claim(s)"
                if serious_unbacked else
                "an unverified placeholder claim_check"
            )
            risks.append(
                f"Semantic-consistency: 'approve' downgraded to "
                f"'human_review' because the report contains {reason}."
            )
            report["route"] = "human_review"

    report["risks"] = risks
    return report


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(
    user_input: str,
    all_outputs: dict,
    evidence_pack: dict | None = None,
) -> dict:
    """Return a full VerificationReport dict ready for formatter / orchestrator.

    Every return path is schema-valid.  Internal failures produce a
    ``_failure_safe_report(...)`` whose route is ``human_review`` so the
    downstream persistence and learning gates fail closed.
    """
    structured = _extract_structured_content(all_outputs, evidence_pack)

    # Evidence-pack-derived sources_used; falls back to extracted value.
    sources_used = structured["sources_used"]

    # Format the user prompt.
    claims_str = "\n".join(f"  - {c}" for c in structured["claims"]) or "(none)"
    findings_str = "\n".join(f"  - {f}" for f in structured["findings"]) or "(none)"
    risks_str = "\n".join(
        f"  [{r['agent']}] {r['description']}" for r in structured["risks"]
    ) or "(none)"
    assumptions_str = "\n".join(f"  - {a}" for a in structured["assumptions"]) or "(none)"
    recs_str = "\n".join(f"  - {r}" for r in structured["recommended_actions"]) or "(none)"
    grant_str = "\n".join(f"  - {g}" for g in structured["grant_angles"]) or "(none)"
    profile_str = "\n".join(f"  - {t}" for t in structured["profile_topics"]) or "(none)"
    sources_str = "\n".join(f"  - {s}" for s in sources_used) or "(none)"
    top_papers_brief = "\n".join(
        f"  - {p.get('title','(untitled)')} [{p.get('source','')}]"
        for p in structured["top_papers"] if isinstance(p, dict)
    ) or "(none)"

    def _format_local_evidence(refs: list) -> str:
        lines: list[str] = []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            safe_ref = ref.get("safe_reference") or ref.get("document_id") or "(unknown)"
            loc = ref.get("location_hint") or ""
            quality = ref.get("extraction_quality") or "unknown"
            score = ref.get("retrieval_score")
            score_str = f" score={score:.3f}" if isinstance(score, (int, float)) else ""
            excerpt = (ref.get("excerpt") or "").strip().replace("\n", " ")
            if len(excerpt) > 600:
                excerpt = excerpt[:600] + "…"
            header = f"  - {safe_ref}"
            if loc:
                header += f" @ {loc}"
            header += f" (quality={quality}{score_str})"
            lines.append(header)
            if excerpt:
                lines.append(f"      excerpt: {excerpt}")
        return "\n".join(lines) or "  (none)"

    local_lit_block = _format_local_evidence(structured["local_literature_evidence"])
    local_pat_block = _format_local_evidence(structured["local_patent_evidence"])

    def _summarize_ingestion(summary: dict) -> str:
        if not isinstance(summary, dict) or not summary:
            return "(not provided)"
        parts = [
            f"used={summary.get('used', False)}",
            f"chunks_indexed={summary.get('chunks_indexed', 0)}",
            f"partial_results={summary.get('partial_results', False)}",
            f"evidence_quality_hint={summary.get('evidence_quality_hint', 'unknown')}",
        ]
        if summary.get("scan_truncated"):
            parts.append(
                f"scan_truncated=true(max_files={summary.get('max_files_applied', 0)},"
                f"omitted~{summary.get('omitted_count', 0)})"
            )
        if summary.get("ocr_used"):
            parts.append("ocr_used=true")
        if summary.get("failure_reason"):
            parts.append(f"failure_reason={str(summary['failure_reason'])[:160]}")
        return "; ".join(parts)

    local_lit_summary_str = _summarize_ingestion(structured["local_literature_ingestion_summary"])
    local_pat_summary_str = _summarize_ingestion(structured["local_patent_ingestion_summary"])

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        claims=claims_str,
        findings=findings_str,
        risks=risks_str,
        assumptions=assumptions_str,
        recommended_actions=recs_str,
        grant_angles=grant_str,
        gap_candidate=structured["gap_candidate"],
        evidence_quality=structured["evidence_quality"],
        scout_confidence=structured["scout_confidence"],
        paper_count=structured["paper_count"],
        mode=structured["mode"],
        literature_scan_used=structured["literature_scan_used"],
        scout_partial_results=structured["scout_partial_results"],
        scout_failed_stage=structured["scout_failed_stage"] or "(none)",
        profile_topics=profile_str,
        sources_used=sources_str,
        top_papers_brief=top_papers_brief,
        local_literature_evidence_block=local_lit_block,
        local_patent_evidence_block=local_pat_block,
        local_literature_ingestion_summary=local_lit_summary_str,
        local_patent_ingestion_summary=local_pat_summary_str,
        user_input=user_input,
    )

    # First attempt.
    raw: dict = {}
    primary_error: str = ""
    try:
        raw_response = ask_llm(SYSTEM_PROMPT, user_prompt, temperature=0.0, json_mode=True)
        raw = _safe_parse_report(raw_response)
    except Exception as exc:
        primary_error = f"primary call failed: {exc}"

    if not raw or not raw.get("claim_checks"):
        # Repair pass with explicit instruction.
        repair_prompt = (
            "The previous attempt returned invalid JSON. "
            "Please output the report again as valid JSON. "
            + user_prompt
        )
        try:
            raw_response2 = ask_llm(SYSTEM_PROMPT, repair_prompt, temperature=0.0, json_mode=True)
            raw2 = _safe_parse_report(raw_response2)
            if raw2:
                raw = raw2
        except Exception as exc:
            primary_error = primary_error or f"repair call failed: {exc}"

    # If we STILL have no parseable JSON, return a fully schema-valid failure.
    if not raw:
        report = _failure_safe_report(
            reason=primary_error or "LLM did not return parseable JSON",
        )
        audit_hash = hashlib.sha256(user_input.encode()).hexdigest()[:12]
        _add_audit_metadata(report, audit_hash, sources_used)
        return report

    report = _backfill_compat_fields(raw)

    audit_hash = hashlib.sha256(user_input.encode()).hexdigest()[:12]
    _add_audit_metadata(report, audit_hash, sources_used)

    # Ensure claim_checks entries are well-formed dicts.
    checks = report.get("claim_checks", [])
    if not isinstance(checks, list):
        checks = []
        report["claim_checks"] = checks

    # Backfill empty/missing ``claim`` text by index from the source
    # ``claims_for_verification`` list.  Some LLMs (e.g. deepseek-v4-flash)
    # return the shape of each claim_check but omit the verbatim claim
    # string, which silently turns every row into "(empty claim, default
    # 0.5 confidence)" and forces the route to ``human_review``.  Echoing
    # the source claim restores both the formatter table AND the
    # verifier's ability to route to ``retrieve_more_evidence``.
    source_claims = structured.get("claims", []) or []
    for idx, c in enumerate(checks):
        if not isinstance(c, dict):
            continue
        existing = (c.get("claim") or "").strip()
        if not existing and idx < len(source_claims):
            c["claim"] = source_claims[idx]
        c.setdefault("claim", "")
        c.setdefault("claim_type", "mechanism")
        c.setdefault("support_status", "unverifiable")
        c.setdefault("severity", "low")
        c.setdefault("confidence", 0.5)
        c.setdefault("evidence_needed", [])
        c.setdefault("correction", "")

    # Capture how many REAL (LLM-produced) claim_checks exist BEFORE we
    # inject placeholders below, so the semantic-consistency pass can
    # tell "the verifier actually checked nothing" apart from "we padded
    # the table".
    real_check_count = len(checks)

    # If the LLM returned fewer claim_checks than source claims, append
    # placeholder entries so each claim is at least visible in the table
    # (status: unverifiable, severity: high — the LLM skipped it).
    for idx in range(len(checks), len(source_claims)):
        checks.append({
            "claim": source_claims[idx],
            "claim_type": "mechanism",
            "support_status": "unverifiable",
            "severity": "high",
            "confidence": 0.0,
            "evidence_needed": [
                "Verifier omitted this claim — re-run with stricter prompt"
                " or retrieve more evidence."
            ],
            "correction": "",
        })
    report["claim_checks"] = checks

    # Safety-critical: coerce invalid enums to fail-closed defaults and
    # derive unsupported_claims / corrections from the per-claim checks.
    report = _normalize_and_derive(report)

    # Centralised semantic-consistency pass (fail closed): catches
    # approve-on-serious-unbacked-claim, approve-on-injected-placeholder,
    # and source-claims-present-but-nothing-checked.
    report = _enforce_semantic_consistency(
        report, len(source_claims), real_check_count=real_check_count,
    )

    return report
