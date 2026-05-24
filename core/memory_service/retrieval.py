"""Namespace-aware memory retrieval for AURA sessions.

Retrieves memories from LangGraph Memory Service scoped to the active user,
project, session, and agent.  All retrieval failures are degraded warnings —
they never crash AURA.
"""
from __future__ import annotations

from .audit import log_retrieval_requested, log_retrieval_succeeded, log_retrieval_failed
from .client import search_memories
from .config import MemoryServiceConfig, load_memory_service_config, is_memory_service_enabled
from .schemas import MemoryRetrievalRequest, MemoryRetrievalResult

# ---------------------------------------------------------------------------
# Namespace builders
# ---------------------------------------------------------------------------

_NS = list[str]


def _user_namespace(user_id: str, ns_type: str) -> _NS:
    return ["aura", "user", user_id or "default", ns_type]


def _project_namespace(project_id: str, ns_type: str) -> _NS:
    return ["aura", "project", project_id or "default", ns_type]


def _agent_namespace(agent_name: str, project_id: str) -> _NS:
    return ["aura", "agent", agent_name or "unknown", project_id or "default"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_relevant_memories(
    prompt: str,
    session_id: str = "",
    *,
    user_id: str = "",
    project_id: str = "",
    agent_name: str = "",
    memory_types: list[str] | None = None,
    config: MemoryServiceConfig | None = None,
) -> MemoryRetrievalResult:
    """Retrieve memories relevant to the current session.

    Returns ``MemoryRetrievalResult(ok=True, memories=[])`` when disabled
    or the service is unreachable.
    """
    cfg = config or load_memory_service_config()

    log_retrieval_requested(session_id, prompt, agent_name, memory_types)

    if not cfg.enabled:
        log_retrieval_succeeded(session_id, 0)
        return MemoryRetrievalResult(
            ok=True,
            memories=[],
            warnings=["Memory service is disabled."],
            degraded=False,
        )

    # Determine which memory types to query
    if memory_types is None or len(memory_types) == 0:
        memory_types = [
            "user_preference",
            "research_profile",
            "project_decision",
            "project_memory",
            "procedural_memory",
            "repository_memory",
        ]

    request = MemoryRetrievalRequest(
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        prompt=prompt,
        agent_name=agent_name,
        memory_types=memory_types,
        max_results=cfg.max_retrieved,
    )

    result = search_memories(request, config=cfg)

    if not result.ok or result.degraded:
        log_retrieval_failed(session_id, result.errors)
    else:
        log_retrieval_succeeded(session_id, len(result.memories))

    return result


def build_memory_context(
    prompt: str,
    session_id: str = "",
    *,
    user_id: str = "",
    project_id: str = "",
    agent_name: str = "",
) -> str:
    """Convenience: retrieve + return compact context string.

    Returns ``""`` when the memory service is disabled.
    """
    result = retrieve_relevant_memories(
        prompt=prompt,
        session_id=session_id,
        user_id=user_id,
        project_id=project_id,
        agent_name=agent_name,
    )
    return result.compact_context
