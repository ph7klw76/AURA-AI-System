"""Test audit logging — no secrets, event correctness."""
from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

from core.planning import audit
from core.planning.schemas import AgentPlan


class TestAudit:
    def test_log_planner_disabled_writes(self):
        with tempfile.TemporaryDirectory() as td:
            logfile = os.path.join(td, "test.jsonl")
            with mock.patch.object(audit, "_LOGFILE", logfile):
                audit.log_planner_disabled("s1", "disabled by default")
                assert os.path.exists(logfile)
                with open(logfile) as f:
                    record = json.loads(f.readline())
                assert record["event"] == "planner_disabled"
                assert record["session_id"] == "s1"

    def test_log_planner_requested_writes(self):
        with tempfile.TemporaryDirectory() as td:
            logfile = os.path.join(td, "test.jsonl")
            with mock.patch.object(audit, "_LOGFILE", logfile):
                audit.log_planner_requested("s2", "abc123hash")
                with open(logfile) as f:
                    record = json.loads(f.readline())
                assert record["event"] == "planner_requested"
                assert record["prompt_hash"] == "abc123hash"

    def test_log_planner_succeeded_writes(self):
        plan = AgentPlan(
            plan_id="p1",
            primary_agent="research_scout",
            secondary_agents=["grant_architect"],
            risk_level="medium",
            confidence="high",
        )
        with tempfile.TemporaryDirectory() as td:
            logfile = os.path.join(td, "test.jsonl")
            with mock.patch.object(audit, "_LOGFILE", logfile):
                audit.log_planner_succeeded("s3", plan.plan_id, "hash1", plan)
                with open(logfile) as f:
                    record = json.loads(f.readline())
                assert record["event"] == "planner_succeeded"
                assert record["primary_agent"] == "research_scout"

    def test_log_planner_failed_writes(self):
        with tempfile.TemporaryDirectory() as td:
            logfile = os.path.join(td, "test.jsonl")
            with mock.patch.object(audit, "_LOGFILE", logfile):
                audit.log_planner_failed("s4", "LLM timeout")
                with open(logfile) as f:
                    record = json.loads(f.readline())
                assert record["event"] == "planner_failed"
                assert "error_hash" in record
                assert len(record["error_hash"]) == 16  # SHA-256 truncated

    def test_log_plan_validated_writes(self):
        with tempfile.TemporaryDirectory() as td:
            logfile = os.path.join(td, "test.jsonl")
            with mock.patch.object(audit, "_LOGFILE", logfile):
                audit.log_plan_validated("s5", "p2", ok=True, errors=[], warnings=["w1"], fallback_used=False)
                with open(logfile) as f:
                    record = json.loads(f.readline())
                assert record["event"] == "plan_validated"
                assert record["ok"] is True

    def test_log_plan_rejected_writes(self):
        with tempfile.TemporaryDirectory() as td:
            logfile = os.path.join(td, "test.jsonl")
            with mock.patch.object(audit, "_LOGFILE", logfile):
                audit.log_plan_validated("s6", "p3", ok=False, errors=["Unknown agent"], warnings=[], fallback_used=False)
                with open(logfile) as f:
                    record = json.loads(f.readline())
                assert record["event"] == "plan_rejected"

    def test_log_fallback_used_writes(self):
        with tempfile.TemporaryDirectory() as td:
            logfile = os.path.join(td, "test.jsonl")
            with mock.patch.object(audit, "_LOGFILE", logfile):
                audit.log_fallback_used("s7", "LLM failed", ["research_scout", "scientific_verifier"])
                with open(logfile) as f:
                    record = json.loads(f.readline())
                assert record["event"] == "fallback_used"
                assert len(record["selected_agents"]) == 2

    def test_no_secrets_in_log(self):
        """Verify that secrets are NOT logged — errors are hashed."""
        with tempfile.TemporaryDirectory() as td:
            logfile = os.path.join(td, "test.jsonl")
            with mock.patch.object(audit, "_LOGFILE", logfile):
                audit.log_planner_failed("s8", "sk-this-is-a-secret-key-deadbeef")
                with open(logfile) as f:
                    record = json.loads(f.readline())
                # error is hashed, never in plaintext
                data = json.dumps(record)
                assert "sk-this-is-a-secret" not in data, "Secret leaked into audit log"
                assert "error_hash" in record, "error should be stored as hash"
