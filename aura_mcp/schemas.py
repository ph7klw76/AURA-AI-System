"""AURA MCP — lightweight input validation.

Deliberately plain (no pydantic coupling) so the MCP layer stays a thin
adapter.  Each validator returns ``(cleaned: dict, errors: list[str])``.  When
``errors`` is non-empty the caller should short-circuit with an error
envelope and NOT invoke any AURA workflow.

These also double as the JSON-Schemas advertised to MCP clients via
``TOOL_INPUT_SCHEMAS``.
"""
from __future__ import annotations

from typing import Any

DEEP_RESEARCH_DEPTHS: tuple[str, ...] = ("rapid", "standard", "extensive")


def _as_clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def validate_health_input(args: dict | None) -> tuple[dict, list[str]]:
    args = args or {}
    check_llm = bool(args.get("check_llm", False))
    return {"check_llm": check_llm}, []


def validate_research_input(args: dict | None) -> tuple[dict, list[str]]:
    args = args or {}
    errors: list[str] = []
    prompt = _as_clean_str(args.get("prompt"))
    if not prompt:
        errors.append("'prompt' is required and must be a non-empty string.")

    session_id = args.get("session_id")
    if session_id is not None and not isinstance(session_id, str):
        errors.append("'session_id' must be a string or null.")
        session_id = None

    max_runtime = args.get("max_runtime_seconds")
    if max_runtime is not None:
        try:
            max_runtime = int(max_runtime)
            if max_runtime <= 0:
                errors.append("'max_runtime_seconds' must be a positive integer.")
                max_runtime = None
        except (TypeError, ValueError):
            errors.append("'max_runtime_seconds' must be an integer or null.")
            max_runtime = None

    return {
        "prompt": prompt,
        "session_id": session_id if isinstance(session_id, str) else None,
        "max_runtime_seconds": max_runtime,
    }, errors


def validate_deep_research_input(args: dict | None) -> tuple[dict, list[str]]:
    args = args or {}
    errors: list[str] = []
    query = _as_clean_str(args.get("query"))
    if not query:
        errors.append("'query' is required and must be a non-empty string.")

    depth = _as_clean_str(args.get("depth")) or "standard"
    if depth not in DEEP_RESEARCH_DEPTHS:
        errors.append(
            f"'depth' must be one of {DEEP_RESEARCH_DEPTHS}; got {depth!r}."
        )
        depth = "standard"

    return {"query": query, "depth": depth}, errors


def validate_verify_claims_input(args: dict | None) -> tuple[dict, list[str]]:
    args = args or {}
    errors: list[str] = []

    raw_claims = args.get("claims")
    claims: list[str] = []
    if not isinstance(raw_claims, list) or not raw_claims:
        errors.append("'claims' is required and must be a non-empty list of strings.")
    else:
        for c in raw_claims:
            if isinstance(c, str) and c.strip():
                claims.append(c.strip())
        if not claims:
            errors.append("'claims' must contain at least one non-empty string.")

    raw_evidence = args.get("evidence")
    evidence: list[dict] = []
    if raw_evidence is None:
        evidence = []
    elif not isinstance(raw_evidence, list):
        errors.append("'evidence' must be a list of objects or null.")
    else:
        for e in raw_evidence:
            if isinstance(e, dict):
                evidence.append(e)

    context = args.get("context")
    if context is not None and not isinstance(context, str):
        errors.append("'context' must be a string or null.")
        context = None

    return {
        "claims": claims,
        "evidence": evidence,
        "context": context if isinstance(context, str) else None,
    }, errors


def validate_get_report_input(args: dict | None) -> tuple[dict, list[str]]:
    args = args or {}
    errors: list[str] = []
    report_path = _as_clean_str(args.get("report_path"))
    if not report_path:
        errors.append("'report_path' is required and must be a non-empty string.")
    return {"report_path": report_path}, errors


# ---------------------------------------------------------------------------
# JSON-Schemas advertised to MCP clients (Phase 1).
# ---------------------------------------------------------------------------

TOOL_INPUT_SCHEMAS: dict[str, dict] = {
    "aura_health": {
        "type": "object",
        "properties": {
            "check_llm": {
                "type": "boolean",
                "description": "If true, attempt a tiny LLM connectivity probe.",
                "default": False,
            },
        },
        "additionalProperties": False,
    },
    "aura_research": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "session_id": {"type": ["string", "null"]},
            "max_runtime_seconds": {"type": ["integer", "null"]},
        },
        "required": ["prompt"],
        "additionalProperties": False,
    },
    "aura_deep_research": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "depth": {"type": "string", "enum": list(DEEP_RESEARCH_DEPTHS)},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "aura_verify_claims": {
        "type": "object",
        "properties": {
            "claims": {"type": "array", "items": {"type": "string"}},
            "evidence": {"type": "array", "items": {"type": "object"}},
            "context": {"type": ["string", "null"]},
        },
        "required": ["claims"],
        "additionalProperties": False,
    },
    "aura_list_reports": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "aura_get_report": {
        "type": "object",
        "properties": {"report_path": {"type": "string"}},
        "required": ["report_path"],
        "additionalProperties": False,
    },
}
