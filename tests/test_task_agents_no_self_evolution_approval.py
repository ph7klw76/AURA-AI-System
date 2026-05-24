"""Verify task agents cannot approve self-evolution proposals."""
from __future__ import annotations

from core.task_agents.policy import validate_agent_spec
from core.task_agents.schemas import AgentSpec


def _spec(**overrides):
    return AgentSpec(
        agent_id="ta-x", name="test", purpose="test",
        parent_session_id="s", parent_agent="o", parent_task="t",
        subtask="s", created_by="o",
        **overrides,
    )


class TestNoSelfEvolutionApproval:
    def test_can_spawn_agents_rejected(self):
        """Task agents cannot spawn more agents (including evolution)."""
        ok, errors = validate_agent_spec(_spec(can_spawn_agents=True))
        assert not ok
        assert any("spawn" in e.lower() for e in errors)

    def test_can_spawn_agents_false_by_default(self):
        s = _spec()
        assert s.can_spawn_agents is False

    def test_evolution_approve_tool_blocked(self):
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["evolution.approve"]
        ))
        assert not ok
        assert any("evolution.approve" in e.lower() for e in errors)

    def test_persistence_allowed_false_by_default(self):
        s = _spec()
        assert s.persistence_allowed is False

    def test_persistence_allowed_blocked_by_policy(self):
        ok, errors = validate_agent_spec(_spec(persistence_allowed=True))
        assert not ok
        assert any("persist" in e.lower() for e in errors)

    def test_cannot_approve_own_outputs(self):
        """Task agents always have verified_by_aura=False — they cannot self-approve."""
        from core.task_agents.schemas import TaskAgentResult
        r = TaskAgentResult(agent_id="ta-1", ok=True, subtask="st")
        assert r.verified_by_aura is False, "Task agents must never self-approve"
        assert r.requires_verification is True
