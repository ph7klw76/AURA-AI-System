"""Phase 3 — conservative hooks that wire the outbound MCP gateway into
selected AURA workflows.

Design: thin and OFF by default.  Each ``gather_*`` helper returns
``{"records": [...], "warnings": [...]}`` where records are normalized
``ExternalMcpEvidenceRecord`` dicts (always ``verified_by_aura=False``).
Agents attach these to their output dict AFTER ``model_dump()`` so no AURA
schema changes are needed; the orchestrator then surfaces them to the
Scientific Verifier and the final ``external_mcp_evidence`` summary.

External MCP evidence NEVER becomes final AURA output without passing through
the verifier + persistence gates that already exist.
"""
from __future__ import annotations

import sys
from typing import Any, Callable

from config import env_bool

from . import external_deep_research, external_idea_check, external_research_search
from .config import load_config

# Research-like Scout modes that may benefit from external research evidence.
_RESEARCH_MODES: frozenset[str] = frozenset({
    "literature_scan", "gap_analysis", "grant_opportunity", "deep_research",
})

# Standard user-facing warnings emitted whenever external MCP evidence is used.
STANDARD_WARNINGS: tuple[str, ...] = (
    "External MCP evidence was used as supplementary context.",
    "External MCP summaries were not treated as primary literature unless "
    "source-level evidence was available.",
    "Commercialization signals are not scientific validation.",
    "Patent reconnaissance remains non-legal, non-exhaustive Stage-1 analysis.",
)


# ---------------------------------------------------------------------------
# Feature flags (all OFF by default except REQUIRE_VERIFIER)
# ---------------------------------------------------------------------------

def _outbound_enabled() -> bool:
    return load_config().outbound_enabled


def use_in_research_scout() -> bool:
    # Honour the canonical per-server flag (AURA_MCP_USE_LOCAL_DEEP_RESEARCH)
    # OR the legacy agent-location flag, for backward compatibility.
    return _outbound_enabled() and (
        env_bool("AURA_MCP_USE_LOCAL_DEEP_RESEARCH", False)
        or env_bool("AURA_MCP_USE_IN_RESEARCH_SCOUT", False)
    )


def use_in_founder() -> bool:
    return _outbound_enabled() and (
        env_bool("AURA_MCP_USE_IDEA_REALITY", False)
        or env_bool("AURA_MCP_USE_IN_FOUNDER", False)
    )


def use_in_patent() -> bool:
    return _outbound_enabled() and (
        env_bool("AURA_MCP_USE_LOCAL_DEEP_RESEARCH", False)
        or env_bool("AURA_MCP_USE_IN_PATENT", False)
    )


def use_in_github() -> bool:
    """READ-ONLY GitHub repo-maintenance is available when outbound is on and
    AURA_MCP_USE_GITHUB=1."""
    return _outbound_enabled() and env_bool("AURA_MCP_USE_GITHUB", False)


def use_in_tooluniverse() -> bool:
    """READ-ONLY ToolUniverse scientific tools are available when outbound is
    on and AURA_MCP_USE_TOOLUNIVERSE=1."""
    return _outbound_enabled() and env_bool("AURA_MCP_USE_TOOLUNIVERSE", False)


def use_in_open_coscientist() -> bool:
    """open-coscientist hypothesis generation is available when outbound is on
    and AURA_MCP_USE_OPEN_COSCIENTIST=1."""
    return _outbound_enabled() and env_bool("AURA_MCP_USE_OPEN_COSCIENTIST", False)


def require_verifier() -> bool:
    """When True (default), external MCP evidence MUST pass AURA's verifier
    before influencing final drafts.  The orchestrator's persistence gate
    already fails closed on a missing/non-affirmative verdict.
    """
    return env_bool("AURA_MCP_REQUIRE_VERIFIER", True)


# ---------------------------------------------------------------------------
# Human approval gate (default ON)
# ---------------------------------------------------------------------------
# Whenever an AGENT is about to call an external MCP server, a human must
# approve it with y/N first.  Fail-safe: with no interactive terminal (e.g.
# the STDIO MCP server, or a piped/CI run) the call is DENIED unless the
# operator explicitly opts out via AURA_MCP_APPROVAL_ASSUME_YES=1.

# Signature: (server, tool, query, session_id) -> bool | (bool, reason)
ApprovalCallback = Callable[[str, str, str, "str | None"], "bool | tuple[bool, str]"]
_APPROVAL_CALLBACK: ApprovalCallback | None = None


