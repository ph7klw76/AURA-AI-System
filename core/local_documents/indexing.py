"""
In-memory chunk index, keyed by ``(session_id, source_type)``.

We deliberately ship a tiny keyword index — no embeddings dependency.
Token overlap scoring is plenty for "give me the local chunks most
relevant to this query" and keeps the test suite hermetic.

A separate index is kept per ``source_type`` so literature chunks never
leak into a patent retrieval and vice versa.
"""
from __future__ import annotations

import re
import threading
from collections import defaultdict
from typing import Iterable

from .models import LocalDocumentChunk, LocalEvidenceRef, SourceType


# (session_id, source_type) -> list[LocalDocumentChunk]
_INDEX: dict[tuple[str, SourceType], list[LocalDocumentChunk]] = defaultdict(list)
_LOCK = threading.RLock()


_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z\-]{2,}")
_STOPWORDS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "from", "into", "that", "this", "those",
    "these", "what", "where", "when", "have", "has", "was", "were", "but",
    "are", "you", "your", "their", "there", "between", "any", "all",
    "some", "more", "less", "than", "such", "also", "thus", "however",
    "would", "could", "should",
})


def _tokens(text: str) -> set[str]:
    return {
        t.lower() for t in _TOKEN_RE.findall(text or "")
        if t.lower() not in _STOPWORDS
    }


def add_chunks(
    session_id: str,
    source_type: SourceType,
    chunks: Iterable[LocalDocumentChunk],
) -> int:
    """Append *chunks* to the per-session index.  Returns count added.

    Defect 14: dedup is now keyed on ``(document_id, content_sha256)`` so
    two DIFFERENT documents that happen to share an identical paragraph
    (e.g. a boilerplate disclaimer, a quoted abstract, or genuinely
    corroborating evidence) both keep their provenance.  Only true
    intra-document duplicates (same document_id + same content_sha256)
    are collapsed.
    """
    if not session_id:
        return 0
    with _LOCK:
        added = 0
        bucket = _INDEX[(session_id, source_type)]
        seen_keys: set[tuple[str, str]] = {
            (c.document_id, c.content_sha256)
            for c in bucket if c.content_sha256
        }
        for c in chunks:
            key = (c.document_id, c.content_sha256)
            if c.content_sha256 and key in seen_keys:
                continue
            bucket.append(c)
            if c.content_sha256:
                seen_keys.add(key)
            added += 1
    return added


def clear_session(session_id: str) -> None:
    """Drop every index entry for *session_id*."""
    if not session_id:
        return
    with _LOCK:
        for key in list(_INDEX.keys()):
            if key[0] == session_id:
                _INDEX.pop(key, None)


def get_chunks(
    session_id: str,
    source_type: SourceType,
) -> list[LocalDocumentChunk]:
    with _LOCK:
        return list(_INDEX.get((session_id, source_type), []))


def search_chunks(
    session_id: str,
    source_type: SourceType,
    query: str,
    *,
    top_k: int = 6,
) -> list[LocalEvidenceRef]:
    """Return the *top_k* most-overlap chunks for *query*.

    Score = |query_tokens ∩ chunk_tokens|.  Ties broken by chunk order.
    Returns ``LocalEvidenceRef`` so callers never see the raw text dict.
    """
    chunks = get_chunks(session_id, source_type)
    if not chunks or not query:
        return []
    q_tokens = _tokens(query)
    if not q_tokens:
        return []

    scored: list[tuple[float, int, LocalDocumentChunk]] = []
    for i, ch in enumerate(chunks):
        ch_tokens = _tokens(ch.text)
        score = len(q_tokens & ch_tokens)
        if score == 0:
            continue
        scored.append((float(score), i, ch))
    scored.sort(key=lambda t: (-t[0], t[1]))

    out: list[LocalEvidenceRef] = []
    for score, _idx, ch in scored[:top_k]:
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
            score=score,
            excerpt=excerpt,
        ))
    return out
