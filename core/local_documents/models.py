"""
Pydantic models for the Phase 4 local-document ingestion subsystem.

All models are intentionally simple and provenance-rich.  Every chunk
carries enough metadata for the Scientific Verifier to trace a claim back
to the exact file, page, and content fingerprint that supplied it.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Source-type taxonomy
# ---------------------------------------------------------------------------

SourceType = Literal[
    "local_literature_folder",
    "local_patent_folder",
]

ExtractionQuality = Literal["good", "partial", "poor", "none"]
PreferenceState = Literal["enabled", "disabled", "ask_later", "unset"]


# ---------------------------------------------------------------------------
# Session preference (defect A — session-scoped, not global)
# ---------------------------------------------------------------------------

class FolderPreference(BaseModel):
    """One agent's literature/patent-folder preference within a session.

    Defect 21: ``validation_error`` is set (and ``state`` stays at
    ``"ask_later"``) when the user supplied ``use_local_folder=True`` with
    an empty / unusable folder_path.  That tells ``needs_prompt`` to
    re-prompt instead of silently demoting an explicit "yes" to "no".
    """
    state: PreferenceState = "unset"
    folder_path: str = ""
    session_id: str = ""
    agent: str = ""              # "research_scout" | "patent_intelligence"
    validation_error: str = ""   # non-empty → response was rejected
    recorded_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class NeedsUserInputRequest(BaseModel):
    """Structured prompt returned to the controller when an agent needs a
    response from the user.  Agents NEVER call ``input()`` directly — they
    return this object and let the controller surface it to the UI / CLI.
    """
    needs_user_input: Literal[True] = True
    user_prompt_type: str = "optional_local_folder"
    target_agent: str = ""
    session_id: str = ""
    message: str = ""
    accepted_response_schema: dict = Field(
        default_factory=lambda: {
            "use_local_folder": "bool",
            "folder_path": "str | null",
            "ask_later": "bool",
        }
    )


# ---------------------------------------------------------------------------
# Discovery + extraction (Sections B, C)
# ---------------------------------------------------------------------------

class DiscoveredFile(BaseModel):
    path: str
    name: str
    ext: str
    size_bytes: int
    is_supported: bool
    skip_reason: str = ""


class DiscoverySummary(BaseModel):
    folder_path: str = ""
    files_discovered: int = 0
    files_supported: int = 0
    files_skipped: int = 0
    unsupported_formats: list[str] = Field(default_factory=list)
    extraction_failures: int = 0        # filled in by pipeline after extraction
    validation_error: str = ""          # non-empty → folder rejected
    discovered_files: list[DiscoveredFile] = Field(default_factory=list)

    # Defect 13: explicit truncation reporting.  ``scan_truncated`` is True
    # when the scan stopped at ``max_files_applied`` without enumerating
    # every remaining file in the folder.  ``omitted_count`` reports the
    # number of files seen during the truncation walk but skipped from the
    # main results because of the cap (best-effort estimate — the scan
    # still stops promptly to keep memory bounded).
    scan_truncated: bool = False
    max_files_applied: int = 0
    omitted_count: int = 0


class ExtractionWarning(BaseModel):
    kind: str = ""          # e.g. "library_missing", "encrypted", "parse_error"
    detail: str = ""
    location: str = ""      # page/paragraph/etc.


class LocalDocumentExtraction(BaseModel):
    """Raw extraction output for ONE file before chunking."""
    document_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    path: str
    file_name: str
    ext: str
    # The raw text (joined). Page-level structure lives in `pages` when known.
    text: str = ""
    pages: list[dict] = Field(default_factory=list)   # [{page_no, text}, ...]
    paragraphs: list[dict] = Field(default_factory=list)   # for DOCX
    extraction_method: str = ""        # "pypdf" | "fitz" | "python-docx" | ...
    extraction_quality: ExtractionQuality = "none"
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    failed: bool = False               # true when extraction did not yield text
    failure_reason: str = ""
    extracted_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Chunking + indexing (Section D)
# ---------------------------------------------------------------------------

class LocalDocumentChunk(BaseModel):
    """One indexed/searchable chunk.

    Provenance fields are mandatory so the verifier can trace a claim back
    to the chunk: (source_type, document_id, file_name, location_hint).
    """
    evidence_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:14])
    source_type: SourceType
    document_id: str
    file_name: str
    # `safe_reference` is a string the report / verifier can show without
    # leaking the full local path.
    safe_reference: str
    location_hint: str = ""          # "page 3" | "paragraph 12" | "table 2 row 1"
    chunk_index: int = 0
    content_sha256: str = ""
    text: str = ""
    extraction_quality: ExtractionQuality = "good"
    ingested_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def fingerprint(self) -> str:
        if self.content_sha256:
            return self.content_sha256
        digest = hashlib.sha256((self.text or "").encode("utf-8")).hexdigest()
        return digest


# ---------------------------------------------------------------------------
# Aggregate ingestion summary (Sections E, F, G)
# ---------------------------------------------------------------------------

class LocalIngestionSummary(BaseModel):
    """Per-agent rollup returned to the agent (and embedded in its output).

    Honest reporting:
      * ``partial_results`` is true whenever ≥1 file failed to extract.
      * ``evidence_quality_hint`` is the worst extraction_quality across
        successful documents (good > partial > poor > none).  Agents must
        NOT use this to inflate confidence (Section E/F: "do not inflate
        confidence merely because local documents exist").
    """
    source_type: SourceType
    folder_path: str = ""
    used: bool = False               # was ingestion actually invoked?
    discovery: DiscoverySummary = Field(default_factory=lambda: DiscoverySummary())
    extractions: list[LocalDocumentExtraction] = Field(default_factory=list)
    chunks_indexed: int = 0
    evidence_quality_hint: ExtractionQuality = "none"
    partial_results: bool = False
    failure_reason: str = ""
    notes: list[str] = Field(default_factory=list)


class LocalEvidenceRef(BaseModel):
    """A retrieval result handed to an agent or the verifier.

    Mirrors a LocalDocumentChunk but trimmed to the fields downstream
    consumers actually need.
    """
    evidence_id: str
    source_type: SourceType
    document_id: str
    file_name: str
    safe_reference: str
    location_hint: str = ""
    chunk_index: int = 0
    extraction_quality: ExtractionQuality = "good"
    score: float = 0.0
    excerpt: str = ""
