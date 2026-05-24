"""Test audit logging — creation, blocking, execution, and failure events."""
from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

import pytest
from core.task_agents.schemas import AgentSpec, TaskAgentResult
from core.task_agents import audit


class TestAuditLogging:
    def test_log_created_writes_to_file(self):
        spec = mock.MagicMock()
        spec.agent_id = "ta-test-1"
        spec.name = "claim_extractor"
        spec.parent_agent = "orchestrator"
        spec.subtask = "extract claims"
        spec.allowed_tools = ["aura.internal.claim_extract"]
        spec.risk_level = "low"
        spec.verifier_required = True
        spec.human_review_required = False

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(audit, "_LOGFILE", os.path.join(tmpdir, "task_agents.jsonl")):
                audit.log_created(spec, "session-1")
                assert os.path.exists(audit._LOGFILE)
                with open(audit._LOGFILE) as f:
                    record = json.loads(f.readline())
                assert record["event"] == "created"
                assert record["agent_id"] == "ta-test-1"

    def test_log_blocked_writes_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(audit, "_LOGFILE", os.path.join(tmpdir, "task_agents.jsonl")):
                audit.log_blocked(
                    "verifier_clone", "verify claims",
                    "Forbidden role", "session-2",
                    existing_agent="scientific_verifier",
                )
                with open(audit._LOGFILE) as f:
                    record = json.loads(f.readline())
                assert record["event"] == "blocked"
                assert record["routed_to"] == "scientific_verifier"

    def test_log_executed_writes_to_file(self):
        result = mock.MagicMock()
        result.agent_id = "ta-test-2"
        result.subtask = "format evidence"
        result.ok = True
        result.confidence = "medium"
        result.findings = ["f1", "f2"]
        result.claims_for_verification = ["c1"]
        result.errors = []
        result.requires_verification = True
        result.verified_by_aura = False

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(audit, "_LOGFILE", os.path.join(tmpdir, "task_agents.jsonl")):
                audit.log_executed(result, "session-3")
                with open(audit._LOGFILE) as f:
                    record = json.loads(f.readline())
                assert record["event"] == "executed"
                assert record["ok"] is True

    def test_log_failed_writes_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(audit, "_LOGFILE", os.path.join(tmpdir, "task_agents.jsonl")):
                audit.log_failed("ta-bad", "bad subtask", ["error1"], "session-4")
                with open(audit._LOGFILE) as f:
                    record = json.loads(f.readline())
                assert record["event"] == "failed"
                assert record["ok"] is False

    def test_no_secrets_in_log(self):
        """Subtask is hashed, not stored in plaintext."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(audit, "_LOGFILE", os.path.join(tmpdir, "task_agents.jsonl")):
                audit.log_blocked("test_role", "secret subtask text", "reason", "s")
                with open(audit._LOGFILE) as f:
                    record = json.loads(f.readline())
                # The subtask itself is NOT in the log — only a hash
                assert "secret subtask text" not in json.dumps(record)
                assert "subtask_hash" in record
