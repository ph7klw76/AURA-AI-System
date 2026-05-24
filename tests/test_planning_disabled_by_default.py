"""Test planner feature-flag defaults — enabled by default with human-approval gate."""
from __future__ import annotations

import os
from unittest import mock

import pytest
from core.planning.policy import is_planner_enabled, allow_external_mcp, allow_task_agents


class TestEnabledByDefault:
    @pytest.fixture(autouse=True)
    def clear_env(self):
        old = {k: os.environ.get(k) for k in (
            "AURA_LLM_PLANNER_ENABLED",
            "AURA_LLM_PLANNER_ALLOW_EXTERNAL_MCP",
            "AURA_LLM_PLANNER_ALLOW_TASK_AGENTS",
        )}
        for k in old:
            os.environ.pop(k, None)
        yield
        for k, v in old.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)  # Always clean up leaked env vars

    def test_enabled_when_not_set(self):
        assert is_planner_enabled() is True

    def test_disabled_when_set_0(self):
        os.environ["AURA_LLM_PLANNER_ENABLED"] = "0"
        assert is_planner_enabled() is False

    def test_enabled_when_set_1(self):
        os.environ["AURA_LLM_PLANNER_ENABLED"] = "1"
        assert is_planner_enabled() is True

    def test_external_mcp_enabled_by_default(self):
        assert allow_external_mcp() is True

    def test_task_agents_enabled_by_default(self):
        assert allow_task_agents() is True

    def test_existing_routing_unchanged_when_disabled(self):
        """Even when disabled (0), fallback returns Governor's selected agents."""
        os.environ["AURA_LLM_PLANNER_ENABLED"] = "0"
        gov = {"selected_agents": ["research_scout", "scientific_verifier"], "risk_level": "medium"}
        from core.planning.fallback import safe_fallback_plan
        plan = safe_fallback_plan("test prompt", governor_decision=gov)
        assert plan.ok is True
        assert "research_scout" in plan.selected_agents
        assert "scientific_verifier" in plan.selected_agents

    def test_policy_required_by_default(self):
        from core.planning.policy import _require_policy
        assert _require_policy() is True

    def test_verifier_required_by_default(self):
        from core.planning.policy import _require_verifier
        assert _require_verifier() is True


class TestHumanApprovalGate:
    """When planner is enabled, human approval must be forced."""

    def test_planner_gate_forces_human_review_in_meta(self):
        from core.orchestrator import _maybe_plan_agents

        gov_ordered = ["research_scout"]
        gov_decision = {"selected_agents": ["research_scout"]}

        with mock.patch("core.planning.propose_agent_plan") as mock_propose:
            from core.planning.schemas import AgentPlan
            mock_propose.return_value = AgentPlan(
                primary_agent="research_scout",
                requires_verifier=True,
                risk_level="medium",
                confidence="medium",
            )
            with mock.patch("core.planning.validate_agent_plan") as mock_validate:
                from core.planning.schemas import ValidatedAgentPlan
                mock_validate.return_value = ValidatedAgentPlan(
                    ok=True,
                    selected_agents=["research_scout", "scientific_verifier"],
                    risk_level="medium",
                    requires_verifier=True,
                    requires_human_review=False,
                )
                result = _maybe_plan_agents(
                    "research CRISPR biomarkers", "s99", gov_decision, gov_ordered,
                )

        assert result["planner"]["plan_used"] is True
        assert result["planner"].get("requires_human_review") is True, (
            "LLM plan MUST require human approval gate"
        )

    def test_fallback_does_not_force_human_review(self):
        """Deterministic fallback is safe — no human review needed."""
        from core.orchestrator import _maybe_plan_agents

        gov_ordered = ["research_scout"]
        gov_decision = {"selected_agents": ["research_scout"]}

        with mock.patch("core.planning.propose_agent_plan") as mock_propose:
            mock_propose.return_value = mock.Mock(
                confidence="low",
                plan_id="x",
                warnings=["bad"],
                model_dump_json=lambda: "{}",
            )
            with mock.patch("core.planning.validate_agent_plan") as mock_validate:
                from core.planning.schemas import ValidatedAgentPlan
                mock_validate.return_value = ValidatedAgentPlan(
                    ok=False,
                    selected_agents=[],
                    risk_level="low",
                    requires_verifier=True,
                    validation_errors=["Unknown agent"],
                )
                result = _maybe_plan_agents(
                    "test", "s100", gov_decision, gov_ordered,
                )

        assert result["planner"]["fallback_used"] is True
        assert result["planner"].get("requires_human_review") is not True, (
            "Deterministic fallback must NOT require human approval"
        )
