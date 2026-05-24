"""
Provider-neutral patent-search interface + data models.

Every concrete provider returns the same :class:`PatentSearchResponse`
regardless of backend.  This is the only contract the Patent Intelligence
Agent depends on, so backends can be swapped without rewriting the
research workflow.

Design notes
------------
* Dataclasses (not Pydantic) for the retrieval layer — these are
  internal value objects, not schema-validated user-facing artefacts.
  The Pydantic ``PatentEvidenceRecord`` downstream is where strict
  validation lives.
* Every response carries explicit ``not_api_verified`` and
  ``non_exhaustive`` flags so downstream code cannot mistake a
  best-effort web result for an authoritative API record.
* Failures are STRUCTURED, never raised at the provider boundary.
  ``success=False`` + ``failure_reason`` + ``warnings`` is the
  contract; pipelines must never see an uncaught provider exception.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass
class PatentSearchResult:
    """A single search hit before any patent-domain filtering or fetching."""
    title: str = ""
    url: str = ""
    snippet: str | None = None
    rank: int | None = None
    source_provider: str = ""
    target_domain: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PatentSearchWarning:
    """One structured warning emitted during a search call.

    ``code`` is a short machine-stable identifier (e.g. ``"google_blocked"``,
    ``"zero_results"``, ``"provider_exception"``).  ``message`` is a
    user-facing sentence safe to surface verbatim in reports.
    """
    code: str = ""
    message: str = ""


@dataclass
class PatentSearchResponse:
    """Provider-neutral search outcome for ONE query.

    Always populated, even on failure — callers inspect ``success``,
    ``failure_reason``, and ``warnings`` to decide what to do.
    """
    query: str
    provider: str
    results: list[PatentSearchResult] = field(default_factory=list)
    success: bool = True
    retrieved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Honesty flags — surfaced verbatim into the report's provenance section
    # so users can tell the difference between best-effort web discovery and
    # an API-verified record.
    not_api_verified: bool = True
    non_exhaustive: bool = True
    fallback_used: bool = False
    fallback_from: str | None = None      # set by the factory when wrapping
    failure_reason: str | None = None
    warnings: list[PatentSearchWarning] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ utils
    def add_warning(self, code: str, message: str) -> None:
        self.warnings.append(PatentSearchWarning(code=code, message=message))


class PatentSearchProviderError(Exception):
    """Reserved for unrecoverable provider-construction errors.

    Providers must NOT raise this during ``search()`` — query-time
    failures are returned as ``PatentSearchResponse(success=False, ...)``.
    This is only for "the configured provider name is unknown" or "this
    provider cannot be constructed at all" situations the factory hits.
    """


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class PatentSearchProvider(Protocol):
    """The single interface the Patent Intelligence Agent depends on.

    Implementations MUST:
      * Never raise from ``search()`` — return a structured failure response.
      * Set ``provider`` to a stable short string (matches factory keys).
      * Honour ``limit`` as a soft cap on results.
      * Populate ``not_api_verified`` truthfully (False only if the backend
        is a verified patent-database API — none of the built-in providers
        qualify).
      * Populate ``non_exhaustive=True`` for any web-discovery backend.
    """

    name: str

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        target_domain: str | None = None,
    ) -> PatentSearchResponse: ...
