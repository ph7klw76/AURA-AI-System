"""
End-to-end local-folder ingestion pipeline.

Single entry point: ``ingest_folder(session_id, agent, folder_path)``.
Returns a fully-populated :class:`LocalIngestionSummary` describing
discovery, per-file extraction outcomes, and the number of chunks
indexed for retrieval.

Behaviour
---------
* NEVER raises — every failure mode produces structured fields on the
  returned summary.
* Folder validation errors are surfaced via
  ``summary.discovery.validation_error`` so the caller can present a
  user-friendly message.
* Per-file extraction failures are listed individually in
  ``summary.extractions[*].failed`` / ``failure_reason`` (Section H —
  "No silent skipping").
* The indexer is updated only when ``ingest_into_index=True``.
"""
from __future__ import annotations

from pathlib import Path

from . import indexing
from .chunking import chunk_extraction
from .convert_legacy_docs import extract_legacy_doc
from .discovery import LEGACY_FORMATS, scan_folder
from .extract_docx import extract_docx
from .extract_pdf import extract_pdf
from .extract_text import extract_text_file
from .models import (
    DiscoveredFile, ExtractionQuality, LocalDocumentExtraction,
    LocalIngestionSummary, SourceType,
)


_QUALITY_RANK: dict[ExtractionQuality, int] = {
    "good": 3, "partial": 2, "poor": 1, "none": 0,
}


def _agent_to_source_type(agent: str) -> SourceType | None:
    """Return the SourceType for a registered agent, or None if unknown.

    Defect 15: previously this raised on an unknown agent, contradicting
    ``ingest_folder``'s ``"NEVER raises"`` contract.  The caller now
    handles ``None`` by returning a structured failure summary.
    """
    if agent == "research_scout":
        return "local_literature_folder"
    if agent == "patent_intelligence":
        return "local_patent_folder"
    return None


def _extract_one(file: DiscoveredFile) -> LocalDocumentExtraction:
    ext = file.ext
    path = Path(file.path)
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".docx":
        return extract_docx(path)
    if ext in (".txt", ".md"):
        return extract_text_file(path)
    if ext in LEGACY_FORMATS:
        return extract_legacy_doc(path)
    # Unsupported extension at this stage — caller should have filtered.
    return LocalDocumentExtraction(
        path=str(path), file_name=path.name, ext=ext,
        extraction_method="unsupported",
        failed=True,
        failure_reason=f"unsupported format {ext}",
        extraction_quality="none",
    )


def _worst_quality(qualities: list[ExtractionQuality]) -> ExtractionQuality:
    if not qualities:
        return "none"
    return min(qualities, key=lambda q: _QUALITY_RANK[q])


def ingest_folder(
    session_id: str,
    agent: str,
    folder_path: str,
    *,
    ingest_into_index: bool = True,
    max_files: int | None = None,
) -> LocalIngestionSummary:
    """Discover, extract, chunk, and (optionally) index a folder.

    The returned ``LocalIngestionSummary`` is the single object the agent
    embeds in its output.  Callers MUST NOT raise on validation errors —
    inspect ``summary.discovery.validation_error`` and surface the
    structured message instead.
    """
    source_type = _agent_to_source_type(agent)
    if source_type is None:
        # Defect 15: structured failure, never a raise.
        return LocalIngestionSummary(
            source_type="local_literature_folder",   # default placeholder
            folder_path=folder_path,
            used=False,
            partial_results=True,
            failure_reason=(
                f"Unknown agent for local-folder ingestion: {agent!r}. "
                f"Supported agents: research_scout, patent_intelligence."
            ),
        )

    summary = LocalIngestionSummary(
        source_type=source_type,
        folder_path=folder_path,
        used=False,
    )

    if not session_id:
        summary.failure_reason = "session_id is required"
        summary.partial_results = True
        return summary

    summary.discovery = scan_folder(folder_path, max_files=max_files)
    if summary.discovery.validation_error:
        summary.failure_reason = summary.discovery.validation_error
        summary.partial_results = True
        return summary

    summary.used = True
    successful_qualities: list[ExtractionQuality] = []

    chunks_total = 0
    extraction_failures = 0

    for discovered in summary.discovery.discovered_files:
        if not discovered.is_supported:
            continue
        extraction = _extract_one(discovered)
        summary.extractions.append(extraction)
        if extraction.failed or extraction.extraction_quality == "none":
            extraction_failures += 1
            continue

        successful_qualities.append(extraction.extraction_quality)

        chunks = chunk_extraction(extraction, source_type=source_type)
        if not chunks:
            extraction_failures += 1
            summary.notes.append(
                f"{discovered.name}: extraction produced no chunks"
            )
            continue
        if ingest_into_index:
            added = indexing.add_chunks(session_id, source_type, chunks)
            chunks_total += added
        else:
            chunks_total += len(chunks)

    summary.discovery.extraction_failures = extraction_failures
    summary.chunks_indexed = chunks_total
    summary.evidence_quality_hint = _worst_quality(successful_qualities)

    # Partial-results when *anything* failed.
    if extraction_failures > 0 or summary.discovery.files_skipped > 0:
        summary.partial_results = True
    if chunks_total == 0 and summary.discovery.files_supported > 0:
        summary.partial_results = True
        summary.failure_reason = summary.failure_reason or (
            "Local ingestion produced zero chunks — see per-file extraction warnings."
        )

    # Defect 13: a truncated scan is by definition partial — surface it.
    if summary.discovery.scan_truncated:
        summary.partial_results = True
        summary.notes.append(
            f"Folder scan truncated at max_files={summary.discovery.max_files_applied} "
            f"(approximately {summary.discovery.omitted_count} additional files "
            "were not analysed)."
        )

    if summary.discovery.unsupported_formats:
        summary.notes.append(
            "Unsupported formats in folder (skipped): "
            + ", ".join(summary.discovery.unsupported_formats)
        )

    return summary
