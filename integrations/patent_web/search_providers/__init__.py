"""
Provider-neutral patent-search subsystem.

Why this package exists
-----------------------
Patent search and the Patent Intelligence Agent are intentionally decoupled
so a search backend can be swapped (SearXNG ↔ Google-oriented public web
discovery ↔ mock ↔ future API providers) without rewriting the research
workflow.  Every provider returns the same :class:`PatentSearchResponse`
shape and preserves:

  * provider name
  * query used
  * retrieval timestamp
  * result provenance
  * whether results are API verified
  * whether results are non-exhaustive
  * whether a fallback was used
  * structured warnings and failure reasons

Honesty contract
----------------
NONE of these providers claim API-verified, exhaustive, or freedom-to-
operate-quality coverage.  All Stage 1 caveats from the surrounding
patent_web integration remain in force; this package is the retrieval
layer only.

Public surface
--------------
    PatentSearchProvider     (Protocol)
    PatentSearchResult       (dataclass)
    PatentSearchResponse     (dataclass)
    PatentSearchWarning      (dataclass)
    PatentSearchProviderError
    build_patent_search_provider(config) -> PatentSearchProvider
    MockPatentSearchProvider
    SearXNGPatentSearchProvider
    GoogleWebNoKeyPatentSearchProvider
"""
from __future__ import annotations

from .base import (
    PatentSearchProvider,
    PatentSearchProviderError,
    PatentSearchResponse,
    PatentSearchResult,
    PatentSearchWarning,
)
from .duckduckgo_html_provider import DuckDuckGoHtmlPatentSearchProvider
from .factory import (
    PROVIDER_AUTO,
    PROVIDER_DDG,
    PROVIDER_GOOGLE,
    PROVIDER_MOCK,
    PROVIDER_SEARXNG,
    SUPPORTED_PROVIDERS,
    PatentSearchConfig,
    build_patent_search_provider,
    resolve_patent_search_config,
    resolve_patent_search_provider,
)
from .google_web_provider import GoogleWebNoKeyPatentSearchProvider
from .mock_provider import MockPatentSearchProvider
from .searxng_provider import SearXNGPatentSearchProvider

__all__ = [
    "PatentSearchProvider",
    "PatentSearchProviderError",
    "PatentSearchResponse",
    "PatentSearchResult",
    "PatentSearchWarning",
    "PatentSearchConfig",
    "build_patent_search_provider",
    "resolve_patent_search_provider",
    "resolve_patent_search_config",
    "MockPatentSearchProvider",
    "SearXNGPatentSearchProvider",
    "GoogleWebNoKeyPatentSearchProvider",
    "DuckDuckGoHtmlPatentSearchProvider",
    "PROVIDER_AUTO",
    "PROVIDER_GOOGLE",
    "PROVIDER_DDG",
    "PROVIDER_MOCK",
    "PROVIDER_SEARXNG",
    "SUPPORTED_PROVIDERS",
]
