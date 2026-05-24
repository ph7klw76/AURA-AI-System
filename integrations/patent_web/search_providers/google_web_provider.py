"""
Google-oriented public web discovery for patents — NO API KEY required.

What this provider IS
---------------------
A best-effort, transparent retrieval path that fetches Google's public
HTML search results page for queries like
``site:patents.google.com "TADF" OLED emitter`` and extracts patent
landing-page URLs from the response.

What this provider is NOT
-------------------------
* It is NOT the Google Custom Search API.
* It is NOT an exhaustive or authoritative patent search.
* It is NOT freedom-to-operate analysis.
* It MUST NOT bypass anti-bot / CAPTCHA / consent controls — when
  Google returns one, this provider FAILS LOUDLY (success=False, a
  structured warning) and the factory's fallback logic takes over.

Design rationale
----------------
Google's HTML SERP layout changes frequently and may block
automated access at any moment.  We therefore:

  * use a single, conservative request (no polling, no retries)
  * detect block / consent / CAPTCHA pages and surface them as failures
  * extract only patent-domain URLs (matching the allow-list)
  * NEVER attempt to circumvent anti-bot protections
  * NEVER claim API-verified or exhaustive coverage
  * disable the provider entirely with ``AURA_GOOGLE_WEB_PATENT_ENABLED=0``

When the request fails or is blocked, the response is
``PatentSearchResponse(success=False, failure_reason=..., warnings=[...])``
so the factory can fall back to SearXNG (or, with explicit consent, mock).
"""
from __future__ import annotations

import os
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from .base import (
    PatentSearchProvider,
    PatentSearchResponse,
    PatentSearchResult,
    PatentSearchWarning,
)


# Conservative defaults — single request, modest result cap.
_DEFAULT_TIMEOUT = 15
_DEFAULT_LIMIT = 10
_DEFAULT_UA = (
    "Mozilla/5.0 (compatible; AURA-Stage1-Patent-Web/1.0; "
    "+https://github.com/anthropics/claude-code)"
)

# Domains we consider patent-relevant.  Hits outside this set are dropped
# (mirrors PATENT_WEB_ALLOWED_DOMAINS but stays self-contained so the
# provider can be re-used outside the patent_web pipeline).
_PATENT_HOSTS = (
    "patents.google.com",
    "patentscope.wipo.int",
    "uspto.gov",
    "worldwide.espacenet.com",
)

# Signals that Google blocked us or wants a CAPTCHA / consent click.
_BLOCK_MARKERS = (
    "/sorry/",
    "id=\"captcha-form\"",
    "g-recaptcha",
    "unusual traffic from your computer",
    "consent.google.com",
    "before you continue to google",
)

# Signals that Google served a "JavaScript required" stub page instead of
# a real SERP.  In 2024-2026 Google increasingly requires JS execution to
# render results — they serve a tiny noscript-redirect page to clients
# that don't run JS (including our requests-based provider).  This is
# NOT a CAPTCHA / consent block; it's a soft-deprecation of the static
# HTML SERP.  We treat it as a structured failure so the factory's
# fallback chain triggers.
_JS_REQUIRED_MARKERS = (
    "/httpservice/retry/enablejs",
    "please click <a href=\"/httpservice/retry/enablejs",
    "noscript><style>table,div,span,p{display:none}",
)

# Compiled patterns
# Match ``href="..."`` only when it's a real HTML attribute — preceded by
# whitespace or ``<``.  Without the prefix anchor, the same regex would
# also match ``data-href="..."`` and ``xlink:href="..."``, which on
# modern Google SERPs would steal the URL away from pass 2's whole-body
# fallback.
_HREF_RE = re.compile(r'(?:^|[\s<])href="([^"]+)"', re.IGNORECASE)
# Google wraps outbound links in /url?q=<actual>&...
_GOOG_REDIRECT_PREFIX = "/url?"
# Fallback: find absolute URLs anywhere in the body (data-attributes,
# embedded JSON, encoded strings).  Google's modern SERP often puts the
# result URLs in JS payloads rather than direct <a href>.  This catches
# them by scanning for patent-host substrings.
_ABS_URL_RE = re.compile(
    r"https?://(?:[a-zA-Z0-9\-]+\.)*"
    r"(?:patents\.google\.com|patentscope\.wipo\.int|uspto\.gov|"
    r"worldwide\.espacenet\.com)"
    r"/[^\"'<>\s\\)]+",
    re.IGNORECASE,
)


