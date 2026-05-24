"""
Search provider abstraction + implementations.

Providers
---------
MockSearchProvider      — synthetic results for testing / offline mode
SearXNGSearchProvider   — self-hosted local instance (requires running SearXNG
                          with JSON output enabled in settings.yml)

Tavily and Brave Search are intentionally NOT supported.  AURA's web-search
layer is SearXNG-only by design — it keeps queries local, free, and
provider-agnostic via SearXNG's meta-search.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from .schemas import SearchResult


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        ...


class MockSearchProvider(SearchProvider):
    """Synthetic provider for offline testing. Results are NOT real web search."""

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        results = []
        for i in range(min(max_results, 3)):
            results.append(SearchResult(
                title=f"Mock result {i+1} for {query}",
                url=f"http://example.com/mock/{i}",
                snippet="This is a mock snippet.",
                provider="mock",
                rank=i + 1,
            ))
        return results


# Single module-level requests import.  Patching _req_lib in tests controls
# HTTP behaviour for SearXNGSearchProvider.
try:
    import requests as _req_lib
    _REQUESTS_AVAILABLE = True
except ImportError:
    _req_lib = None  # type: ignore[assignment]
    _REQUESTS_AVAILABLE = False

# Required by SearXNG's botdetection when accessed directly without a proxy.
_SEARXNG_HEADERS = {
    "X-Forwarded-For": "127.0.0.1",
    "X-Real-IP": "127.0.0.1",
}


class SearXNGSearchProvider(SearchProvider):
    """Search via a self-hosted SearXNG instance.

    Requires SearXNG to be running and its JSON output format to be enabled
    in settings.yml (search.formats: [html, json]).  Use core.searxng_runtime
    to verify / start SearXNG before constructing this provider.
    """

    def __init__(self, base_url: str | None = None, timeout: int = 20) -> None:
        self.base_url = (
            base_url or os.environ.get("SEARXNG_URL", "http://localhost:8080")
        ).rstrip("/")
        self.timeout = timeout

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not _REQUESTS_AVAILABLE:
            return []

        endpoint = f"{self.base_url}/search"
        params = {"q": query, "format": "json", "pageno": 1}
        try:
            resp = _req_lib.get(  # type: ignore[union-attr]
                endpoint, params=params,
                headers=_SEARXNG_HEADERS, timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        results: list[SearchResult] = []
        for idx, item in enumerate(data.get("results", [])[:max_results]):
            engine = item.get("engine", "unknown")
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", item.get("snippet", "")),
                provider=f"searxng/{engine}",
                rank=idx + 1,
            ))
        return results
