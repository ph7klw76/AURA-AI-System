"""
Best-effort metadata extraction from patent landing-page HTML.

Stage 1 — web scraping, not API access.  Per-host extractors look for
recognisable signals:

- patents.google.com: ``citation_*`` / DC.* meta tags + heading sections.
- patentscope.wipo.int: server-rendered table layout with field labels.
- uspto.gov: mixed; falls back to regex over body text.

Fallback for ALL hosts:
- ``<title>`` tag for title,
- ``<meta name="description">`` for abstract,
- regex sweep over the cleaned body text for a publication number.

The extractor NEVER raises.  Returns a ``PatentPageExtraction`` whose
``extraction_quality`` and ``extraction_notes`` describe how much we trust it.

Quality bands (per spec):
- "high":   publication_number + title + abstract + ≥1 strong metadata field
            (assignee, inventor, filing_date, or publication_date)
- "medium": title + abstract, OR title + publication_number
- "low":    everything else (snippet-like content only)
"""

from __future__ import annotations

import re

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]
    _BS4_AVAILABLE = False

from .page_fetcher import FetchResult
from .schemas import (
    ExtractionQuality, FetchStatus,
    PatentPageExtraction, PatentSearchHit, PatentSource,
)


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _safe_text(node) -> str:
    if node is None:
        return ""
    try:
        return (node.get_text(strip=True) or "").strip()
    except Exception:
        return ""


def _meta(soup, name: str) -> str:
    """Return content of <meta name=...> or <meta property=...> (case-insensitive)."""
    if soup is None:
        return ""
    target = name.strip().lower()
    try:
        for el in soup.find_all("meta"):
            attr = (el.get("name") or el.get("property") or "").strip().lower()
            if attr == target:
                return (el.get("content") or "").strip()
    except Exception:
        pass
    return ""


def _all_meta(soup, name: str) -> list[str]:
    if soup is None:
        return []
    target = name.strip().lower()
    items: list[str] = []
    try:
        for el in soup.find_all("meta"):
            attr = (el.get("name") or "").strip().lower()
            if attr == target:
                c = (el.get("content") or "").strip()
                if c:
                    items.append(c)
    except Exception:
        pass
    return items


_JURISDICTION_PREFIX = re.compile(r"^([A-Z]{2})")


def _jurisdiction_from(pub_number: str, url: str) -> str:
    if pub_number:
        m = _JURISDICTION_PREFIX.match(pub_number.strip())
        if m:
            return m.group(1)
    host = url.lower()
    if "uspto" in host:
        return "US"
    if "wipo" in host:
        return "WO"
    return ""


def _extract_section_excerpt(soup, keywords: list[str], max_chars: int = 1500) -> str:
    """Find a heading containing any of *keywords* and return the text below it.

    Defensive: returns "" if nothing matches.  Used for Claims / Description
    excerpts on Google Patents and similar layouts.
    """
    if soup is None:
        return ""
    pattern = re.compile("|".join(re.escape(k) for k in keywords), re.I)
    try:
        for heading in soup.find_all(["h1", "h2", "h3", "h4", "section"]):
            text = heading.get_text(strip=True)
            if not text or not pattern.search(text):
                continue
            # Collect text from the following siblings until the next heading
            # or until we hit the char cap.
            chunks: list[str] = []
            for sib in heading.find_next_siblings():
                if sib.name in ("h1", "h2", "h3", "h4"):
                    break
                t = sib.get_text(separator=" ", strip=True)
                if t:
                    chunks.append(t)
                if sum(len(c) for c in chunks) >= max_chars:
                    break
            joined = " ".join(chunks)
            return joined[:max_chars]
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Per-host extractors
# ---------------------------------------------------------------------------

