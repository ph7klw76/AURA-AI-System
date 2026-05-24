"""
Deterministic mock patent-search provider for tests and explicit fallback.

The mock provider exists for two reasons only:

  1. Hermetic unit tests that cannot touch the live web.
  2. Explicit ``mock`` fallback configuration where the user has
     consciously accepted that all results are synthetic.

It MUST:

  * always set ``not_api_verified=True`` and ``non_exhaustive=True``
  * mark every result with ``source_provider="mock"`` so downstream code
    can never confuse it for a real provider
  * carry a loud warning so reports show "MOCK results — synthetic"
  * never be silently selected without being asked for
"""
from __future__ import annotations

from urllib.parse import quote_plus

from .base import (
    PatentSearchProvider,
    PatentSearchResponse,
    PatentSearchResult,
    PatentSearchWarning,
)

_DEFAULT_DOMAINS = (
    "patents.google.com",
    "patentscope.wipo.int",
    "uspto.gov",
)


class MockPatentSearchProvider(PatentSearchProvider):
    """Synthetic patent-oriented hits.  Never real data."""

    name = "mock"

    def __init__(self, *, default_n: int = 3) -> None:
        self.default_n = max(1, int(default_n))

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        target_domain: str | None = None,
    ) -> PatentSearchResponse:
        q = (query or "").strip()
        cap = max(1, min(int(limit), self.default_n))
        domains = (target_domain,) if target_domain else _DEFAULT_DOMAINS

        results: list[PatentSearchResult] = []
        for i in range(cap):
            host = domains[i % len(domains)]
            slug = quote_plus(q or "topic")
            results.append(PatentSearchResult(
                title=f"MOCK patent result {i + 1} — {q or 'topic'}",
                url=f"https://{host}/mock-result/{i + 1}?q={slug}",
                snippet=(
                    "Synthetic snippet for offline testing. "
                    "This entry is NOT real patent data."
                ),
                rank=i + 1,
                source_provider="mock",
                target_domain=host,
                raw_metadata={"synthetic": True},
            ))

        resp = PatentSearchResponse(
            query=q,
            provider=self.name,
            results=results,
            success=True,
            not_api_verified=True,
            non_exhaustive=True,
            warnings=[PatentSearchWarning(
                code="mock_provider",
                message=(
                    "MOCK patent-search provider — results are SYNTHETIC. "
                    "No real web search was performed."
                ),
            )],
            raw_metadata={"backend": "mock", "synthetic": True},
        )
        return resp
