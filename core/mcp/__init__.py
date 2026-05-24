"""AURA outbound-MCP gateway (Phase 2).

AURA can call selected, allowlisted external MCP servers as **evidence /
context providers** — never as authorities.  External outputs are normalized,
confidence-capped, audited, and marked ``verified_by_aura=False`` until AURA's
Scientific Verifier reviews them (Phase 3).

Safe by default: outbound MCP is DISABLED unless ``AURA_MCP_OUTBOUND_ENABLED=1``.

Public adapter helpers (each: check policy → call tool → normalize → audit):
    external_research_search(query, session_id=None)
    external_deep_research(query, depth="quick", session_id=None)
    external_idea_check(idea_text, depth="quick", session_id=None)
"""
from __future__ import annotations

from typing import Any

from . import audit as _audit
from . import client as _client
from . import config as _config
from . import evidence_bridge as _bridge

__all__ = [
    "external_research_search",
    "external_research_report",
    "external_deep_research",
    "external_idea_check",
    "external_github_repo_context",
    "external_github",
    "external_github_open_issues",
    "external_github_issue",
    "external_github_pull_requests",
    "external_github_ci_failures",
    "external_github_ci_logs",
    "external_github_commit_history",
    "external_github_compare_branches",
    "external_github_code_review",
    "external_tooluniverse",
    "external_generate_hypotheses",
    "external_jupyter_notebook_tool",
    "external_paper_qa_query",
    "external_paper_qa_add_pdf",
    "external_paper_qa_status",
    "GITHUB_MAINTENANCE_PLAYBOOK",
    "call_mcp_tool",
    "is_mcp_available",
    "is_external_mcp_available",
    "list_allowed_mcp_tools",
]

# Re-export the low-level client surface.
call_mcp_tool = _client.call_mcp_tool
is_mcp_available = _client.is_mcp_available
is_external_mcp_available = _client.is_external_mcp_available
list_allowed_mcp_tools = _client.list_allowed_mcp_tools


def _run_adapter(
    *,
    server: str,
    tool: str,
    arguments: dict,
    query: str,
    session_id: str | None,
) -> dict[str, Any]:
    """Shared flow: policy-gated call → normalize → audit → return.

    Returns a JSON-serializable dict::

        {"ok": bool, "evidence": {...}|None, "warnings": [...], "errors": [...]}

    The normalized evidence is ALWAYS ``verified_by_aura=False`` in Phase 2 —
    it is NOT inserted into any final AURA draft here.
    """
    cfg = _config.load_config()
    warnings: list[str] = []
    errors: list[str] = []

    call_result = _client.call_mcp_tool(server, tool, arguments, session_id, config=cfg)
    record = _bridge.normalize_result(call_result, query=query, session_id=session_id)

    if not call_result.ok:
        errors.append(f"{call_result.error_type}: {call_result.error}")
    else:
        warnings.append(
            "External MCP evidence is UNVERIFIED — it must pass AURA's "
            "Scientific Verifier before influencing final drafts."
        )
        if record.mock_mode:
            warnings.append("Mock/synthetic external output (confidence forced low).")

    # Audit every outbound attempt (hashed args/results, no raw secrets).
    try:
        rec = _audit.build_audit_record(
            session_id=session_id,
            server=server,
            tool=tool,
            arguments=arguments,
            raw_result=call_result.raw_result,
            ok=call_result.ok,
            error_type=call_result.error_type,
            duration_seconds=call_result.duration_seconds,
            normalized_evidence_type=record.result_type,
            verified_by_aura=record.verified_by_aura,
            mock_mode=record.mock_mode,
        )
        _audit.log_call(rec, config=cfg)
    except Exception:  # noqa: BLE001 — auditing never breaks the adapter
        warnings.append("Audit logging failed (non-fatal).")

    return {
        "ok": bool(call_result.ok),
        "evidence": record.model_dump(),
        "warnings": warnings,
        "errors": errors,
    }


