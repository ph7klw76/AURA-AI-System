"""AURA MCP — a thin, read-only / governed Model Context Protocol adapter.

Phase 1 exposes AURA to external AI agents over **STDIO transport only**.  It
is a thin adapter: every generative or research workflow goes through AURA's
existing orchestrator (``core.orchestrator.run_aura_core``) so the Strategic
Governor, permission gates, Scientific Verifier, and draft-persistence rules
are NEVER bypassed.

Public surface:
    aura_mcp.policy        — tool allowlist + standard response envelope
    aura_mcp.schemas       — lightweight input validation
    aura_mcp.report_access — read-only, path-safe report access
    aura_mcp.server        — the MCP tool implementations + STDIO entrypoint
"""
from __future__ import annotations

__all__ = ["policy", "schemas", "report_access", "server"]

__version__ = "0.1.0"
