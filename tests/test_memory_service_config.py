"""Test memory-service configuration — env-driven, disabled by default."""
from __future__ import annotations

import os
from unittest import mock

import pytest
from core.memory_service.config import (
    MemoryServiceConfig,
    is_memory_service_enabled,
    load_memory_service_config,
)


class TestConfigDefaults:
    """All settings have correct defaults."""

    @pytest.fixture(autouse=True)
    def clear_env(self):
        keys = [k for k in os.environ if k.startswith("AURA_MEMORY_")]
        old = {k: os.environ.pop(k) for k in keys}
        yield
        for k, v in old.items():
            os.environ[k] = v

    def test_disabled_by_default(self):
        assert is_memory_service_enabled() is False

    def test_all_defaults(self):
        cfg = load_memory_service_config()
        assert cfg.enabled is False
        assert cfg.service_url == "http://localhost:2024"
        assert cfg.write_mode == "propose_only"
        assert cfg.require_review_for_procedural is True
        assert cfg.require_verifier_for_evidence is True
        assert cfg.max_retrieved == 8
        assert cfg.namespace_prefix == "aura"
        assert cfg.audit_log_path == "data/memory_service.jsonl"
        assert cfg.pending_file_path == "data/memory_candidates.jsonl"
        assert cfg.timeout_seconds == 30
        assert cfg.fail_closed is False

    def test_properties(self):
        cfg = load_memory_service_config()
        assert cfg.write_disabled is True   # disabled + not enabled
        assert cfg.propose_only is False    # propose_only but not enabled
        assert cfg.approved_only is False


class TestConfigEnvOverrides:
    """Environment variables override defaults."""

    @pytest.fixture(autouse=True)
    def clear_env(self):
        keys = [k for k in os.environ if k.startswith("AURA_MEMORY_")]
        old = {k: os.environ.pop(k) for k in keys}
        yield
        for k, v in old.items():
            os.environ[k] = v

    def test_enabled_when_set(self):
        os.environ["AURA_MEMORY_SERVICE_ENABLED"] = "1"
        assert is_memory_service_enabled() is True

    def test_enabled_with_env_1(self):
        os.environ["AURA_MEMORY_SERVICE_ENABLED"] = "1"
        cfg = load_memory_service_config()
        assert cfg.enabled is True
        assert cfg.write_disabled is False

    def test_write_mode_override(self):
        os.environ["AURA_MEMORY_SERVICE_ENABLED"] = "1"
        os.environ["AURA_MEMORY_WRITE_MODE"] = "disabled"
        cfg = load_memory_service_config()
        assert cfg.write_disabled is True

    def test_fail_closed_default_false(self):
        cfg = load_memory_service_config()
        assert cfg.fail_closed is False

    def test_fail_closed_override(self):
        os.environ["AURA_MEMORY_FAIL_CLOSED"] = "1"
        cfg = load_memory_service_config()
        assert cfg.fail_closed is True

    def test_max_retrieved_override(self):
        os.environ["AURA_MEMORY_MAX_RETRIEVED"] = "12"
        cfg = load_memory_service_config()
        assert cfg.max_retrieved == 12

    def test_timeout_override(self):
        os.environ["AURA_MEMORY_TIMEOUT_SECONDS"] = "60"
        cfg = load_memory_service_config()
        assert cfg.timeout_seconds == 60