def external_research_search(query: str, session_id: str | None = None) -> dict[str, Any]:
    """Local Deep Research ``search`` → normalized ``raw_search`` evidence."""
    return _run_adapter(
        server="local_deep_research", tool="search",
        arguments={"query": query}, query=query, session_id=session_id,
    )


def external_deep_research(
    query: str, depth: str = "quick", session_id: str | None = None,
) -> dict[str, Any]:
    """Local Deep Research ``quick_research`` / ``detailed_research`` →
    normalized ``research_summary`` evidence.
    """
    tool = "detailed_research" if depth in ("detailed", "extensive", "deep") else "quick_research"
    return _run_adapter(
        server="local_deep_research", tool=tool,
        arguments={"query": query}, query=query, session_id=session_id,
    )


def external_research_report(
    query: str, depth: str = "quick", session_id: str | None = None,
) -> dict[str, Any]:
    """Local Deep Research ``generate_report`` → normalized ``external_report``.

    Secondary evidence unless source-level citations are present.
    """
    return _run_adapter(
        server="local_deep_research", tool="generate_report",
        arguments={"query": query, "depth": depth},
        query=query, session_id=session_id,
    )


def external_idea_check(
    idea_text: str, depth: str = "quick", session_id: str | None = None,
) -> dict[str, Any]:
    """idea-reality ``idea_check`` → normalized market/competitor signal.

    The result is explicitly NOT scientific evidence.
    """
    # idea-reality's idea_check signature is idea_check(idea_text, depth)
    # where depth is "quick" | "deep".
    norm_depth = "deep" if str(depth).lower() in ("deep", "detailed", "extensive") else "quick"
    return _run_adapter(
        server="idea_reality", tool="idea_check",
        arguments={"idea_text": idea_text, "depth": norm_depth},
        query=idea_text, session_id=session_id,
    )


def external_github_repo_context(
    query_or_path: str, session_id: str | None = None,
) -> dict[str, Any]:
    """GitHub MCP read-only repository context.

    Uses ``search_code`` for free-text queries and ``get_file_contents`` for
    path-like inputs.  READ-ONLY: the policy blocks every write/admin tool, so
    this can never mutate a repository.  Returns ``repository_context``
    evidence (code/repo context, NOT scientific evidence).
    """
    text = (query_or_path or "").strip()
    looks_like_path = ("/" in text and " " not in text) or text.endswith(
        (".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini")
    )
    if looks_like_path:
        tool, arguments = "get_file_contents", {"path": text}
    else:
        tool, arguments = "search_code", {"query": text}
    return _run_adapter(
        server="github", tool=tool, arguments=arguments,
        query=text, session_id=session_id,
    )


# ---------------------------------------------------------------------------
# GitHub read-only repo-maintenance helpers
# ---------------------------------------------------------------------------
# These cover the AI repo-maintenance use cases (issues, PRs, CI failures,
# history, branch comparison, code review).  Every tool is READ-ONLY and
# policy-gated; arguments follow the github-mcp-server schema (owner/repo).
# If your server version reports a "missing/unexpected argument" validation
# error, adjust the argument names — the structured error tells you which.

def external_github(
    tool: str, arguments: dict | None = None, session_id: str | None = None,
) -> dict[str, Any]:
    """General READ-ONLY GitHub MCP call.

    Policy enforces read-only (only allowlisted get_/list_/search_/compare_
    tools pass; every write/admin/merge/delete tool is blocked), so this can
    never mutate a repository.  Use it for any allowlisted read tool.
    """
    args = arguments if isinstance(arguments, dict) else {}
    query = args.get("query") or args.get("path") or f"{tool}({sorted(args)})"
    return _run_adapter(
        server="github", tool=tool, arguments=args,
        query=str(query), session_id=session_id,
    )


