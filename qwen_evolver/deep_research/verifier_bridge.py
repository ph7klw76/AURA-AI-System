"""
Bridge from Deep Research → AURA Scientific Verifier.

The Scientific Verifier's structured extractor (``_extract_structured_content``)
reads claims from ``all_outputs["research_scout"]["claims_for_verification"]``.
Deep Research stores its claims in ``EvidencePack.evidence_claims`` and its
top-level findings in ``EvidencePack.key_findings``.  Those need to be
surfaced as a synthetic ``research_scout`` payload so the verifier actually
audits them rather than silently ignoring the deep-research run (defect 4).

The function always returns a ``ResearchVerificationResult`` — its failure
path now reports structured details instead of just ``Verdict.human_review``.
"""

from __future__ import annotations

import agents.scientific_verifier as verifier_module

from .schemas import EvidencePack, ResearchVerificationResult, Verdict


def _synthetic_scout_payload(pack: EvidencePack) -> dict:
    """Build a ``research_scout``-shaped dict that surfaces DR claims/evidence."""
    claims = [c.claim_text for c in pack.evidence_claims if c.claim_text]

    risks: list[str] = list(pack.contradictions or [])
    for q in (pack.unresolved_questions or []):
        if q:
            risks.append(f"Unresolved question: {q}")

    top_papers = [
        {
            "title": s.title or "(untitled)",
            "source": s.provider or "deep_research",
            "total_score": 0.0,
            "url": s.url,
            "source_id": s.source_id,
        }
        for s in (pack.sources or [])
    ]

    # Evidence-quality heuristic.  Never strong from deep research at this
    # stage.
    #
    # Phase 2 (goal J): a run that fetched ZERO sources has ABSENT evidence,
    # not "weak" evidence.  Labelling it "weak" implies real-but-thin
    # evidence exists; "none" truthfully signals there is nothing to weigh.
    # Confidence is forced to "low" in that case so downstream gates cannot
    # treat an empty pack as a medium-confidence result.
    supported = sum(
        1 for c in pack.evidence_claims
        if getattr(c.support_status, "value", str(c.support_status)) == "supported"
    )
    no_sources = len(pack.sources or []) == 0
    if no_sources:
        evidence_quality = "none"
        confidence = "low"
    else:
        confidence = pack.confidence_summary or "medium"
        if supported == 0:
            evidence_quality = "weak"
        elif supported < 3:
            evidence_quality = "weak"
        else:
            evidence_quality = "moderate"

    return {
        "mode": "deep_research",
        "summary": pack.research_question or "",
        "findings": list(pack.key_findings or []),
        "claims_for_verification": claims,
        "risks": risks,
        "top_papers": top_papers,
        "literature_scan_used": True,
        "confidence": confidence,
        "evidence_quality": evidence_quality,
        "partial_results": no_sources,
        "failed_stage": "no_sources_fetched" if no_sources else "",
    }


def verify_evidence(pack: EvidencePack, user_input: str) -> ResearchVerificationResult:
    """Run the AURA Scientific Verifier over a Deep Research evidence pack."""
    synthetic_scout = _synthetic_scout_payload(pack)

    evidence_pack = {
        "profile_topics": [],
        "sources_used": list({
            s.provider for s in (pack.sources or []) if s.provider
        }),
        "top_papers": synthetic_scout["top_papers"],
        "scout_mode": "deep_research",
        "scout_confidence": pack.confidence_summary or "medium",
        "evidence_quality": synthetic_scout["evidence_quality"],
    }

    prior = {
        "strategic_governor": {"task_type": "deep_research"},
        "research_scout": synthetic_scout,
        "specialists": {},
        "evidence_pack": pack.model_dump(),
    }

    try:
        result = verifier_module.run(user_input, prior, evidence_pack=evidence_pack)
    except Exception as exc:
        # Phase 1 / 3 failure-closed path: structured details + sentinel
        # confidence (-1.0) so callers can distinguish "verifier failed"
        # from "verifier returned 0.0".
        return ResearchVerificationResult(
            decision=Verdict.human_review,
            unsupported_claims=[
                "Deep Research verifier bridge failed before route decision."
            ],
            contradictions=[],
            risks=[f"Verifier bridge exception: {exc}"],
            claims_needing_more_evidence=[
                f"Verifier bridge exception: {exc}"
            ],
            report_revision_notes=[
                "Manual review required — verifier did not produce a verdict."
            ],
            overall_confidence=-1.0,
        )

    route_raw = (result.get("route") or "").strip().lower() if isinstance(result, dict) else ""
    try:
        decision = Verdict(route_raw) if route_raw else Verdict.human_review
    except ValueError:
        decision = Verdict.human_review

    # Defect 5: contradictions and risks are DIFFERENT concepts.  The verifier
    # may emit both — preserve each in its own field.  If the verifier omits
    # `contradictions`, the bridge MUST NOT silently substitute `risks`.
    raw_contradictions = result.get("contradictions") or []
    raw_risks = result.get("risks") or []
    # Coerce risk dicts (Phase 1 verifier emits {agent, description} dicts)
    # into flat strings for the deep-research consumer.
    def _flatten(items):
        out: list[str] = []
        for it in items or []:
            if isinstance(it, str):
                if it.strip():
                    out.append(it.strip())
            elif isinstance(it, dict):
                desc = it.get("description") or it.get("claim") or ""
                if desc:
                    agent = it.get("agent", "")
                    out.append(f"[{agent}] {desc}" if agent else desc)
        return out

    return ResearchVerificationResult(
        decision=decision,
        unsupported_claims=_flatten(result.get("unsupported_claims")),
        contradictions=_flatten(raw_contradictions),
        risks=_flatten(raw_risks),
        claims_needing_more_evidence=_flatten(result.get("revision_instructions")),
        report_revision_notes=_flatten(result.get("corrections")),
        # Defect 6: derive confidence DETERMINISTICALLY from the verifier's
        # decision route.  Never fabricate a 0.5 default.  If the verifier
        # actually emitted a numeric `overall_confidence`, honour it and
        # clamp into [0.0, 1.0].
        overall_confidence=_derive_overall_confidence(decision, result),
    )


# Defect 6: deterministic confidence derivation.  Documented mapping —
# each route corresponds to one fixed confidence value so the field cannot
# drift away from the verifier's actual verdict.
_ROUTE_TO_CONFIDENCE: dict[Verdict, float] = {
    Verdict.approve:                  0.85,
    Verdict.revise:                   0.55,
    Verdict.retrieve_more_evidence:   0.35,
    Verdict.human_review:             0.20,
    Verdict.reject:                   0.10,
}


def _derive_overall_confidence(decision: Verdict, result: dict) -> float:
    """Return the confidence the verifier actually justifies.

    Priority:
      1. If the verifier emitted a numeric ``overall_confidence`` field,
         honour it (clamped into [0, 1]).
      2. Otherwise, map the decision route to its documented confidence
         floor (see ``_ROUTE_TO_CONFIDENCE``).

    Returns -1.0 as a sentinel if neither source yields a usable number
    (the verifier output was non-dict or somehow malformed).
    """
    if isinstance(result, dict):
        raw = result.get("overall_confidence")
        if isinstance(raw, (int, float)):
            value = float(raw)
            if 0.0 <= value <= 1.0:
                return value
            # Out-of-range value can't be trusted — fall through to mapping.
    mapped = _ROUTE_TO_CONFIDENCE.get(decision)
    if mapped is not None:
        return mapped
    return -1.0