def require_approval_enabled() -> bool:
    """Human approval is required for agent-triggered external MCP calls
    unless AURA_MCP_REQUIRE_APPROVAL=0 (default: required)."""
    return env_bool("AURA_MCP_REQUIRE_APPROVAL", True)


def set_approval_callback(callback: ApprovalCallback | None) -> None:
    """Override the approval prompt (e.g. a GUI dialog, or tests)."""
    global _APPROVAL_CALLBACK
    _APPROVAL_CALLBACK = callback


def reset_approval_callback() -> None:
    set_approval_callback(None)


def _default_approval(server: str, tool: str, query: str, session_id: str | None) -> tuple[bool, str]:
    """Interactive y/N prompt on stderr; fail-safe DENY when non-interactive."""
    if env_bool("AURA_MCP_APPROVAL_ASSUME_YES", False):
        return True, "auto-approved (AURA_MCP_APPROVAL_ASSUME_YES=1)"
    stdin = getattr(sys, "stdin", None)
    if stdin is None or not getattr(stdin, "isatty", lambda: False)():
        # No human at the keyboard (STDIO MCP server, pipe, CI) → deny.
        return False, ("no interactive terminal to obtain human approval "
                       "(fail-safe deny; set AURA_MCP_APPROVAL_ASSUME_YES=1 to bypass)")
    msg = (
        f"\n[AURA] An agent wants to call the EXTERNAL MCP server "
        f"'{server}' (tool '{tool}').\n"
        f"        Query: {str(query)[:120]}\n"
        f"        External output is UNVERIFIED supplementary evidence and is "
        f"still reviewed by the Scientific Verifier.\n"
        f"        Approve this external call? [y/N]: "
    )
    try:
        print(msg, file=sys.stderr, end="", flush=True)
        ans = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False, "approval prompt aborted (treated as decline)"
    if ans in ("y", "yes"):
        return True, "approved by user"
    return False, "declined by user"


def request_approval(server: str, tool: str, query: str, session_id: str | None) -> tuple[bool, str]:
    """Return (approved, reason).  Logs the decision to the MCP audit log."""
    if not require_approval_enabled():
        decision, reason = True, "approval not required (AURA_MCP_REQUIRE_APPROVAL=0)"
    else:
        cb = _APPROVAL_CALLBACK or _default_approval
        try:
            result = cb(server, tool, query, session_id)
        except Exception as exc:  # noqa: BLE001 — never crash the agent on prompt error
            decision, reason = False, f"approval callback error (fail-safe deny): {exc}"
        else:
            if isinstance(result, tuple):
                decision, reason = bool(result[0]), str(result[1])
            else:
                decision, reason = bool(result), ("approved" if result else "declined")

    # Audit the human decision (no raw secrets; arguments hashed).
    try:
        from . import audit as _audit
        rec = _audit.build_audit_record(
            session_id=session_id, server=server, tool=tool,
            arguments={"query": query}, raw_result=None,
            ok=decision, error_type=None if decision else "approval_declined",
            duration_seconds=0.0,
            normalized_evidence_type="approval_decision",
            verified_by_aura=False,
        )
        rec["approval_decision"] = decision
        rec["approval_reason"] = reason
        _audit.log_call(rec)
    except Exception:  # noqa: BLE001 — auditing must never break the gate
        pass

    return decision, reason


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _research_like(query: str) -> bool:
    """Cheap heuristic: a non-trivial, prose-like query worth searching."""
    q = (query or "").strip()
    return len(q) >= 8


def _empty() -> dict[str, list]:
    return {"records": [], "warnings": []}


def _absorb(adapter_out: dict, records: list, warnings: list) -> None:
    """Append a successful adapter result's normalized record + warnings."""
    if not isinstance(adapter_out, dict):
        return
    if adapter_out.get("ok") and isinstance(adapter_out.get("evidence"), dict):
        records.append(adapter_out["evidence"])
        for w in adapter_out.get("warnings", []) or []:
            if w not in warnings:
                warnings.append(w)
    else:
        for e in adapter_out.get("errors", []) or []:
            warnings.append(f"External MCP call failed: {e}")


# ---------------------------------------------------------------------------
# Per-workflow gather functions
# ---------------------------------------------------------------------------

