"""AURA MCP policy — tool allowlist + standard response envelope.

This module is the single source of truth for *which* tools the MCP server is
permitted to expose.  It is deliberately dependency-free (no AURA imports, no
MCP SDK) so it can be imported and asserted against in tests cheaply.

Safety posture (Phase 1):
  * Only the six read-only / governed tools below are exposed.
  * There are NO tools that mutate memory or profile, approve self-evolution,
    send email, publish content, submit grants, file patents, run shell
    commands, read arbitrary files, or access local document folders.
  * Every tool returns a structured envelope instead of raising.
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Allowlist — the ONLY tools the server may expose in Phase 1.
# ---------------------------------------------------------------------------

EXPOSED_TOOLS: tuple[str, ...] = (
    "aura_health",
    "aura_research",
    "aura_deep_research",
    "aura_verify_claims",
    "aura_list_reports",
    "aura_get_report",
)

# ---------------------------------------------------------------------------
# Explicitly-forbidden tool name fragments.  These are NOT implemented; the
# list documents the safety boundary and is asserted against in tests so a
# future regression that adds a dangerous tool fails loudly.
# ---------------------------------------------------------------------------

FORBIDDEN_TOOL_FRAGMENTS: tuple[str, ...] = (
    # memory / profile mutation
    "save_memory", "write_memory", "update_memory", "delete_memory",
    "save_profile", "write_profile", "update_profile", "mutate_profile",
    "edit_profile",
    # self-evolution approval / application
    "approve_evolution", "apply_evolution", "approve_proposal",
    "apply_proposal", "evolve_apply",
    # external consequences
    "send_email", "send_message", "publish", "post_linkedin", "submit_grant",
    "submit_proposal", "file_patent", "execute_trade", "make_payment",
    # raw system access
    "shell", "exec", "run_command", "subprocess", "read_file", "write_file",
    "delete_file", "open_folder", "local_folder", "local_documents",
)


def is_tool_allowed(name: str) -> bool:
    """Return True only for tools on the explicit allowlist."""
    return name in EXPOSED_TOOLS


def assert_no_forbidden_tools(tool_names: list[str]) -> list[str]:
    """Return any *tool_names* that match a forbidden fragment (should be []).

    Used by tests to prove the dangerous categories are not exposed.
    """
    bad: list[str] = []
    for name in tool_names:
        lowered = name.lower()
        if any(frag in lowered for frag in FORBIDDEN_TOOL_FRAGMENTS):
            bad.append(name)
    return bad


# ---------------------------------------------------------------------------
# Standard response envelope
# ---------------------------------------------------------------------------

def make_envelope(
    tool: str,
    *,
    ok: bool,
    data: dict | None = None,
    session_id: str | None = None,
    warnings: list | None = None,
    errors: list | None = None,
) -> dict[str, Any]:
    """Build the canonical JSON-serializable response envelope.

    Shape::

        {
          "ok": bool,
          "tool": "...",
          "session_id": "... optional ...",
          "data": {...},
          "warnings": [...],
          "errors": [...]
        }
    """
    env: dict[str, Any] = {
        "ok": bool(ok),
        "tool": tool,
        "data": data if isinstance(data, dict) else {},
        "warnings": list(warnings or []),
        "errors": list(errors or []),
    }
    # session_id is optional; include it whenever it is known (even if None
    # the key is meaningful for research tools).
    if session_id is not None:
        env["session_id"] = session_id
    return env


def error_envelope(
    tool: str,
    message: str,
    *,
    session_id: str | None = None,
    warnings: list | None = None,
) -> dict[str, Any]:
    """Convenience for a failed envelope carrying a single error string."""
    return make_envelope(
        tool, ok=False, session_id=session_id,
        warnings=warnings, errors=[message],
    )


def guarded(tool_name: str) -> Callable:
    """Decorator: never let a tool raise — convert exceptions to an error
    envelope so the MCP client always receives a structured result.
    """
    def deco(fn: Callable[..., dict]) -> Callable[..., dict]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> dict:
            if not is_tool_allowed(tool_name):
                return error_envelope(
                    tool_name, f"Tool {tool_name!r} is not on the MCP allowlist."
                )
            try:
                result = fn(*args, **kwargs)
                if not isinstance(result, dict):
                    return error_envelope(
                        tool_name,
                        f"Tool returned a non-dict result ({type(result).__name__}).",
                    )
                return result
            except Exception as exc:  # noqa: BLE001 — intentional catch-all
                return error_envelope(
                    tool_name, f"{type(exc).__name__}: {exc}"
                )
        return wrapper
    return deco
