"""
Pydantic schemas for the patent_web integration (Stage 1).

Pipeline data flow
------------------
    PatentSearchQuery
        (planner output: query + purpose + target_domains + priority)
            ↓
    PatentSearchHit
        (raw provider hit: title/url/snippet/source_domain/rank/query/provider)
            ↓
    PatentPageExtraction
        (per-page extraction result with fetch_status + extraction_quality
         + extraction_notes — DOES NOT promise correctness, signals quality)
            ↓
    PatentEvidenceRecord
        (normalised, dedup-ready record; carries `web_extracted=True` and
         `not_api_verified=True` provenance flags)
            ↓
    PatentWebSearchRun
        (aggregate wrapper: queries + hits + extractions + dedup records +
         source_errors + provider_used + mock/partial flags + limitations)

All extraction confidence is conservative.  `extraction_quality="high"` is
the highest signal we emit; we never claim API-level verification at Stage 1.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PatentSource(str, Enum):
    """Hosting domain the record was discovered on."""
    google_patents = "patents.google.com"
    wipo = "patentscope.wipo.int"
    uspto = "uspto.gov"
    other = "other"


ExtractionQuality = Literal["high", "medium", "low"]
FetchStatus = Literal[
    "ok",
    "http_403",
    "http_404",
    "http_429",
    "http_other",
    "timeout",
    "non_html",
    "too_large",
    "request_error",
    "skipped",
]


# ---------------------------------------------------------------------------
# Stage 1 — planning
# ---------------------------------------------------------------------------

QueryIntent = Literal[
    "patent_landing_page",
    "broad_prior_art_discovery",
    "inventor_or_assignee_discovery",
    "technology_cluster_search",
    "unspecified",
]


class PatentSearchQuery(BaseModel):
    """A single planned search query.

    `target_domains` lists the patent-hosting domains the query is biased
    toward (encoded as `site:` filters in the query string).  `priority`
    is a small integer; lower = run earlier when budget is tight.
    `intent` lets downstream layers reason about WHY a query was emitted
    (e.g. site-restricted exact-phrase vs cross-domain hint).
    """
    query: str
    purpose: str = ""
    target_domains: list[str] = Field(default_factory=list)
    priority: int = 0
    intent: QueryIntent = "unspecified"


# ---------------------------------------------------------------------------
# Stage 2 — raw search hits
# ---------------------------------------------------------------------------

class PatentSearchHit(BaseModel):
    """Pre-fetch search-result entry.

    `source_domain` is the host we classified the URL to (one of
    ``ALLOWED_HOSTS``).  Hits outside the allow-list are dropped before
    they reach this object.
    """
    title: str = ""
    url: str = ""
    snippet: str = ""
    source_domain: PatentSource = PatentSource.other
    rank: int = 0
    query: str = ""           # originating query string
    provider: str = ""        # e.g. "searxng/google", "mock"
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Stage 3 — per-page extraction result
# ---------------------------------------------------------------------------

class PatentPageExtraction(BaseModel):
    """The result of fetching ONE patent page and trying to parse it.

    Always returned, even on failure — callers inspect `fetch_status` and
    `extraction_quality` to decide whether to trust the record.
    """
    url: str = ""
    source_domain: PatentSource = PatentSource.other

    # Fetch outcome ---------------------------------------------------------
    fetch_status: FetchStatus = "skipped"
    http_status: int = 0

    # Best-effort extracted fields ------------------------------------------
    title: str = ""
    publication_number: str = ""
    application_number: str = ""
    assignee_or_applicant: list[str] = Field(default_factory=list)
    inventors: list[str] = Field(default_factory=list)
    filing_date: str = ""
    publication_date: str = ""
    priority_date: str = ""
    abstract: str = ""
    claims_excerpt: str = ""
    description_excerpt: str = ""

    # Raw text excerpt — for the LLM if structured fields are sparse.
    raw_text_excerpt: str = ""
    raw_text_path: str = ""        # path to cached HTML on disk

    # Quality signals -------------------------------------------------------
    extraction_quality: ExtractionQuality = "low"
    extraction_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 4 — normalised evidence record
# ---------------------------------------------------------------------------

class PatentEvidenceRecord(BaseModel):
    """A normalised, dedup-ready record carrying explicit provenance flags.

    Distinct from PatentPageExtraction:
        * extraction = raw parse output, may be partial / low quality
        * evidence   = normalised + canonicalised + provenance-tagged

    The two flag fields are required by the spec so downstream agents and the
    verifier can never mistake a Stage-1 record for an API-verified record.
    """
    record_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])

    # Normalised metadata ---------------------------------------------------
    title: str = ""
    publication_number: str = ""
    application_number: str = ""
    normalised_key: str = ""           # used by dedup
    assignee_or_applicant: list[str] = Field(default_factory=list)
    inventors: list[str] = Field(default_factory=list)
    jurisdiction: str = ""             # "US", "WO", "EP", ...
    filing_date: str = ""
    publication_date: str = ""
    priority_date: str = ""
    abstract: str = ""
    claims_excerpt: str = ""
    description_excerpt: str = ""

    # Provenance ------------------------------------------------------------
    url: str = ""
    source_domain: PatentSource = PatentSource.other
    originating_query: str = ""
    provider: str = ""

    # REQUIRED stage-1 honesty flags ---------------------------------------
    web_extracted: bool = True         # always true at Stage 1
    not_api_verified: bool = True      # always true at Stage 1

    # Quality / caution -----------------------------------------------------
    extraction_quality: ExtractionQuality = "low"
    extraction_notes: list[str] = Field(default_factory=list)
    caution_flags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 5 — run aggregate
# ---------------------------------------------------------------------------

class PatentSourceError(BaseModel):
    """Structured error surfaced from any pipeline stage."""
    stage: str                 # "search" | "fetch" | "extract" | "normalize"
    url: str = ""
    query: str = ""
    kind: str = ""             # short error class, e.g. "http_403", "timeout"
    detail: str = ""           # human-readable detail


class PatentWebSearchRun(BaseModel):
    """Top-level output of `pipeline.run_patent_web_search()`.

    Mirrors the spec field-for-field so downstream agents and report writers
    consume a stable shape.
    """
    topic: str = ""
    queries: list[PatentSearchQuery] = Field(default_factory=list)
    search_hits: list[PatentSearchHit] = Field(default_factory=list)
    extractions: list[PatentPageExtraction] = Field(default_factory=list)
    deduplicated_records: list[PatentEvidenceRecord] = Field(default_factory=list)
    source_errors: list[PatentSourceError] = Field(default_factory=list)

    # Run-level diagnostics ------------------------------------------------
    provider_used: str = ""
    mock_mode_used: bool = False
    partial_results: bool = False
    limitations: list[str] = Field(default_factory=list)

    # Structured retrieval provenance — populated from the provider-neutral
    # patent-search subsystem so the agent + report can render a clear
    # "where did this come from?" section without re-deriving it.  Keys:
    #   primary_provider   (str) — provider configured first
    #   provider_used      (str) — whichever provider finally produced results
    #   not_api_verified   (bool, always True at Stage 1)
    #   non_exhaustive     (bool, always True at Stage 1)
    #   fallback_used      (bool)
    #   fallback_from      (str | None)
    #   warnings           (list[{code, message}])
    retrieval_provenance: dict = Field(default_factory=dict)

    # Stage-1 disclaimer the agent / report inlines verbatim.
    disclaimer: str = (
        "Preliminary patent-landscape reconnaissance from publicly indexed "
        "patent pages. Web-retrieved and NOT API-verified. Non-exhaustive. "
        "NOT legal advice and NOT a freedom-to-operate analysis. "
        "Formal review by qualified patent counsel is required before any "
        "filing, licensing, or commercial decision."
    )
