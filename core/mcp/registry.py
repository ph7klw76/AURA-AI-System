"""Allowlist registry of external MCP servers AURA may call (outbound).

Only servers + tools listed here can ever be invoked, and only when outbound
MCP is explicitly enabled (see :mod:`core.mcp.config`).  Nothing here assumes
the servers are actually installed — the client degrades gracefully when a
server is unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config as _mcp_config


@dataclass(frozen=True)
class McpServerSpec:
    name: str
    transport: str                       # "stdio" only in Phase 2
    allowed_tools: frozenset[str]
    # Default launch command (subprocess STDIO).  Subject to the policy
    # command whitelist; overridable per-server via env (see config).
    launch_command: tuple[str, ...] = ()
    is_network: bool = False
    description: str = ""
    # Map tool → research-grade timeout selector ("default" | "research").
    research_tools: frozenset[str] = field(default_factory=frozenset)
    # Whether this server requires a token in env (never logged).
    token_env_vars: tuple[str, ...] = ()
    # If True, this server has a very large dynamic toolset (e.g. ToolUniverse's
    # 2000+ scientific tools) and is admitted by a READ-ONLY name pattern
    # instead of an explicit allowlist (see policy ``_is_dynamic_readonly_tool``).
    dynamic_readonly: bool = False


# ---------------------------------------------------------------------------
# The allowlist.  Conceptual servers — presence is NOT assumed.
# ---------------------------------------------------------------------------

MCP_SERVER_REGISTRY: dict[str, McpServerSpec] = {
    "local_deep_research": McpServerSpec(
        name="local_deep_research",
        transport="stdio",
        allowed_tools=frozenset({
            "quick_research",
            "detailed_research",
            "generate_report",
            "analyze_documents",
            "search",
            "list_search_engines",
            "list_strategies",
            "get_configuration",
        }),
        # Default to python -m (more reliable than ldr-mcp console script).
        # Overridable via AURA_LDR_MCP_COMMAND/_ARGS.
        launch_command=("python", "-m", "local_deep_research.mcp"),
        is_network=False,
        description="Local Deep Research MCP server (self-hosted research).",
        research_tools=frozenset({
            "quick_research", "detailed_research", "generate_report",
            "analyze_documents",
        }),
    ),
    "idea_reality": McpServerSpec(
        name="idea_reality",
        transport="stdio",
        allowed_tools=frozenset({"idea_check"}),
        launch_command=("python", "-m", "idea_reality_mcp"),
        is_network=False,
        description="idea-reality MCP server (market/competition reality check).",
        research_tools=frozenset(),
    ),
    "github": McpServerSpec(
        name="github",
        transport="stdio",
        # READ-ONLY allowlist ONLY (Phase 2/3).  No create/update/delete/
        # merge/push/release/admin tools are listed here — and the policy
        # write-denylist below is a second guard.
        # READ-ONLY allowlist matching github-mcp-server's CONSOLIDATED tool
        # names (v1.x): e.g. issue_read / pull_request_read / actions_list /
        # actions_get take a ``method`` parameter.  Verified against the live
        # server's list_tools().  No write/admin tool is listed; the
        # write-verb denylist below + the server's own ``--read-only`` flag are
        # additional guards.
        allowed_tools=frozenset({
            # context / identity
            "get_me",
            # repos + history
            "get_file_contents", "get_repository_tree", "search_code",
            "search_repositories", "list_branches", "list_tags", "get_tag",
            "list_commits", "get_commit", "list_releases", "get_latest_release",
            "get_release_by_tag",
            # issues (open issues / triage)
            "list_issues", "issue_read", "search_issues", "list_issue_types",
            # pull requests + code review (issue_read/pull_request_read are reads)
            "list_pull_requests", "pull_request_read", "search_pull_requests",
            # actions / CI failures
            "actions_list", "actions_get", "get_job_logs",
            # code security (read)
            "list_code_scanning_alerts", "get_code_scanning_alert",
            "list_secret_scanning_alerts", "get_secret_scanning_alert",
            "list_dependabot_alerts", "get_dependabot_alert",
            # discussions + notifications (read)
            "list_discussions", "get_discussion", "get_discussion_comments",
            "list_discussion_categories",
            "list_notifications", "get_notification_details",
        }),
        # Default to the official binary in STDIO mode; overridable via
        # AURA_GITHUB_MCP_COMMAND / AURA_GITHUB_MCP_ARGS.
        launch_command=("github-mcp-server", "stdio"),
        is_network=False,   # remote mode stays disabled unless explicitly configured
        description="GitHub MCP server — READ-ONLY repository/issue/PR/actions context.",
        research_tools=frozenset(),
        token_env_vars=("GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_TOKEN"),
    ),
    "tooluniverse": McpServerSpec(
        name="tooluniverse",
        transport="stdio",
        # 2000+ scientific tools — admitted by a READ-ONLY name pattern, not an
        # explicit list (see dynamic_readonly).  Writes are blocked, every call
        # is human-approved, and outputs are verified by AURA.
        allowed_tools=frozenset(),
        launch_command=("python", "-c", "from core.mcp.tooluniverse_nonbiomed_filter import run; run()"),
        is_network=False,
        description=(
            "ToolUniverse (mims-harvard) — READ-ONLY scientific tool MCP "
            "(literature, genes, drugs, structures, datasets). Unverified "
            "external evidence; not definitive scientific findings."
        ),
        # Many ToolUniverse tools can be slow (remote DB queries) → research timeout.
        research_tools=frozenset(),
        dynamic_readonly=True,
    ),
    "open_coscientist": McpServerSpec(
        name="open_coscientist",
        transport="stdio",
        # AURA's STDIO wrapper (mcp_wrappers/open_coscientist) exposes exactly
        # these two tools.  generate_hypotheses is GENERATIVE (LLM only, no
        # external writes); output is speculative and AURA-verified.
        allowed_tools=frozenset({"generate_hypotheses", "coscientist_health"}),
        # Launched via the wrapper's ISOLATED venv python — set the full path
        # in AURA_OPEN_COSCIENTIST_MCP_COMMAND/_ARGS (default below is a hint).
        launch_command=("python", "mcp_wrappers/open_coscientist/coscientist_server.py"),
        is_network=False,
        description=(
            "open-coscientist (AI Co-Scientist) — AURA STDIO wrapper for "
            "multi-agent research HYPOTHESIS GENERATION. Speculative ideation, "
            "NOT validated science; AURA-verified."
        ),
        # Hypothesis generation is a long multi-agent LLM loop → research timeout.
        research_tools=frozenset({"generate_hypotheses"}),
    ),
    "jupyter_mcp_server": McpServerSpec(
        name="jupyter_mcp_server",
        transport="stdio",
        allowed_tools=frozenset({
            "list_files",
            "list_kernels",
            "use_notebook",
            "list_notebooks",
            "restart_notebook",
            "unuse_notebook",
            "read_notebook",
            "read_cell",
            "insert_cell",
            "overwrite_cell_source",
            "edit_cell_source",
            "delete_cell",
            "move_cell",
            "execute_cell",
            "execute_code",
        }),
        launch_command=("python", "-m", "jupyter_mcp_server"),
        is_network=False,
        description=(
            "jupyter-mcp-server2 — Jupyter notebook MCP server for "
            "programmatic notebook editing, cell execution, and kernel management."
        ),
        research_tools=frozenset(),
        token_env_vars=("JUPYTER_TOKEN",),
    ),
    "paper_qa": McpServerSpec(
        name="paper_qa",
        transport="stdio",
        allowed_tools=frozenset({
            "paperqa_query",
            "paperqa_add_pdf",
            "paperqa_status",
        }),
        launch_command=("python", "-m", "paperqa.mcp_server"),
        is_network=False,
        description=(
            "paper-qa2 — Document Q&A MCP server. Add PDFs and ask "
            "scientific questions about them. Powered by LLM-based retrieval."
        ),
        research_tools=frozenset({"paperqa_query"}),
        token_env_vars=("DEEPSEEK_API_KEY",),
    ),
}

# ToolUniverse-style dynamic admission: a tool is allowed ONLY if its
# underscore-tokenised name contains a READ verb and NO write verb.
DYNAMIC_READ_VERBS: frozenset[str] = frozenset({
    "get", "search", "list", "query", "fetch", "find", "lookup", "retrieve",
    "read", "count", "describe", "info", "details", "view", "browse",
    "summary", "summarize", "predict", "score", "annotate", "analyze",
    "compute", "check", "map", "convert", "translate", "compare", "calc",
    "calculate", "validate", "parse", "extract", "resolve", "match", "rank",
    "classify", "show", "load", "stats", "metadata",
})
DYNAMIC_WRITE_VERBS: frozenset[str] = frozenset({
    "submit", "create", "update", "delete", "remove", "add", "post", "put",
    "upload", "register", "set", "write", "send", "insert", "modify", "edit",
    "run", "execute", "start", "stop", "cancel", "schedule", "deploy",
    "publish", "save", "store", "push", "sync", "login", "logout",
    "authenticate", "feedback", "request", "ask", "report", "vote", "rate",
})


# Write/mutation verbs.  Defense-in-depth on top of the explicit read-only
# allowlist (the PRIMARY gate): any GitHub tool whose underscore-separated
# name contains one of these verb TOKENS is treated as a write/mutation/admin
# tool and blocked by policy.
#
# Token-boundary matching (not substring) is deliberate so it does NOT
# false-positive on legitimate consolidated READ tools such as
# ``issue_read`` / ``pull_request_read`` / ``actions_list`` / ``actions_get``,
# nor on reads like ``list_releases`` or ``get_pull_request`` (older naming).
# ``request`` is intentionally EXCLUDED (it is a token in ``pull_request_*``).
GITHUB_WRITE_VERBS: frozenset[str] = frozenset({
    "create", "update", "delete", "remove", "add", "merge", "push", "fork",
    "close", "reopen", "dispatch", "transfer", "rename", "set", "write",
    "edit", "patch", "archive", "enable", "disable", "assign", "unassign",
    "lock", "unlock", "subscribe", "unsubscribe", "submit", "approve",
    "deny", "revoke", "grant", "mark", "move", "convert", "link", "unlink",
    "pin", "unpin", "minimize", "admin", "star", "unstar",
})

# Back-compat aliases (kept so any external import still resolves).
GITHUB_READ_PREFIXES: tuple[str, ...] = ("get_", "list_", "search_", "compare_")


def is_server_allowed(server_name: str) -> bool:
    return server_name in MCP_SERVER_REGISTRY


def get_server_spec(server_name: str) -> McpServerSpec | None:
    return MCP_SERVER_REGISTRY.get(server_name)


def is_dynamic_readonly_tool(tool_name: str) -> bool:
    """Admit a tool from a dynamic-read-only server (e.g. ToolUniverse): its
    underscore-tokenised name must contain a READ verb and NO write verb."""
    tokens = (tool_name or "").lower().split("_")
    if any(t in DYNAMIC_WRITE_VERBS for t in tokens):
        return False
    return any(t in DYNAMIC_READ_VERBS for t in tokens)


def is_tool_allowed(server_name: str, tool_name: str) -> bool:
    spec = MCP_SERVER_REGISTRY.get(server_name)
    if not spec:
        return False
    if spec.dynamic_readonly:
        return is_dynamic_readonly_tool(tool_name)
    return tool_name in spec.allowed_tools


def allowed_tools(server_name: str) -> list[str]:
    spec = MCP_SERVER_REGISTRY.get(server_name)
    if not spec:
        return []
    if spec.dynamic_readonly:
        # Cannot enumerate thousands of tools; report the admission policy.
        return ["<dynamic read-only admission: get/search/list/query/... and no write verb>"]
    return sorted(spec.allowed_tools)


def resolve_launch_command(server_name: str) -> tuple[str, ...]:
    """Return the env-resolved launch command (falls back to the spec default)."""
    spec = MCP_SERVER_REGISTRY.get(server_name)
    if spec is None:
        return ()
    return _mcp_config.server_launch_command(server_name, default=spec.launch_command)


def list_servers() -> list[str]:
    return sorted(MCP_SERVER_REGISTRY)
