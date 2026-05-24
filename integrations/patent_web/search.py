"""
Patent-targeted web search via AURA's SearXNG (or any compatible provider).

This module is a thin adapter on top of a ``SearchProvider``.  It:
- runs each planned query through the provider,
- tags each result with the originating query,
- filters results to the configured allow-list of patent-hosting domains,
- returns ``PatentSearchHit`` objects and a list of structured
  ``PatentSourceError`` records distinguishing zero-results vs provider-fail
  vs malformed-response.

It does NOT fetch any pages — that's ``page_fetcher.fetch_patent_page()``.
"""

from __future__ import annotations

from urllib.parse import urlparse

import config

from .schemas import PatentSearchHit, PatentSearchQuery, PatentSource, PatentSourceError

# Static map from a KNOWN patent host → PatentSource enum.
#
# Classification behaviour (see ``_classify_host``):
#   * A URL whose host is NOT on the configured allow-list
#     (``PATENT_WEB_ALLOWED_DOMAINS``) returns ``None`` → the hit is dropped.
#   * A URL whose host IS on the allow-list but is NOT one of the three
#     known hosts below is classified as ``PatentSource.other`` (it is NOT
#     dropped here) — though the per-host extractor only understands these
#     three, so an "other" host yields limited structured metadata.
HOST_SOURCE_MAP: dict[str, PatentSource] = {
    "patents.google.com": PatentSource.google_patents,
    "patentscope.wipo.int": PatentSource.wipo,
    "uspto.gov": PatentSource.uspto,
}


