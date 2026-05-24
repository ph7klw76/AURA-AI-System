"""
Legacy doc/rtf/odt — controlled, fail-closed conversion stub.

Phase 4 intentionally does NOT ship an automatic legacy-format converter
(running soffice/LibreOffice silently has security and reproducibility
implications).  Files with these extensions are reported as unsupported
with a structured warning so the user knows they were not analysed,
rather than being silently dropped.
"""
from __future__ import annotations

from pathlib import Path

from .models import ExtractionWarning, LocalDocumentExtraction


def extract_legacy_doc(file_path: str | Path) -> LocalDocumentExtraction:
    p = Path(file_path)
    out = LocalDocumentExtraction(
        path=str(p), file_name=p.name, ext=p.suffix.lower(),
        extraction_method="legacy_unsupported",
        failed=True,
        failure_reason=(
            f"Legacy format {p.suffix} is not supported by the local-document "
            "ingestion subsystem in this build. Convert to .docx or .pdf "
            "and rescan the folder."
        ),
        extraction_quality="none",
    )
    out.warnings.append(ExtractionWarning(
        kind="unsupported_legacy",
        detail=(
            f"{p.suffix} files are recognised but not extracted (would require "
            "soffice/LibreOffice). File listed in the ingestion summary so "
            "the user knows it was not analysed."
        ),
    ))
    return out
