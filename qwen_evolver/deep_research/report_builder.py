"""
Report Builder — synthesises the final DeepResearchReport.

Phase 3 changes:
    * Defect 7: claims are SEGREGATED by support_status before being shown
      to the LLM.  Only supported / partial claims are fed as primary
      synthesis inputs; unsupported / contradicted claims are passed
      separately and labelled as "evidence_to_exclude" so the synthesiser
      cannot mistake them for ordinary evidence.
    * Defect 10: ``build_report`` now accepts the
      ``ResearchVerificationResult`` and reflects rejected / unsupported /
      revise verdicts in the final report.
    * Defect 11: ``build_report`` returns a 2-tuple ``(report, status)`` so
      the orchestrator can tell that the LLM call failed.  ``status`` is
      either ``"ok"`` or ``"failed:<reason>"``.
"""

from __future__ import annotations

from core.llm import ask_json
from core import normalization as _norm

from .citation_manager import build_citation
from .schemas import (
    DeepResearchReport, EvidencePack, ResearchVerificationResult, Verdict,
)


REPORT_PROMPT = """\
You are a research synthesis engine.

You receive a structured evidence pack split into two buckets:
  * SUPPORTING_EVIDENCE      — supported and partially-supported claims.
                               Use these as the basis of the report.
  * EVIDENCE_TO_EXCLUDE      — unsupported and contradicted claims.
                               You MUST NOT use these as report evidence.
                               You MAY mention them ONLY in the
                               `evidence_caveats` and
                               `unresolved_uncertainties` sections, and only
                               as cautions or open questions.

You also receive the verifier's verdict (`verifier_decision`,
`verifier_unsupported_claims`, `verifier_contradictions`,
`verifier_revision_notes`).  Reflect rejected / revise verdicts in
`evidence_caveats` and `unresolved_uncertainties`.  If the verdict is
`reject`, write the report in cautious / preliminary tone and explicitly
state that the verifier rejected the synthesis.

Return strict JSON:
{
  "title": "...",
  "executive_summary": "...",
  "research_question": "...",
  "methodology": "...",
  "findings": ["..."],
  "opportunity_analysis": "...",
  "strategic_recommendations": ["..."],
  "evidence_caveats": ["..."],
  "unresolved_uncertainties": ["..."]
}

Embed inline citations using source IDs in the form [SRC_xxx].
Do not invent claims beyond the supplied SUPPORTING_EVIDENCE.
"""


# Support-status buckets used by _split_claims_by_support.
_SUPPORTED_STATES: frozenset[str] = frozenset({"supported", "partial"})
_EXCLUDED_STATES: frozenset[str] = frozenset({"unsupported", "contradicted"})


def _split_claims_by_support(pack: EvidencePack) -> tuple[list[str], list[str]]:
    """Return ``(supported, excluded)`` claim-summary strings.

    Defect 7: ``unsupported`` and ``contradicted`` claims are routed to
    the EXCLUDED bucket and presented to the synthesiser only as caveats.
    """
    supported: list[str] = []
    excluded: list[str] = []
    for c in pack.evidence_claims:
        status_val = getattr(c.support_status, "value", str(c.support_status))
        line = (
            f"[SRC_{c.source_id}] {c.claim_text[:200]} "
            f"(support:{status_val}, conf:{c.confidence_score})"
        )
        if status_val in _SUPPORTED_STATES:
            supported.append(line)
        elif status_val in _EXCLUDED_STATES:
            excluded.append(line)
        # "inferred" / other states are dropped from both buckets — they
        # cannot be used as evidence, but they are not labelled as wrong.
    return supported[:30], excluded[:30]