def gather_research_evidence(
    query: str, session_id: str | None, *, mode: str,
) -> dict[str, list]:
    """Research Scout: optional Local Deep Research evidence.

    Only runs when AURA_MCP_USE_IN_RESEARCH_SCOUT=1 (and outbound enabled), the
    Scout mode is research-like, and the query looks research-like.  Returns
    UNVERIFIED external evidence records to be APPENDED to the Scout pack
    (never substituting scholarly source search).
    """
    if not use_in_research_scout():
        return _empty()
    if mode not in _RESEARCH_MODES:
        return _empty()
    if not _research_like(query):
        return _empty()

    # Human approval gate (y/N) — required before any agent-triggered call.
    approved, reason = request_approval("local_deep_research", "search", query, session_id)
    if not approved:
        return {"records": [], "warnings": [
            f"External MCP 'local_deep_research' NOT used — {reason}."
        ]}

    records: list[dict] = []
    warnings: list[str] = []

    _absorb(external_research_search(query, session_id=session_id), records, warnings)
    # Deeper modes also pull a research summary (still supplementary).
    if mode in ("deep_research", "grant_opportunity"):
        depth = "detailed" if mode == "deep_research" else "quick"
        _absorb(external_deep_research(query, depth=depth, session_id=session_id), records, warnings)

    return {"records": records, "warnings": warnings}


def gather_idea_signal(idea_text: str, session_id: str | None) -> dict[str, list]:
    """Founder Innovation: optional idea-reality market/competition signal.

    NOT scientific evidence; NOT legal/financial/investment/patent advice.
    """
    if not use_in_founder():
        return _empty()
    if not _research_like(idea_text):
        return _empty()
    approved, reason = request_approval("idea_reality", "idea_check", idea_text, session_id)
    if not approved:
        return {"records": [], "warnings": [
            f"External MCP 'idea_reality' NOT used — {reason}."
        ]}
    records: list[dict] = []
    warnings: list[str] = []
    _absorb(external_idea_check(idea_text, session_id=session_id), records, warnings)
    return {"records": records, "warnings": warnings}


def gather_patent_context(query: str, session_id: str | None) -> dict[str, list]:
    """Patent Intelligence: optional supplementary Local Deep Research search.

    Stays Stage-1 supplementary context.  idea-reality competitor signals are
    deliberately NOT used here (they are not patent prior art).
    """
    if not use_in_patent():
        return _empty()
    if not _research_like(query):
        return _empty()
    approved, reason = request_approval("local_deep_research", "search", query, session_id)
    if not approved:
        return {"records": [], "warnings": [
            f"External MCP 'local_deep_research' NOT used — {reason}."
        ]}
    records: list[dict] = []
    warnings: list[str] = []
    _absorb(external_research_search(query, session_id=session_id), records, warnings)
    return {"records": records, "warnings": warnings}


def gather_github_maintenance(
    tool: str, arguments: dict, session_id: str | None, *, summary: str | None = None,
) -> dict[str, list]:
    """Repository-maintenance: READ-ONLY GitHub MCP, approval-gated.

    For AI repo maintenance (issues, PRs, CI failures, history, branch
    comparison, code review).  Every call is read-only (policy blocks writes),
    requires y/N human approval, and is normalized to repo/issue/PR context
    (NOT scientific evidence).
    """
    from . import external_github  # local import to avoid cycle at module load

    if not use_in_github():
        return _empty()
    approved, reason = request_approval(
        "github", tool, summary or f"{tool} {arguments}", session_id,
    )
    if not approved:
        return {"records": [], "warnings": [
            f"External MCP 'github' NOT used — {reason}."
        ]}
    records: list[dict] = []
    warnings: list[str] = []
    _absorb(external_github(tool, arguments, session_id=session_id), records, warnings)
    return {"records": records, "warnings": warnings}


def gather_tooluniverse(
    tool: str, arguments: dict, session_id: str | None, *, summary: str | None = None,
) -> dict[str, list]:
    """READ-ONLY ToolUniverse scientific-tool call, approval-gated.

    Returns ``scientific_tool_result`` evidence — UNVERIFIED (a DB/API lookup,
    not a definitive finding); still routed through the Scientific Verifier.
    """
    from . import external_tooluniverse  # local import to avoid cycle at load

    if not use_in_tooluniverse():
        return _empty()
    approved, reason = request_approval(
        "tooluniverse", tool, summary or f"{tool} {arguments}", session_id,
    )
    if not approved:
        return {"records": [], "warnings": [
            f"External MCP 'tooluniverse' NOT used — {reason}."
        ]}
    records: list[dict] = []
    warnings: list[str] = []
    _absorb(external_tooluniverse(tool, arguments, session_id=session_id), records, warnings)
    return {"records": records, "warnings": warnings}


