"""Test memory-service retrieval — namespace-aware, fail-safe."""
from __future__ import annotations

import json
import os
from unittest import mock

import pytest
from core.memory_service.retrieval import (
    retrieve_relevant_memories,
    build_memory_context,
)
from core.memory_service.config import MemoryServiceConfig
from core.memory_service.schemas import (
    AURAMemoryRecord,
    MemoryRetrievalResult,
)


_ENABLED_CFG = MemoryServiceConfig(
    enabled=True,
    service_url="http://localhost:2024",
    max_retrieved=8,
)


def _mock_search(return_result=None):
    """Patch search_memories to return a controlled result."""
    if return_result is None:
        return_result = MemoryRetrievalResult(ok=True, memories=[])
    return mock.patch(
        "core.memory_service.retrieval.search_memories",
        return_value=return_result,
    )


class TestRetrievalWithEnabledConfig:
    @pytest.fixture(autouse=True)
    def clear_env(self):
        keys = [k for k in os.environ if k.startswith("AURA_MEMORY_")]
        old = {k: os.environ.pop(k) for k in keys}
        yield
        for k, v in old.items():
            os.environ[k] = v

    def test_returns_empty_when_service_returns_empty(self):
        with _mock_search():
            result = retrieve_relevant_memories(
                "test", session_id="s1", config=_ENABLED_CFG,
            )
        assert result.ok is True
        assert result.memories == []

    def test_returns_memories_from_service(self):
        mem = AURAMemoryRecord(
            memory_id="mem-1",
            memory_type="user_preference",
            content={"style": "concise"},
        )
        with _mock_search(MemoryRetrievalResult(
            ok=True, memories=[mem],
            compact_context='[user_preference] {"style": "concise"}',
        )):
            result = retrieve_relevant_memories(
                "test", session_id="s2", config=_ENABLED_CFG,
            )
        assert len(result.memories) == 1
        assert result.memories[0].memory_id == "mem-1"
        assert result.compact_context != ""

    def test_degraded_result_propagates(self):
        with _mock_search(MemoryRetrievalResult(
            ok=True, degraded=True, warnings=["Timeout"],
        )):
            result = retrieve_relevant_memories(
                "test", session_id="s3", config=_ENABLED_CFG,
            )
        assert result.degraded is True
        assert "Timeout" in str(result.warnings)

    def test_build_memory_context_wraps_retrieval(self):
        mem = AURAMemoryRecord(
            memory_id="mem-2",
            memory_type="project_decision",
            content={"decision": "Use PostgreSQL"},
        )
        with mock.patch(
            "core.memory_service.retrieval.retrieve_relevant_memories",
            return_value=MemoryRetrievalResult(
                ok=True, memories=[mem],
                compact_context='[project_decision] {"decision": "Use PostgreSQL"}',
            ),
        ):
            ctx = build_memory_context(
                "test", session_id="s4",
            )
        assert "project_decision" in ctx
        assert "PostgreSQL" in ctx

    def test_max_retrieved_enforced_in_request(self):
        """Verify that max_results is set from config.max_retrieved."""
        cfg = MemoryServiceConfig(
            enabled=True,
            service_url="http://localhost:1",
            max_retrieved=5,
        )
        # Patch at search_memories level to inspect the request
        with mock.patch(
            "core.memory_service.retrieval.search_memories",
        ) as mock_search:
            mock_search.return_value = MemoryRetrievalResult(ok=True)
            retrieve_relevant_memories("test", session_id="s5", config=cfg)
            call_args = mock_search.call_args[0]
            assert call_args[0].max_results == 5

    def test_memory_types_default_when_none(self):
        """When memory_types is None, a default set is used."""
        cfg = MemoryServiceConfig(
            enabled=True,
            service_url="http://localhost:1",
            max_retrieved=8,
        )
        with mock.patch(
            "core.memory_service.retrieval.search_memories",
        ) as mock_search:
            mock_search.return_value = MemoryRetrievalResult(ok=True)
            retrieve_relevant_memories(
                "test", session_id="s6", config=cfg, memory_types=None,
            )
            call_args = mock_search.call_args[0]
            req = call_args[0]
            assert len(req.memory_types) > 0
            assert "user_preference" in req.memory_types
            assert "procedural_memory" in req.memory_types
