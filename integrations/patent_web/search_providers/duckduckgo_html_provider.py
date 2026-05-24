"""
DuckDuckGo HTML public-web patent search — NO API key required.

Why this provider exists
------------------------
Google's static HTML SERP was deprecated in 2024–2026 in many regions —
clients without JavaScript receive a tiny noscript redirect instead of
real results.  DuckDuckGo still operates a dedicated HTML endpoint
(``https://html.duckduckgo.com/html/``) that returns a server-rendered
results page with classic ``<a class="result__a" href="…">`` tags.  No
account, no API key, no JS required.

This is the real working "no-key public web discovery" path in late
2025 / early 2026.  It honours the same honesty contract as the Google
provider:

  * ``not_api_verified=True``
  * ``non_exhaustive=True``
  * structured warnings; never raises
  * no anti-bot bypass — if DDG ever serves a CAPTCHA, we fail loudly

DuckDuckGo's HTML page may rate-limit or change formatting at any moment.
The provider is conservative: single request, modest result cap, dedup
within patent-host allow-list.
"""
from __future__ import annotations

import os
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .base import (
    PatentSearchProvider,
    PatentSearchResponse,
    PatentSearchResult,
)


_DEFAULT_TIMEOUT = 15
_DEFAULT_UA = (
    # DuckDuckGo's HTML endpoint accepts ordinary browser UAs.
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


_PATENT_HOSTS = (
    "patents.google.com",
    "patentscope.wipo.int",
    "uspto.gov",
    "worldwide.espacenet.com",
)

# Each result is rendered as <a class="result__a" href="…">title</a>
# (the href is sometimes wrapped in /l/?uddg=<actual>&… redirect).
_RESULT_A_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
# Fallback: any absolute patent-host URL anywhere in the body.
_ABS_URL_RE = re.compile(
    r"https?://(?:[a-zA-Z0-9\-]+\.)*"
    r"(?:patents\.google\.com|patentscope\.wipo\.int|uspto\.gov|"
    r"worldwide\.espacenet\.com)"
    r"/[^\"'<>\s\\)]+",
    re.IGNORECASE,
)

_BLOCK_MARKERS = (
    "anomaly_detected",
    "captcha",
    "we just need to make sure you",
    "verify you are a human",
)

# DDG occasionally serves HTTP 202 with a small JS-challenge body when
# they want to verify a non-browser client.  Treat as a soft-block so
# the fallback chain fires instead of presenting "results = 0".
_SOFT_BLOCK_STATUSES = (202, 403, 429)


class DuckDuckGoHtmlPatentSearchProvider(PatentSearchProvider):
    """No-key DuckDuckGo HTML SERP scraper for patent-host URLs."""

    name = "duckduckgo_html"

    def __init__(
        self,
        *,
        timeout: int = _DEFAULT_TIMEOUT,
        user_agent: str | None = None,
        endpoint: str = "https://html.duckduckgo.com/html/",
        http_session: Any | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent or _DEFAULT_UA
        self.endpoint = endpoint
        self._http = http_session
        if enabled is None:
            enabled = os.getenv(
                "AURA_DDG_HTML_PATENT_ENABLED", "1",
            ).strip() != "0"
        self.enabled = bool(enabled)

    # ---------------------------------------------------------------- search
    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        target_domain: str | None = None,
    ) -> PatentSearchResponse:
        q = (query or "").strip()
        if not q:
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=False,
                failure_reason="empty_query",
            )
            resp.add_warning("empty_query", "Empty query — nothing to send.")
            return resp

        if not self.enabled:
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=False,
                failure_reason="provider_disabled",
            )
            resp.add_warning(
                "provider_disabled",
                "DuckDuckGo HTML no-key discovery is disabled "
                "(AURA_DDG_HTML_PATENT_ENABLED=0).",
            )
            return resp

        session = self._http
        if session is None:
            try:
                import requests as _req
                session = _req
            except ImportError:
                resp = PatentSearchResponse(
                    query=q, provider=self.name, success=False,
                    failure_reason="requests_missing",
                )
                resp.add_warning(
                    "requests_missing",
                    "The `requests` library is required for DDG HTML "
                    "no-key discovery but is not installed.",
                )
                return resp

        # DDG accepts POST or GET; GET is simpler and well-cached.
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        }
        params = {"q": q, "kl": "us-en"}

        try:
            r = session.get(
                self.endpoint, params=params, headers=headers,
                timeout=self.timeout,
            )
        except Exception as exc:
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=False,
                failure_reason=f"request_error: {exc.__class__.__name__}",
            )
            resp.add_warning(
                "request_error",
                f"DDG HTML request raised: {exc.__class__.__name__}: {exc}",
            )
            return resp

        status = getattr(r, "status_code", 0)
        body = getattr(r, "text", "") or ""
        body_lower = body.lower()

        if status in _SOFT_BLOCK_STATUSES or any(
            m in body_lower for m in _BLOCK_MARKERS
        ):
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=False,
                failure_reason="blocked_or_captcha",
            )
            resp.add_warning(
                "ddg_blocked",
                f"DuckDuckGo HTML discovery was unavailable or rate-limited "
                f"(HTTP {status} or JS-challenge body detected). "
                "AURA does NOT bypass anti-bot protections — falling back.",
            )
            resp.raw_metadata["http_status"] = status
            return resp

        if status != 200 or not body:
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=False,
                failure_reason=f"http_{status or 'empty'}",
            )
            resp.add_warning(
                "unexpected_response",
                f"DuckDuckGo HTML returned HTTP {status} with "
                f"{len(body)}-byte body; cannot extract results.",
            )
            resp.raw_metadata["http_status"] = status
            return resp

        try:
            extracted = _extract_results(body, target_domain=target_domain)
        except Exception as exc:
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=False,
                failure_reason=f"parse_error: {exc.__class__.__name__}",
            )
            resp.add_warning(
                "parse_error",
                f"Failed to parse DDG HTML SERP: "
                f"{exc.__class__.__name__}: {exc}",
            )
            return resp

        if not extracted:
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=True, results=[],
            )
            resp.add_warning(
                "zero_results",
                "DuckDuckGo HTML returned no patent-domain URLs for this query.",
            )
            resp.raw_metadata["http_status"] = status
            return resp

        results: list[PatentSearchResult] = []
        for idx, (url, title) in enumerate(extracted[:limit], start=1):
            host = _host_of(url)
            results.append(PatentSearchResult(
                title=title or url,
                url=url,
                snippet=None,
                rank=idx,
                source_provider="duckduckgo_html",
                target_domain=host,
                raw_metadata={"discovered_via": "duckduckgo_html"},
            ))

        resp = PatentSearchResponse(
            query=q,
            provider=self.name,
            results=results,
            success=True,
            not_api_verified=True,
            non_exhaustive=True,
            raw_metadata={"http_status": status, "backend": "duckduckgo_html"},
        )
        resp.add_warning(
            "best_effort_disclaimer",
            "Best-effort DuckDuckGo HTML discovery — NOT an official API, "
            "NOT exhaustive, prone to rate-limiting and HTML drift.",
        )
        return resp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _host_of(url: str) -> str | None:
    try:
        return urlparse(url).netloc.lower() or None
    except Exception:
        return None


