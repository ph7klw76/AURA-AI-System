"""Outbound-MCP configuration — safe by default.

Configuration is read at CALL TIME (not import time) from environment
variables, with an optional YAML overlay.  Defaults are deliberately the
safest possible posture:

  * outbound MCP DISABLED unless explicitly enabled,
  * network servers DISABLED,
  * mock external output DISABLED,
  * no automatic memory/profile writes (the gateway never writes them).

Environment variables
---------------------
  AURA_MCP_OUTBOUND_ENABLED          0/1   (default 0)
  AURA_MCP_ALLOW_NETWORK_SERVERS     0/1   (default 0)
  AURA_MCP_ALLOW_MOCK                0/1   (default 0)
  AURA_MCP_TIMEOUT_SECONDS           int   (default 60)
  AURA_MCP_RESEARCH_TIMEOUT_SECONDS  int   (default 1800)
  AURA_MCP_AUDIT_LOG                 path  (default data/mcp_calls.jsonl)
  AURA_MCP_CONFIG_FILE               path  (optional YAML overlay)
  AURA_MCP_MAX_ARG_BYTES             int   (default 200000)
  AURA_MCP_MAX_RESULT_BYTES          int   (default 5000000)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import config as _aura_config

# Reuse AURA's robust env parsers (Phase 3) so a malformed value can never
# crash the gateway at call time.
from config import env_bool, env_int


@dataclass(frozen=True)
class McpOutboundConfig:
    outbound_enabled: bool = False
    require_verifier: bool = True
    allow_network_servers: bool = False
    allow_mock: bool = False
    timeout_seconds: int = 60
    research_timeout_seconds: int = 1800
    audit_log_path: Path = field(
        default_factory=lambda: _aura_config.BASE_DIR / "data" / "mcp_calls.jsonl"
    )
    max_arg_bytes: int = 200_000
    max_result_bytes: int = 5_000_000
    # Per-server enable flags (all OFF by default).
    use_local_deep_research: bool = False
    use_idea_reality: bool = False
    use_github: bool = False
    use_tooluniverse: bool = False
    use_open_coscientist: bool = False


# Per-server enable env vars + launch-command env vars.  These let an operator
# point AURA at an installed external MCP server WITHOUT hardcoding a fragile
# command in source.  Everything is OFF / unset by default.
SERVER_ENABLE_ENV: dict[str, str] = {
    "local_deep_research": "AURA_MCP_USE_LOCAL_DEEP_RESEARCH",
    "idea_reality": "AURA_MCP_USE_IDEA_REALITY",
    "github": "AURA_MCP_USE_GITHUB",
    "tooluniverse": "AURA_MCP_USE_TOOLUNIVERSE",
    "open_coscientist": "AURA_MCP_USE_OPEN_COSCIENTIST",
}
SERVER_COMMAND_ENV: dict[str, tuple[str, str]] = {
    # server_name -> (command_env_var, args_env_var)
    "local_deep_research": ("AURA_LDR_MCP_COMMAND", "AURA_LDR_MCP_ARGS"),
    "idea_reality": ("AURA_IDEA_REALITY_MCP_COMMAND", "AURA_IDEA_REALITY_MCP_ARGS"),
    "github": ("AURA_GITHUB_MCP_COMMAND", "AURA_GITHUB_MCP_ARGS"),
    "tooluniverse": ("AURA_TOOLUNIVERSE_MCP_COMMAND", "AURA_TOOLUNIVERSE_MCP_ARGS"),
    "open_coscientist": ("AURA_OPEN_COSCIENTIST_MCP_COMMAND", "AURA_OPEN_COSCIENTIST_MCP_ARGS"),
}


def server_enabled(server_name: str) -> bool:
    """Return True only if this specific external server is explicitly enabled.

    Read at call time so runtime env changes are honoured.  Default OFF.
    """
    env = SERVER_ENABLE_ENV.get(server_name)
    return env_bool(env, False) if env else False


def server_launch_command(server_name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Resolve a server's launch command from env, falling back to *default*.

    ``AURA_<SERVER>_MCP_COMMAND`` sets the executable; ``..._ARGS`` sets the
    (shell-split) arguments.  When unset, the registry default is used.  This
    never executes anything — it only assembles the token tuple for the policy
    command whitelist + the STDIO client.
    """
    pair = SERVER_COMMAND_ENV.get(server_name)
    if not pair:
        return default
    cmd_env, args_env = pair
    cmd = os.getenv(cmd_env, "").strip()
    if not cmd:
        return default
    args_raw = os.getenv(args_env, "").strip()
    if args_raw:
        import shlex
        try:
            args = shlex.split(args_raw, posix=(os.name != "nt"))
        except ValueError:
            args = args_raw.split()
    else:
        args = []
    return (cmd, *args)


