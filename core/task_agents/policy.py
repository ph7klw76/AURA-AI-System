"""Policy enforcement for task-scoped agent specs.

Every AgentSpec must pass validation before a task agent may be created or
executed.  Policy is deterministic — no LLM decisions at this layer.
"""

from __future__ import annotations

import os
from typing import Tuple

from .schemas import AgentSpec

# ---------------------------------------------------------------------------
# Configurable bounds (env‑var overridable, clamped by hard policy ceilings)
# ---------------------------------------------------------------------------
_MAX_STEPS = int(os.getenv("AURA_TASK_AGENTS_MAX_STEPS", "5"))
_MAX_TIMEOUT = 300
_MAX_PER_SESSION = int(os.getenv("AURA_TASK_AGENTS_MAX_PER_SESSION", "3"))


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


# ---------------------------------------------------------------------------
# Blocked tool patterns — any tool name matching one of these is rejected
# (prefix match on dot-separated namespaces).
# ---------------------------------------------------------------------------
_BLOCKED_TOOL_PATTERNS: tuple[str, ...] = (
    "shell.",
    "os.",
    "subprocess.",
    "github.write.",
    "github.merge.",
    "github.delete.",
    "github.release.",
    "github.create.",
    "github.update.",
    "github.push.",
    "github.fork.",
    "memory.write",
    "profile.write",
    "evolution.approve",
    "draft.persist",
    "email.send",
    "grant.submit",
    "patent.file",
)

# ---------------------------------------------------------------------------
# Allowed tool namespace prefixes.  A tool IS allowed if it starts with any
# of these.  Everything else is blocked (fail-closed).
# ---------------------------------------------------------------------------
_ALLOWED_TOOL_PREFIXES: tuple[str, ...] = (
    "aura.internal.",
    "aura.mcp.local_deep_research.",
    "aura.mcp.idea_reality.",
    "aura.mcp.github.",
    "aura.mcp.paper_qa.",
    "aura.mcp.tooluniverse.",
)


def validate_agent_spec(spec: AgentSpec) -> tuple[bool, list[str]]:
    """Validate *spec* against all policy rules.

    Returns ``(ok, errors)`` — structured errors, never raises.
    """
    errors: list[str] = []

    # --- hard capability blocks ---
    if spec.can_spawn_agents:
        errors.append("can_spawn_agents must be False — task agents may not spawn agents")
    if spec.can_modify_memory:
        errors.append("can_modify_memory must be False — task agents may not modify memory")
    if spec.can_modify_profile:
        errors.append("can_modify_profile must be False — task agents may not modify profiles")
    if spec.persistence_allowed:
        errors.append("persistence_allowed must be False — task agents may not persist drafts")
    if spec.can_write_files:
        errors.append("can_write_files must be False in this phase")

    # --- bounds ---
    if spec.max_steps > _MAX_STEPS:
        errors.append(f"max_steps {spec.max_steps} exceeds limit {_MAX_STEPS}")
    if spec.timeout_seconds > _MAX_TIMEOUT:
        errors.append(f"timeout_seconds {spec.timeout_seconds} exceeds limit {_MAX_TIMEOUT}")

    # --- verifier gating ---
    if not spec.verifier_required:
        errors.append("verifier_required must be True — task agents cannot bypass the Scientific Verifier")
    if spec.risk_level == "high" and not spec.human_review_required:
        errors.append("human_review_required must be True for high-risk task agents")

    # --- external MCP gate ---
    if spec.allowed_mcp_servers and not spec.can_call_external_mcp:
        errors.append(
            "allowed_mcp_servers is non-empty but can_call_external_mcp is False"
        )

    # --- tool validation ---
    for tool in spec.allowed_tools:
        tool_err = _validate_tool(tool)
        if tool_err:
            errors.append(f"tool '{tool}': {tool_err}")

    # --- forbid tools ---
    for tool in spec.forbidden_tools:
        if tool in spec.allowed_tools:
            errors.append(f"tool '{tool}' is both allowed and forbidden — rejected")

    return len(errors) == 0, errors


def _validate_tool(tool: str) -> str | None:
    """Check a single tool name against blocked patterns and allowed prefixes.

    Returns an error string or None.
    """
    # Blocked patterns (fail first)
    for blocked in _BLOCKED_TOOL_PATTERNS:
        if tool.startswith(blocked) or tool == blocked.rstrip("."):
            return f"matches blocked pattern '{blocked}'"

    # Must match at least one allowed prefix
    for prefix in _ALLOWED_TOOL_PREFIXES:
        if tool.startswith(prefix):
            return None  # OK

    return f"does not match any allowed namespace prefix"


def is_task_agents_enabled() -> bool:
    """Check whether task agents are globally enabled."""
    return _env_bool("AURA_TASK_AGENTS_ENABLED", False)


def max_per_session() -> int:
    return _MAX_PER_SESSION


def verifier_required_by_default() -> bool:
    return _env_bool("AURA_TASK_AGENTS_REQUIRE_VERIFIER", True)
