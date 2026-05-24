"""
Evidence Extractor — runs LLM on source text to extract EvidenceClaim list.
"""

from __future__ import annotations

from core.llm import ask_json
from .schemas import SourceRecord, EvidenceClaim, EvidenceType, SupportStatus

EXTRACTION_PROMPT = """\
You are an evidence extraction assistant.
Read the provided source content and extract factual claims that are **directly supported** by the content.

Return strict JSON with a list of claims:
{
  "claims": [
    {
      "claim_text": "...the specific factual claim...",
      "source_location": "relevant quote or span",
      "evidence_type": "quote | paraphrase | table | figure | metadata | inferred",
      "support_status": "supported | partial | unsupported | contradicted",
      "confidence_score": 0.0-1.0,
      "notes": "any caveats"
    }
  ]
}

Do NOT invent information. If a claim is not supported, set support_status to 'unsupported' and confidence 0.0."""

def extract_claims(source: SourceRecord) -> list[EvidenceClaim]:
    if not source.inline_text or source.status != "fetched":
        return []
    try:
        raw = ask_json(
            EXTRACTION_PROMPT,
            f"Source title: {source.title}\n\nContent:\n{source.inline_text}",
            temperature=0.0,
        )
        claims_data = raw.get("claims", [])[:12]
        result = []
        for c in claims_data:
            result.append(EvidenceClaim(
                claim_text=c.get("claim_text", ""),
                source_id=source.source_id,
                source_location=c.get("source_location", ""),
                evidence_type=EvidenceType(c.get("evidence_type", "paraphrase")),
                support_status=SupportStatus(c.get("support_status", "unsupported")),
                confidence_score=float(c.get("confidence_score", 0.0)),
                notes=c.get("notes", ""),
            ))
        return result
    except Exception:
        return []
