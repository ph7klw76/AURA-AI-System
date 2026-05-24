"""Test Pydantic schemas for task-scoped agents."""
from __future__ import annotations

import pytest
from core.task_agents.schemas import (
    AgentSpec, TaskAgentRequest, TaskAgentResult, AgentCreationDecision,
)


class TestTaskAgentRequest:
    def test_minimal_creation(self):
        r = TaskAgentRequest(
            parent_session_id="s1", parent_agent="orchestrator",
            requested_role="claim_extractor", subtask="extract claims",
        )
        assert r.context == {}
        assert r.requested_tools == []
        assert r.risk_level is None

    def test_full_creation(self):
        r = TaskAgentRequest(
            parent_session_id="s2", parent_agent="research_scout",
            requested_role="evidence_table_formatter", subtask="format evidence",
            context={"text": "some data"}, requested_tools=["aura.internal.evidence_format"],
            risk_level="low",
        )
        assert r.context["text"] == "some data"
        assert r.risk_level == "low"


class TestAgentSpec:
    def test_defaults_are_safe(self):
        s = AgentSpec(
            agent_id="ta-1", name="test", purpose="test",
            parent_session_id="s1", parent_agent="orch", parent_task="t",
            subtask="st", created_by="orch",
        )
        assert s.can_spawn_agents is False
        assert s.can_modify_memory is False
        assert s.can_modify_profile is False
        assert s.persistence_allowed is False
        assert s.can_write_files is False
        assert s.can_call_external_mcp is False
        assert s.verifier_required is True
        assert s.human_review_required is False
        assert s.risk_level == "low"
        assert s.max_steps == 5
        assert s.timeout_seconds == 120

    def test_high_risk_requires_human_review(self):
        s = AgentSpec(
            agent_id="ta-2", name="test_h", purpose="high risk",
            parent_session_id="s2", parent_agent="orch", parent_task="t",
            subtask="st", created_by="orch",
            risk_level="high", human_review_required=True,
        )
        assert s.risk_level == "high"
        assert s.human_review_required is True


class TestTaskAgentResult:
    def test_defaults_unverified(self):
        r = TaskAgentResult(agent_id="ta-1", ok=True, subtask="st")
        assert r.verified_by_aura is False
        assert r.requires_verification is True
        assert r.confidence == "low"
        assert r.route is None

    def test_failure_result(self):
        r = TaskAgentResult(
            agent_id="ta-1", ok=False, subtask="failed_subtask",
            errors=["Bad input"], confidence="low",
        )
        assert r.ok is False
        assert len(r.errors) == 1


class TestAgentCreationDecision:
    def test_route_to_existing(self):
        d = AgentCreationDecision(
            create_agent=False,
            reason="Overlap with research_scout",
            use_existing_agent="research_scout",
        )
        assert d.create_agent is False
        assert d.use_existing_agent == "research_scout"
        assert d.proposed_spec is None

    def test_create_new(self):
        spec = AgentSpec(
            agent_id="ta-x", name="test", purpose="p",
            parent_session_id="s", parent_agent="o", parent_task="t",
            subtask="s", created_by="o",
        )
        d = AgentCreationDecision(create_agent=True, reason="OK", proposed_spec=spec)
        assert d.create_agent is True
        assert d.proposed_spec is not None
