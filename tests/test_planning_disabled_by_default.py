"""Test planner is disabled by default and AURA behavior unchanged."""
from __future__ import annotations

import os
from unittest import mock

import pytest
from core.planning.policy import is_planner_enabled


class TestDisabledByDefault:
    @pytest.fixture(autouse=True)
    def clear_env(self):
        old = os.environ.pop("AURA_LLM_PLANNER_ENABLED", None)
        yield
        if old is not None:
            os.environ["AURA_LLM_PLANNER_ENABLED"] = old

    def test_disabled_when_not_set(self):
        assert is_planner_enabled() is False

    def test_disabled_when_set_0(self):
        os.environ["AURA_LLM_PLANNER_ENABLED"] = "0"
        assert is_planner_enabled() is False

    def test_enabled_when_set_1(self):
        os.environ["AURA_LLM_PLANNER_ENABLED"] = "1"
        assert is_planner_enabled() is True

    def test_existing_routing_unchanged_when_disabled(self):
        """When disabled, the fallback returns the Governor's selected agents."""
        gov = {"selected_agents": ["research_scout", "scientific_verifier"], "risk_level": "medium"}
        from core.planning.fallback import safe_fallback_plan
        plan = safe_fallback_plan("test prompt", governor_decision=gov)
        assert plan.ok is True
        assert "research_scout" in plan.selected_agents
        assert "scientific_verifier" in plan.selected_agents

    def test_all_external_mcp_disabled_by_default(self):
        from core.planning.policy import allow_external_mcp
        assert allow_external_mcp() is False

    def test_all_task_agents_disabled_by_default(self):
        from core.planning.policy import allow_task_agents
        assert allow_task_agents() is False

    def test_policy_required_by_default(self):
        from core.planning.policy import _require_policy
        assert _require_policy() is True