class GoogleWebNoKeyPatentSearchProvider(PatentSearchProvider):
    """Best-effort Google SERP scraper for patent discovery (no API key)."""

    name = "google_web_no_key"

    def __init__(
        self,
        *,
        timeout: int = _DEFAULT_TIMEOUT,
        user_agent: str | None = None,
        endpoint: str = "https://www.google.com/search",
        http_session: Any | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent or _DEFAULT_UA
        self.endpoint = endpoint
        # Allow tests to inject a fake requests-like object.
        self._http = http_session
        # Master enable flag — defaults to True so the provider is available
        # but can be killed via env without touching code.
        if enabled is None:
            enabled = os.getenv(
                "AURA_GOOGLE_WEB_PATENT_ENABLED", "1",
            ).strip() != "0"
        self.enabled = bool(enabled)

    # ------------------------------------------------------------------ search
    def search(
        self,
        query: str,
        *,
        limit: int = _DEFAULT_LIMIT,
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
                "Google-oriented no-key discovery is disabled "
                "(AURA_GOOGLE_WEB_PATENT_ENABLED=0).",
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
                    "The `requests` library is required for Google-oriented "
                    "no-key discovery but is not installed.",
                )
                return resp

        params = {"q": q, "num": str(max(1, min(int(limit), 20))), "hl": "en"}
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
        }

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
                f"Google-oriented no-key request raised: "
                f"{exc.__class__.__name__}: {exc}",
            )
            return resp

        status = getattr(r, "status_code", 0)
        body = getattr(r, "text", "") or ""
        body_lower = body.lower()

        # --- Blocked / CAPTCHA / consent detection ------------------------
        if status in (403, 429) or any(m in body_lower for m in _BLOCK_MARKERS):
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=False,
                failure_reason="blocked_or_captcha",
            )
            resp.add_warning(
                "google_blocked",
                "Google-oriented no-key discovery was unavailable or blocked "
                "(consent / CAPTCHA / rate-limit page detected). "
                "AURA does NOT bypass anti-bot protections — falling back.",
            )
            resp.raw_metadata["http_status"] = status
            return resp

        # --- "JavaScript required" stub page detection --------------------
        # Google now ships a tiny noscript-redirect HTML to non-JS clients
        # in many regions.  Treat as a structured failure (NOT silent zero
        # results) so the fallback chain takes over.
        if any(m in body_lower for m in _JS_REQUIRED_MARKERS):
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=False,
                failure_reason="js_required",
            )
            resp.add_warning(
                "google_js_required",
                "Google served a JavaScript-required stub page; the static "
                "HTML SERP is no longer available to scraping clients. "
                "AURA does NOT execute Google's JS — falling back to "
                "another provider (DuckDuckGo HTML / SearXNG).",
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
                f"Google returned HTTP {status} with "
                f"{len(body)}-byte body; cannot extract results.",
            )
            resp.raw_metadata["http_status"] = status
            return resp

        # --- Extraction ----------------------------------------------------
        try:
            urls = _extract_patent_urls(body, target_domain=target_domain)
        except Exception as exc:
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=False,
                failure_reason=f"parse_error: {exc.__class__.__name__}",
            )
            resp.add_warning(
                "parse_error",
                f"Failed to parse Google SERP HTML: "
                f"{exc.__class__.__name__}: {exc}",
            )
            return resp

        if not urls:
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=True,
                results=[],
            )
            resp.add_warning(
                "zero_results",
                "Google SERP returned no patent-domain URLs for this query.",
            )
            resp.raw_metadata["http_status"] = status
            return resp

        results: list[PatentSearchResult] = []
        for idx, url in enumerate(urls[:limit], start=1):
            host = _host_of(url)
            results.append(PatentSearchResult(
                title=_title_for_url(body, url) or url,
                url=url,
                snippet=None,            # SERP snippets are fragile to parse
                rank=idx,
                source_provider="google_web_no_key",
                target_domain=host,
                raw_metadata={"discovered_via": "google_serp_html"},
            ))

        resp = PatentSearchResponse(
            query=q,
            provider=self.name,
            results=results,
            success=True,
            not_api_verified=True,
            non_exhaustive=True,
            raw_metadata={"http_status": status, "backend": "google_web_no_key"},
        )
        resp.add_warning(
            "best_effort_disclaimer",
            "Best-effort public-web Google discovery — NOT the official "
            "Google API, NOT exhaustive, prone to blocking and HTML drift.",
        )
        return resp


# ---------------------------------------------------------------------------
# HTML extraction helpers
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