def external_github_open_issues(owner: str, repo: str, session_id: str | None = None) -> dict[str, Any]:
    """Open issues for project maintenance triage."""
    return external_github("list_issues", {"owner": owner, "repo": repo, "state": "OPEN"}, session_id)


def external_github_issue(owner: str, repo: str, issue_number: int, session_id: str | None = None) -> dict[str, Any]:
    """Read a single issue (consolidated ``issue_read`` tool, method=get)."""
    return external_github(
        "issue_read",
        {"method": "get", "owner": owner, "repo": repo, "issue_number": issue_number},
        session_id,
    )


def external_github_pull_requests(owner: str, repo: str, session_id: str | None = None) -> dict[str, Any]:
    """Open pull requests."""
    return external_github("list_pull_requests", {"owner": owner, "repo": repo, "state": "open"}, session_id)


def external_github_ci_failures(owner: str, repo: str, session_id: str | None = None) -> dict[str, Any]:
    """Recent CI/workflow runs (consolidated ``actions_list`` tool).

    Use ``external_github_ci_logs`` to pull failed job logs for a run.
    """
    return external_github(
        "actions_list",
        {"method": "list_workflow_runs", "owner": owner, "repo": repo},
        session_id,
    )


def external_github_ci_logs(owner: str, repo: str, run_id: int, session_id: str | None = None) -> dict[str, Any]:
    """Failed-job logs for a workflow run (CI failure triage)."""
    return external_github(
        "get_job_logs",
        {"owner": owner, "repo": repo, "run_id": run_id, "failed_only": True, "return_content": True},
        session_id,
    )


def external_github_commit_history(owner: str, repo: str, session_id: str | None = None) -> dict[str, Any]:
    """Recent commit history."""
    return external_github("list_commits", {"owner": owner, "repo": repo}, session_id)


def external_github_compare_branches(
    owner: str, repo: str, base: str, head: str, session_id: str | None = None,
) -> dict[str, Any]:
    """Best-effort 'branch comparison'.

    NOTE: github-mcp-server (v1.x) exposes no native compare tool, so this
    returns the recent commit history of the ``head`` branch (via list_commits
    with ``sha=head``).  For a true diff, inspect commits on both branches.
    """
    return external_github(
        "list_commits", {"owner": owner, "repo": repo, "sha": head}, session_id,
    )


def external_github_code_review(
    owner: str, repo: str, pull_number: int, session_id: str | None = None,
) -> dict[str, Any]:
    """Read a PR's diff for AI-assisted code review (READ-ONLY — never posts).

    Uses the consolidated ``pull_request_read`` tool with ``method=get_diff``.
    """
    return external_github(
        "pull_request_read",
        {"method": "get_diff", "owner": owner, "repo": repo, "pullNumber": pull_number},
        session_id,
    )


def external_tooluniverse(
    tool: str, arguments: dict | None = None, session_id: str | None = None,
) -> dict[str, Any]:
    """Call a READ-ONLY ToolUniverse scientific tool.

    ToolUniverse exposes 2000+ tools; policy admits only read-only ones
    (``get_``/``search_``/``list_``/``query_``... and no write verb).  Result is
    normalized to ``scientific_tool_result`` — UNVERIFIED external evidence
    (a DB/API lookup, NOT a definitive finding); the Scientific Verifier still
    reviews it.
    """
    args = arguments if isinstance(arguments, dict) else {}
    query = args.get("query") or args.get("name") or args.get("q") or f"{tool}({sorted(args)})"
    return _run_adapter(
        server="tooluniverse", tool=tool, arguments=args,
        query=str(query), session_id=session_id,
    )


