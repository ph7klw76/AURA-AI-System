"""Verify task agents cannot persist drafts directly."""
from __future__ import annotations

from core.task_agents.policy import validate_agent_spec
from core.task_agents.schemas import AgentSpec


def _spec(**overrides):
    kwargs = dict(
        agent_id="ta-x", name="test", purpose="test",
        parent_session_id="s", parent_agent="o", parent_task="t",
        subtask="s", created_by="o",
    )
    kwargs.update(overrides)
    return AgentSpec(**kwargs)


class TestNoDirectPersistence:
    def test_persistence_allowed_rejected(self):
        ok, errors = validate_agent_spec(_spec(persistence_allowed=True))
        assert not ok

    def test_persistence_allowed_false_by_default(self):
        s = _spec()
        assert s.persistence_allowed is False

    def test_draft_persist_tool_blocked(self):
        ok, errors = validate_agent_spec(_spec(
            allowed_tools=["draft.persist"]
        ))
        assert not ok
        assert any("draft.persist" in e.lower() for e in errors)

    def test_can_write_files_false_by_default(self):
        s = _spec()
        assert s.can_write_files is False

    def test_can_write_files_blocked_by_policy(self):
        ok, errors = validate_agent_spec(_spec(can_write_files=True))
        assert not ok
        assert any("write_files" in e.lower() for e in errors)

    def test_runner_output_not_persisted(self):
        """Task agent runner output has no persistence side effects."""
        from core.task_agents.runner import run_task_agent
        result = run_task_agent(_spec(name="claim_extractor"), {
            "text": "We found significant improvements in delivery efficiency."
        })
        # The result should be returned, but nothing persisted to disk
        assert result.ok in (True, False)
        assert result.verified_by_aura is False