def _extract_google_patents(soup) -> dict:
    """Google Patents — rich Schema.org / citation_* meta tags."""
    return {
        "title": _meta(soup, "DC.title") or _meta(soup, "citation_title"),
        "abstract": _meta(soup, "DC.description") or _meta(soup, "description"),
        "publication_number": (
            _meta(soup, "citation_patent_publication_number")
            or _meta(soup, "citation_patent_number")
        ),
        "application_number": _meta(soup, "citation_patent_application_number"),
        "inventors": _all_meta(soup, "DC.contributor") or _all_meta(soup, "citation_inventor"),
        "assignee_or_applicant": [a for a in [_meta(soup, "DC.creator")] if a],
        "filing_date": _meta(soup, "DC.date.filed") or _meta(soup, "citation_filing_date"),
        "publication_date": (
            _meta(soup, "DC.date.issued") or _meta(soup, "citation_publication_date")
        ),
        "priority_date": _meta(soup, "DC.date.priority"),
        "claims_excerpt": _extract_section_excerpt(soup, ["Claims"]),
        "description_excerpt": _extract_section_excerpt(soup, ["Description", "Background", "Summary"]),
    }


def _extract_wipo_patentscope(soup) -> dict:
    text = soup.get_text(separator="\n") if soup else ""
    pub = re.search(r"Publication Number\s*[:\n]\s*([A-Z0-9/]+)", text)
    app = re.search(r"Application Number\s*[:\n]\s*([A-Z0-9/]+)", text)
    title_el = soup.find("h2") if soup else None
    return {
        "title": _safe_text(title_el),
        "abstract": _meta(soup, "description"),
        "publication_number": pub.group(1) if pub else "",
        "application_number": app.group(1) if app else "",
        "assignee_or_applicant": [],
        "inventors": [],
        "filing_date": "",
        "publication_date": "",
        "priority_date": "",
        "claims_excerpt": _extract_section_excerpt(soup, ["Claim", "Claims"]),
        "description_excerpt": _extract_section_excerpt(soup, ["Description", "Abstract"]),
    }


_USPTO_PUB_PATTERNS = [
    re.compile(r"Publication Number[:\s]+([A-Z0-9/,\.\-]+)", re.I),
    re.compile(r"Patent No\.?\s*[:\s]*([A-Z0-9/,\.\-]+)", re.I),
    re.compile(r"\b(US\d{7,12}[A-Z]?\d?)\b"),
]


def _extract_uspto(soup) -> dict:
    text = soup.get_text(separator="\n") if soup else ""
    pub_number = ""
    for pat in _USPTO_PUB_PATTERNS:
        m = pat.search(text)
        if m:
            pub_number = m.group(1).strip()
            break
    return {
        "title": _safe_text(soup.find("title")) if soup else "",
        "abstract": _meta(soup, "description"),
        "publication_number": pub_number,
        "application_number": "",
        "assignee_or_applicant": [],
        "inventors": [],
        "filing_date": "",
        "publication_date": "",
        "priority_date": "",
        "claims_excerpt": _extract_section_excerpt(soup, ["Claims", "Claim"]),
        "description_excerpt": _extract_section_excerpt(soup, ["Description", "Specification"]),
    }


_HOST_DISPATCH = {
    PatentSource.google_patents: _extract_google_patents,
    PatentSource.wipo: _extract_wipo_patentscope,
    PatentSource.uspto: _extract_uspto,
}


# ---------------------------------------------------------------------------
# Quality assessment
# ---------------------------------------------------------------------------

def _assess_quality(
    title: str, abstract: str, pub_number: str,
    assignees: list[str], inventors: list[str],
    filing_date: str, publication_date: str,
) -> ExtractionQuality:
    has_title = bool(title)
    has_abs = bool(abstract) and len(abstract) > 30
    has_num = bool(pub_number)
    strong_metadata_count = sum(bool(x) for x in (assignees, inventors, filing_date, publication_date))

    if has_title and has_abs and has_num and strong_metadata_count >= 1:
        return "high"
    if has_title and (has_abs or has_num):
        return "medium"
    return "low"