def _load_yaml_overlay() -> dict:
    """Load an optional YAML overlay (env still wins).  Never raises."""
    path = os.getenv("AURA_MCP_CONFIG_FILE", "").strip()
    if not path:
        return {}
    try:
        p = Path(path)
        if not p.is_absolute():
            p = _aura_config.BASE_DIR / p
        if not p.exists():
            return {}
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — config overlay must never crash startup
        return {}


def _yaml_bool(overlay: dict, key: str, default: bool) -> bool:
    val = overlay.get(key)
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, str)):
        return str(val).strip().lower() in ("1", "true", "yes", "on")
    return default


def _yaml_int(overlay: dict, key: str, default: int) -> int:
    val = overlay.get(key)
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def load_config() -> McpOutboundConfig:
    """Build the effective outbound-MCP config (env wins over YAML overlay)."""
    overlay = _load_yaml_overlay()

    audit_raw = os.getenv("AURA_MCP_AUDIT_LOG", "").strip() or str(
        overlay.get("audit_log") or "data/mcp_calls.jsonl"
    )
    audit_path = Path(audit_raw)
    if not audit_path.is_absolute():
        audit_path = _aura_config.BASE_DIR / audit_path

    return McpOutboundConfig(
        outbound_enabled=env_bool(
            "AURA_MCP_OUTBOUND_ENABLED",
            _yaml_bool(overlay, "outbound_enabled", False),
        ),
        require_verifier=env_bool(
            "AURA_MCP_REQUIRE_VERIFIER",
            _yaml_bool(overlay, "require_verifier", True),
        ),
        use_local_deep_research=server_enabled("local_deep_research"),
        use_idea_reality=server_enabled("idea_reality"),
        use_github=server_enabled("github"),
        use_tooluniverse=server_enabled("tooluniverse"),
        use_open_coscientist=server_enabled("open_coscientist"),
        allow_network_servers=env_bool(
            "AURA_MCP_ALLOW_NETWORK_SERVERS",
            _yaml_bool(overlay, "allow_network_servers", False),
        ),
        allow_mock=env_bool(
            "AURA_MCP_ALLOW_MOCK",
            _yaml_bool(overlay, "allow_mock", False),
        ),
        timeout_seconds=env_int(
            "AURA_MCP_TIMEOUT_SECONDS",
            _yaml_int(overlay, "timeout_seconds", 60),
        ),
        research_timeout_seconds=env_int(
            "AURA_MCP_RESEARCH_TIMEOUT_SECONDS",
            _yaml_int(overlay, "research_timeout_seconds", 1800),
        ),
        audit_log_path=audit_path,
        max_arg_bytes=env_int(
            "AURA_MCP_MAX_ARG_BYTES",
            _yaml_int(overlay, "max_arg_bytes", 200_000),
        ),
        max_result_bytes=env_int(
            "AURA_MCP_MAX_RESULT_BYTES",
            _yaml_int(overlay, "max_result_bytes", 5_000_000),
        ),
    )
