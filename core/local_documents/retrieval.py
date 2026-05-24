"""
High-level retrieval helpers for agents.

Wraps the in-memory indexer with a stable signature so agents don't have
to import index internals.
"""
from __future__ import annotations

from .indexing import get_chunks, search_chunks
from .models import LocalEvidenceRef, SourceType


def retrieve_local_evidence(
    session_id: str,
    source_type: SourceType,
    query: str,
    *,
    top_k: int = 6,
) -> list[LocalEvidenceRef]:
    return search_chunks(session_id, source_type, query, top_k=top_k)


def retrieve_literature_evidence(
    session_id: str, query: str, *, top_k: int = 6,
) -> list[LocalEvidenceRef]:
    return retrieve_local_evidence(
        session_id, "local_literature_folder", query, top_k=top_k,
    )


def retrieve_patent_evidence(
    session_id: str, query: str, *, top_k: int = 6,
) -> list[LocalEvidenceRef]:
    return retrieve_local_evidence(
        session_id, "local_patent_folder", query, top_k=top_k,
    )


def retrieve_evidence_per_document(
    session_id: str,
    source_type: SourceType,
    query: str,
    *,
    per_document: int = 3,
    max_total: int = 60,
) -> list[LocalEvidenceRef]:
    """Retrieve top-K chunks PER document so coverage spans every file.

    The standard ``search_chunks`` ranks all chunks globally by token
    overlap with the query, which means a 14-document folder where 4
    documents happen to share a common phrase can hog all top-K slots,
    leaving the other 10 documents unrepresented in the analysis.

    This helper instead:
      1. Runs the same global keyword overlap to score chunks against
         the query (so we still prefer relevant content per document).
      2. Groups by ``document_id`` and keeps the top ``per_document``
         chunks from each.
      3. For documents that have NO query-overlapping chunks, falls
         back to the first ``per_document`` chunks by insertion order
         so EVERY indexed document gets at least some representation.
      4. Caps the total at ``max_total`` (preserving the per-document
         distribution as evenly as possible).

    Returns ordered ``LocalEvidenceRef`` objects ready for the prompt.
    """
    all_chunks = get_chunks(session_id, source_type)
    if not all_chunks:
        return []

    # 1. Score all chunks with the global ranker.  We ask for a generous
    #    limit so we get scores for every chunk that has ANY overlap.
    scored_refs = search_chunks(
        session_id, source_type, query, top_k=len(all_chunks),
    )
    by_doc_scored: dict[str, list[LocalEvidenceRef]] = {}
    for r in scored_refs:
        by_doc_scored.setdefault(r.document_id, []).append(r)

    # 2. Gather all documents in their indexed order (deterministic).
    seen: set[str] = set()
    doc_order: list[str] = []
    chunks_by_doc: dict[str, list] = {}
    for c in all_chunks:
        if c.document_id not in seen:
            seen.add(c.document_id)
            doc_order.append(c.document_id)
        chunks_by_doc.setdefault(c.document_id, []).append(c)

    # 3. For each document, take top-N scored refs.  If the document
    #    has zero query-overlap, fall back to its first N chunks so
    #    every document is represented.
    out: list[LocalEvidenceRef] = []
    for doc_id in doc_order:
        scored = by_doc_scored.get(doc_id, [])[:per_document]
        if scored:
            out.extend(scored)
            continue
        # Fallback: synthesize refs from raw chunks (no score).
        for ch in chunks_by_doc.get(doc_id, [])[:per_document]:
            excerpt = (ch.text or "")[:400]
            out.append(LocalEvidenceRef(
                evidence_id=ch.evidence_id,
                source_type=ch.source_type,
                document_id=ch.document_id,
                file_name=ch.file_name,
                safe_reference=ch.safe_reference,
                location_hint=ch.location_hint,
                chunk_index=ch.chunk_index,
                extraction_quality=ch.extraction_quality,
                score=0.0,
                excerpt=excerpt,
            ))

    # 4. Cap.
    if len(out) > max_total:
        out = out[:max_total]
    return out


def retrieve_patent_evidence_per_document(
    session_id: str, query: str,
    *, per_document: int = 3, max_total: int = 60,
) -> list[LocalEvidenceRef]:
    return retrieve_evidence_per_document(
        session_id, "local_patent_folder", query,
        per_document=per_document, max_total=max_total,
    )


def retrieve_literature_evidence_per_document(
    session_id: str, query: str,
    *, per_document: int = 3, max_total: int = 60,
) -> list[LocalEvidenceRef]:
    return retrieve_evidence_per_document(
        session_id, "local_literature_folder", query,
        per_document=per_document, max_total=max_total,
    )
