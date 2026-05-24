"""
Chunking with overlap + provenance preservation (Section D).

We split extracted text into ~800-character chunks with a 150-character
overlap.  Each chunk inherits page/paragraph hints when available so
provenance survives all the way to the verifier.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

from .models import (
    ExtractionQuality, LocalDocumentChunk, LocalDocumentExtraction, SourceType,
)


DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 150
MIN_CHUNK_CHARS = 80   # drop tiny tail chunks


_WS = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Collapse whitespace, strip nulls, trim."""
    if not text:
        return ""
    text = text.replace("\x00", " ")
    return _WS.sub(" ", text).strip()


def _split_window(text: str, size: int, overlap: int) -> list[tuple[int, int, str]]:
    """Window-walk *text*, returning ``(start, end, chunk_text)`` triples.

    Tries to break on a space within the last 80 chars of the window so
    we don't slice mid-word.
    """
    if not text:
        return []
    out: list[tuple[int, int, str]] = []
    n = len(text)
    step = max(1, size - max(0, overlap))
    start = 0
    while start < n:
        end = min(n, start + size)
        if end < n:
            # Try not to slice mid-word.
            ws = text.rfind(" ", max(start + size - 80, start), end)
            if ws != -1 and ws > start + size // 2:
                end = ws
        snippet = text[start:end].strip()
        if len(snippet) >= MIN_CHUNK_CHARS or end >= n:
            out.append((start, end, snippet))
        start = end if end > start else start + 1
        if step > 0:
            start = end - overlap if end - overlap > 0 else end
        if end >= n:
            break
    return out


def _safe_reference(file_name: str, location_hint: str) -> str:
    if location_hint:
        return f"{file_name}::{location_hint}"
    return file_name


def chunk_extraction(
    extraction: LocalDocumentExtraction,
    *,
    source_type: SourceType,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[LocalDocumentChunk]:
    """Convert ``extraction`` into a list of provenance-rich chunks."""
    if extraction.failed or extraction.extraction_quality == "none":
        return []

    chunks: list[LocalDocumentChunk] = []
    chunk_idx = 0
    file_name = extraction.file_name

    # Page-aware chunking for PDFs.
    if extraction.pages:
        for page in extraction.pages:
            text = _normalise(page.get("text", ""))
            if not text:
                continue
            for _, _, snippet in _split_window(text, chunk_size, overlap):
                if not snippet:
                    continue
                loc = f"page {page.get('page_no')}"
                chunks.append(_make_chunk(
                    source_type, extraction, file_name, loc, chunk_idx,
                    snippet,
                ))
                chunk_idx += 1
        if chunks:
            return chunks

    # Paragraph-aware chunking for DOCX.
    if extraction.paragraphs:
        buf: list[str] = []
        buf_loc: str = ""
        running_size = 0
        for para in extraction.paragraphs:
            ptext = _normalise(para.get("text", ""))
            if not ptext:
                continue
            loc = _location_for_paragraph(para)
            if not buf:
                buf_loc = loc
            buf.append(ptext)
            running_size += len(ptext)
            if running_size >= chunk_size:
                snippet = _normalise(" ".join(buf))
                chunks.append(_make_chunk(
                    source_type, extraction, file_name, buf_loc, chunk_idx,
                    snippet,
                ))
                chunk_idx += 1
                # overlap = last paragraph
                buf = buf[-1:] if overlap else []
                running_size = sum(len(b) for b in buf)
                buf_loc = loc
        if buf:
            snippet = _normalise(" ".join(buf))
            if len(snippet) >= MIN_CHUNK_CHARS or not chunks:
                chunks.append(_make_chunk(
                    source_type, extraction, file_name, buf_loc, chunk_idx,
                    snippet,
                ))
        if chunks:
            return chunks

    # Fallback: flat text.
    text = _normalise(extraction.text)
    for _, _, snippet in _split_window(text, chunk_size, overlap):
        if not snippet:
            continue
        chunks.append(_make_chunk(
            source_type, extraction, file_name, "", chunk_idx, snippet,
        ))
        chunk_idx += 1
    return chunks


def _location_for_paragraph(para: dict) -> str:
    if para.get("style") == "table_row":
        return f"table {para.get('table_no', '?')} row {para.get('row_no', '?')}"
    if para.get("is_heading"):
        return f"heading paragraph {para.get('paragraph_no', '?')}"
    return f"paragraph {para.get('paragraph_no', '?')}"


def _make_chunk(
    source_type: SourceType,
    extraction: LocalDocumentExtraction,
    file_name: str,
    location_hint: str,
    chunk_index: int,
    text: str,
) -> LocalDocumentChunk:
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    quality: ExtractionQuality = extraction.extraction_quality
    return LocalDocumentChunk(
        source_type=source_type,
        document_id=extraction.document_id,
        file_name=file_name,
        safe_reference=_safe_reference(file_name, location_hint),
        location_hint=location_hint,
        chunk_index=chunk_index,
        content_sha256=sha,
        text=text,
        extraction_quality=quality,
    )


def chunk_many(
    extractions: Iterable[LocalDocumentExtraction],
    *,
    source_type: SourceType,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[LocalDocumentChunk]:
    """Convenience helper — chunk a list of extractions."""
    all_chunks: list[LocalDocumentChunk] = []
    for ex in extractions:
        all_chunks.extend(chunk_extraction(
            ex, source_type=source_type, chunk_size=chunk_size, overlap=overlap,
        ))
    return all_chunks