def _unwrap_google_redirect(href: str) -> str:
    """Google wraps outbound links as /url?q=<actual>&... — unwrap to <actual>."""
    if not href.startswith(_GOOG_REDIRECT_PREFIX):
        return href
    try:
        parsed = urlparse(href)
        q = parse_qs(parsed.query)
        actual = q.get("q") or q.get("url")
        if actual:
            return unquote(actual[0])
    except Exception:
        pass
    return href


def _extract_patent_urls(body: str, *, target_domain: str | None) -> list[str]:
    """Return ordered, deduped patent-host URLs from a Google SERP body.

    Two passes:
      1. Classic ``<a href="...">`` extraction (with /url?q= unwrapping).
         Catches the static-HTML SERP variant.
      2. Whole-body scan for absolute patent-host URLs.  Catches modern
         JS-driven SERPs where the result URLs live in data attributes,
         embedded JSON, or encoded strings rather than direct hrefs.
    Both passes feed the same dedup so we never emit the same URL twice.
    """
    seen: set[str] = set()
    out: list[str] = []

    def _accept(url: str) -> None:
        # Strip trailing JSON / URL escape artifacts that can leak in when
        # URLs are embedded in JS payloads ("...US10593881B2&foo=bar").
        url = url.split("\\u")[0].rstrip(".,;")
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
        out.append(url)

    # Pass 1: classic hrefs (with /url?q=… unwrap).  Works on the static
    # SERP variant that Google still serves to some User-Agents.
    for raw_href in _HREF_RE.findall(body):
        if not raw_href:
            continue
        href = unescape(raw_href.strip())
        if href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        url = _unwrap_google_redirect(href)
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        _accept(url)

    # Pass 2 (fallback): when pass 1 found nothing, scan the entire body
    # for absolute patent-host URLs.  This catches modern JS-driven
    # SERPs where the result URLs live in data attributes or embedded
    # JSON rather than in classic ``<a href>`` tags.
    #
    # Google's SERP HTML JSON-escapes the URLs inside script blocks:
    #   forward slashes  →  \/
    #   ampersands       →  &
    #   unicode quotes   →  ' / "
    # So we make a decoded copy that unescapes those, then run the
    # absolute-URL regex on it.  We strip Google's tracking-param tails
    # (``&sa=U``, ``&ved=…``, ``&usg=…``) so otherwise-identical URLs
    # collapse.
    if not out:
        decoded = _json_unescape(unescape(body))
        for match in _ABS_URL_RE.finditer(decoded):
            url = _strip_google_tracking_params(match.group(0))
            _accept(url)

    return out


def _json_unescape(s: str) -> str:
    """Undo the JSON-style escapes Google's SERP uses inside script blocks.

    Concretely: ``\\/`` → ``/``, ``\\u0026`` → ``&``, ``\\u0027`` → ``'``,
    ``\\u0022`` → ``"``.  Done with simple string replacement; we never
    eval or parse JSON, so the operation is safe on partial / malformed
    payloads.
    """
    return (
        s
        .replace("\\u002F", "/").replace("\\u002f", "/")
        .replace("\\/", "/")
        .replace("\\u0026", "&")
        .replace("\\u0027", "'")
        .replace("\\u0022", '"')
        .replace("\\x2f", "/").replace("\\x2F", "/")
        .replace("\\x26", "&")
    )


def _strip_google_tracking_params(url: str) -> str:
    """Remove Google-tracker query params (``&sa=U``, ``&ved=…``, ``&usg=…``)
    that get appended when the URL is embedded in a Google SERP payload."""
    return re.sub(
        r"&(?:amp;)?(?:sa|ved|usg|source|rct|opi)=[^&\"'<>\s\\)]*",
        "", url,
    )


def _title_for_url(body: str, url: str) -> str | None:
    """Best-effort: pull the anchor text of the nearest <a href="...url..."> tag.

    Returns ``None`` when nothing reasonable is found — the caller falls
    back to the URL itself.  We intentionally keep this dumb — over-fitting
    to Google's HTML structure would defeat the resilience goal.
    """
    try:
        # Find the FIRST occurrence of the URL inside an href, then read the
        # next ``</a>``-bounded text.  Encoded variants (& vs &amp;) covered
        # by also trying the escaped form.
        anchor_re = re.compile(
            r'<a[^>]+href="([^"]*?' + re.escape(url[:60]) + r'[^"]*)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        m = anchor_re.search(body)
        if not m:
            return None
        text = re.sub(r"<[^>]+>", "", m.group(2))
        text = unescape(text).strip()
        if 3 <= len(text) <= 240:
            return text
    except Exception:
        return None
    return None