def _is_patent_host(host: str | None) -> bool:
    if not host:
        return False
    return any(host == p or host.endswith("." + p) for p in _PATENT_HOSTS)


def _unwrap_ddg_redirect(href: str) -> str:
    """DDG occasionally proxies outbound links through /l/?uddg=<actual>&…"""
    if not href:
        return href
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urlparse(href)
        if "duckduckgo.com" in (parsed.netloc or "") and parsed.path == "/l/":
            q = parse_qs(parsed.query)
            actual = q.get("uddg") or q.get("u")
            if actual:
                return unquote(actual[0])
    except Exception:
        pass
    return href


def _extract_results(
    body: str, *, target_domain: str | None,
) -> list[tuple[str, str]]:
    """Return ordered, deduped (url, title) pairs from the DDG SERP HTML."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    def _accept(url: str, title: str) -> None:
        url = _unwrap_ddg_redirect(url.strip())
        if not (url.startswith("http://") or url.startswith("https://")):
            return
        host = _host_of(url)
        if not _is_patent_host(host):
            return
        if target_domain and host != target_domain and not host.endswith(
            "." + target_domain
        ):
            return
        if url in seen:
            return
        seen.add(url)
        clean_title = re.sub(r"<[^>]+>", "", title or "").strip()
        clean_title = unescape(clean_title)
        out.append((url, clean_title[:240] if clean_title else ""))

    # Primary pass: classic DDG result anchors.
    for m in _RESULT_A_RE.finditer(body):
        href = unescape(m.group(1))
        title_html = m.group(2)
        _accept(href, title_html)

    # Fallback pass: scan whole body for absolute patent-host URLs.
    if not out:
        for m in _ABS_URL_RE.finditer(body):
            _accept(m.group(0), "")

    return out
