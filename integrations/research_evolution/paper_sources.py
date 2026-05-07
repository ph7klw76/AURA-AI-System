from __future__ import annotations

import hashlib
import time
import xml.etree.ElementTree as ET
from typing import Any

import requests

import config

OPENALEX_BASE = "https://api.openalex.org/works"
ARXIV_BASE = "https://export.arxiv.org/api/query"
REQUEST_TIMEOUT = 15


def _make_key(url: str, title: str) -> str:
    base = url.strip() if url.strip() else title.strip().lower()
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    if not inverted_index:
        return ""
    word_positions: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join(w for _, w in word_positions)


def search_openalex(query: str, max_results: int = 5) -> list[dict]:
    params: dict[str, Any] = {
        "search": query,
        "per-page": max_results,
        "sort": "publication_date:desc",
        "filter": "is_oa:true",
    }
    if config.OPENALEX_API_KEY:
        params["api_key"] = config.OPENALEX_API_KEY

    try:
        response = requests.get(OPENALEX_BASE, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return [{"source_error": f"OpenAlex error for '{query}': {exc}"}]

    papers: list[dict] = []
    for item in data.get("results", []):
        title = item.get("title", "") or ""
        url = item.get("primary_location", {}) or {}
        url = url.get("landing_page_url", "") or item.get("id", "") or ""
        abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in (item.get("authorships") or [])[:5]
        ]
        published_date = (item.get("publication_date") or "")[:10]
        cited_by_count = item.get("cited_by_count", 0) or 0
        papers.append({
            "source": "openalex",
            "title": title,
            "abstract": abstract,
            "url": url,
            "published_date": published_date,
            "authors": authors,
            "cited_by_count": cited_by_count,
            "unique_key": _make_key(url, title),
        })
    return papers


def search_arxiv(query: str, max_results: int = 5) -> list[dict]:
    params = {
        "search_query": f"all:{query}",
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        response = requests.get(ARXIV_BASE, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception as exc:
        return [{"source_error": f"arXiv error for '{query}': {exc}"}]

    papers: list[dict] = []
    try:
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", "", ns) or "").strip()
            abstract = (entry.findtext("atom:summary", "", ns) or "").strip()
            url = (entry.findtext("atom:id", "", ns) or "").strip()
            published_date = (entry.findtext("atom:published", "", ns) or "")[:10]
            authors = [
                (a.findtext("atom:name", "", ns) or "").strip()
                for a in entry.findall("atom:author", ns)[:5]
            ]
            papers.append({
                "source": "arxiv",
                "title": title,
                "abstract": abstract,
                "url": url,
                "published_date": published_date,
                "authors": authors,
                "cited_by_count": 0,
                "unique_key": _make_key(url, title),
            })
    except ET.ParseError as exc:
        return [{"source_error": f"arXiv XML parse error: {exc}"}]
    return papers


def deduplicate_papers(papers: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for p in papers:
        if "source_error" in p:
            continue
        key = p.get("unique_key", "") or p.get("url", "") or p.get("title", "").lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def search_all_sources(topics: list[str], max_per_topic: int = 3) -> list[dict]:
    all_papers: list[dict] = []
    errors: list[dict] = []
    for topic in topics[:6]:
        oa = search_openalex(topic, max_per_topic)
        for p in oa:
            if "source_error" in p:
                errors.append(p)
            else:
                all_papers.append(p)
        time.sleep(0.3)
        ax = search_arxiv(topic, max_per_topic)
        for p in ax:
            if "source_error" in p:
                errors.append(p)
            else:
                all_papers.append(p)
        time.sleep(0.3)
    deduped = deduplicate_papers(all_papers)
    if errors:
        deduped.append({"source_errors": errors})
    return deduped
