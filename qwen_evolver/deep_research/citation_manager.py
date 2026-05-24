"""
Citation manager — generates citation keys and appendix.
"""

from __future__ import annotations

from .schemas import SourceRecord, CitationEntry


def build_citation(record: SourceRecord) -> CitationEntry:
    return CitationEntry(
        source_id=record.source_id,
        title=record.title,
        url=record.url,
        retrieved_at=record.retrieved_at,
        source_type=record.source_type,
    )

def format_inline(citation: CitationEntry) -> str:
    return f"[SRC_{citation.source_id}]"
