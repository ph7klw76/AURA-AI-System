"""Optional LangGraph Memory Service adapter — retrieval + write pipeline.

This package is **enabled by default** (``AURA_MEMORY_SERVICE_ENABLED=1``).
When enabled it provides cross-session long-term memory via the LangGraph
Memory Service REST API, but all writes are gated behind policy, verifier,
and human-review checks.

Capabilities:
  - Configuration via environment variables
  - Structured Pydantic v2 schemas
  - Safe HTTP client wrapper (no SDK dependency)
  - Namespace-aware retrieval
  - Deterministic memory candidate extraction
  - Policy-gated write validation (secrets blocked, types validated)
  - Review pipeline → pending JSONL + approved commits
  - JSONL audit logging

Public API:
    from core.memory_service import (
        # Config
        is_memory_service_enabled,
        load_memory_service_config,
        # Retrieval
        retrieve_relevant_memories,
        build_memory_context,
        # Client
        memory_service_available,
        search_memories,
        # Pipeline (Stage 2-3)
        extract_memory_candidates_from_session,
        classify_memory_candidate,
        validate_memory_write,
        review_memory_candidates,
        # Schemas
        AURAMemoryRecord,
        MemoryCandidate,
        MemoryRetrievalRequest,
        MemoryRetrievalResult,
        MemoryWriteDecisionResult,
    )
"""
from __future__ import annotations

from .config import is_memory_service_enabled, load_memory_service_config, MemoryServiceConfig
from .client import memory_service_available, search_memories
from .retrieval import retrieve_relevant_memories, build_memory_context
from .extractor import extract_memory_candidates_from_session
from .policy import classify_memory_candidate, validate_memory_write
from .review import review_memory_candidates
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
    "search_memories",
    # retrieval
    "retrieve_relevant_memories",
    "build_memory_context",
    # extractor
    "extract_memory_candidates_from_session",
    # policy
    "classify_memory_candidate",
    "validate_memory_write",
    # review
    "review_memory_candidates",
    # schemas
    "AURAMemoryRecord",
    "MemoryCandidate",
    "MemoryRetrievalRequest",
    "MemoryRetrievalResult",
    "MemoryWriteDecisionResult",
]
