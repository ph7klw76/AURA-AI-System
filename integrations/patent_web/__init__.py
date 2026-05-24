"""
AURA patent_web integration — Stage 1.

Public API
----------
    run_patent_web_search(topic) -> PatentWebSearchRun
    plan_patent_queries(topic)   -> list[PatentSearchQuery]

Status (Stage 1):
- Web-scraped, NOT API-verified.
- Restricted to publicly indexed patent landing pages on Google Patents,
  WIPO Patentscope, and USPTO.
- Best-effort extraction. Family-level resolution is NOT performed.
- NOT legal advice. NOT a freedom-to-operate analysis. NOT exhaustive.
"""

from .evidence_builder import build_evidence_record, build_evidence_records
from .pipeline import run_patent_web_search
from .query_planner import plan_patent_queries
from .schemas import (
    PatentEvidenceRecord,
    PatentPageExtraction,
    PatentSearchHit,
    PatentSearchQuery,
    PatentSource,
    PatentSourceError,
    PatentWebSearchRun,
)

__all__ = [
    "run_patent_web_search",
    "plan_patent_queries",
    "build_evidence_record",
    "build_evidence_records",
    "PatentSearchQuery",
    "PatentSearchHit",
    "PatentPageExtraction",
    "PatentEvidenceRecord",
    "PatentSourceError",
    "PatentWebSearchRun",
    "PatentSource",
]
