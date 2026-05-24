"""Test orchestrator integration — task-agent dispatch and session limits."""
from __future__ import annotations

import os
from unittest import mock

import pytest


class TestOrchestratorIntegration:
    @pytest.fixture(autouse=True)
    def enable_task_agents(self):
        old = os.environ.get("AURA_TASK_AGENTS_ENABLED", "")
        os.environ["AURA_TASK_AGENTS_ENABLED"] = "1"
        yield
        if old:
            os.environ["AURA_TASK_AGENTS_ENABLED"] = old
        else:
            os.environ.pop("AURA_TASK_AGENTS_ENABLED", None)

    def test_dispatch_runs_when_enabled(self):
        """_dispatch_task_agent_requests creates results when governor requests."""
        from core.orchestrator import _dispatch_task_agent_requests

        result = {"strategic_governor": {
            "task_agent_requests": [
                {"role": "claim_extractor", "subtask": "extract claims",
                 "context": {"text": "We found significant results."}},
            ]
        }}
        _dispatch_task_agent_requests(result, "session-test")

        assert "task_agent_results" in result
        assert len(result["task_agent_results"]) == 1
        r = result["task_agent_results"][0]
        assert r["role"] == "claim_extractor"
        assert r["verified_by_aura"] is False
        assert r["requires_verification"] is True

    def test_dispatch_skips_disabled(self):
        """When disabled, no task agent results are created."""
        from core.orchestrator import _dispatch_task_agent_requests

        os.environ["AURA_TASK_AGENTS_ENABLED"] = "0"
        result = {"strategic_governor": {
            "task_agent_requests": [
                {"role": "claim_extractor", "subtask": "extract",
                 "context": {"text": "test"}},
            ]
        }}
        _dispatch_task_agent_requests(result, "session-test")
        assert result.get("task_agent_results") is None or len(result.get("task_agent_results", [])) == 0
        os.environ["AURA_TASK_AGENTS_ENABLED"] = "1"

    def test_dispatch_overlap_routes_to_existing(self):
        """Broad tasks are routed to existing agents, not task agents."""
        from core.orchestrator import _dispatch_task_agent_requests

        result = {"strategic_governor": {
            "task_agent_requests": [
                {"role": "helper", "subtask": "literature search for biomarkers",
                 "context": {}},
            ]
        }}
        _dispatch_task_agent_requests(result, "session-test")

        assert "task_agent_results" in result
        r = result["task_agent_results"][0]
        assert r.get("routed_to") == "research_scout"

    def test_dispatch_max_per_session_enforced(self):
        """Max per session (default 3) is enforced."""
        from core.orchestrator import _dispatch_task_agent_requests

        result = {"strategic_governor": {
            "task_agent_requests": [
                {"role": "claim_extractor", "subtask": "task1", "context": {"text": "t1"}},
                {"role": "claim_extractor", "subtask": "task2", "context": {"text": "t2"}},
                {"role": "claim_extractor", "subtask": "task3", "context": {"text": "t3"}},
                {"role": "claim_extractor", "subtask": "task4", "context": {"text": "t4"}},
                {"role": "claim_extractor", "subtask": "task5", "context": {"text": "t5"}},
            ]
        }}
        _dispatch_task_agent_requests(result, "session-test")

        assert "task_agent_results" in result
        assert len(result["task_agent_results"]) <= 3  # max 3

    def test_dispatch_handles_missing_requests_gracefully(self):
        from core.orchestrator import _dispatch_task_agent_requests

        result = {"strategic_governor": {}}  # No task_agent_requests
        _dispatch_task_agent_requests(result, "session-test")
        # Should not crash
        assert True

    def test_dispatch_result_always_unverified(self):
        """Every task-agent result must have verified_by_aura=False."""
        from core.orchestrator import _dispatch_task_agent_requests

        result = {"strategic_governor": {
            "task_agent_requests": [
                {"role": "claim_extractor", "subtask": "extract",
                 "context": {"text": "We found evidence."}},
            ]
        }}
        _dispatch_task_agent_requests(result, "session-test")

        for r in result.get("task_agent_results", []):
            assert r.get("verified_by_aura") is False, f"Result not marked unverified: {r}"
            assert r.get("requires_verification") is True

    def test_dispatch_does_not_crash_on_bad_input(self):
        """Dispatch should never crash the orchestrator."""
        from core.orchestrator import _dispatch_task_agent_requests

        result = {}
        _dispatch_task_agent_requests(result, "session-test")
        assert True  # no exception
