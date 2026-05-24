"""AURA MCP server — Phase 1 (STDIO transport only).

THIN ADAPTER CONTRACT
---------------------
This server NEVER calls specialist agents directly.  Every generative or
research workflow is delegated to AURA's orchestrator
(``core.orchestrator.run_aura_core``) so the Strategic Governor, permission
gates, Scientific Verifier, and draft-persistence rules stay in force.

The tool *implementations* are plain functions returning the standard policy
envelope, so they can be imported and unit-tested without the MCP SDK
installed.  The STDIO transport is wired lazily in :func:`main` and only
imports the ``mcp`` package when the server is actually started.

Run with:

    python -m aura_mcp.server
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import importlib.util
import os
import platform
import sys
from typing import Any, Callable

# Module-level import so tests can patch ``aura_mcp.server.run_aura_core`` and
# assert the research tools delegate to the orchestrator (never specialists).
from core.orchestrator import run_aura_core

from . import policy, schemas, report_access

SERVER_NAME = "aura-mcp"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _module_available(dotted: str) -> bool:
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _run_with_optional_timeout(
    fn: Callable[[], Any], max_runtime_seconds: int | None,
) -> tuple[Any, list[str]]:
    """Run *fn* directly, or under a best-effort soft deadline.

    NON-PREEMPTIVE: ``run_aura_core`` is not cancellable, so on timeout the
    background work may continue; we simply stop waiting and surface a
    warning.  Returns ``(result_or_None, warnings)``.  Raises TimeoutError on
    timeout so the caller can build an error envelope.
    """
    if not max_runtime_seconds:
        return fn(), []
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = pool.submit(fn)
    try:
        return fut.result(timeout=max_runtime_seconds), [
            "max_runtime_seconds is advisory: AURA work is not preemptively "
            "cancellable; the pipeline completed within the budget."
        ]
    finally:
        pool.shutdown(wait=False)


def _scout_summary(result: dict) -> str | None:
    scout = result.get("research_scout")
    if isinstance(scout, dict):
        return scout.get("summary")
    return None


def _specialist_summaries(result: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    specialists = result.get("specialists") or {}
    if isinstance(specialists, dict):
        for name, payload in specialists.items():
            if isinstance(payload, dict) and payload.get("summary"):
                out[name] = payload.get("summary")
    return out


def _verifier_view(result: dict) -> dict | None:
    """Return the verifier verdict WITHOUT suppression."""
    sv = result.get("scientific_verifier")
    if not isinstance(sv, dict):
        return None
    return {
        "route": sv.get("route"),
        "overall_assessment": sv.get("overall_assessment"),
        "final_recommendation": sv.get("final_recommendation"),
        "escalated_by": sv.get("escalated_by"),
        "escalation_rationale": sv.get("escalation_rationale"),
    }


def _draft_paths(result: dict) -> dict:
    return {
        "draft_paths": result.get("draft_paths") or {},
        "drafts_persisted": result.get("drafts_persisted"),
        "drafts_persisted_paths": result.get("drafts_persisted_paths") or [],
        "unverified_draft_paths": result.get("unverified_draft_paths") or {},
    }


# ---------------------------------------------------------------------------
# Tool: aura_health
# ---------------------------------------------------------------------------

@policy.guarded("aura_health")
def aura_health(arguments: dict | None = None) -> dict:
    cleaned, errors = schemas.validate_health_input(arguments)
    if errors:
        return policy.error_envelope("aura_health", "; ".join(errors))

    warnings: list[str] = []
    model_env = {
        k: os.environ[k]
        for k in ("AURA_MODEL", "LLM_MODEL", "AURA_DEFAULT_MODEL", "REMOTE_API_URL")
        if k in os.environ
    }
    modules = {
        "core.orchestrator": _module_available("core.orchestrator"),
        "core.path_safety": _module_available("core.path_safety"),
        "agents.scientific_verifier": _module_available("agents.scientific_verifier"),
        "qwen_evolver.deep_research.orchestrator":
            _module_available("qwen_evolver.deep_research.orchestrator"),
    }

    data: dict[str, Any] = {
        "python_version": platform.python_version(),
        "aura_importable": modules["core.orchestrator"],
        "model_env": model_env,
        "modules_available": modules,
        "llm_checked": False,
    }

    if cleaned["check_llm"]:
        data["llm_checked"] = True
        try:
            from core.llm import ask_llm
            resp = ask_llm(
                system_prompt="You are a connectivity tester.",
                user_prompt="Return the word OK exactly.",
                temperature=0.0,
            )
            data["llm_ok"] = True
            data["llm_response_preview"] = str(resp)[:80]
        except Exception as exc:  # noqa: BLE001
            data["llm_ok"] = False
            warnings.append(f"LLM connectivity probe failed: {type(exc).__name__}: {exc}")

    return policy.make_envelope("aura_health", ok=True, data=data, warnings=warnings)


# ---------------------------------------------------------------------------
# Tool: aura_research  (delegates to run_aura_core)
# ---------------------------------------------------------------------------

@policy.guarded("aura_research")
def aura_research(arguments: dict | None = None) -> dict:
    cleaned, errors = schemas.validate_research_input(arguments)
    if errors:
        return policy.error_envelope("aura_research", "; ".join(errors))

    warnings: list[str] = []

    def _call() -> dict:
        # THIN ADAPTER: the ONLY entry point is the governed orchestrator.
        return run_aura_core(cleaned["prompt"], session_id=cleaned["session_id"])

    try:
        result, run_warnings = _run_with_optional_timeout(
            _call, cleaned["max_runtime_seconds"],
        )
        warnings.extend(run_warnings)
    except concurrent.futures.TimeoutError:
        return policy.error_envelope(
            "aura_research",
            f"AURA run exceeded max_runtime_seconds="
            f"{cleaned['max_runtime_seconds']} (background work may continue).",
            session_id=cleaned["session_id"],
        )

    if not isinstance(result, dict):
        return policy.error_envelope(
            "aura_research", "Orchestrator returned a non-dict result."
        )

    governor = result.get("strategic_governor") or {}
    data = {
        "pipeline_status": result.get("pipeline_status"),
        "selected_agents": governor.get("selected_agents") if isinstance(governor, dict) else None,
        "research_scout_summary": _scout_summary(result),
        "specialist_summaries": _specialist_summaries(result),
        "scientific_verifier": _verifier_view(result),  # never suppressed
        "drafts": _draft_paths(result),
        "pending_prompt": result.get("pending_prompt"),
    }
    # Surface orchestrator errors as warnings (the run did not raise).
    for err in (result.get("errors") or []):
        warnings.append(
            f"[{err.get('agent', '?')}] {err.get('error', err)}"
            if isinstance(err, dict) else str(err)
        )

    return policy.make_envelope(
        "aura_research", ok=True, data=data,
        session_id=result.get("session_id"), warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Tool: aura_deep_research  (delegates to AURA's deep-research orchestrator)
# ---------------------------------------------------------------------------

@policy.guarded("aura_deep_research")
def aura_deep_research(arguments: dict | None = None) -> dict:
    cleaned, errors = schemas.validate_deep_research_input(arguments)
    if errors:
        return policy.error_envelope("aura_deep_research", "; ".join(errors))

    try:
        from qwen_evolver.deep_research.orchestrator import run_research
        from qwen_evolver.deep_research.schemas import ResearchMission, ResearchDepth
    except Exception as exc:  # noqa: BLE001
        return policy.error_envelope(
            "aura_deep_research",
            f"Deep-research subsystem unavailable: {type(exc).__name__}: {exc}",
        )

    warnings: list[str] = []
    mission = ResearchMission(
        original_user_request=cleaned["query"],
        interpreted_objective=cleaned["query"],
        requested_depth=ResearchDepth(cleaned["depth"]),
    )
    result = run_research(mission)
    if not isinstance(result, dict):
        return policy.error_envelope(
            "aura_deep_research", "Deep-research returned a non-dict result."
        )

    mission_id = (result.get("mission") or {}).get("mission_id") or mission.mission_id
    report_path = result.get("report_path") or ""

    # Derive evidence/reflection paths (path-safe) without reading them.
    evidence_path = ""
    reflection_path = ""
    try:
        from core.path_safety import safe_mission_path
        import config as _cfg
        data_base = _cfg.BASE_DIR / "data" / "deep_research"
        ev = safe_mission_path(data_base / "evidence", mission_id, "_evidence.jsonl")
        rf = safe_mission_path(data_base / "reflections", mission_id, "_reflection.json")
        evidence_path = str(ev.relative_to(_cfg.BASE_DIR)) if ev.exists() else ""
        reflection_path = str(rf.relative_to(_cfg.BASE_DIR)) if rf.exists() else ""
    except Exception:  # noqa: BLE001
        pass

    warnings.extend(result.get("provider_warnings") or [])
    if result.get("report_generation_failed"):
        warnings.append(
            f"Report generation degraded (status={result.get('report_status')!r})."
        )
    warnings.append(
        "Deep research is preliminary reconnaissance — NOT a systematic review "
        "and NOT a statement of final truth."
    )

    data = {
        "mission_id": mission_id,
        "report_path": report_path,
        "evidence_path": evidence_path,
        "reflection_path": reflection_path,
        "mock_mode": result.get("mock_mode_used"),
        "source_count": result.get("source_count"),
        "provider_label": result.get("provider_label"),
        "verifier_decision": (result.get("verification") or {}).get("decision"),
    }
    return policy.make_envelope(
        "aura_deep_research", ok=True, data=data, warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Tool: aura_verify_claims  (wrapped through run_aura_core — governed)
# ---------------------------------------------------------------------------

def _build_verification_prompt(claims: list[str], evidence: list[dict], context: str | None) -> str:
    lines = [
        "Verify the following claims against the supplied evidence. For each "
        "claim, assess whether the evidence supports it, identify unsupported "
        "or overstated claims, and list any missing evidence.",
        "",
        "CLAIMS:",
    ]
    for i, c in enumerate(claims, 1):
        lines.append(f"  {i}. {c}")
    lines.append("")
    lines.append("EVIDENCE:")
    if evidence:
        import json as _json
        for i, e in enumerate(evidence, 1):
            lines.append(f"  E{i}. {_json.dumps(e, default=str)[:600]}")
    else:
        lines.append("  (no structured evidence provided)")
    if context:
        lines.append("")
        lines.append(f"CONTEXT: {context}")
    return "\n".join(lines)


@policy.guarded("aura_verify_claims")
def aura_verify_claims(arguments: dict | None = None) -> dict:
    cleaned, errors = schemas.validate_verify_claims_input(arguments)
    if errors:
        return policy.error_envelope("aura_verify_claims", "; ".join(errors))

    prompt = _build_verification_prompt(
        cleaned["claims"], cleaned["evidence"], cleaned["context"],
    )
    # Wrapped through the orchestrator so the Scientific Verifier runs inside
    # AURA's governed pipeline rather than being invoked out-of-band.
    result = run_aura_core(prompt)
    if not isinstance(result, dict):
        return policy.error_envelope(
            "aura_verify_claims", "Orchestrator returned a non-dict result."
        )

    sv = result.get("scientific_verifier")
    if not isinstance(sv, dict):
        return policy.make_envelope(
            "aura_verify_claims", ok=True,
            session_id=result.get("session_id"),
            data={
                "route": None,
                "claim_issues": [],
                "missing_evidence": [],
                "recommended_next_action": "human_review",
            },
            warnings=["AURA did not produce a Scientific Verifier verdict for this input."],
        )

    route = sv.get("route")
    claim_issues = sv.get("claim_checks") or []
    missing_evidence = list(sv.get("unsupported_claims") or [])
    for c in claim_issues:
        if isinstance(c, dict) and c.get("support_status") in ("unverifiable", "contradicted"):
            txt = c.get("claim") or c.get("correction") or ""
            if txt and txt not in missing_evidence:
                missing_evidence.append(txt)

    recommended = sv.get("final_recommendation") or {
        "approve": "proceed",
        "revise": "revise_claims",
        "retrieve_more_evidence": "gather_more_evidence",
        "human_review": "human_review",
        "reject": "do_not_use",
    }.get((route or "").strip().lower(), "human_review")

    data = {
        "route": route,
        "overall_assessment": sv.get("overall_assessment"),
        "claim_issues": claim_issues,
        "missing_evidence": missing_evidence,
        "recommended_next_action": recommended,
    }
    return policy.make_envelope(
        "aura_verify_claims", ok=True, data=data,
        session_id=result.get("session_id"),
    )


# ---------------------------------------------------------------------------
# Tool: aura_list_reports  (read-only)
# ---------------------------------------------------------------------------

@policy.guarded("aura_list_reports")
def aura_list_reports(arguments: dict | None = None) -> dict:
    reports = report_access.list_reports()
    return policy.make_envelope(
        "aura_list_reports", ok=True,
        data={"reports": reports, "count": len(reports)},
    )


# ---------------------------------------------------------------------------
# Tool: aura_get_report  (read-only, path-safe)
# ---------------------------------------------------------------------------

@policy.guarded("aura_get_report")
def aura_get_report(arguments: dict | None = None) -> dict:
    cleaned, errors = schemas.validate_get_report_input(arguments)
    if errors:
        return policy.error_envelope("aura_get_report", "; ".join(errors))

    content, err = report_access.read_report(cleaned["report_path"])
    if err is not None:
        return policy.error_envelope("aura_get_report", err)
    return policy.make_envelope(
        "aura_get_report", ok=True,
        data={"report_path": cleaned["report_path"], "content": content},
    )


# ---------------------------------------------------------------------------
# Tool registry + dispatch
# ---------------------------------------------------------------------------

TOOLS: dict[str, dict] = {
    "aura_health": {
        "fn": aura_health,
        "description": "Report whether AURA is importable/configured. Does not "
                       "call an LLM unless check_llm=true.",
        "input_schema": schemas.TOOL_INPUT_SCHEMAS["aura_health"],
    },
    "aura_research": {
        "fn": aura_research,
        "description": "Run a research/analysis task through AURA's governed "
                       "orchestrator (Strategic Governor + Scientific Verifier).",
        "input_schema": schemas.TOOL_INPUT_SCHEMAS["aura_research"],
    },
    "aura_deep_research": {
        "fn": aura_deep_research,
        "description": "Run AURA's multi-round deep-research pipeline. Returns "
                       "report/evidence/reflection paths. NOT a systematic review.",
        "input_schema": schemas.TOOL_INPUT_SCHEMAS["aura_deep_research"],
    },
    "aura_verify_claims": {
        "fn": aura_verify_claims,
        "description": "Verify claims against evidence via AURA's Scientific "
                       "Verifier (wrapped through the governed orchestrator).",
        "input_schema": schemas.TOOL_INPUT_SCHEMAS["aura_verify_claims"],
    },
    "aura_list_reports": {
        "fn": aura_list_reports,
        "description": "List safe, report-like files under reports/ (read-only).",
        "input_schema": schemas.TOOL_INPUT_SCHEMAS["aura_list_reports"],
    },
    "aura_get_report": {
        "fn": aura_get_report,
        "description": "Read one approved report file under reports/ (read-only, "
                       "path-safe).",
        "input_schema": schemas.TOOL_INPUT_SCHEMAS["aura_get_report"],
    },
}

# Defensive invariant: the registry must exactly match the policy allowlist.
assert set(TOOLS) == set(policy.EXPOSED_TOOLS), (
    "aura_mcp.server.TOOLS drifted from policy.EXPOSED_TOOLS"
)


def list_tools() -> list[str]:
    """Return the names of exposed tools (allowlist-gated)."""
    return [name for name in TOOLS if policy.is_tool_allowed(name)]


def dispatch(tool_name: str, arguments: dict | None = None) -> dict:
    """Validate the tool against the allowlist and invoke it.

    Always returns the standard envelope — never raises.
    """
    if not policy.is_tool_allowed(tool_name) or tool_name not in TOOLS:
        return policy.error_envelope(
            tool_name, f"Unknown or disallowed tool: {tool_name!r}."
        )
    return TOOLS[tool_name]["fn"](arguments or {})


# ---------------------------------------------------------------------------
# STDIO transport entrypoint (lazy MCP SDK import)
# ---------------------------------------------------------------------------

def _build_mcp_server():
    """Construct an ``mcp.server.Server`` wired to the dispatch table.

    Imported lazily so the rest of this module (and the tests) work without
    the ``mcp`` SDK installed.
    """
    import mcp.types as types
    from mcp.server import Server

    server = Server(SERVER_NAME)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=name,
                description=spec["description"],
                inputSchema=spec["input_schema"],
            )
            for name, spec in TOOLS.items()
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
        import json as _json
        # CRITICAL (STDIO transport): stdout is the JSON-RPC channel.  AURA's
        # orchestrator and agents emit progress via ``print(..., flush=True)``
        # to stdout (e.g. "[research_scout] starting ..."), which would corrupt
        # the protocol stream.  Redirect stdout → stderr for the duration of
        # tool execution so ONLY JSON-RPC messages reach stdout.  (dispatch
        # itself is left untouched so library/test callers keep normal stdout.)
        with contextlib.redirect_stdout(sys.stderr):
            envelope = dispatch(name, arguments or {})
        return [types.TextContent(type="text", text=_json.dumps(envelope, default=str))]

    return server


def main() -> int:
    """STDIO-only entrypoint: ``python -m aura_mcp.server``."""
    try:
        import anyio
        import mcp.server.stdio
    except Exception as exc:  # noqa: BLE001 — SDK not installed
        sys.stderr.write(
            "AURA MCP requires the 'mcp' SDK for STDIO transport.\n"
            f"Import failed: {type(exc).__name__}: {exc}\n"
            "Install it with:  pip install \"mcp>=1.0\"\n"
        )
        return 1

    server = _build_mcp_server()

    async def _serve() -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream,
                server.create_initialization_options(),
            )

    # STDIO transport: logs MUST go to stderr — only JSON-RPC may touch stdout.
    print(
        f"[{SERVER_NAME}] STDIO MCP server starting. "
        f"Exposed tools: {', '.join(list_tools())}",
        file=sys.stderr,
        flush=True,
    )
    anyio.run(_serve)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
