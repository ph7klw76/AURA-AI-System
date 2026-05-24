"""
Deduplicate PatentEvidenceRecord lists.

Priority order (per the Stage 1 spec)
-------------------------------------
1. Exact normalised publication number      ("PUB::<key>")
2. Exact normalised application number      ("APP::<key>")
3. Normalised URL                            ("URL::<key>")
4. Approximate title + assignee/applicant   (fallback)

Within a group the record with the highest extraction quality wins; ties go
to the one with the longer abstract.  Order is preserved relative to the
first occurrence so callers receive a stable list.

We DO NOT claim this performs true patent-family deduplication.  Stage 2
(structured-API integration) is responsible for that.
"""

from __future__ import annotations

from .normalizer import normalise_publication_number, normalise_title
from .schemas import ExtractionQuality, PatentEvidenceRecord

_QUALITY_RANK: dict[ExtractionQuality, int] = {"high": 3, "medium": 2, "low": 1}


def _is_better(candidate: PatentEvidenceRecord, current: PatentEvidenceRecord) -> bool:
    c_rank = _QUALITY_RANK.get(candidate.extraction_quality, 0)
    n_rank = _QUALITY_RANK.get(current.extraction_quality, 0)
    if c_rank != n_rank:
        return c_rank > n_rank
    return len(candidate.abstract or "") > len(current.abstract or "")


def _title_assignee_key(rec: PatentEvidenceRecord) -> str:
    """Fallback key when no number / URL is usable."""
    t = normalise_title(rec.title)
    if not t:
        return ""
    assignee = ""
    if rec.assignee_or_applicant:
        assignee = rec.assignee_or_applicant[0].strip().lower()
    return f"TITLE::{t}::{assignee}"


def dedupe_evidence_records(
    records: list[PatentEvidenceRecord],
) -> tuple[list[PatentEvidenceRecord], int]:
    """Return ``(deduplicated, dropped_count)``.

    Walks records twice:
        1. PUB / APP / URL keys (already set by evidence_builder).
        2. Title+assignee fallback for the leftovers.
    """
    keyed: dict[str, PatentEvidenceRecord] = {}
    order: list[str] = []
    dropped = 0
    leftovers: list[PatentEvidenceRecord] = []

    for r in records:
        key = r.normalised_key
        if not key:
            leftovers.append(r)
            continue
        if key not in keyed:
            keyed[key] = r
            order.append(key)
        else:
            if _is_better(r, keyed[key]):
                keyed[key] = r
            dropped += 1

    # Title+assignee fallback for leftovers.
    fallback_keyed: dict[str, PatentEvidenceRecord] = {}
    fallback_order: list[str] = []
    truly_unique: list[PatentEvidenceRecord] = []
    for r in leftovers:
        tk = _title_assignee_key(r)
        if not tk:
            truly_unique.append(r)
            continue
        if tk not in fallback_keyed:
            fallback_keyed[tk] = r
            fallback_order.append(tk)
        else:
            if _is_better(r, fallback_keyed[tk]):
                fallback_keyed[tk] = r
            dropped += 1

    deduped = (
        [keyed[k] for k in order]
        + [fallback_keyed[k] for k in fallback_order]
        + truly_unique
    )
    return deduped, dropped
