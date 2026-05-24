"""Normalize external MCP results into AURA evidence records.

INVARIANTS (do not weaken):
  * All external MCP evidence starts UNVERIFIED (``verified_by_aura=False``).
  * Confidence is capped at "medium" before AURA verification — never "high".
  * Market/competition signals are NOT scientific evidence.
  * Mock/synthetic outputs force "low" confidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .audit import hash_obj
from .schemas import Confidence, ExternalMcpCallResult, ExternalMcpEvidenceRecord

# tool → result_type mapping per server.
_RESULT_TYPE_MAP: dict[tuple[str, str], str] = {
    ("local_deep_research", "search"): "raw_search",
    ("local_deep_research", "quick_research"): "research_summary",
    ("local_deep_research", "detailed_research"): "research_summary",
    ("local_deep_research", "generate_report"): "external_report",
    ("local_deep_research", "analyze_documents"): "document_rag",
    ("idea_reality", "idea_check"): "market_signal",
}

# GitHub read tools → context result_type (prefix-based, since the GitHub MCP
# server exposes many read tools).  Issue/PR tools take precedence over the
# generic repository_context fallback.
_GITHUB_ISSUE_TOOL_HINTS: tuple[str, ...] = ("issue",)
_GITHUB_PR_TOOL_HINTS: tuple[str, ...] = ("pull_request", "pull_requests", "pr_")

# Result types that are explicitly NON-scientific (market/competition).
_NON_SCIENTIFIC_TYPES: frozenset[str] = frozenset({"market_signal", "competitor_signal"})

# Result types that are repository/code context (NOT scientific evidence).
_REPO_CONTEXT_TYPES: frozenset[str] = frozenset({
    "repository_context", "issue_context", "pull_request_context",
})

# Base (pre-verification) confidence per result type — capped at medium.
_BASE_CONFIDENCE: dict[str, Confidence] = {
    "raw_search": "low",
    "research_summary": "medium",
    "external_report": "medium",
    "document_rag": "medium",
    "market_signal": "low",
    "competitor_signal": "low",
    "repository_context": "medium",
    "issue_context": "medium",
    "pull_request_context": "medium",
    "scientific_tool_result": "medium",
    "hypothesis_signal": "low",
    "metadata": "low",
    "unknown": "low",
}

_VERIFY_LIMITATION = (
    "Unverified external MCP output — must pass AURA's Scientific Verifier "
    "before influencing any final draft."
)


def _cap_confidence(level: Confidence) -> Confidence:
    """Never allow 'high' before AURA verification."""
    return "medium" if level == "high" else level


def classify_result_type(server: str, tool: str, raw: Any) -> str:
    """Determine the normalized result_type, refining market vs competitor."""
    base = _RESULT_TYPE_MAP.get((server, tool))
    if base == "market_signal" and isinstance(raw, dict):
        # idea-reality may emphasise competitors; reflect that honestly.
        keys = {str(k).lower() for k in raw.keys()}
        text = " ".join(str(v).lower() for v in raw.values() if isinstance(v, str))
        if "competitor" in " ".join(keys) or "competitor" in text:
            return "competitor_signal"
    if base is not None:
        return base
    # ToolUniverse: any admitted (read-only) scientific tool.
    if server == "tooluniverse":
        return "scientific_tool_result"
    # open-coscientist: AI-generated research hypotheses (speculative ideation).
    if server == "open_coscientist":
        return "hypothesis_signal"
    # GitHub read tools → repository/issue/PR context.
    if server == "github":
        t = (tool or "").lower()
        if any(h in t for h in _GITHUB_PR_TOOL_HINTS):
            return "pull_request_context"
        if any(h in t for h in _GITHUB_ISSUE_TOOL_HINTS):
            return "issue_context"
        return "repository_context"
    # Read-only metadata tools.
    if tool in ("list_search_engines", "list_strategies", "get_configuration"):
        return "metadata"
    return "unknown"


def _extract_sources(raw: Any) -> list[str]:
    sources: list[str] = []
    if isinstance(raw, dict):
        for key in ("sources", "urls", "links", "citations", "references"):
            val = raw.get(key)
            if isinstance(val, list):
                for v in val:
                    if isinstance(v, str) and v.strip():
                        sources.append(v.strip())
                    elif isinstance(v, dict):
                        url = v.get("url") or v.get("link") or v.get("href")
                        if isinstance(url, str) and url.strip():
                            sources.append(url.strip())
    # De-dup, preserve order, cap.
    seen: set[str] = set()
    out: list[str] = []
    for s in sources:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out[:50]


def normalize_result(
    call_result: ExternalMcpCallResult,
    *,
    query: str,
    session_id: str | None = None,
) -> ExternalMcpEvidenceRecord:
    """Convert a successful (or failed) MCP call into a normalized record.

    A failed call still yields a record (empty content, low confidence) so the
    audit/evidence trail is consistent.
    """
    server = call_result.server
    tool = call_result.tool
    raw = call_result.raw_result
    result_type = classify_result_type(server, tool, raw)

    limitations = [_VERIFY_LIMITATION]
    if result_type in _NON_SCIENTIFIC_TYPES:
        limitations.append(
            "Market/competition signal — NOT scientific evidence; do not cite "
            "as scientific support."
        )
    if result_type in _REPO_CONTEXT_TYPES:
        limitations.append(
            "Repository/code context — supports code/repo claims only, NOT "
            "scientific claims."
        )
    if result_type == "scientific_tool_result":
        limitations.append(
            "External scientific-tool output (ToolUniverse) — UNVERIFIED; a "
            "database/API lookup, NOT a definitive scientific finding. Must be "
            "checked against primary sources by the Scientific Verifier."
        )
    if result_type == "hypothesis_signal":
        limitations.append(
            "AI-generated research hypotheses (open-coscientist) — SPECULATIVE "
            "ideation, NOT validated science and NOT evidence. Use only as "
            "candidate directions; must pass AURA's Scientific Verifier."
        )

    # Confidence: base by type, force low on mock/failure, cap at medium.
    confidence: Confidence = _BASE_CONFIDENCE.get(result_type, "low")
    if call_result.mock_mode:
        confidence = "low"
        limitations.append("Mock/synthetic external output — confidence forced to low.")
    if not call_result.ok:
        confidence = "low"
        limitations.append(
            f"External call failed ({call_result.error_type}); no evidence retrieved."
        )
    confidence = _cap_confidence(confidence)

    content: dict | str
    if isinstance(raw, (dict, str)):
        content = raw
    elif raw is None:
        content = ""
    else:
        content = str(raw)

    return ExternalMcpEvidenceRecord(
        provider=server,
        tool_name=tool,
        query=query,
        result_type=result_type,
        content=content,
        sources=_extract_sources(raw),
        confidence_hint=confidence,
        retrieved_at=call_result.started_at or datetime.now(timezone.utc).isoformat(),
        mock_mode=bool(call_result.mock_mode),
        verified_by_aura=False,  # ALWAYS false in Phase 2
        limitations=limitations,
        raw_result_hash=hash_obj(raw),
        session_id=session_id,
    )
