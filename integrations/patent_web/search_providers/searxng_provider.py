"""
SearXNG-backed patent-search provider.

Wraps the existing ``qwen_evolver.deep_research.search_providers.SearXNGSearchProvider``
so we have ONE SearXNG implementation in the repo (no duplication of the
botdetection headers / JSON-format quirks), but expose results through the
provider-neutral :class:`PatentSearchResponse` interface.

Honesty
-------
SearXNG is meta-search over public web engines.  Results are NOT API
verified by any patent office and the coverage is NOT exhaustive — both
flags are set accordingly on every response.
"""
from __future__ import annotations

from typing import Any

from .base import (
    PatentSearchProvider,
    PatentSearchResponse,
    PatentSearchResult,
    PatentSearchWarning,
)


class SearXNGPatentSearchProvider(PatentSearchProvider):
    """Adapter that exposes a SearXNG backend via the patent-search protocol."""

    name = "searxng"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: int = 20,
        backend: Any | None = None,
    ) -> None:
        """``backend`` lets tests inject a stub; production callers leave it
        ``None`` so the existing SearXNGSearchProvider is constructed."""
        if backend is not None:
            self._backend = backend
        else:
            # Local import — keeps the patent_web package importable even if
            # the deep_research subsystem is being refactored.
            from qwen_evolver.deep_research.search_providers import (
                SearXNGSearchProvider as _LegacyBackend,
            )
            self._backend = _LegacyBackend(base_url=base_url, timeout=timeout)
        self._base_url = base_url

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
            resp.add_warning("empty_query", "SearXNG was called with an empty query.")
            return resp

        results = self._run_query(q, int(limit), target_domain)

        # Site-filter fallback.  In 2025-2026 Google increasingly rejects
        # ``site:DOMAIN`` queries from SearXNG instances, and DDG/Bing/Brave
        # either don't honour ``site:`` or return generic non-patent
        # results.  When a ``site:``-restricted query yields zero hits OR
        # zero patent-host hits, retry WITHOUT the ``site:`` prefix and
        # let the upstream patent-host filter pick the relevant URLs.
        # This recovers most queries on real-world SearXNG deployments.
        if isinstance(results, PatentSearchResponse):
            # _run_query returned an early failure-response.
            return results

        patent_count = _count_patent_host_results(results)
        if q.lower().startswith("site:") and patent_count == 0:
            # Strip "site:DOMAIN " prefix and retry.
            stripped = _strip_site_prefix(q)
            if stripped and stripped != q:
                retry = self._run_query(stripped, int(limit), target_domain)
                if isinstance(retry, list) and _count_patent_host_results(retry):
                    fallback_resp = PatentSearchResponse(
                        query=q,                  # log the ORIGINAL query
                        provider=self.name,
                        results=retry,
                        success=True,
                        not_api_verified=True,
                        non_exhaustive=True,
                        raw_metadata={
                            "backend": "searxng",
                            "base_url": self._base_url or "",
                            "site_filter_dropped": True,
                            "fallback_query": stripped,
                        },
                    )
                    fallback_resp.add_warning(
                        "site_filter_dropped",
                        f"site:-restricted query returned no patent-host "
                        f"results from SearXNG; retried as plain keyword "
                        f"query ({stripped!r}) and let the upstream "
                        "patent-host filter select relevant URLs.",
                    )
                    return fallback_resp

        resp = PatentSearchResponse(
            query=q,
            provider=self.name,
            results=results,
            success=True,
            not_api_verified=True,
            non_exhaustive=True,
            raw_metadata={"backend": "searxng", "base_url": self._base_url or ""},
        )
        if not results:
            resp.add_warning(
                "zero_results",
                "SearXNG returned no usable results for this query.",
            )
        return resp

    # ---------------------------------------------------------------- helpers
    def _run_query(
        self, q: str, limit: int, target_domain: str | None,
    ) -> "list[PatentSearchResult] | PatentSearchResponse":
        """Execute one query.  Returns a list on success, or an early
        ``PatentSearchResponse`` on protocol-level failure."""
        try:
            raw = self._backend.search(q, max_results=limit)
        except Exception as exc:
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=False,
                failure_reason=f"provider_exception: {exc.__class__.__name__}",
            )
            resp.add_warning(
                "provider_exception",
                f"SearXNG provider raised: {exc.__class__.__name__}: {exc}",
            )
            return resp

        if raw is None:
            resp = PatentSearchResponse(
                query=q, provider=self.name, success=False,
                failure_reason="malformed_response",
            )
            resp.add_warning(
                "malformed_response",
                "SearXNG returned None instead of a result list.",
            )
            return resp

        results: list[PatentSearchResult] = []
        for sr in raw:
            url = (getattr(sr, "url", "") or "").strip()
            if not url:
                continue
            results.append(PatentSearchResult(
                title=getattr(sr, "title", "") or "",
                url=url,
                snippet=getattr(sr, "snippet", "") or "",
                rank=getattr(sr, "rank", 0) or 0,
                source_provider=getattr(sr, "provider", "") or "searxng",
                target_domain=target_domain,
                raw_metadata={"engine": getattr(sr, "provider", "")},
            ))
        return results


# ---------------------------------------------------------------------------
# Module-level helpers (no state)
# ---------------------------------------------------------------------------

_PATENT_HOST_SUBSTRINGS = (
    "patents.google.com",
    "patentscope.wipo.int",
    "uspto.gov",
    "worldwide.espacenet.com",
)


def _count_patent_host_results(results: list) -> int:
    n = 0
    for r in results:
        url = getattr(r, "url", "") or ""
        if any(h in url for h in _PATENT_HOST_SUBSTRINGS):
            n += 1
    return n


def _strip_site_prefix(q: str) -> str:
    """``site:DOMAIN keywords...`` -> ``keywords...``."""
    parts = q.split(None, 1)
    if not parts or not parts[0].lower().startswith("site:"):
        return q
    return parts[1].strip() if len(parts) > 1 else ""