# Prompt patterns that signal a research-HYPOTHESIS-GENERATION request — used
# to decide when an agent should consult open-coscientist.
_HYPOTHESIS_KEYWORDS: tuple[str, ...] = (
    "hypothes",                 # hypothesis / hypotheses / hypothesize
    "brainstorm",
    "research direction", "research directions",
    "research question", "research questions",
    "propose mechanism", "candidate mechanism", "possible mechanism",
    "novel approach", "novel approaches",
    "testable idea", "testable hypothes",
    "generate idea", "generate hypotheses", "co-scientist", "coscientist",
)


def looks_like_hypothesis_request(text: str) -> bool:
    """True if the prompt asks for research-hypothesis generation/ideation."""
    t = (text or "").lower()
    return any(k in t for k in _HYPOTHESIS_KEYWORDS)


def maybe_gather_hypotheses(user_input: str, session_id: str | None) -> dict[str, list]:
    """Agent-facing convenience: consult open-coscientist ONLY when enabled and
    the prompt is hypothesis-generation-oriented.  Approval-gated.  Returns the
    same ``{records, warnings}`` shape so an agent can merge it into its pack.
    """
    if not use_in_open_coscientist():
        return _empty()
    if not looks_like_hypothesis_request(user_input):
        return _empty()
    return gather_hypotheses(user_input, session_id)


def gather_hypotheses(
    research_goal: str, session_id: str | None, *, summary: str | None = None, **kwargs,
) -> dict[str, list]:
    """open-coscientist hypothesis generation, approval-gated.

    Returns ``hypothesis_signal`` records — SPECULATIVE AI-generated hypotheses,
    NOT validated science; still routed through the Scientific Verifier.
    """
    from . import external_generate_hypotheses  # local import to avoid cycle

    if not use_in_open_coscientist():
        return _empty()
    if not _research_like(research_goal):
        return _empty()
    approved, reason = request_approval(
        "open_coscientist", "generate_hypotheses",
        summary or research_goal, session_id,
    )
    if not approved:
        return {"records": [], "warnings": [
            f"External MCP 'open_coscientist' NOT used — {reason}."
        ]}
    records: list[dict] = []
    warnings: list[str] = []
    _absorb(
        external_generate_hypotheses(research_goal, session_id=session_id, **kwargs),
        records, warnings,
    )
    return {"records": records, "warnings": warnings}


# ---------------------------------------------------------------------------
# Attachment + summary helpers (used by agents and the orchestrator)
# ---------------------------------------------------------------------------

def merge_gathered(*gathered: dict) -> dict[str, list]:
    """Merge several ``{records, warnings}`` dicts into one."""
    records: list = []
    warnings: list = []
    for g in gathered:
        if isinstance(g, dict):
            records.extend(g.get("records") or [])
            for w in (g.get("warnings") or []):
                if w not in warnings:
                    warnings.append(w)
    return {"records": records, "warnings": warnings}


def attach_to_output(output: dict, gathered: dict) -> dict:
    """Attach gathered external evidence to an agent's output dict in place.

    No-op when nothing was gathered, so disabled runs leave the output clean.
    """
    if not isinstance(output, dict):
        return output
    records = (gathered or {}).get("records") or []
    warnings = (gathered or {}).get("warnings") or []
    if not records and not warnings:
        return output
    if records:
        output["external_mcp_evidence"] = records
    if warnings:
        output["external_mcp_warnings"] = warnings
    return output


def summarize_records(records: list[dict], warnings: list[str]) -> dict[str, Any]:
    """Build the compact ``external_mcp_evidence`` summary section."""
    providers = sorted({
        r.get("provider") for r in records
        if isinstance(r, dict) and r.get("provider")
    })
    mock = sum(1 for r in records if isinstance(r, dict) and r.get("mock_mode"))
    merged_warnings = list(dict.fromkeys(list(warnings) + list(STANDARD_WARNINGS)))
    return {
        "used": bool(records),
        "providers": providers,
        "records": len(records),
        "mock_records": mock,
        "warnings": merged_warnings if records else list(warnings),
    }
