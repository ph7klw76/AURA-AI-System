"""Verify task agents cannot modify AURA memory or profiles."""
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


class TestNoMemoryMutation:
    def test_can_modify_memory_rejected_by_policy(self):
        ok, errors = validate_agent_spec(_spec(can_modify_memory=True))
        assert not ok
        assert any("memory" in e.lower() for e in errors)

    def test_can_modify_memory_false_by_default(self):
        s = _spec()
        assert s.can_modify_memory is False

    def test_can_modify_profile_rejected_by_policy(self):
        ok, errors = validate_agent_spec(_spec(can_modify_profile=True))
        assert not ok
        assert any("profile" in e.lower() for e in errors)

    def test_can_modify_profile_false_by_default(self):
        s = _spec()
        assert s.can_modify_profile is False

    def test_memory_write_tool_blocked(self):
        ok, errors = validate_agent_spec(_spec(allowed_tools=["memory.write"]))
        assert not ok
        assert any("memory.write" in e.lower() for e in errors)

    def test_profile_write_tool_blocked(self):
        ok, errors = validate_agent_spec(_spec(allowed_tools=["profile.write"]))
        assert not ok
        assert any("profile.write" in e.lower() for e in errors)
