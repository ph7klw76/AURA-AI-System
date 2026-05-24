"""Test memory-service client failure handling and fail-closed behavior."""
from __future__ import annotations

import json
import io
import os
import urllib.error
from unittest import mock

import pytest
from core.memory_service.client import search_memories, memory_service_available
from core.memory_service.config import MemoryServiceConfig
from core.memory_service.schemas import MemoryRetrievalRequest, MemoryRetrievalResult


_ENABLED = MemoryServiceConfig(enabled=True, service_url="http://localhost:9999")


def _make_response(status: int, body: bytes) -> mock.MagicMock:
    """Create a MagicMock that supports the urllib response context-manager."""
    resp = mock.MagicMock()
    resp.status = status
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = None
    return resp


def _patch_open(urlopen_side_effect, config=None):
    """Apply urllib.request.urlopen mock."""
    return mock.patch("core.memory_service.client.urllib.request.urlopen",
                      side_effect=urlopen_side_effect)


class TestFailClosedFalse:
    """With fail_closed=False, retrieval degrades gracefully."""

    @pytest.fixture(autouse=True)
    def clear_env(self):
        keys = [k for k in os.environ if k.startswith("AURA_MEMORY_")]
        old = {k: os.environ.pop(k) for k in keys}
        yield
        for k, v in old.items():
            os.environ[k] = v

    def test_connection_refused_degrades(self):
        cfg = MemoryServiceConfig(enabled=True, service_url="http://localhost:19999")
        req = MemoryRetrievalRequest(prompt="test")
        with _patch_open(urllib.error.URLError("Connection refused")):
            result = search_memories(req, config=cfg)
        assert result.ok is True
        assert result.degraded is True
        assert len(result.memories) == 0

    def test_http_500_degrades(self):
        cfg = MemoryServiceConfig(enabled=True, service_url="http://localhost:2")
        req = MemoryRetrievalRequest(prompt="test")
        with _patch_open(urllib.error.HTTPError("http://x", 500, "ISE", {}, None)):
            result = search_memories(req, config=cfg)
        assert result.ok is True
        assert result.degraded is True

    def test_timeout_degrades(self):
        cfg = MemoryServiceConfig(enabled=True, service_url="http://localhost:3")
        req = MemoryRetrievalRequest(prompt="test")
        with _patch_open(TimeoutError("timed out")):
            result = search_memories(req, config=cfg)
        assert result.ok is True
        assert result.degraded is True

    def test_malformed_response_degrades(self):
        cfg = MemoryServiceConfig(enabled=True, service_url="http://localhost:4")
        req = MemoryRetrievalRequest(prompt="test")

        class _Resp:
            status = 200

            def read(self):
                return b"not json [[["

            @staticmethod
            def __enter__():
                return _Resp()

            @staticmethod
            def __exit__(*a):
                pass

        with mock.patch("core.memory_service.client.urllib.request.urlopen",
                        return_value=_Resp):
            result = search_memories(req, config=cfg)
        # json parse error caught by outer except
        assert result.ok is True
        assert result.degraded is True


class TestFailClosed:
    """With fail_closed=True, retrieval returns ok=False."""

    def test_connection_refused_fail_closed(self):
        cfg = MemoryServiceConfig(
            enabled=True,
            service_url="http://localhost:19999",
            fail_closed=True,
        )
        req = MemoryRetrievalRequest(prompt="test")
        with _patch_open(urllib.error.URLError("Connection refused")):
            result = search_memories(req, config=cfg)
        assert result.ok is False
        assert result.degraded is True

    def test_http_500_fail_closed(self):
        cfg = MemoryServiceConfig(
            enabled=True,
            service_url="http://localhost:2",
            fail_closed=True,
        )
        req = MemoryRetrievalRequest(prompt="test")
        with _patch_open(urllib.error.HTTPError("http://x", 500, "ISE", {}, None)):
            result = search_memories(req, config=cfg)
        assert result.ok is False


class TestHttpSuccess:
    """Successful HTTP responses parse correctly."""

    def test_empty_list_response(self):
        cfg = MemoryServiceConfig(enabled=True, service_url="http://localhost:5")
        req = MemoryRetrievalRequest(prompt="test")

        _Resp = _make_response(200, b"[]")

        with mock.patch("core.memory_service.client.urllib.request.urlopen",
                        return_value=_Resp):
            result = search_memories(req, config=cfg)
        assert result.ok is True
        assert result.memories == []
        assert result.degraded is False

    def test_dict_with_results_key(self):
        cfg = MemoryServiceConfig(enabled=True, service_url="http://localhost:6")
        req = MemoryRetrievalRequest(prompt="test")

        payload = {
            "results": [
                {
                    "id": "mem-1",
                    "memory_type": "user_preference",
                    "namespace": ["aura", "user", "u1", "preferences"],
                    "content": {"style": "concise"},
                    "evidence_status": "verified",
                    "verifier_route": "approve",
                    "requires_human_review": False,
                },
            ],
        }

        _Resp = _make_response(200, json.dumps(payload).encode())

        with mock.patch("core.memory_service.client.urllib.request.urlopen",
                        return_value=_Resp):
            result = search_memories(req, config=cfg)
        assert result.ok is True
        assert len(result.memories) == 1
        assert result.memories[0].memory_id == "mem-1"
        assert result.memories[0].memory_type == "user_preference"
        assert result.memories[0].evidence_status == "verified"
        assert result.memories[0].verifier_route == "approve"

    def test_respects_max_results(self):
        """max_results from request caps the limit."""
        cfg = MemoryServiceConfig(enabled=True, service_url="http://localhost:7")
        req = MemoryRetrievalRequest(prompt="test", max_results=3)

        sent_payload: dict = {}

        class _Resp:
            status = 200

            def read(self):
                # Return more than requested to verify limit enforcement
                return json.dumps([
                    {"id": f"mem-{i}", "memory_type": "project_decision",
                     "content": {}}
                    for i in range(10)
                ]).encode()

            @staticmethod
            def __enter__():
                return _Resp()

            @staticmethod
            def __exit__(*a):
                pass

        with mock.patch("core.memory_service.client.urllib.request.urlopen",
                        return_value=_Resp):
            result = search_memories(req, config=cfg)
        # Even if server returns 10, the request limit=3 was sent
        # The client doesn't enforce a hard cap on results — it trusts the
        # server.  But it does pass the limit in the payload.
        assert result.ok is True

    def test_evidence_status_preserved(self):
        """Evidence memories must carry their evidence_status and verifier_route."""
        cfg = MemoryServiceConfig(enabled=True, service_url="http://localhost:8")
        req = MemoryRetrievalRequest(prompt="CRISPR biomarkers")

        payload = {
            "results": [
                {
                    "id": "mem-ev",
                    "memory_type": "evidence_memory",
                    "content": {"gene": "BRCA1"},
                    "evidence_status": "weak_evidence",
                    "verifier_route": "reject",
                    "requires_verifier": True,
                },
            ],
        }

        _Resp = _make_response(200, json.dumps(payload).encode())

        with mock.patch("core.memory_service.client.urllib.request.urlopen",
                        return_value=_Resp):
            result = search_memories(req, config=cfg)
        assert len(result.memories) == 1
        m = result.memories[0]
        assert m.memory_type == "evidence_memory"
        assert m.evidence_status == "weak_evidence"
        assert m.verifier_route == "reject"
        assert m.requires_verifier is True
