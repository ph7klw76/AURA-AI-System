"""Defensive outbound-MCP client.

Public surface:
  * ``call_mcp_tool(server, tool, arguments, session_id=None)`` -> ExternalMcpCallResult
  * ``is_mcp_available(server)`` -> bool
  * ``list_allowed_mcp_tools()`` -> dict

The client NEVER raises into the AURA orchestrator: connection errors,
malformed JSON, timeouts, missing SDK, and missing servers all become
structured ``ExternalMcpCallResult`` failures.

The real STDIO transport is implemented in :func:`_invoke_server`, which
lazily imports the ``mcp`` SDK so AURA core works without it installed.  Tests
monkeypatch ``_invoke_server`` to simulate success/timeout/unavailability.
"""
from __future__ import annotations

import concurrent.futures
import shutil
import time
from typing import Any

from . import policy, registry
from .config import McpOutboundConfig, load_config
from .schemas import ExternalMcpCallResult


class McpUnavailable(RuntimeError):
    """Raised internally when the SDK or the server binary is unavailable."""


def _leaf_exception(exc: BaseException) -> BaseException:
    """Recursively descend (Base)ExceptionGroups to the first leaf exception.

    anyio surfaces transport/protocol failures as nested ExceptionGroups; the
    useful cause (e.g. an MCP ``McpError``) is the leaf.
    """
    seen = exc
    for _ in range(20):  # bounded; avoid pathological cycles
        subs = getattr(seen, "exceptions", None)
        if not subs:
            return seen
        seen = subs[0]
    return seen


def _sdk_importable() -> bool:
    import importlib.util
    try:
        return importlib.util.find_spec("mcp") is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _resolve_launch_command(spec) -> tuple[str, ...]:
    """Env-resolved launch command for *spec* (falls back to the spec default)."""
    return registry.resolve_launch_command(spec.name) or tuple(spec.launch_command or ())


def _resolve_executable(spec) -> str | None:
    """Return the resolved launch executable if it exists on PATH, else None."""
    cmd = _resolve_launch_command(spec)
    if not cmd:
        return None
    return shutil.which(cmd[0])


def _server_env(spec) -> dict:
    """Build the subprocess env for *spec*, forwarding ONLY the token vars the
    server declares (e.g. GITHUB_PERSONAL_ACCESS_TOKEN).  Token VALUES are
    never logged anywhere.
    """
    import os
    env = dict(os.environ)  # inherit PATH etc.
    # (Tokens already in os.environ are forwarded as-is; we never print them.)
    return env