def _quality_notes(
    title: str, abstract: str, pub_number: str,
    assignees: list[str], inventors: list[str],
    filing_date: str, publication_date: str,
) -> list[str]:
    notes: list[str] = []
    if not title:
        notes.append("title not extracted")
    if not abstract:
        notes.append("abstract not extracted")
    if not pub_number:
        notes.append("publication number not extracted")
    if not assignees:
        notes.append("assignee/applicant not extracted")
    if not inventors:
        notes.append("inventors not extracted")
    if not filing_date and not publication_date:
        notes.append("no filing/publication dates extracted")
    return notes


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_from_page(
    hit: PatentSearchHit,
    fetch: FetchResult,
) -> PatentPageExtraction:
    """Build a PatentPageExtraction from a search hit + fetch result.

    Always returned (never raises).  Even on fetch/parse failure we return a
    PatentPageExtraction so the run-aggregator sees every URL we attempted.
    """
    notes: list[str] = list(fetch.notes)
    status: FetchStatus = fetch.status  # type: ignore[assignment]

    base = PatentPageExtraction(
        url=hit.url,
        source_domain=hit.source_domain,
        fetch_status=status,
        http_status=fetch.http_status,
        title=hit.title,
        abstract=hit.snippet,
        raw_text_path=fetch.cached_path,
        extraction_quality="low",
        extraction_notes=notes,
    )

    # Fetch did not produce HTML — nothing more to do.
    if not fetch.ok:
        notes.append(f"fetch_status={status}; structured extraction skipped")
        base.extraction_notes = notes
        return base

    if not _BS4_AVAILABLE:
        notes.append("beautifulsoup4 not installed; extraction skipped")
        base.extraction_notes = notes
        return base

    try:
        soup = BeautifulSoup(fetch.html or "", "html.parser")
    except Exception as exc:
        notes.append(f"html parse failed: {exc}")
        base.extraction_notes = notes
        return base

    extractor_fn = _HOST_DISPATCH.get(hit.source_domain)
    fields: dict = {}
    if extractor_fn is not None:
        try:
            fields = extractor_fn(soup) or {}
        except Exception as exc:
            notes.append(f"{hit.source_domain.value} extractor failed: {exc}")
            fields = {}

    # Generic fallback for empty title/abstract.
    try:
        if not fields.get("title"):
            fields["title"] = _safe_text(soup.find("title"))
        if not fields.get("abstract"):
            fields["abstract"] = _meta(soup, "description")
    except Exception as exc:
        notes.append(f"generic-fallback failed: {exc}")

    # Body-text fallback for publication number (catches USPTO-style pages
    # where meta tags are absent).
    if not fields.get("publication_number"):
        body = (soup.get_text(separator=" ", strip=True) or "")[:50_000]
        for pat in _USPTO_PUB_PATTERNS:
            m = pat.search(body)
            if m:
                fields["publication_number"] = m.group(1).strip()
                notes.append("publication_number recovered via body-text fallback")
                break

    title = (fields.get("title") or hit.title or "").strip()
    abstract = (fields.get("abstract") or hit.snippet or "").strip()
    pub_number = (fields.get("publication_number") or "").strip()
    assignees = [a for a in (fields.get("assignee_or_applicant") or []) if a]
    inventors = [i for i in (fields.get("inventors") or []) if i]
    filing_date = (fields.get("filing_date") or "").strip()
    publication_date = (fields.get("publication_date") or "").strip()

    quality = _assess_quality(
        title, abstract, pub_number,
        assignees, inventors, filing_date, publication_date,
    )
    notes.extend(_quality_notes(
        title, abstract, pub_number,
        assignees, inventors, filing_date, publication_date,
    ))

    raw_excerpt = (fetch.cleaned_text or "")[:8000]

    return PatentPageExtraction(
        url=hit.url,
        source_domain=hit.source_domain,
        fetch_status="ok",
        http_status=fetch.http_status,
        title=title,
        publication_number=pub_number,
        application_number=(fields.get("application_number") or "").strip(),
        assignee_or_applicant=assignees,
        inventors=inventors,
        filing_date=filing_date,
        publication_date=publication_date,
        priority_date=(fields.get("priority_date") or "").strip(),
        abstract=abstract,
        claims_excerpt=(fields.get("claims_excerpt") or "")[:2000],
        description_excerpt=(fields.get("description_excerpt") or "")[:2000],
        raw_text_excerpt=raw_excerpt,
        raw_text_path=fetch.cached_path,
        extraction_quality=quality,
        extraction_notes=notes,
    )