def _classify_host(url: str, allowed_domains: list[str]) -> PatentSource | None:
    """Return the PatentSource for *url* if its host is on the allow-list."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    if not host:
        return None
    for allowed in allowed_domains:
        a = allowed.strip().lower()
        if not a:
            continue
        if host == a or host.endswith("." + a):
            return HOST_SOURCE_MAP.get(a, PatentSource.other)
    return None


def search_patents(
    queries: list[PatentSearchQuery],
    provider,
    *,
    max_results_per_query: int | None = None,
    max_total_hits: int | None = None,
    allowed_domains: list[str] | None = None,
) -> tuple[list[PatentSearchHit], list[PatentSourceError], dict]:
    """Run each query through *provider*; return ``(hits, errors, provenance)``.

    Errors are NOT exceptions — every issue (provider raising, zero results,
    malformed response) becomes a ``PatentSourceError`` so the caller can
    surface it on the run-level diagnostics.

    Provider compatibility
    ----------------------
    Supports BOTH provider shapes:

      * NEW: ``PatentSearchProvider`` from ``search_providers/`` —
        ``.search(query, limit=..., target_domain=...)`` returning a
        ``PatentSearchResponse`` (preferred).
      * OLD: legacy ``SearXNGSearchProvider`` /
        ``MockSearchProvider`` from ``qwen_evolver.deep_research`` —
        ``.search(query, max_results=...)`` returning a plain list.

    The shape is detected by inspecting the call signature.  This keeps
    older tests and the deep-research orchestrator working unchanged.

    ``provenance`` is the aggregated retrieval-provenance dict for the run.
    """
    per_q = max_results_per_query or config.PATENT_WEB_MAX_RESULTS_PER_QUERY
    total = max_total_hits or (config.PATENT_WEB_MAX_PAGES_TO_FETCH * 2)
    allow = allowed_domains or config.PATENT_WEB_ALLOWED_DOMAINS
    is_new_provider = _looks_like_new_provider(provider)

    hits: list[PatentSearchHit] = []
    errors: list[PatentSourceError] = []
    seen_urls: set[str] = set()
    raw_name = getattr(provider, "name", "")
    safe_name = raw_name if isinstance(raw_name, str) and raw_name else ""
    # ``primary_provider`` is set at init from the wrapper.
    # ``provider_used`` starts EMPTY and is filled only by the child
    # response that actually produced results.  If we initialised it to
    # ``safe_name`` here, a FallbackProvider wrapper (whose .name is
    # literally "fallback") would lock that string in and _merge_provenance
    # would never overwrite it — leaving the saved draft saying
    # "Provider used: fallback" instead of the actual winning child.
    provenance: dict = {
        "primary_provider": safe_name,
        "provider_used": "",
        "not_api_verified": True,
        "non_exhaustive": True,
        "fallback_used": False,
        "fallback_from": None,
        "warnings": [],
    }

    for q in queries:
        try:
            if is_new_provider:
                response = provider.search(
                    q.query, limit=per_q,
                    target_domain=(q.target_domains[0] if q.target_domains else None),
                )
                results, response_meta = _adapt_new_provider_response(
                    response, errors=errors, query=q.query,
                )
                if response_meta:
                    _merge_provenance(provenance, response_meta)
            else:
                raw = provider.search(q.query, max_results=per_q)
                results = _adapt_legacy_provider_results(
                    raw, errors=errors, query=q.query,
                )
        except Exception as exc:
            errors.append(PatentSourceError(
                stage="search", query=q.query,
                kind="provider_exception", detail=str(exc),
            ))
            continue

        if results is None:
            continue   # already recorded as malformed_response

        if not results:
            errors.append(PatentSourceError(
                stage="search", query=q.query,
                kind="zero_results", detail="provider returned empty list",
            ))
            continue

        query_hit_count = 0
        for sr in results:
            try:
                url = (getattr(sr, "url", "") or "").strip()
            except Exception:
                errors.append(PatentSourceError(
                    stage="search", query=q.query,
                    kind="malformed_response",
                    detail="result missing url attribute",
                ))
                continue
            if not url or url in seen_urls:
                continue
            source = _classify_host(url, allow)
            if source is None:
                continue
            seen_urls.add(url)
            hits.append(PatentSearchHit(
                title=getattr(sr, "title", "") or "",
                url=url,
                snippet=getattr(sr, "snippet", "") or "",
                source_domain=source,
                rank=getattr(sr, "rank", 0) or 0,
                query=q.query,
                provider=(
                    getattr(sr, "source_provider", "")
                    or getattr(sr, "provider", "")
                    or ""
                ),
            ))
            query_hit_count += 1
            if len(hits) >= total:
                return hits, errors, provenance

        if query_hit_count == 0:
            errors.append(PatentSourceError(
                stage="search", query=q.query,
                kind="zero_results_after_filter",
                detail="all results were off-domain or duplicates",
            ))

    return hits, errors, provenance


# ---------------------------------------------------------------------------
# Provider-shape detection + adapters
# ---------------------------------------------------------------------------

def _looks_like_new_provider(provider) -> bool:
    """True if *provider* is a ``PatentSearchProvider`` from search_providers/.

    NOTE: we deliberately do NOT use ``isinstance(provider, PatentSearchProvider)``
    here even though ``PatentSearchProvider`` is ``@runtime_checkable``.  A
    runtime-checkable Protocol only inspects attribute presence, and a
    ``MagicMock`` has every attribute — so the isinstance check would
    misclassify legacy test providers as new-shape.  We instead check
    against the concrete classes in this subsystem, plus the factory's
    fallback wrapper.
    """
    if not hasattr(provider, "search"):
        return False
    try:
        from .search_providers.duckduckgo_html_provider import (
            DuckDuckGoHtmlPatentSearchProvider,
        )
        from .search_providers.factory import _FallbackProvider
        from .search_providers.google_web_provider import (
            GoogleWebNoKeyPatentSearchProvider,
        )
        from .search_providers.mock_provider import MockPatentSearchProvider
        from .search_providers.searxng_provider import (
            SearXNGPatentSearchProvider,
        )
        for cls in (
            MockPatentSearchProvider,
            SearXNGPatentSearchProvider,
            GoogleWebNoKeyPatentSearchProvider,
            DuckDuckGoHtmlPatentSearchProvider,
            _FallbackProvider,
        ):
            if isinstance(provider, cls):
                return True
    except Exception:
        pass
    # Last resort: inspect the signature for the new-shape ``limit`` kwarg.
    # MagicMock's signature is ``(*args, **kwargs)`` which does NOT name
    # ``limit`` as a parameter, so MagicMock-based tests correctly fall
    # through to the legacy path.
    try:
        import inspect
        sig = inspect.signature(provider.search)
        params = sig.parameters
        return "limit" in params and "max_results" not in params
    except (TypeError, ValueError):
        return False


def _adapt_new_provider_response(
    response, *, errors: list, query: str,
):
    """Convert a ``PatentSearchResponse`` into the iteration loop's shape.

    Returns ``(results_iterable, provenance_dict)``.  Records search
    errors for failed responses and emits warnings into the provenance.
    """
    if response is None:
        errors.append(PatentSourceError(
            stage="search", query=query,
            kind="malformed_response", detail="provider returned None",
        ))
        return None, None

    raw_provider = getattr(response, "provider", "")
    safe_provider = raw_provider if isinstance(raw_provider, str) else ""
    meta: dict = {
        "provider_used": safe_provider,
        "fallback_used": bool(getattr(response, "fallback_used", False)),
        "fallback_from": getattr(response, "fallback_from", None),
        "warnings": [
            {"code": w.code, "message": w.message}
            for w in (getattr(response, "warnings", []) or [])
        ],
        "not_api_verified": bool(getattr(response, "not_api_verified", True)),
        "non_exhaustive": bool(getattr(response, "non_exhaustive", True)),
    }

    if not getattr(response, "success", False):
        reason = getattr(response, "failure_reason", "") or "unknown"
        errors.append(PatentSourceError(
            stage="search", query=query,
            kind=str(reason)[:60],
            detail="; ".join(
                f"{w.code}: {w.message}" for w in (response.warnings or [])
            ) or reason,
        ))
        return [], meta

    return list(response.results or []), meta


def _adapt_legacy_provider_results(raw, *, errors: list, query: str):
    """Adapt the old-shape list[SearchResult] return value."""
    if raw is None:
        errors.append(PatentSourceError(
            stage="search", query=query,
            kind="malformed_response", detail="provider returned None",
        ))
        return None
    return raw


def _merge_provenance(into: dict, more: dict) -> None:
    """Merge per-query response metadata into the run-level provenance."""
    # Provider name should reflect whichever child actually produced
    # results.  ALWAYS overwrite if the new value names a real backend
    # (i.e. is non-empty and not the literal "fallback" wrapper name).
    new_used = more.get("provider_used", "")
    if new_used and new_used != "fallback":
        into["provider_used"] = new_used
    elif new_used and not into.get("provider_used"):
        into["provider_used"] = new_used
    if more.get("fallback_used"):
        into["fallback_used"] = True
        if more.get("fallback_from") and not into.get("fallback_from"):
            into["fallback_from"] = more["fallback_from"]
    # Deduplicate warnings by code+message so repeated queries don't bloat.
    existing = {(w["code"], w["message"]) for w in into["warnings"]}
    for w in more.get("warnings", []):
        key = (w.get("code", ""), w.get("message", ""))
        if key in existing:
            continue
        existing.add(key)
        into["warnings"].append(w)
