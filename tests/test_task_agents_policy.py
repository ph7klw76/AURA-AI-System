"""Test policy enforcement — blocked capabilities, tools, and bounds."""
from __future__ import annotations

import os
import pytest
from core.task_agents.schemas import AgentSpec
from core.task_agents.policy import validate_agent_spec, is_task_agents_enabled


def _make_spec(**overrides) -> AgentSpec:
    kwargs = dict(
        agent_id="ta-test", name="test", purpose="test",
        parent_session_id="s1", parent_agent="orch", parent_task="t",
        subtask="st", created_by="orch",
    )
    kwargs.update(overrides)
    return AgentSpec(**kwargs)


class TestPolicyBlocks:
    def test_can_spawn_agents_rejected(self):
        ok, errors = validate_agent_spec(_make_spec(can_spawn_agents=True))
        assert not ok
        assert any("spawn" in e.lower() for e in errors)

    def test_can_modify_memory_rejected(self):
        ok, errors = validate_agent_spec(_make_spec(can_modify_memory=True))
        assert not ok
        assert any("memory" in e.lower() for e in errors)

    def test_can_modify_profile_rejected(self):
        ok, errors = validate_agent_spec(_make_spec(can_modify_profile=True))
        assert not ok
        assert any("profile" in e.lower() for e in errors)

    def test_persistence_allowed_rejected(self):
        ok, errors = validate_agent_spec(_make_spec(persistence_allowed=True))
        assert not ok
        assert any("persist" in e.lower() for e in errors)

    def test_can_write_files_rejected(self):
        ok, errors = validate_agent_spec(_make_spec(can_write_files=True))
        assert not ok
        assert any("write_files" in e.lower() for e in errors)

    def test_max_steps_exceeds_limit(self):
        ok, errors = validate_agent_spec(_make_spec(max_steps=100))
        assert not ok
        assert any("max_steps" in e.lower() for e in errors)

    def test_timeout_exceeds_limit(self):
        ok, errors = validate_agent_spec(_make_spec(timeout_seconds=9999))
        assert not ok
        assert any("timeout" in e.lower() for e in errors)

    def test_verifier_required_missing(self):
        ok, errors = validate_agent_spec(_make_spec(verifier_required=False))
        assert not ok
        assert any("verifier" in e.lower() for e in errors)

    def test_high_risk_without_human_review(self):
        ok, errors = validate_agent_spec(
            _make_spec(risk_level="high", human_review_required=False)
        )
        assert not ok
        assert any("human_review" in e.lower() for e in errors)

    def test_mcp_servers_without_external_mcp_flag(self):
        ok, errors = validate_agent_spec(
            _make_spec(allowed_mcp_servers=["local_deep_research"])
        )
        assert not ok
        assert any("can_call_external_mcp" in e.lower() for e in errors)

    def test_valid_spec_passes(self):
        ok, errors = validate_agent_spec(_make_spec())
        assert ok, f"Expected OK but got errors: {errors}"
        assert len(errors) == 0


class TestToolValidation:
    def test_allowed_internal_tool_passes(self):
        spec = _make_spec(allowed_tools=["aura.internal.claim_extract"])
        ok, errors = validate_agent_spec(spec)
        assert ok, f"Errors: {errors}"

    def test_allowed_mcp_tool_passes(self):
        spec = _make_spec(
            allowed_tools=["aura.mcp.local_deep_research.search"],
            can_call_external_mcp=True,
        )
        ok, errors = validate_agent_spec(spec)
        assert ok, f"Errors: {errors}"

    def test_shell_tool_rejected(self):
        spec = _make_spec(allowed_tools=["shell.run"])
        ok, errors = validate_agent_spec(spec)
        assert not ok
        assert any("shell" in e.lower() for e in errors)

    def test_github_write_tool_rejected(self):
        spec = _make_spec(allowed_tools=["github.write.push"])
        ok, errors = validate_agent_spec(spec)
        assert not ok
        assert any("github.write" in e.lower() for e in errors)

    def test_github_merge_tool_rejected(self):
        spec = _make_spec(allowed_tools=["github.merge.pr"])
        ok, errors = validate_agent_spec(spec)
        assert not ok

    def test_github_delete_tool_rejected(self):
        spec = _make_spec(allowed_tools=["github.delete.repo"])
        ok, errors = validate_agent_spec(spec)
        assert not ok

    def test_draft_persist_tool_rejected(self):
        spec = _make_spec(allowed_tools=["draft.persist"])
        ok, errors = validate_agent_spec(spec)
        assert not ok
        assert any("draft.persist" in e.lower() for e in errors)

    def test_evolution_approve_rejected(self):
        spec = _make_spec(allowed_tools=["evolution.approve"])
        ok, errors = validate_agent_spec(spec)
        assert not ok

    def test_memory_write_rejected(self):
        spec = _make_spec(allowed_tools=["memory.write"])
        ok, errors = validate_agent_spec(spec)
        assert not ok

    def test_grant_submit_rejected(self):
        spec = _make_spec(allowed_tools=["grant.submit"])
        ok, errors = validate_agent_spec(spec)
        assert not ok

    def test_unprefixed_tool_rejected(self):
        spec = _make_spec(allowed_tools=["some_random_tool"])
        ok, errors = validate_agent_spec(spec)
        assert not ok
        assert any("namespace" in e.lower() for e in errors)


class TestDisabledByDefault:
    @pytest.fixture(autouse=True)
    def clear_env(self):
        old = os.environ.pop("AURA_TASK_AGENTS_ENABLED", None)
        yield
        if old is not None:
            os.environ["AURA_TASK_AGENTS_ENABLED"] = old

    def test_enabled_by_default(self):
        assert is_task_agents_enabled() is True

    def test_enabled_when_set_1(self):
        os.environ["AURA_TASK_AGENTS_ENABLED"] = "1"
        assert is_task_agents_enabled() is True