def _verifier_context_block(verification: ResearchVerificationResult | None) -> str:
    """Render the verifier's verdict for the synthesiser prompt.

    Defect 10: the report stage must SEE the verifier's verdict so the
    final report reflects rejected / revise / unsupported state.
    """
    if verification is None:
        return "verifier_decision: (no verification result available)"
    return (
        f"verifier_decision: {verification.decision.value}\n"
        f"verifier_unsupported_claims: "
        f"{verification.unsupported_claims[:8]}\n"
        f"verifier_contradictions: "
        f"{verification.contradictions[:8]}\n"
        f"verifier_revision_notes: "
        f"{verification.report_revision_notes[:8]}\n"
        f"verifier_overall_confidence: {verification.overall_confidence:.2f}"
    )


def build_report(
    pack: EvidencePack,
    verification: ResearchVerificationResult | None = None,
) -> tuple[DeepResearchReport, str]:
    """Synthesise the final DeepResearchReport.

    Returns ``(report, status)`` where status is ``"ok"`` on success or
    ``"failed:<reason>"`` if the LLM call or JSON parsing failed
    (defect 11).  Callers MUST inspect the status — they can no longer
    silently assume the report is complete.
    """
    supported, excluded = _split_claims_by_support(pack)
    verifier_block = _verifier_context_block(verification)
    rejected = (
        verification is not None
        and verification.decision == Verdict.reject
    )

    supporting_block = "\n".join(supported) or "(none)"
    excluded_block = "\n".join(excluded) or "(none)"

    user_prompt = (
        f"Evidence pack mission_id: {pack.mission_id}\n"
        f"Research question: {pack.research_question}\n\n"
        f"=== SUPPORTING_EVIDENCE ===\n{supporting_block}\n\n"
        f"=== EVIDENCE_TO_EXCLUDE ===\n{excluded_block}\n\n"
        f"=== VERIFIER VERDICT ===\n{verifier_block}\n"
    )

    citations = [build_citation(s) for s in pack.sources if s.status == "fetched"]

    try:
        raw = ask_json(REPORT_PROMPT, user_prompt, temperature=0.2)
    except Exception as exc:
        # Defect 11: surface the failure so the orchestrator can mark the
        # pipeline as partial_results / failed_stage="report_generation".
        return (
            DeepResearchReport(
                title="Report generation failed",
                executive_summary=(
                    "The deep-research report could not be synthesised.  "
                    "The evidence pack is preserved for manual review."
                ),
                research_question=pack.research_question,
                methodology="(unavailable — report generation failed)",
                findings=[],
                evidence_caveats=[f"Report generation failed: {exc}"],
                unresolved_uncertainties=[
                    "Synthesis stage did not complete — see logs."
                ],
                citations=citations,
            ),
            f"failed:{type(exc).__name__}:{str(exc)[:120]}",
        )

    # Pull excluded-claim summaries into evidence_caveats so the report still
    # surfaces them as cautions even if the LLM forgot to include them.
    # Defect 20: never let ``list("ABC")`` shred a string into characters.
    raw_caveats = _norm.ensure_str_list(raw.get("evidence_caveats"))
    for ex in excluded:
        if not any(ex[:40] in c for c in raw_caveats):
            raw_caveats.append(f"Excluded (unsupported/contradicted): {ex}")
    if rejected:
        raw_caveats.insert(0, (
            "Verifier rejected this synthesis — treat the report as "
            "preliminary and seek independent review before acting on it."
        ))

    report = DeepResearchReport(
        title=_norm.ensure_str(raw.get("title")),
        executive_summary=_norm.ensure_str(raw.get("executive_summary")),
        research_question=_norm.ensure_str(
            raw.get("research_question"), default=pack.research_question,
        ),
        methodology=_norm.ensure_str(raw.get("methodology")),
        findings=_norm.ensure_str_list(raw.get("findings")),
        opportunity_analysis=_norm.ensure_str(raw.get("opportunity_analysis")),
        strategic_recommendations=_norm.ensure_str_list(
            raw.get("strategic_recommendations"),
        ),
        evidence_caveats=raw_caveats,
        unresolved_uncertainties=_norm.ensure_str_list(
            raw.get("unresolved_uncertainties"),
        ),
        citations=citations,
    )
    return report, "ok"
