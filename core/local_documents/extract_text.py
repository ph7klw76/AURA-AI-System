"""
Plain-text and Markdown extraction (Section C — txt/md leg).
"""
from __future__ import annotations

from pathlib import Path

from .models import (
    ExtractionWarning, LocalDocumentExtraction,
)


def extract_text_file(file_path: str | Path) -> LocalDocumentExtraction:
    """Read a .txt or .md file with safe UTF-8 decoding."""
    p = Path(file_path)
    out = LocalDocumentExtraction(
        path=str(p), file_name=p.name, ext=p.suffix.lower(),
        extraction_method="plain_text",
    )
    try:
        raw = p.read_bytes()
    except (OSError, FileNotFoundError) as exc:
        out.failed = True
        out.failure_reason = f"read failed: {exc}"
        out.extraction_quality = "none"
        out.warnings.append(ExtractionWarning(kind="read_error", detail=str(exc)))
        return out

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-8", errors="replace")
            out.warnings.append(ExtractionWarning(
                kind="unicode_replaced",
                detail="non-UTF-8 bytes replaced with U+FFFD",
            ))
        except Exception as exc:
            out.failed = True
            out.failure_reason = f"decode failed: {exc}"
            out.extraction_quality = "none"
            return out

    out.text = text
    if text.strip():
        out.extraction_quality = "good"
        out.pages = [{"page_no": 1, "text": text}]
    else:
        out.extraction_quality = "poor"
        out.warnings.append(ExtractionWarning(
            kind="empty_file", detail="file contained no text after decoding",
        ))
    return out
