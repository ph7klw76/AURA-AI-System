"""Schemas for outbound-MCP calls and normalized external evidence."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

Confidence = Literal["low", "medium", "high"]

# The complete normalized result-type vocabulary (ExternalMcpEvidenceRecord
# .result_type is kept a plain ``str`` so a new external tool degrades to
# ``unknown`` rather than raising — but classification only emits these).
RESULT_TYPES: tuple[str, ...] = (
    "raw_search",
    "research_summary",
    "external_report",
    "document_rag",
    "market_signal",
    "competitor_signal",
    "repository_context",
    "issue_context",
    "pull_request_context",
    "unknown",
)


class ExternalMcpCallRequest(BaseModel):
    """A single outbound MCP tool-call request (validated before dispatch)."""
    server_name: str
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    session_id: str | None = None
    timeout_seconds: int | None = None


@dataclass
class ExternalMcpCallResult:
    """Low-level result of a single outbound MCP tool call.

    Always returned (never raised) by the client so the orchestrator can never
    be crashed by an external server.
    """
    ok: bool
    server: str
    tool: str
    raw_result: Any = None
    error_type: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0
    mock_mode: bool = False
    started_at: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "server": self.server,
            "tool": self.tool,
            "raw_result": self.raw_result,
            "error_type": self.error_type,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "mock_mode": self.mock_mode,
            "started_at": self.started_at,
        }


class ExternalMcpEvidenceRecord(BaseModel):
    """Normalized AURA evidence record derived from an external MCP result.

    INVARIANT: external MCP output is NEVER an authority.  ``verified_by_aura``
    is False until AURA's Scientific Verifier reviews it (Phase 3), and
    ``confidence_hint`` is capped at "medium" before that review.
    """
    provider: str
    tool_name: str
    query: str
    result_type: str
    content: dict | str = ""
    sources: list[str] = Field(default_factory=list)
    confidence_hint: Confidence = "low"
    retrieved_at: str = ""
    mock_mode: bool = False
    verified_by_aura: bool = False
    limitations: list[str] = Field(default_factory=list)
    raw_result_hash: str = ""
    session_id: str | None = None
