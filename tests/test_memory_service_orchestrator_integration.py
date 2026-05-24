"""Test memory-service orchestrator integration — retrieval + extraction hooks."""
from __future__ import annotations

import os
from unittest import mock

import pytest


class TestOrchestratorMemoryServiceHooks:
    """Verify run_aura_core includes memory_service in result."""

    @pytest.fixture(autouse=True)
    def clear_env(self):
        keys = [k for k in os.environ if k.startswith("AURA_MEMORY_")]
        old = {k: os.environ.pop(k) for k in keys}
        yield
        for k, v in old.items():
            os.environ[k] = v

    def test_result_has_memory_service_field(self):
        """run_aura_core always populates result['memory_service']."""
        from core.orchestrator import run_aura_core

        with mock.patch("agents.strategic_governor.run") as mock_gov:
            mock_gov.return_value = {
                "selected_agents": ["research_scout"],
                "risk_level": "low",
                "blocked_actions": [],
                "memory_policy": {"retrieve_memory": True, "allow_memory_write": False},
                "self_evolution_policy": {"run": True},
            }
            with mock.patch("agents.research_scout.run") as mock_scout:
                mock_scout.return_value = {
                    "summary": "test",
                    "sources": [],
                    "claims": [],
                }
                with mock.patch("agents.scientific_verifier.run") as mock_verif:
                    mock_verif.return_value = {
                        "verifier_route": "approve",
                        "evidence_status": "verified",
                        "claims": [],
                    }
                    with mock.patch("agents.self_evolution_engine.run") as mock_ev:
                        mock_ev.return_value = {
                            "what_worked": [],
                            "what_failed_or_was_weak": [],
                            "reusable_lessons": [],
                            "memory_updates": [],
                            "workflow_improvements": [],
                            "suggested_profile_updates": [],
                        }
                        result = run_aura_core("test query")

        assert "memory_service" in result
        ms = result["memory_service"]
        assert "enabled" in ms
        assert "retrieved_count" in ms
        assert "candidate_count" in ms
        assert "committed_count" in ms
        assert "pending_review_count" in ms

    def test_disabled_when_env_0(self):
        """When AURA_MEMORY_SERVICE_ENABLED=0, memory_service shows enabled=False."""
        os.environ["AURA_MEMORY_SERVICE_ENABLED"] = "0"
        from core.orchestrator import run_aura_core

        with mock.patch("agents.strategic_governor.run") as mock_gov:
            mock_gov.return_value = {
                "selected_agents": ["research_scout"],
                "risk_level": "low",
                "blocked_actions": [],
                "memory_policy": {"retrieve_memory": True, "allow_memory_write": False},
                "self_evolution_policy": {"run": True},
            }
            with mock.patch("agents.research_scout.run") as mock_scout:
                mock_scout.return_value = {
                    "summary": "test",
                    "sources": [],
                    "claims": [],
                }
                with mock.patch("agents.scientific_verifier.run") as mock_verif:
                    mock_verif.return_value = {
                        "verifier_route": "approve",
                        "evidence_status": "verified",
                        "claims": [],
                    }
                    with mock.patch("agents.self_evolution_engine.run") as mock_ev:
                        mock_ev.return_value = {
                            "what_worked": [],
                            "what_failed_or_was_weak": [],
                            "reusable_lessons": [],
                            "memory_updates": [],
                            "workflow_improvements": [],
                            "suggested_profile_updates": [],
                        }
                        result = run_aura_core("test query")

        # When disabled via env=0, the build_memory_context returns "" so enabled=False
        assert result["memory_service"]["enabled"] is False

    def test_self_evolution_still_runs(self):
        """Memory service must not interfere with self-evolution."""
        os.environ["AURA_MEMORY_SERVICE_ENABLED"] = "0"
        from core.orchestrator import run_aura_core

        with mock.patch("agents.strategic_governor.run") as mock_gov:
            mock_gov.return_value = {
                "selected_agents": ["research_scout"],
                "risk_level": "low",
                "blocked_actions": [],
                "memory_policy": {"retrieve_memory": True, "allow_memory_write": False},
                "self_evolution_policy": {"run": True},
            }
            with mock.patch("agents.research_scout.run") as mock_scout:
                mock_scout.return_value = {
                    "summary": "test",
                    "sources": [],
                    "claims": [],
                }
                with mock.patch("agents.scientific_verifier.run") as mock_verif:
                    mock_verif.return_value = {
                        "verifier_route": "approve",
                        "evidence_status": "verified",
                        "claims": [],
                    }
                    with mock.patch("agents.self_evolution_engine.run") as mock_ev:
                        mock_ev.return_value = {
                            "what_worked": ["good query"],
                            "what_failed_or_was_weak": [],
                            "reusable_lessons": [],
                            "memory_updates": [],
                            "workflow_improvements": [],
                            "suggested_profile_updates": [],
                        }
                        result = run_aura_core("test query")

        assert "self_evolution_engine" in result
        assert result["self_evolution_engine"]["what_worked"] == ["good query"]
