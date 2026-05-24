"""Optional LangGraph Memory Service adapter — Stage 1 (retrieval only).

This package is **disabled by default** (``AURA_MEMORY_SERVICE_ENABLED=0``).
When enabled it provides cross-session long-term memory via the LangGraph
Memory Service REST API, but all writes are gated behind policy, verifier,
and human-review checks.

Stage 1 capabilities:
  - Configuration via environment variables
  - Structured Pydantic v2 schemas
  - Safe HTTP client wrapper (no SDK dependency)
  - Namespace-aware retrieval
  - JSONL audit logging

Public API:
    from core.memory_service import (
        is_memory_service_enabled,
        load_memory_service_config,
        retrieve_relevant_memories,
        build_memory_context,
        memory_service_available,
        AURAMemoryRecord,
        MemoryRetrievalRequest,
        MemoryRetrievalResult,
    )
"""
from __future__ import annotations

from .config import is_memory_service_enabled, load_memory_service_config, MemoryServiceConfig
from .client import memory_service_available
from .retrieval import retrieve_relevant_memories, build_memory_context
from .schemas import (
    AURAMemoryRecord,
    MemoryCandidate,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    MemoryWriteDecisionResult,
)

__all__ = [
    # config
    "is_memory_service_enabled",
    "load_memory_service_config",
    "MemoryServiceConfig",
    # client
    "memory_service_available",
    # retrieval
    "retrieve_relevant_memories",
    "build_memory_context",
    # schemas
    "AURAMemoryRecord",
    "MemoryCandidate",
    "MemoryRetrievalRequest",
    "MemoryRetrievalResult",
    "MemoryWriteDecisionResult",
]
