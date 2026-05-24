"""
Convert PatentPageExtraction objects into PatentEvidenceRecord objects.

This is the canonicalisation + provenance-tagging stage.  The output records
carry the mandatory Stage-1 honesty flags:

    web_extracted    = True       # always
    not_api_verified = True       # always

…and a per-record list of ``caution_flags`` such as ``"fetch_failed"``,
``"low_extraction_quality"``, or ``"missing_metadata"`` so the verifier and
the LLM analyser can weigh records appropriately.
"""

from __future__ import annotations

from .normalizer import normalise_publication_number
from .schemas import (
    PatentEvidenceRecord, PatentPageExtraction, PatentSearchHit, PatentSource,
)


def _infer_jurisdiction(pub_number: str, source: PatentSource) -> str:
    if pub_number and len(pub_number) >= 2 and pub_number[:2].isalpha():
        return pub_number[:2].upper()
    if source == PatentSource.uspto:
        return "US"
    if source == PatentSource.wipo:
        return "WO"
    return ""


def _build_caution_flags(extraction: PatentPageExtraction) -> list[str]:
    flags: list[str] = []
    if extraction.fetch_status != "ok":
        flags.append(f"fetch_failed:{extraction.fetch_status}")
    if extraction.extraction_quality == "low":
        flags.append("low_extraction_quality")
    if not extraction.publication_number:
        flags.append("missing_publication_number")
    if not extraction.abstract:
        flags.append("missing_abstract")
    if not extraction.assignee_or_applicant:
        flags.append("missing_assignee")
    return flags


def _normalised_key_for(extraction: PatentPageExtraction) -> str:
    """Pick the highest-quality key available for dedup."""
    pn = normalise_publication_number(extraction.publication_number)
    if pn:
        return f"PUB::{pn}"
    an = normalise_publication_number(extraction.application_number)
    if an:
        return f"APP::{an}"
    from .normalizer import normalise_url
    nu = normalise_url(extraction.url)
    if nu:
        return f"URL::{nu}"
    return ""


def build_evidence_record(
    extraction: PatentPageExtraction,
    hit: PatentSearchHit,
) -> PatentEvidenceRecord:
    """Build one PatentEvidenceRecord from an extraction + originating hit."""
    pub_number = extraction.publication_number.strip()
    return PatentEvidenceRecord(
        title=extraction.title.strip(),
        publication_number=pub_number,
        application_number=extraction.application_number.strip(),
        normalised_key=_normalised_key_for(extraction),
        assignee_or_applicant=list(extraction.assignee_or_applicant),
        inventors=list(extraction.inventors),
        jurisdiction=_infer_jurisdiction(pub_number, extraction.source_domain),
        filing_date=extraction.filing_date,
        publication_date=extraction.publication_date,
        priority_date=extraction.priority_date,
        abstract=extraction.abstract,
        claims_excerpt=extraction.claims_excerpt,
        description_excerpt=extraction.description_excerpt,
        url=extraction.url,
        source_domain=extraction.source_domain,
        originating_query=hit.query,
        provider=hit.provider,
        web_extracted=True,         # Stage 1 always
        not_api_verified=True,      # Stage 1 always
        extraction_quality=extraction.extraction_quality,
        extraction_notes=list(extraction.extraction_notes),
        caution_flags=_build_caution_flags(extraction),
    )


def build_evidence_records(
    extractions: list[PatentPageExtraction],
    hits_by_url: dict[str, PatentSearchHit],
) -> list[PatentEvidenceRecord]:
    """Vector form. Pairs each extraction with its originating hit (by url)."""
    out: list[PatentEvidenceRecord] = []
    fallback_hit = PatentSearchHit()
    for ex in extractions:
        hit = hits_by_url.get(ex.url, fallback_hit)
        out.append(build_evidence_record(ex, hit))
    return out
