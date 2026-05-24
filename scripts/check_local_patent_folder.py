"""
Pre-flight diagnostic for a local patent folder.

Walks the folder, runs the same extraction pipeline AURA uses, and prints
a per-file table showing what succeeded, what came up empty, and whether
OCR would help.  Also checks whether Tesseract is installed and how to
fix it if not.

Usage
-----
    # Default folder (the one in this user's report):
    python scripts/check_local_patent_folder.py

    # Custom folder:
    python scripts/check_local_patent_folder.py "C:\\path\\to\\patents"

    # With explicit OCR on (overrides auto-detect):
    set AURA_LOCAL_PDF_OCR=1
    python scripts/check_local_patent_folder.py

No AURA agents are invoked — this is purely a folder-inspection tool.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.local_documents.discovery import scan_folder    # noqa: E402
from core.local_documents.extract_pdf import (              # noqa: E402
    _tesseract_available, extract_pdf,
)
from core.local_documents.extract_docx import extract_docx  # noqa: E402
from core.local_documents.extract_text import extract_text_file  # noqa: E402


DEFAULT_FOLDER = r"C:\Users\Woon\Documents\UM\OLED\patent"


def _extract_one(path: Path):
    ext = path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf(path)
    if ext == ".docx":
        return extract_docx(path)
    if ext in (".txt", ".md"):
        return extract_text_file(path)
    return None


def _check_tesseract() -> tuple[bool, str]:
    """Return ``(installed, hint)``."""
    if _tesseract_available():
        return True, (
            "Tesseract found at "
            f"{shutil.which('tesseract') or os.getenv('TESSERACT_CMD')}"
        )
    if os.name == "nt":
        hint = (
            "Tesseract not found on PATH.\n"
            "  Install on Windows:\n"
            "    1. Download:  https://github.com/UB-Mannheim/tesseract/wiki\n"
            "    2. Run installer (defaults are fine).\n"
            "    3. Open a NEW cmd / PowerShell so PATH refreshes, OR\n"
            "       set TESSERACT_CMD=\"C:\\Program Files\\Tesseract-OCR\\tesseract.exe\""
        )
    else:
        hint = (
            "Tesseract not found.\n"
            "  Install:\n"
            "    macOS:   brew install tesseract\n"
            "    Ubuntu:  sudo apt install tesseract-ocr\n"
            "    Then re-run."
        )
    return False, hint


def _check_python_deps() -> list[str]:
    missing: list[str] = []
    for pkg in ("pypdf", "fitz", "pytesseract", "PIL"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg if pkg != "PIL" else "Pillow")
    return missing


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    folder = argv[1] if len(argv) > 1 else DEFAULT_FOLDER
    print(f"Folder           : {folder}")
    print(f"Tesseract on PATH: {_tesseract_available()}")
    print(f"AURA_LOCAL_PDF_OCR={os.getenv('AURA_LOCAL_PDF_OCR', '')!r}")
    print("-" * 78)

    missing = _check_python_deps()
    if missing:
        print(f"⚠  Missing Python packages: {', '.join(missing)}")
        print("   Install with:  pip install " + " ".join(missing))
        print("-" * 78)

    p = Path(folder)
    if not p.exists():
        print(f"❌ Folder does not exist: {p}")
        return 2
    if not p.is_dir():
        print(f"❌ Not a directory: {p}")
        return 2

    summary = scan_folder(str(p))
    print(f"Discovered files : {summary.files_discovered}")
    print(f"  supported      : {summary.files_supported}")
    print(f"  skipped        : {summary.files_skipped}")
    if summary.unsupported_formats:
        print(f"  unsupported    : {', '.join(summary.unsupported_formats)}")
    print("-" * 78)

    counts = {"extracted": 0, "no_text": 0, "failed": 0}
    pdf_no_text = 0
    pdf_total = 0
    for f in summary.discovered_files:
        if not f.is_supported:
            continue
        ex = _extract_one(Path(f.path))
        if ex is None:
            continue
        name = f.name
        quality = ex.extraction_quality
        method = ex.extraction_method or "(none)"
        if f.ext == ".pdf":
            pdf_total += 1

        if ex.failed:
            counts["failed"] += 1
            icon = "❌"
            label = "failed"
            if f.ext == ".pdf":
                pdf_no_text += 1
        elif quality == "none":
            counts["no_text"] += 1
            icon = "⚠ "
            label = "no_text"
            if f.ext == ".pdf":
                pdf_no_text += 1
        else:
            counts["extracted"] += 1
            icon = "✅"
            label = "extracted"

        line = f"{icon} {name:<50} {label:<10} method={method:<10} q={quality}"
        print(line)
        if ex.failure_reason:
            print(f"     reason: {ex.failure_reason[:200]}")

    print("-" * 78)
    print(
        f"Outcome: {counts['extracted']} extracted, "
        f"{counts['no_text']} no_text, {counts['failed']} failed"
    )

    # Recommendation engine.
    print()
    if counts["extracted"] == summary.files_supported > 0:
        print("✅ All supported files extracted cleanly — no action needed.")
        return 0

    pdf_scan_ratio = (pdf_no_text / max(1, pdf_total)) if pdf_total else 0
    if pdf_scan_ratio >= 0.5:
        print(
            "⚠  Most PDFs returned no text — they look like SCANNED / image "
            "PDFs.\n"
            "   To recover the text, enable OCR:\n"
        )
        ok, hint = _check_tesseract()
        if not ok:
            print("   " + hint.replace("\n", "\n   "))
        else:
            print("   ✅ Tesseract is installed.  Enable OCR for the next run:")
            print("      cmd.exe       :  set AURA_LOCAL_PDF_OCR=1")
            print("      PowerShell    :  $env:AURA_LOCAL_PDF_OCR=\"1\"")
            print("   Then re-run this script to confirm OCR recovers the text.")
    else:
        print(
            "Most files extracted, but a minority failed.  "
            "Re-run with logging to see per-file detail; the failed files "
            "are likely encrypted, malformed, or non-PDF."
        )

    return 0 if counts["extracted"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