def _invoke_server(
    spec,
    tool_name: str,
    arguments: dict,
    *,
    timeout_seconds: int,
    config: McpOutboundConfig,
) -> Any:
    """Actually connect to the MCP server over STDIO and call *tool_name*.

    Lazily imports the MCP SDK.  Raises ``McpUnavailable`` when the SDK or the
    server binary is missing, ``TimeoutError`` on deadline, or other
    exceptions on transport/protocol failure — all of which the caller
    converts into a structured failure.
    """
    if not _sdk_importable():
        raise McpUnavailable("the 'mcp' SDK is not installed")

    cmd = _resolve_launch_command(spec)
    exe = _resolve_executable(spec)
    if exe is None:
        first = cmd[0] if cmd else "(none)"
        raise McpUnavailable(
            f"server executable {first!r} not found on PATH"
        )

    # Lazy SDK imports — only reached when the SDK + server binary exist.
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_env = _server_env(spec)

    async def _run() -> Any:
        params = StdioServerParameters(
            command=exe, args=list(cmd[1:]), env=server_env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                # Prefer structured content; fall back to text content.
                payload: Any = getattr(result, "structuredContent", None)
                if payload is None:
                    parts = []
                    for c in getattr(result, "content", []) or []:
                        text = getattr(c, "text", None)
                        if text is not None:
                            parts.append(text)
                    payload = "\n".join(parts) if parts else {}
                return payload

    def _runner() -> Any:
        return anyio.run(_run)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(_runner).result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError as exc:
        raise TimeoutError(
            f"MCP call to {spec.name}.{tool_name} exceeded {timeout_seconds}s"
        ) from exc
    finally:
        pool.shutdown(wait=False)


def call_mcp_tool(
    server_name: str,
    tool_name: str,
    arguments: dict | None = None,
    session_id: str | None = None,
    *,
    config: McpOutboundConfig | None = None,
) -> ExternalMcpCallResult:
    """Policy-gated, defensive outbound MCP tool call.

    Always returns an :class:`ExternalMcpCallResult`; never raises.
    """
    cfg = config or load_config()
    arguments = arguments if isinstance(arguments, dict) else {}
    started = time.monotonic()
    from .audit import utc_now
    started_at = utc_now()

    decision = policy.evaluate_call(server_name, tool_name, arguments, config=cfg)
    if not decision.allowed:
        return ExternalMcpCallResult(
            ok=False, server=server_name, tool=tool_name,
            error_type=decision.error_type or "policy_blocked",
            error=decision.reason, started_at=started_at,
        )

    spec = registry.get_server_spec(server_name)
    timeout_seconds = policy.select_timeout(server_name, tool_name, cfg)

    try:
        raw = _invoke_server(
            spec, tool_name, arguments,
            timeout_seconds=timeout_seconds, config=cfg,
        )
    except McpUnavailable as exc:
        return ExternalMcpCallResult(
            ok=False, server=server_name, tool=tool_name,
            error_type="mcp_unavailable", error=str(exc),
            duration_seconds=time.monotonic() - started, started_at=started_at,
        )
    except TimeoutError as exc:
        return ExternalMcpCallResult(
            ok=False, server=server_name, tool=tool_name,
            error_type="timeout", error=str(exc),
            duration_seconds=time.monotonic() - started, started_at=started_at,
        )
    except (ConnectionError, BrokenPipeError, OSError) as exc:
        return ExternalMcpCallResult(
            ok=False, server=server_name, tool=tool_name,
            error_type="connection_error", error=str(exc),
            duration_seconds=time.monotonic() - started, started_at=started_at,
        )
    except (ValueError, TypeError) as exc:
        # Malformed JSON / protocol payloads land here.
        return ExternalMcpCallResult(
            ok=False, server=server_name, tool=tool_name,
            error_type="malformed_result", error=str(exc),
            duration_seconds=time.monotonic() - started, started_at=started_at,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the orchestrator
        # anyio wraps transport/tool failures in nested ExceptionGroups; unwrap
        # to the leaf so the real cause (e.g. an MCP "unknown tool" / tool
        # error) is surfaced instead of an opaque "ExceptionGroup".
        leaf = _leaf_exception(exc)
        leaf_name = type(leaf).__name__
        leaf_msg = str(leaf)
        lowered = leaf_msg.lower()
        if "unknown tool" in lowered or "tool not found" in lowered:
            error_type = "unknown_tool"
        elif leaf_name == "McpError":
            error_type = "tool_error"
        else:
            error_type = "unexpected_error"
        return ExternalMcpCallResult(
            ok=False, server=server_name, tool=tool_name,
            error_type=error_type, error=f"{leaf_name}: {leaf_msg}"[:300],
            duration_seconds=time.monotonic() - started, started_at=started_at,
        )

    # Result-size guard.
    try:
        import json as _json
        size = len(_json.dumps(raw, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        size = 0
    if size > cfg.max_result_bytes:
        return ExternalMcpCallResult(
            ok=False, server=server_name, tool=tool_name,
            error_type="result_too_large",
            error=f"result {size} bytes > {cfg.max_result_bytes}",
            duration_seconds=time.monotonic() - started, started_at=started_at,
        )

    # mock_mode is only ever True if the user explicitly allowed it AND the
    # server flagged synthetic output.
    mock_flag = bool(cfg.allow_mock) and bool(
        isinstance(raw, dict) and raw.get("mock_mode")
    )

    return ExternalMcpCallResult(
        ok=True, server=server_name, tool=tool_name, raw_result=raw,
        duration_seconds=time.monotonic() - started, mock_mode=mock_flag,
        started_at=started_at,
    )


def is_mcp_available(server_name: str, *, config: McpOutboundConfig | None = None) -> bool:
    """Best-effort availability check.  False unless outbound is enabled, the
    server is allowlisted, the SDK is importable, and the executable resolves.
    Never raises.
    """
    cfg = config or load_config()
    if not cfg.outbound_enabled:
        return False
    spec = registry.get_server_spec(server_name)
    if spec is None:
        return False
    if spec.is_network and not cfg.allow_network_servers:
        return False
    try:
        return _sdk_importable() and _resolve_executable(spec) is not None
    except Exception:  # noqa: BLE001
        return False


def is_external_mcp_available(
    server_name: str, *, config: McpOutboundConfig | None = None,
) -> bool:
    """True only when this specific server is ENABLED and reachable.

    Stricter than :func:`is_mcp_available`: also requires the per-server
    enable flag (AURA_MCP_USE_*).  Never raises.
    """
    cfg = config or load_config()
    from .config import server_enabled
    if not server_enabled(server_name):
        return False
    return is_mcp_available(server_name, config=cfg)


def list_allowed_mcp_tools(*, config: McpOutboundConfig | None = None) -> dict:
    """Return the allowlisted servers/tools, their enablement and availability."""
    cfg = config or load_config()
    from .config import server_enabled
    out: dict[str, dict] = {}
    for name in registry.list_servers():
        spec = registry.get_server_spec(name)
        out[name] = {
            "tools": registry.allowed_tools(name),
            "is_network": bool(spec.is_network) if spec else False,
            "enabled": server_enabled(name),
            "available": is_external_mcp_available(name, config=cfg),
        }
    return out
