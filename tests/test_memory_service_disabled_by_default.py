"""Test memory-service enabled-by-default behavior with env override.

The service is now enabled by default, but setting
AURA_MEMORY_SERVICE_ENABLED=0 must still disable it fully.
"""
from __future__ import annotations

import os
from unittest import mock

import pytest
from core.memory_service import (
    is_memory_service_enabled,
    memory_service_available,
    retrieve_relevant_memories,
    build_memory_context,
)
from core.memory_service.client import search_memories
from core.memory_service.schemas import MemoryRetrievalRequest


class TestEnabledByDefault:
    """Memory service is enabled by default."""

    @pytest.fixture(autouse=True)
    def clear_env(self):
        keys = [k for k in os.environ if k.startswith("AURA_MEMORY_")]
        old = {k: os.environ.pop(k) for k in keys}
        yield
        for k, v in old.items():
            os.environ[k] = v

    def test_is_memory_service_enabled_true(self):
        assert is_memory_service_enabled() is True

    def test_memory_service_available_runs_health_check(self):
        """When enabled, it attempts to reach the service (may fail but not crash)."""
        result = memory_service_available()
        # Returns bool — False if unreachable, True if service responds
        assert isinstance(result, bool)

    def test_retrieve_attempts_service(self):
        """When enabled, retrieval attempts to reach the service."""
        result = retrieve_relevant_memories("test query", session_id="s1")
        assert result.ok is True
        # May be degraded if service is unreachable, but never crashes

    def test_build_memory_context_does_not_crash(self):
        ctx = build_memory_context("test", session_id="s2")
        assert isinstance(ctx, str)

    def test_search_memories_attempts_service(self):
        req = MemoryRetrievalRequest(prompt="test")
        result = search_memories(req)
        assert result.ok is True


class TestDisabledWhenExplicitlySet:
    """Setting AURA_MEMORY_SERVICE_ENABLED=0 fully disables the service."""

    @pytest.fixture(autouse=True)
    def disable_service(self):
        os.environ["AURA_MEMORY_SERVICE_ENABLED"] = "0"
        yield
        os.environ.pop("AURA_MEMORY_SERVICE_ENABLED", None)

    def test_is_memory_service_enabled_false(self):
        assert is_memory_service_enabled() is False

    def test_memory_service_available_false(self):
        assert memory_service_available() is False

    def test_retrieve_returns_empty(self):
        result = retrieve_relevant_memories("test query", session_id="s3")
        assert result.ok is True
        assert result.memories == []
        assert any("disabled" in w.lower() for w in result.warnings)

    def test_search_memories_returns_empty(self):
        req = MemoryRetrievalRequest(prompt="test")
        result = search_memories(req)
        assert result.ok is True
        assert result.memories == []

    def test_build_memory_context_returns_empty(self):
        ctx = build_memory_context("test", session_id="s4")
        assert ctx == ""
