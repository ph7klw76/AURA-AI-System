"""Test memory-service JSONL audit logging."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from core.memory_service import audit as _audit_mod
from core.memory_service.audit import (
    _log_path,
    _ensure_log_file,
    _append,
    log_retrieval_requested,
    log_retrieval_succeeded,
    log_retrieval_failed,
    log_service_unavailable,
    log_candidate_extracted,
    log_candidate_blocked,
    log_candidate_pending_review,
)


class TestAuditLogging:
    @pytest.fixture(autouse=True)
    def temp_log(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "memory_service.jsonl"
            monkeypatch.setattr(_audit_mod, "_LOG_PATH", log_file)
            yield log_file

    def test_retrieval_requested_logged(self, temp_log):
        log_retrieval_requested("s1", "CRISPR research", "research_scout")
        records = _read_log(temp_log)
        assert len(records) == 1
        r = records[0]
        assert r["event"] == "retrieval_requested"
        assert r["session_id"] == "s1"
        # prompt is hashed, not stored in plaintext
        assert "prompt_hash" in r
        assert r["prompt_hash"] != "CRISPR research"
        assert r["agent_name"] == "research_scout"

    def test_retrieval_succeeded_logged(self, temp_log):
        log_retrieval_succeeded("s2", 5)
        records = _read_log(temp_log)
        assert records[0]["event"] == "retrieval_succeeded"
        assert records[0]["retrieved_count"] == 5
        assert records[0]["ok"] is True

    def test_retrieval_failed_logged(self, temp_log):
        log_retrieval_failed("s3", ["Connection refused"])
        records = _read_log(temp_log)
        assert records[0]["event"] == "retrieval_failed"
        assert records[0]["ok"] is False
        assert "Connection refused" in records[0]["errors"]

    def test_service_unavailable_logged(self, temp_log):
        log_service_unavailable("s4", "Timeout after 30s")
        records = _read_log(temp_log)
        assert records[0]["event"] == "service_unavailable"
        assert "Timeout" in records[0]["reason"]

    def test_candidate_extracted_logged(self, temp_log):
        log_candidate_extracted("s5", "c1", "user_preference",
                                source_agent="orchestrator")
        records = _read_log(temp_log)
        r = records[0]
        assert r["event"] == "candidate_extracted"
        assert r["candidate_id"] == "c1"
        assert r["memory_type"] == "user_preference"

    def test_candidate_blocked_logged(self, temp_log):
        log_candidate_blocked("s6", "c2", "Contains API key",
                              memory_type="procedural_memory")
        records = _read_log(temp_log)
        r = records[0]
        assert r["event"] == "candidate_blocked"
        assert r["ok"] is False
        assert "API key" in r["reason"]

    def test_candidate_pending_review_logged(self, temp_log):
        log_candidate_pending_review("s7", "c3", "procedural_memory")
        records = _read_log(temp_log)
        r = records[0]
        assert r["event"] == "candidate_pending_review"
        assert r["requires_human_review"] is True

    def test_timestamp_present_on_every_event(self, temp_log):
        log_retrieval_requested("s8", "test")
        records = _read_log(temp_log)
        assert "timestamp" in records[0]
        assert len(records[0]["timestamp"]) > 0

    def test_multiple_events_appended(self, temp_log):
        log_retrieval_requested("s9", "q1")
        log_retrieval_succeeded("s9", 3)
        log_candidate_extracted("s9", "c4", "project_decision")
        records = _read_log(temp_log)
        assert len(records) == 3
        assert [r["event"] for r in records] == [
            "retrieval_requested", "retrieval_succeeded", "candidate_extracted",
        ]

    def test_no_secret_in_prompt_hash(self, temp_log):
        """Prompt is SHA-256 hashed — raw text never appears in audit log."""
        prompt = "api_key=sk-secret123"
        log_retrieval_requested("s10", prompt)
        records = _read_log(temp_log)
        raw = temp_log.read_text()
        # The raw prompt should NOT appear in the file
        assert "sk-secret" not in raw
        assert records[0]["prompt_hash"] != prompt


def _read_log(path: Path) -> list[dict]:
    records: list[dict] = []
    if path.exists():
        for line in path.read_text().strip().splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records
