"""
Gap Analyzer — LLM identifies missing information and contradictions.
"""

from __future__ import annotations

from core.llm import ask_json
from .schemas import EvidencePack, GapAnalysis, GapRecommendation

GAP_PROMPT = """\
You are a research gap analyst.
Review the provided evidence pack and identify:

- missing information
- weakly supported claims
- contradictory evidence
- source quality issues

Then suggest follow-up queries.

Return strict JSON:
{
  "missing_information": [],
  "weakly_supported_claims": [],
  "contradictory_evidence": [],
  "source_quality_issues": [],
  "followup_queries": [],
  "recommendation": "continue_research | proceed_to_verification | human_review"
}

Be concise. Only suggest follow-up queries that are actionable."""

def analyse_gaps(pack: EvidencePack) -> GapAnalysis:
    claims_text = "\n".join(
        f"- {c.claim_text[:120]} (support:{c.support_status.value}, conf:{c.confidence_score})"
        for c in pack.evidence_claims[:20]
    )
    try:
        raw = ask_json(
            GAP_PROMPT,
            f"Evidence pack mission_id: {pack.mission_id}\nResearch question: {pack.research_question}\n\n"
            f"Evidence claims:\n{claims_text}\n\n",
            temperature=0.1,
        )
        return GapAnalysis(
            missing_information=raw.get("missing_information", []),
            weakly_supported_claims=raw.get("weakly_supported_claims", []),
            contradictory_evidence=raw.get("contradictory_evidence", []),
            source_quality_issues=raw.get("source_quality_issues", []),
            followup_queries=raw.get("followup_queries", []),
            recommendation=GapRecommendation(raw.get("recommendation", "continue_research")),
        )
    except Exception:
        return GapAnalysis(recommendation=GapRecommendation.human_review)
