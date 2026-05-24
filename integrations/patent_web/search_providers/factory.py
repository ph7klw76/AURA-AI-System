"""
Provider selection + fallback wrapping for patent search.

Resolves a configured provider name into a concrete
:class:`PatentSearchProvider`, and (optionally) wraps it in a fallback
chain so a primary failure (e.g. Google blocked) transparently demotes
to SearXNG, with explicit warnings every step of the way.

Configuration sources (in precedence order):

  1. Explicit ``PatentSearchConfig`` passed to ``build_patent_search_provider``.
  2. ``config.get_patent_search_settings()`` — the single source of truth
     that normalizes ``AURA_PATENT_SEARCH_*`` (and legacy
     ``PATENT_WEB_*``) env vars.  This factory does NOT re-parse the
     environment; it only maps provider *names* onto ``SUPPORTED_PROVIDERS``.

The factory is the *only* place that knows about provider names.  Agents
and pipelines only see a ``PatentSearchProvider`` instance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .base import (
    PatentSearchProvider,
    PatentSearchProviderError,
    PatentSearchResponse,
    PatentSearchWarning,
)


# Provider keys accepted in configuration.
PROVIDER_GOOGLE = "google_web_no_key"
PROVIDER_DDG = "duckduckgo_html"
PROVIDER_SEARXNG = "searxng"
PROVIDER_MOCK = "mock"
PROVIDER_AUTO = "auto"

SUPPORTED_PROVIDERS = frozenset({
    PROVIDER_GOOGLE, PROVIDER_DDG, PROVIDER_SEARXNG, PROVIDER_MOCK, PROVIDER_AUTO,
})


@dataclass
class PatentSearchConfig:
    """Runtime configuration for the patent search subsystem."""
    provider: str = PROVIDER_AUTO
    allow_fallback: bool = True
    fallback_chain: tuple[str, ...] = (PROVIDER_SEARXNG,)
    max_results: int = 10
    # Mock fallback is opt-in: we never silently substitute synthetic
    # results unless the user explicitly asked for it.
    allow_mock_fallback: bool = False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def resolve_patent_search_config() -> PatentSearchConfig:
    """Build a config object from the centralized config provider.

    Phase 3 (goal F): the single source of truth for these env vars is
    ``config.get_patent_search_settings()``.  This factory NO LONGER parses
    the environment independently — it consumes the normalized settings and
    only maps provider *names* onto its own ``SUPPORTED_PROVIDERS`` keys.
    """
    import config

    settings = config.get_patent_search_settings()

    provider = (settings.get("provider") or PROVIDER_AUTO).strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        provider = PROVIDER_AUTO

    # Validate the configured fallback chain against the provider keys this
    # factory actually understands.
    fallback_chain = tuple(
        p.strip().lower() for p in str(settings.get("fallback_chain", "")).split(",")
        if p.strip().lower() in SUPPORTED_PROVIDERS
        and p.strip().lower() != PROVIDER_AUTO
    )
    if not fallback_chain:
        fallback_chain = (PROVIDER_DDG, PROVIDER_SEARXNG)

    return PatentSearchConfig(
        provider=provider,
        allow_fallback=bool(settings.get("allow_fallback", True)),
        fallback_chain=fallback_chain,
        max_results=max(1, int(settings.get("max_results", 10))),
        allow_mock_fallback=bool(settings.get("allow_mock_fallback", False)),
    )


def build_patent_search_provider(
    config: PatentSearchConfig | None = None,
    *,
    on_status: Callable[[str], None] | None = None,
) -> PatentSearchProvider:
    """Resolve config → provider (wrapped in fallback if configured).

    Tests can pass an explicit ``PatentSearchConfig``.  Production callers
    typically leave it ``None`` so env vars drive selection.

    Never raises for ordinary config — unknown providers degrade to the
    safest available (mock, only if the user explicitly opted in).
    """
    cfg = config or resolve_patent_search_config()
    say = on_status or (lambda _m: None)
    primary_name = cfg.provider
    if primary_name == PROVIDER_AUTO:
        primary_name = _auto_pick_primary()

    primary = _construct(primary_name, on_status=say)

    if not cfg.allow_fallback:
        return primary

    chain: list[PatentSearchProvider] = [primary]
    for name in cfg.fallback_chain:
        if name == primary_name:
            continue
        if name == PROVIDER_MOCK and not cfg.allow_mock_fallback:
            continue
        try:
            chain.append(_construct(name, on_status=say))
        except PatentSearchProviderError as exc:
            say(f"patent_search: skipping fallback {name!r}: {exc}")
    # Mock as last-resort ONLY if user opted in.
    if cfg.allow_mock_fallback and not any(
        getattr(p, "name", "") == PROVIDER_MOCK for p in chain
    ):
        chain.append(_construct(PROVIDER_MOCK, on_status=say))

    if len(chain) == 1:
        return primary
    return _FallbackProvider(chain)


# Alias matching the spec name.
resolve_patent_search_provider = build_patent_search_provider


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _auto_pick_primary() -> str:
    """``auto`` picks SearXNG when enabled (preserves prior behaviour),
    otherwise DuckDuckGo HTML — the most reliable no-key path in 2025-2026
    after Google deprecated their static SERP for non-JS clients.

    Google-oriented no-key discovery remains AVAILABLE as a primary when
    explicitly configured (``AURA_PATENT_SEARCH_PROVIDER=google_web_no_key``),
    but it is no longer the auto-pick default — too many regions now get
    the noscript-redirect stub instead of real results.
    """
    try:
        import config as _cfg
        if getattr(_cfg, "SEARXNG_ENABLED", False):
            return PROVIDER_SEARXNG
    except Exception:
        pass
    return PROVIDER_DDG


def _construct(
    name: str, *, on_status: Callable[[str], None] | None = None,
) -> PatentSearchProvider:
    name = (name or "").strip().lower()
    if name == PROVIDER_MOCK:
        from .mock_provider import MockPatentSearchProvider
        return MockPatentSearchProvider()
    if name == PROVIDER_SEARXNG:
        from .searxng_provider import SearXNGPatentSearchProvider
        try:
            import config as _cfg
            return SearXNGPatentSearchProvider(
                base_url=getattr(_cfg, "SEARXNG_URL", None),
                timeout=int(getattr(_cfg, "SEARXNG_TIMEOUT_SECONDS", 20)),
            )
        except Exception:
            return SearXNGPatentSearchProvider()
    if name == PROVIDER_GOOGLE:
        from .google_web_provider import GoogleWebNoKeyPatentSearchProvider
        return GoogleWebNoKeyPatentSearchProvider()
    if name == PROVIDER_DDG:
        from .duckduckgo_html_provider import DuckDuckGoHtmlPatentSearchProvider
        return DuckDuckGoHtmlPatentSearchProvider()
    raise PatentSearchProviderError(f"Unknown patent search provider: {name!r}")


class _FallbackProvider(PatentSearchProvider):
    """Provider wrapper that tries each backend in order until one succeeds.

    Failed attempts are NOT silent — every fallback step is annotated
    with the originating provider name + reason, and the final response
    records ``fallback_used=True`` plus the primary that was tried first.
    """

    name = "fallback"

    def __init__(self, chain: list[PatentSearchProvider]) -> None:
        if not chain:
            raise PatentSearchProviderError("fallback chain cannot be empty")
        self._chain = chain
        self.primary_name = getattr(chain[0], "name", "unknown")

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        target_domain: str | None = None,
    ) -> PatentSearchResponse:
        accumulated_warnings: list[PatentSearchWarning] = []
        last_failure: PatentSearchResponse | None = None
        primary_attempted = self.primary_name

        for idx, provider in enumerate(self._chain):
            resp = provider.search(
                query, limit=limit, target_domain=target_domain,
            )
            if idx > 0:
                resp.fallback_used = True
                resp.fallback_from = primary_attempted
                resp.warnings = (
                    accumulated_warnings + list(resp.warnings)
                )
            if resp.success and resp.results:
                # Ensure ``provider`` reflects the CHILD that actually
                # produced results, not the wrapper's "fallback" name —
                # otherwise the report's provenance section reads
                # ``Provider used: fallback`` which is unhelpful.
                if not resp.provider or resp.provider == self.name:
                    resp.provider = getattr(provider, "name", resp.provider)
                return resp
            # Not successful — collect its warnings and keep trying.
            for w in resp.warnings:
                accumulated_warnings.append(PatentSearchWarning(
                    code=f"{provider.name}:{w.code}",
                    message=w.message,
                ))
            accumulated_warnings.append(PatentSearchWarning(
                code=f"{provider.name}:fallback_step",
                message=(
                    f"Provider {provider.name!r} returned "
                    f"success={resp.success} results={len(resp.results)} "
                    f"reason={resp.failure_reason or '(none)'}; "
                    "trying next provider in fallback chain."
                ),
            ))
            last_failure = resp

        # All providers failed.
        final = last_failure or PatentSearchResponse(
            query=query, provider="fallback", success=False,
            failure_reason="no_providers_in_chain",
        )
        final.success = False
        final.fallback_used = True
        final.fallback_from = primary_attempted
        final.failure_reason = (
            final.failure_reason
            or "all_providers_failed_or_returned_no_results"
        )
        final.warnings = list(accumulated_warnings)
        final.add_warning(
            "fallback_exhausted",
            (
                "All configured patent-search providers failed or returned "
                "no usable results.  Patent reconnaissance confidence remains low."
            ),
        )
        return final
