"""
PDF extraction with native-text preference, quality-driven fallback, and an
optional OCR pathway (Phase 2 defects 10 + 11).

Library precedence
------------------
  1. ``pypdf`` (preferred — pure Python, MIT)
  2. ``PyPDF2`` (legacy alias for pypdf)
  3. ``fitz`` (PyMuPDF — fastest, AGPL/commercial)

Quality-driven fallback (defect 10)
-----------------------------------
The previous version only tried the second/third parser when the first
parser was MISSING.  Now we also fall back when the first parser:

  * raised an exception,
  * returned no usable text,
  * or reported ``extraction_quality in {"none", "poor"}``.

The best result across all parsers wins.

OCR pathway (defect 11)
-----------------------
Image-only PDFs (scans, photographs of paper) yield no text from the
native parsers.  When OCR is enabled, the extractor renders each page to
an image and runs ``pytesseract`` on it.  OCR is OFF by default — opt in
via:

  * ``AURA_LOCAL_PDF_OCR=1`` env var (process-wide), OR
  * ``extract_pdf(path, enable_ocr=True)`` (per-call).

OCR-derived output is labelled honestly:

  * ``extraction_method = "ocr"``
  * ``extraction_quality`` is capped at ``"partial"`` so downstream
    confidence cannot inflate just because OCR ran.
  * a warning ``kind="ocr"`` records that the text was machine-read.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .models import (
    ExtractionWarning, LocalDocumentExtraction,
)


# Extraction-quality bands that DON'T satisfy the "good enough" bar.
_LOW_QUALITIES: frozenset[str] = frozenset({"none", "poor"})


def _try_pypdf(path: Path) -> tuple[str, list[dict], list[ExtractionWarning], str]:
    """Return ``(joined_text, pages, warnings, method)``.

    Returns empty text + an explanatory warning if pypdf is unavailable.
    """
    try:
        import pypdf as _pdfmod
        method = "pypdf"
    except ImportError:
        try:
            import PyPDF2 as _pdfmod    # type: ignore[no-redef]
            method = "PyPDF2"
        except ImportError:
            return "", [], [ExtractionWarning(
                kind="library_missing",
                detail="pypdf / PyPDF2 not installed",
            )], ""

    warnings: list[ExtractionWarning] = []
    pages: list[dict] = []
    try:
        reader = _pdfmod.PdfReader(str(path))
    except Exception as exc:
        warnings.append(ExtractionWarning(
            kind="parse_error",
            detail=f"could not open PDF: {exc.__class__.__name__}: {exc}",
        ))
        return "", [], warnings, method

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:
            warnings.append(ExtractionWarning(
                kind="encrypted",
                detail="PDF is encrypted and no password is available",
            ))
            return "", [], warnings, method

    for idx, page in enumerate(getattr(reader, "pages", []), start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            warnings.append(ExtractionWarning(
                kind="page_extract_failed",
                detail=str(exc),
                location=f"page {idx}",
            ))
            text = ""
        pages.append({"page_no": idx, "text": text})

    joined = "\n".join(p.get("text", "") for p in pages)
    return joined, pages, warnings, method


def _try_fitz(path: Path) -> tuple[str, list[dict], list[ExtractionWarning], str]:
    """PyMuPDF fallback."""
    try:
        import fitz   # type: ignore
    except ImportError:
        return "", [], [ExtractionWarning(
            kind="library_missing",
            detail="PyMuPDF (fitz) not installed",
        )], ""

    warnings: list[ExtractionWarning] = []
    pages: list[dict] = []
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        warnings.append(ExtractionWarning(
            kind="parse_error", detail=str(exc),
        ))
        return "", [], warnings, "fitz"

    for idx, page in enumerate(doc, start=1):
        try:
            text = page.get_text() or ""
        except Exception as exc:
            warnings.append(ExtractionWarning(
                kind="page_extract_failed", detail=str(exc),
                location=f"page {idx}",
            ))
            text = ""
        pages.append({"page_no": idx, "text": text})
    joined = "\n".join(p.get("text", "") for p in pages)
    return joined, pages, warnings, "fitz"


def _assess_pdf_quality(joined: str, pages: list[dict]) -> str:
    """Heuristic: many empty pages → poor; mostly empty → partial; else good."""
    if not pages:
        return "none"
    non_empty = sum(1 for p in pages if (p.get("text") or "").strip())
    ratio = non_empty / max(1, len(pages))
    if ratio >= 0.8 and len(joined.strip()) > 200:
        return "good"
    if ratio >= 0.3:
        return "partial"
    return "poor"


# ---------------------------------------------------------------------------
# OCR pathway (defect 11)
# ---------------------------------------------------------------------------

def _ocr_enabled(explicit: Optional[bool]) -> bool:
    """Resolve OCR enablement with three-tier precedence.

    1. Explicit ``enable_ocr=True/False`` argument always wins.
    2. ``AURA_LOCAL_PDF_OCR`` env var: ``"1"`` forces ON, ``"0"`` forces OFF.
    3. Auto-detect: when neither is set, OCR is enabled IFF the Tesseract
       binary is discoverable on PATH (or via ``TESSERACT_CMD``).  This
       removes friction for users who installed Tesseract — they don't
       need to set an env var to get scanned-PDF support — while still
       defaulting to OFF on machines without OCR installed (avoiding
       confusing import-time failures).
    """
    if explicit is True:
        return True
    if explicit is False:
        return False
    env = os.getenv("AURA_LOCAL_PDF_OCR", "").strip()
    if env == "1":
        return True
    if env == "0":
        return False
    return _tesseract_available()


def _tesseract_available() -> bool:
    """Return True iff the Tesseract binary is on PATH (or set via env).

    Pure file-system check — uses ``shutil.which`` + an optional
    ``TESSERACT_CMD`` env override.  NEVER imports ``pytesseract`` here:
    that import (transitively numpy on Windows) can crash test
    environments that patch ``builtins.__import__``.  Binding the
    binary path to pytesseract is deferred until :func:`_try_ocr`
    actually needs it.

    Cached for the process lifetime so repeated extractions don't repeat
    the lookup.
    """
    global _TESS_CACHE
    try:
        return _TESS_CACHE
    except NameError:
        pass
    import shutil
    candidate = os.getenv("TESSERACT_CMD") or "tesseract"
    found = bool(shutil.which(candidate))
    if not found and os.name == "nt":
        # Common Windows install locations the UB-Mannheim installer uses.
        # Just probe the file system; binding the path to pytesseract
        # happens in _try_ocr().
        for guess in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if Path(guess).exists():
                os.environ.setdefault("TESSERACT_CMD", guess)
                found = True
                break
    globals()["_TESS_CACHE"] = found
    return found


def _try_ocr(path: Path) -> tuple[str, list[dict], list[ExtractionWarning], str]:
    """Render each page to an image and run pytesseract.

    Backend chain:
      * Prefer ``fitz`` (PyMuPDF) for rendering — no external binary needed.
      * Fall back to ``pdf2image`` (which requires the poppler binary).

    Returns ``("", [], [warning], "")`` when no backend is available.
    """
    warnings: list[ExtractionWarning] = []
    try:
        import pytesseract   # type: ignore
        from PIL import Image  # type: ignore  # noqa: F401
        # Bind the explicit Tesseract path (if Windows-installer-detected
        # by ``_tesseract_available``) so pytesseract finds the binary
        # even when it's not on PATH.
        _tess_cmd = os.getenv("TESSERACT_CMD")
        if _tess_cmd:
            try:
                pytesseract.pytesseract.tesseract_cmd = _tess_cmd
            except Exception:
                pass
    except ImportError:
        return "", [], [ExtractionWarning(
            kind="library_missing",
            detail="OCR requires pytesseract + Pillow",
        )], ""

    # Try fitz first — rendering is fast and dependency-free.
    pages: list[dict] = []
    method = ""
    rendered_images: list = []
    try:
        import fitz   # type: ignore
        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            warnings.append(ExtractionWarning(
                kind="parse_error", detail=f"fitz could not open PDF: {exc}",
            ))
            doc = None
        if doc is not None:
            from PIL import Image as _PILImage  # type: ignore
            import io as _io
            for idx, page in enumerate(doc, start=1):
                try:
                    pix = page.get_pixmap(dpi=200)
                    img = _PILImage.open(_io.BytesIO(pix.tobytes("png")))
                    rendered_images.append((idx, img))
                except Exception as exc:
                    warnings.append(ExtractionWarning(
                        kind="page_extract_failed",
                        detail=f"fitz render failed: {exc}",
                        location=f"page {idx}",
                    ))
            method = "ocr"
    except ImportError:
        pass

    # pdf2image fallback (requires poppler binary).
    if not rendered_images:
        try:
            from pdf2image import convert_from_path  # type: ignore
            images = convert_from_path(str(path), dpi=200)
            rendered_images = list(enumerate(images, start=1))
            method = "ocr"
        except ImportError:
            warnings.append(ExtractionWarning(
                kind="library_missing",
                detail="OCR rendering requires fitz or pdf2image+poppler",
            ))
            return "", [], warnings, ""
        except Exception as exc:
            warnings.append(ExtractionWarning(
                kind="parse_error",
                detail=f"pdf2image conversion failed: {exc}",
            ))
            return "", [], warnings, "ocr"

    if not rendered_images:
        return "", [], warnings, "ocr"

    warnings.append(ExtractionWarning(
        kind="ocr",
        detail=(
            "Text was reconstructed from page images via OCR "
            "(pytesseract).  Treat all extracted strings as machine-read."
        ),
    ))

    for idx, img in rendered_images:
        try:
            text = pytesseract.image_to_string(img) or ""
        except Exception as exc:
            warnings.append(ExtractionWarning(
                kind="page_extract_failed",
                detail=f"OCR failed: {exc}",
                location=f"page {idx}",
            ))
            text = ""
        pages.append({"page_no": idx, "text": text})

    joined = "\n".join(p.get("text", "") for p in pages)
    return joined, pages, warnings, method


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _better(a: tuple[str, list[dict], str], b: tuple[str, list[dict], str]) -> tuple[str, list[dict], str]:
    """Pick the higher-quality (joined, pages, method) tuple."""
    quality_order = {"good": 3, "partial": 2, "poor": 1, "none": 0, "": 0}
    qa = _assess_pdf_quality(a[0], a[1])
    qb = _assess_pdf_quality(b[0], b[1])
    if quality_order[qa] >= quality_order[qb]:
        return a
    return b


def extract_pdf(
    file_path: str | Path,
    *,
    enable_ocr: Optional[bool] = None,
) -> LocalDocumentExtraction:
    """Extract text from a PDF.

    Parameters
    ----------
    file_path
        Path to the PDF on disk.
    enable_ocr
        Tri-state opt-in for OCR:
          * ``True``  → run OCR if native parsers produce poor/no text
          * ``False`` → never run OCR
          * ``None``  → honour the ``AURA_LOCAL_PDF_OCR=1`` env var
    """
    p = Path(file_path)
    out = LocalDocumentExtraction(
        path=str(p), file_name=p.name, ext=p.suffix.lower(),
    )

    # Try pypdf first.
    j1, pages1, w1, m1 = _try_pypdf(p)
    accumulated_warnings: list[ExtractionWarning] = list(w1)
    best: tuple[str, list[dict], str] = (j1, pages1, m1)
    q1 = _assess_pdf_quality(j1, pages1) if m1 else "none"

    # Defect 10: fall back to fitz when pypdf was missing OR produced
    # poor/no text — not only on missing import.
    if (not m1) or q1 in _LOW_QUALITIES:
        j2, pages2, w2, m2 = _try_fitz(p)
        accumulated_warnings.extend(w2)
        if m2:
            best = _better(best, (j2, pages2, m2))

    # Defect 11: OCR fallback (opt-in) when no native parser produced
    # acceptable text.
    final_quality = _assess_pdf_quality(best[0], best[1])
    method = best[2]
    if _ocr_enabled(enable_ocr) and final_quality in _LOW_QUALITIES:
        j3, pages3, w3, m3 = _try_ocr(p)
        accumulated_warnings.extend(w3)
        if m3 == "ocr" and j3.strip():
            # OCR results are conservatively capped at "partial".
            best = (j3, pages3, "ocr")
            method = "ocr"
            final_quality = "partial"

    out.warnings = accumulated_warnings
    out.pages = best[1]
    out.text = best[0]

    if not method:
        out.failed = True
        out.failure_reason = (
            "No PDF extraction backend installed (pypdf / PyPDF2 / fitz / OCR)."
        )
        out.warnings.append(ExtractionWarning(
            kind="library_missing",
            detail="install pypdf or python-docx for full local-folder support",
        ))
        out.extraction_quality = "none"
        return out

    out.extraction_method = method
    if not best[0].strip():
        out.failed = True
        out.failure_reason = "PDF produced no extractable text"
        out.extraction_quality = "none"
        return out

    out.extraction_quality = final_quality if method != "ocr" else "partial"
    return out