def external_generate_hypotheses(
    research_goal: str,
    *,
    initial_hypotheses_count: int = 3,
    max_iterations: int = 1,
    evolution_max_count: int = 2,
    preferences: str = "",
    constraints: str = "",
    session_id: str | None = None,
) -> dict[str, Any]:
    """open-coscientist hypothesis generation (AI Co-Scientist) via STDIO wrapper.

    Returns ``hypothesis_signal`` evidence — SPECULATIVE AI-generated research
    hypotheses, NOT validated science; still routed through the Scientific
    Verifier.  Long-running multi-agent LLM loop; requires an LLM key in the
    wrapper's environment.
    """
    args: dict[str, Any] = {
        "research_goal": research_goal,
        "initial_hypotheses_count": initial_hypotheses_count,
        "max_iterations": max_iterations,
        "evolution_max_count": evolution_max_count,
    }
    if preferences:
        args["preferences"] = preferences
    if constraints:
        args["constraints"] = constraints
    return _run_adapter(
        server="open_coscientist", tool="generate_hypotheses",
        arguments=args, query=research_goal, session_id=session_id,
    )


# ---------------------------------------------------------------------------
# jupyter-mcp-server2 adapter
# ---------------------------------------------------------------------------


def external_jupyter_notebook_tool(
    tool: str, arguments: dict | None = None, session_id: str | None = None,
) -> dict[str, Any]:
    """Call a jupyter-mcp-server2 tool (notebook editing, cell execution, etc.).

    Tools: list_files, list_kernels, use_notebook, list_notebooks,
    read_notebook, read_cell, insert_cell, execute_cell, execute_code, etc.
    Returns ``notebook_tool_result`` — UNVERIFIED notebook manipulation.
    """
    args = arguments if isinstance(arguments, dict) else {}
    query = args.get("path") or args.get("notebook_path") or args.get("code", f"{tool}")[:200]
    return _run_adapter(
        server="jupyter_mcp_server", tool=tool, arguments=args,
        query=str(query), session_id=session_id,
    )


# ---------------------------------------------------------------------------
# paper-qa2 adapters
# ---------------------------------------------------------------------------


def external_paper_qa_query(
    question: str, session_id: str | None = None,
) -> dict[str, Any]:
    """Ask a question about documents indexed in paper-qa2.

    Returns ``document_qa_result`` — UNVERIFIED LLM-based answer from
    indexed scientific PDFs.
    """
    return _run_adapter(
        server="paper_qa", tool="paperqa_query",
        arguments={"question": question},
        query=question, session_id=session_id,
    )


def external_paper_qa_add_pdf(
    pdf_path: str, docname: str = "", session_id: str | None = None,
) -> dict[str, Any]:
    """Add a PDF to the paper-qa2 index for later querying.

    Returns ``document_index_result``.
    """
    args: dict[str, Any] = {"path": pdf_path}
    if docname:
        args["docname"] = docname
    return _run_adapter(
        server="paper_qa", tool="paperqa_add_pdf",
        arguments=args, query=pdf_path, session_id=session_id,
    )


def external_paper_qa_status(
    session_id: str | None = None,
) -> dict[str, Any]:
    """Get paper-qa2 status (indexed documents, settings).

    Returns ``document_status_result``.
    """
    return _run_adapter(
        server="paper_qa", tool="paperqa_status",
        arguments={}, query="status", session_id=session_id,
    )


# Documented mapping of the AI repo-maintenance use cases → recommended
# read-only tools (github-mcp-server v1.x consolidated names).  Surfaced in
# core/mcp/README.md.
GITHUB_MAINTENANCE_PLAYBOOK: dict[str, str] = {
    "open issues": "list_issues / issue_read(method=get) / search_issues",
    "pull requests": "list_pull_requests / pull_request_read(method=get|get_status)",
    "CI failures": "actions_list(method=list_workflow_runs) / get_job_logs(failed_only=true)",
    "repository history": "list_commits / get_commit",
    "remote branch comparisons": "list_commits(sha=branch) — no native compare in v1.x",
    "code review": "pull_request_read(method=get_diff|get_files|get_reviews)",
    "project maintenance": "list_issues + list_pull_requests + actions_list + list_notifications",
}
