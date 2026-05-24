"""
End-to-end Stage 1 patent reconnaissance pipeline.

Flow
----
1. Resolve a SearXNG provider (or, if PATENT_WEB_ALLOW_MOCK_FALLBACK=1, mock).
2. Plan ``PatentSearchQuery`` objects from the user topic.
3. ``search_patents()``  → ``PatentSearchHit[]`` + ``PatentSourceError[]``.
4. For each hit: ``fetch_patent_page()`` → ``extract_from_page()`` → record.
5. Build ``PatentEvidenceRecord``s (web_extracted/not_api_verified flags).
6. Dedupe with the PUB/APP/URL/title+assignee priority.
7. Return a ``PatentWebSearchRun`` with all counters, errors, and flags.

The pipeline never raises on individual failures — every problem becomes a
``PatentSourceError`` entry on the returned run.
"""

from __future__ import annotations

from typing import Callable

import config

from .dedup import dedupe_evidence_records
from .evidence_builder import build_evidence_records
from .extractor import extract_from_page
from .page_fetcher import FetchResult, fetch_patent_page
from .query_planner import plan_patent_queries
from .schemas import (
    PatentSearchHit, PatentSearchQuery, PatentSourceError, PatentWebSearchRun,
)
from .search import search_patents


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------

def _resolve_provider(
    on_status: Callable[[str], None] | None = None,
) -> tuple[object, str, bool, list[str]]:
    """Return ``(provider, label, used_real, warnings)``.

    Delegates to the provider-neutral
    :func:`integrations.patent_web.search_providers.build_patent_search_provider`,
    which honours ``AURA_PATENT_SEARCH_PROVIDER`` /
    ``AURA_PATENT_SEARCH_ALLOW_FALLBACK`` and supports the new
    ``google_web_no_key`` backend.  Falls back to the legacy SearXNG path
    when the configured primary fails.
    """
    say = on_status or (lambda _: None)
    warnings: list[str] = []
    from .search_providers import (
        PROVIDER_MOCK,
        build_patent_search_provider,
        resolve_patent_search_config,
    )

    # If SearXNG is configured and enabled, give it a runtime readiness
    # check the same way the legacy resolver did — but DON'T fail closed
    # here; the factory's fallback chain will demote to another provider
    # if SearXNG is unhealthy.
    cfg = resolve_patent_search_config()
    if cfg.provider in ("searxng", "auto") and config.SEARXNG_ENABLED:
        try:
            from core.searxng_runtime import ensure_searxng_ready
            status = ensure_searxng_ready(
                timeout_s=float(config.SEARXNG_TIMEOUT_SECONDS),
                on_status=say,
            )
            if not status.get("ok"):
                warnings.append(
                    f"SearXNG unavailable: {status.get('message', 'unknown')}"
                )
        except Exception as exc:
            warnings.append(f"SearXNG runtime check error: {exc}")

    # Mock fallback is OPT-IN ONLY via the NEW
    # ``AURA_PATENT_SEARCH_ALLOW_MOCK_FALLBACK=1`` env var (already
    # parsed into ``cfg.allow_mock_fallback`` by
    # ``resolve_patent_search_config``).  We deliberately do NOT honour
    # the legacy ``PATENT_WEB_ALLOW_MOCK_FALLBACK`` env var here anymore:
    # its old default of "1" caused mock to silently win the fallback
    # chain even when SearXNG was healthy, producing draft reports full
    # of ``patents.google.com/mock-result/N`` URLs that the patent-host
    # filter happily accepted as "real".  The legacy flag is preserved
    # only for the in-process unit tests that monkey-patch it directly.

    provider = build_patent_search_provider(cfg, on_status=say)
    label = getattr(provider, "name", cfg.provider) or cfg.provider
    used_real = label not in (PROVIDER_MOCK, "mock")
    if not used_real:
        warnings.append(
            "Mock fallback used — results are SYNTHETIC and do not "
            "represent real patent reconnaissance."
        )
    return provider, label, used_real, warnings


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_patent_web_search(
    topic: str,
    *,
    use_llm_for_queries: bool = True,
    on_status: Callable[[str], None] | None = None,
    provider_override=None,
) -> PatentWebSearchRun:
    """Run the full Stage 1 patent reconnaissance pipeline.

    Always returns a ``PatentWebSearchRun``.  Errors at any stage are
    collected in ``run.source_errors``; the run-level diagnostic flags are:
        * ``mock_mode_used``  — provider was mock
        * ``partial_results`` — at least one stage produced an error

    Parameters
    ----------
    topic
        User-supplied technology phrase.
    use_llm_for_queries
        If True, the planner asks the LLM for synonyms.
    on_status
        Optional status callback used by interactive shells.
    provider_override
        If not None, used directly instead of resolving SearXNG/Mock.
        Tests pass a MagicMock here.
    """
    say = on_status or (lambda _: None)
    warnings: list[str] = []
    errors: list[PatentSourceError] = []

    # Default provenance — overwritten by ``search_patents`` once we run.
    provenance: dict = {
        "primary_provider": "", "provider_used": "",
        "not_api_verified": True, "non_exhaustive": True,
        "fallback_used": False, "fallback_from": None, "warnings": [],
    }

    # --- 1. Provider ------------------------------------------------------
    if provider_override is not None:
        provider = provider_override
        # Guard against MagicMock(): ``mock.name`` returns a Mock attribute,
        # not a string — would fail Pydantic validation on PatentWebSearchRun.
        raw_name = getattr(provider, "name", "")
        label = raw_name if isinstance(raw_name, str) and raw_name else "override"
        used_real = label not in ("mock",)
    else:
        provider, label, used_real, provider_warnings = _resolve_provider(on_status=say)
        warnings.extend(provider_warnings)
        if provider is None:
            # Refused to run (e.g., mock-fallback disabled).
            provenance["provider_used"] = label
            provenance["primary_provider"] = label
            return PatentWebSearchRun(
                topic=topic,
                provider_used=label,
                mock_mode_used=False,
                partial_results=True,
                limitations=warnings + [
                    "Pipeline did not execute — no usable search provider.",
                ],
                retrieval_provenance=provenance,
            )

    # --- 2. Queries -------------------------------------------------------
    try:
        queries: list[PatentSearchQuery] = plan_patent_queries(
            topic, use_llm=use_llm_for_queries,
        )
    except Exception as exc:
        errors.append(PatentSourceError(
            stage="plan", kind="planner_exception", detail=str(exc),
        ))
        queries = []

    if not queries:
        provenance["provider_used"] = label
        provenance["primary_provider"] = label
        return PatentWebSearchRun(
            topic=topic,
            queries=queries,
            source_errors=errors,
            provider_used=label,
            mock_mode_used=not used_real,
            partial_results=True,
            limitations=warnings + ["No queries generated for the given topic."],
            retrieval_provenance=provenance,
        )

    # --- 3. Search --------------------------------------------------------
    hits, search_errors, provenance = search_patents(queries, provider)
    errors.extend(search_errors)
    say(f"patent_web: {len(hits)} hits across {len(queries)} queries")
    # If the search layer ran the new provider abstraction, the final
    # provider-name (post-fallback) may differ from the label resolved at
    # construction time.  Honour the runtime label so the report is honest.
    runtime_provider = provenance.get("provider_used") if provenance else ""
    if runtime_provider:
        label = runtime_provider
        used_real = label not in ("mock",)

    # --- 4. Fetch + extract ---------------------------------------------
    extractions = []
    hits_by_url: dict[str, PatentSearchHit] = {}
    fetch_cap = config.PATENT_WEB_MAX_PAGES_TO_FETCH

    for hit in hits[:fetch_cap]:
        hits_by_url[hit.url] = hit
        if not used_real:
            # Mock mode: synthesise an empty FetchResult so we still build an
            # extraction object (with fetch_status="skipped"), but we do NOT
            # claim real data.
            fr = FetchResult(status="skipped",
                             notes=["mock mode — no real fetch attempted"])
            extractions.append(extract_from_page(hit, fr))
            continue

        fr = fetch_patent_page(hit.url)
        if not fr.ok:
            errors.append(PatentSourceError(
                stage="fetch", url=hit.url, query=hit.query,
                kind=fr.status,
                detail="; ".join(fr.notes) or f"fetch failed with status {fr.status}",
            ))
        extractions.append(extract_from_page(hit, fr))

    # --- 5. Evidence records ---------------------------------------------
    evidence = build_evidence_records(extractions, hits_by_url)

    # --- 6. Dedup --------------------------------------------------------
    deduped, dropped = dedupe_evidence_records(evidence)
    if dropped:
        warnings.append(f"deduplicated {dropped} record(s) by pub/app/url/title-assignee")

    # --- 7. Run aggregate ------------------------------------------------
    partial = bool(errors) or (used_real and not deduped)
    limitations = list(warnings)
    if not used_real:
        limitations.append(
            "Mock fallback used — output is SYNTHETIC and not real reconnaissance."
        )

    # Finalise the provenance dict so downstream consumers (agent, report)
    # have one consistent place to read retrieval metadata from.
    if not provenance:
        provenance = {}
    provenance.setdefault("primary_provider", label)
    # ``provider_used`` is the runtime winner.  Use whatever search.py
    # captured from per-query responses; only fall back to the wrapper
    # name if NOTHING set it (e.g. zero queries).
    runtime_winner = provenance.get("provider_used") or label
    provenance["provider_used"] = runtime_winner
    label = runtime_winner
    # mock_mode_used must reflect the runtime winner, not the wrapper.
    used_real = runtime_winner not in ("mock", "")
    provenance.setdefault("not_api_verified", True)
    provenance.setdefault("non_exhaustive", True)
    provenance.setdefault("fallback_used", False)
    provenance.setdefault("fallback_from", None)
    provenance.setdefault("warnings", [])

    return PatentWebSearchRun(
        topic=topic,
        queries=queries,
        search_hits=hits,
        extractions=extractions,
        deduplicated_records=deduped,
        source_errors=errors,
        provider_used=label,
        mock_mode_used=not used_real,
        partial_results=partial,
        limitations=limitations,
        retrieval_provenance=provenance,
    )
