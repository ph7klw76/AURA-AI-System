"""Outbound-MCP policy enforcement.

Every outbound call is gated here BEFORE any subprocess is launched or any
network is touched.  Policy enforces:

  * outbound MCP must be explicitly enabled,
  * allowlisted servers only,
  * allowlisted tools only,
  * subprocess launch-command whitelist (no arbitrary shell),
  * network servers blocked unless explicitly allowed,
  * argument-size limit,
  * no shell metacharacters in the launch command.

It performs NO writes, NO memory/profile mutation, and NO self-evolution
approval — the gateway simply has no code paths for those.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from . import registry
from .config import McpOutboundConfig

# Executable basenames permitted to launch a subprocess MCP server.  Anything
# else — and any token containing a shell metacharacter — is rejected.
COMMAND_WHITELIST: frozenset[str] = frozenset({
    "python", "python3", "python.exe",
    "uv", "uvx", "npx", "node",
    "docker", "docker.exe",
    # LearningCircuit/local-deep-research console scripts (real binary is
    # ``ldr-mcp``; ``local-deep-research-mcp`` kept for older installs).
    "ldr-mcp", "ldr-mcp.exe",
    "local-deep-research-mcp", "local-deep-research-mcp.exe",
    "idea-reality-mcp", "idea-reality-mcp.exe",
    "github-mcp-server", "github-mcp-server.exe",
    # ToolUniverse (mims-harvard) STDIO MCP server console scripts.
    "tooluniverse-smcp-stdio", "tooluniverse-smcp-stdio.exe",
    "tooluniverse", "tooluniverse.exe",
})

# Characters that indicate shell-injection intent — never allowed in a
# launch-command token.
_SHELL_METACHARS = (";", "&", "|", "`", "$", "(", ")", "<", ">", "\n", "\r", "*", "?", "{", "}", "\\", "!")


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""
    error_type: str | None = None


def _basename(token: str) -> str:
    return os.path.basename(token.strip())


def validate_launch_command(command) -> PolicyDecision:
    """Validate a subprocess launch command against the whitelist.

    Rejects empty commands, shell metacharacters, and any executable whose
    basename is not on :data:`COMMAND_WHITELIST`.
    """
    if not command or not isinstance(command, (list, tuple)):
        return PolicyDecision(False, "Empty or non-list launch command.", "policy_blocked")
    tokens = [str(t) for t in command]
    for tok in tokens:
        if any(ch in tok for ch in _SHELL_METACHARS):
            return PolicyDecision(
                False,
                f"Launch command token contains a shell metacharacter: {tok!r}.",
                "policy_blocked",
            )
    exe = _basename(tokens[0])
    if exe not in COMMAND_WHITELIST:
        return PolicyDecision(
            False,
            f"Executable {exe!r} is not on the MCP command whitelist.",
            "policy_blocked",
        )
    return PolicyDecision(True, "launch command ok")


def _argument_size_bytes(arguments: dict) -> int:
    try:
        return len(json.dumps(arguments, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return 0


def is_server_enabled(server_name: str, config: McpOutboundConfig) -> bool:
    """A specific external server must be EXPLICITLY enabled (default OFF)."""
    from .config import server_enabled
    return bool(config.outbound_enabled) and server_enabled(server_name)


def _github_tool_is_write(tool_name: str) -> bool:
    """Defense-in-depth: treat a GitHub tool as a write/mutation/admin tool if
    any underscore-separated TOKEN of its name is a known write verb.

    Token-boundary matching avoids false positives on legitimate consolidated
    READ tools (``issue_read``, ``pull_request_read``, ``actions_list``,
    ``actions_get``) and on reads like ``list_releases`` /
    ``get_pull_request_reviews``.  The explicit read-only allowlist in the
    registry remains the PRIMARY gate; this is the secondary guard.
    """
    tokens = (tool_name or "").lower().split("_")
    return any(tok in registry.GITHUB_WRITE_VERBS for tok in tokens)


def evaluate_call(
    server_name: str,
    tool_name: str,
    arguments: dict,
    *,
    config: McpOutboundConfig,
) -> PolicyDecision:
    """Gate a single outbound tool call.  Returns a structured decision."""
    if not config.outbound_enabled:
        return PolicyDecision(
            False, "Outbound MCP is disabled (AURA_MCP_OUTBOUND_ENABLED=0).",
            "outbound_disabled",
        )

    if not registry.is_server_allowed(server_name):
        return PolicyDecision(
            False, f"Server {server_name!r} is not on the allowlist.",
            "server_not_allowed",
        )

    spec = registry.get_server_spec(server_name)
    assert spec is not None  # guarded by is_server_allowed

    if not registry.is_tool_allowed(server_name, tool_name):
        return PolicyDecision(
            False,
            f"Tool {tool_name!r} is not allowlisted for server {server_name!r}.",
            "tool_not_allowed",
        )

    # GitHub: hard-block any write/admin/merge/delete/release tool even if it
    # somehow appeared in an allowlist (Phase 2/3 is READ-ONLY).
    if server_name == "github" and _github_tool_is_write(tool_name):
        return PolicyDecision(
            False,
            f"GitHub tool {tool_name!r} is a write/mutation/admin tool; "
            "AURA's GitHub MCP integration is READ-ONLY.",
            "github_write_blocked",
        )

    if spec.is_network and not config.allow_network_servers:
        return PolicyDecision(
            False,
            f"Server {server_name!r} is a network server; "
            "network MCP servers are disabled (AURA_MCP_ALLOW_NETWORK_SERVERS=0).",
            "network_blocked",
        )

    if not isinstance(arguments, dict):
        return PolicyDecision(False, "arguments must be a dict.", "bad_arguments")

    size = _argument_size_bytes(arguments)
    if size > config.max_arg_bytes:
        return PolicyDecision(
            False,
            f"arguments too large ({size} bytes > {config.max_arg_bytes}).",
            "argument_too_large",
        )

    # Non-STDIO transport is blocked by default (only stdio specs exist today).
    if spec.transport != "stdio":
        return PolicyDecision(
            False,
            f"Transport {spec.transport!r} is not allowed (STDIO only by default).",
            "transport_not_allowed",
        )

    # Subprocess launch-command whitelist (STDIO transport).  Validate the
    # ENV-RESOLVED command so an operator override is still policy-checked.
    resolved_cmd = registry.resolve_launch_command(server_name)
    cmd_decision = validate_launch_command(resolved_cmd)
    if not cmd_decision.allowed:
        return cmd_decision

    return PolicyDecision(True, "ok")


def select_timeout(server_name: str, tool_name: str, config: McpOutboundConfig) -> int:
    """Pick the research-grade timeout for long-running research tools."""
    spec = registry.get_server_spec(server_name)
    if spec and tool_name in spec.research_tools:
        return config.research_timeout_seconds
    return config.timeout_seconds
