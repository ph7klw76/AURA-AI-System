"""
DOCX extraction (Section C).

Uses ``python-docx``.  Paragraphs, headings (with hierarchy hint), and
tables are preserved as separate structured blocks.  Location hints
are paragraph index, heading level, or ``table N row M``.

Like the PDF extractor, this NEVER raises — failures become structured
records on ``LocalDocumentExtraction``.
"""
from __future__ import annotations

from pathlib import Path

from .models import (
    ExtractionWarning, LocalDocumentExtraction,
)


def extract_docx(file_path: str | Path) -> LocalDocumentExtraction:
    p = Path(file_path)
    out = LocalDocumentExtraction(
        path=str(p), file_name=p.name, ext=p.suffix.lower(),
        extraction_method="python-docx",
    )
    try:
        import docx   # type: ignore
    except ImportError:
        out.failed = True
        out.failure_reason = "python-docx not installed"
        out.warnings.append(ExtractionWarning(
            kind="library_missing",
            detail="install python-docx for DOCX support",
        ))
        out.extraction_quality = "none"
        return out

    try:
        doc = docx.Document(str(p))
    except Exception as exc:
        out.failed = True
        out.failure_reason = f"could not open DOCX: {exc.__class__.__name__}"
        out.warnings.append(ExtractionWarning(
            kind="parse_error", detail=str(exc),
        ))
        out.extraction_quality = "none"
        return out

    paragraphs: list[dict] = []
    text_blocks: list[str] = []

    # Paragraphs (headings + body).
    for idx, para in enumerate(getattr(doc, "paragraphs", []), start=1):
        text = (getattr(para, "text", "") or "").strip()
        if not text:
            continue
        style_name = ""
        try:
            style_name = getattr(getattr(para, "style", None), "name", "") or ""
        except Exception:
            style_name = ""
        is_heading = style_name.lower().startswith("heading")
        paragraphs.append({
            "paragraph_no": idx,
            "text": text,
            "style": style_name,
            "is_heading": is_heading,
        })
        text_blocks.append(text)

    # Tables.
    for t_idx, table in enumerate(getattr(doc, "tables", []), start=1):
        for r_idx, row in enumerate(getattr(table, "rows", []), start=1):
            try:
                cells = [c.text.strip() for c in row.cells]
            except Exception:
                continue
            row_text = " | ".join(cells)
            if not row_text.strip():
                continue
            paragraphs.append({
                "paragraph_no": -1,
                "text": row_text,
                "style": "table_row",
                "is_heading": False,
                "table_no": t_idx,
                "row_no": r_idx,
            })
            text_blocks.append(f"[Table {t_idx} row {r_idx}] {row_text}")

    if not text_blocks:
        out.failed = True
        out.failure_reason = "DOCX produced no extractable text"
        out.extraction_quality = "none"
        return out

    out.paragraphs = paragraphs
    out.text = "\n\n".join(text_blocks)
    out.extraction_quality = "good" if len(out.text) > 200 else "partial"
    return out
