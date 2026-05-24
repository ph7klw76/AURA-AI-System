"""Safe HTTP wrapper around LangGraph Memory Service.

This module wraps the LangGraph Memory Service REST API.  It does NOT depend
on any SDK — plain ``urllib.request`` calls are used so the package has zero
external dependencies beyond the Python standard library.

All errors are caught and returned as structured results.  The memory service
must never crash AURA.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .config import MemoryServiceConfig, load_memory_service_config
from .schemas import (
    AURAMemoryRecord,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    MemoryWriteDecisionResult,
)

# ---------------------------------------------------------------------------
# Health / availability
# ---------------------------------------------------------------------------

def memory_service_available(config: MemoryServiceConfig | None = None) -> bool:
    """Check whether the LangGraph Memory Service is reachable.

    Returns False if the service is disabled or unreachable.
    """
    cfg = config or load_memory_service_config()
    if not cfg.enabled:
        return False
    try:
        req = urllib.request.Request(
            f"{cfg.service_url.rstrip('/')}/ok",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:
            return resp.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _namespace_filter(memory_types: list[str], ns_prefix: str) -> dict[str, object] | None:
    """Build a namespace filter for the LangGraph Memory API.

    Returns ``None`` when no filter is needed (all namespaces).
    """
    if not memory_types:
        return None
    namespaces: list[list[str]] = []
    for mt in memory_types:
        namespaces.append([ns_prefix, mt])
    return {"namespaces": namespaces} if namespaces else None


def search_memories(
    request: MemoryRetrievalRequest,
    config: MemoryServiceConfig | None = None,
) -> MemoryRetrievalResult:
    """Search memories via the LangGraph Memory Service HTTP API.

    On any failure (timeout, connection refused, bad response) returns a
    degraded ``MemoryRetrievalResult`` with ``ok=True, degraded=True`` so
    the caller can continue without crashing.
    """
    cfg = config or load_memory_service_config()

    if not cfg.enabled:
        return MemoryRetrievalResult(
            ok=True,
            degraded=False,
            warnings=["Memory service is disabled."],
        )

    results: list[AURAMemoryRecord] = []
    warnings: list[str] = []
    errors: list[str] = []

    payload: dict[str, object] = {
        "query": request.prompt,
        "limit": min(request.max_results or cfg.max_retrieved, cfg.max_retrieved),
    }
    ns_filter = _namespace_filter(request.memory_types, cfg.namespace_prefix)
    if ns_filter:
        payload["filter"] = ns_filter

    try:
        url = f"{cfg.service_url.rstrip('/')}/memories"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        if isinstance(body, list):
            raw = body
        elif isinstance(body, dict):
            raw = body.get("results") or body.get("memories") or []
        else:
            raw = []

        for item in raw:
            try:
                record = AURAMemoryRecord(
                    memory_id=str(item.get("id") or item.get("memory_id") or ""),
                    memory_type=item.get("memory_type", "unknown"),
                    namespace=list(item.get("namespace") or []),
                    key=str(item.get("key") or ""),
                    content=item.get("content") or {},
                    source_session_id=str(item.get("source_session_id") or ""),
                    source_agent=str(item.get("source_agent") or ""),
                    confidence=item.get("confidence", "medium"),
                    evidence_status=str(item.get("evidence_status") or "unverified"),
                    verifier_route=str(item.get("verifier_route") or ""),
                    requires_verifier=bool(item.get("requires_verifier")),
                    requires_human_review=bool(item.get("requires_human_review")),
                    created_at=str(item.get("created_at") or ""),
                    updated_at=str(item.get("updated_at") or ""),
                    tags=list(item.get("tags") or []),
                    limitations=list(item.get("limitations") or []),
                )
                results.append(record)
            except Exception as parse_exc:
                warnings.append(f"Skipped unparseable memory: {parse_exc}")

    except urllib.error.HTTPError as exc:
        errors.append(f"Memory service HTTP {exc.code}: {exc.reason}")
        if cfg.fail_closed:
            return MemoryRetrievalResult(
                ok=False, degraded=True, errors=errors, warnings=warnings,
            )
        warnings.append(f"Memory service HTTP {exc.code} — degraded retrieval.")
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        warnings.append(f"Memory service unreachable: {reason}")
        if cfg.fail_closed:
            return MemoryRetrievalResult(
                ok=False, degraded=True, errors=[reason], warnings=warnings,
            )
    except Exception as exc:
        errors.append(f"Memory service retrieval error: {exc}")
        if cfg.fail_closed:
            return MemoryRetrievalResult(
                ok=False, degraded=True, errors=errors, warnings=warnings,
            )
        warnings.append(f"Memory service retrieval degraded: {exc}")

    # Build compact context
    lines: list[str] = []
    for mem in results:
        tag = f"[{mem.memory_type}]"
        verif = f" (verifier={mem.verifier_route})" if mem.verifier_route else ""
        lines.append(f"{tag}{verif} {json.dumps(mem.content)}")
    compact = "\n".join(lines)

    return MemoryRetrievalResult(
        ok=True,
        memories=results,
        warnings=warnings,
        errors=errors,
        degraded=bool(warnings or errors),
        compact_context=compact,
    )


# ---------------------------------------------------------------------------
# Write support (Stage 2-3)
# ---------------------------------------------------------------------------

def propose_memory(
    record: dict[str, object],
    *,
    config: MemoryServiceConfig | None = None,
) -> dict[str, object]:
    """Propose a memory record to the LangGraph Memory Service.

    In ``propose_only`` mode the record is sent as a proposal (pending).
    In ``approved_only`` mode it is committed immediately.

    Returns ``{"ok": True, "memory_id": "..."}`` on success.
    Returns ``{"ok": False, "error": "..."}`` on failure.
    """
    cfg = config or load_memory_service_config()

    if cfg.write_disabled:
        return {"ok": False, "error": "Memory writes are disabled."}

    payload: dict[str, object] = {
        "action": "propose" if cfg.propose_only else "put",
        "record": record,
        "write_mode": cfg.write_mode,
    }

    try:
        url = f"{cfg.service_url.rstrip('/')}/memories"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if isinstance(body, dict):
                return {
                    "ok": True,
                    "memory_id": str(body.get("id") or body.get("memory_id") or ""),
                    "status": body.get("status", "proposed"),
                }
            return {"ok": True, "memory_id": ""}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}: {exc.reason}"}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"Unreachable: {exc.reason}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def commit_approved_memory(
    record: dict[str, object],
    *,
    config: MemoryServiceConfig | None = None,
) -> dict[str, object]:
    """Commit an approved memory record to the LangGraph Memory Service.

    Returns ``{"ok": True, "memory_id": "..."}`` on success.
    Returns ``{"ok": False, "error": "..."}`` on failure.
    """
    cfg = config or load_memory_service_config()

    if cfg.write_disabled:
        return {"ok": False, "error": "Memory writes are disabled."}

    payload: dict[str, object] = {
        "action": "put",
        "record": record,
    }

    try:
        url = f"{cfg.service_url.rstrip('/')}/memories"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=cfg.timeout_seconds) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if isinstance(body, dict):
                return {
                    "ok": True,
                    "memory_id": str(body.get("id") or body.get("memory_id") or ""),
                }
            return {"ok": True, "memory_id": ""}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}: {exc.reason}"}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": f"Unreachable: {exc.reason}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def delete_memory(
    memory_id: str,
    *,
    config: MemoryServiceConfig | None = None,
) -> dict[str, object]:
    """Delete a memory record — NOT IMPLEMENTED in MVP.

    Requires explicit human approval before use.
    """
    return {
        "ok": False,
        "error": "Delete is not implemented. Requires explicit human approval.",
    }
