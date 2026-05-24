"""Test Stage 2 orchestrator integration — planner hook in run_aura_core."""
from __future__ import annotations

import os
from unittest import mock

import pytest


class TestMaybePlanAgentsDisabledByDefault:
    """When disabled, the planner hook returns the Governor's agents unchanged."""

    def test_disabled_returns_governor_ordered_unchanged(self):
        from core.orchestrator import _maybe_plan_agents

        gov_ordered = ["research_scout", "grant_architect"]
        gov_decision = {
            "selected_agents": ["research_scout", "grant_architect"],
            "risk_level": "medium",
        }
        result = _maybe_plan_agents("draft a grant", "s1", gov_decision, gov_ordered)
        assert result["augmented_ordered"] == gov_ordered
        assert result["planner"]["enabled"] is False

    def test_disabled_does_not_remove_agents(self):
        from core.orchestrator import _maybe_plan_agents

        gov_ordered = ["research_scout", "patent_intelligence", "founder_innovation"]
        result = _maybe_plan_agents("analyze patent", "s2", {}, gov_ordered)
        assert result["augmented_ordered"] == gov_ordered

    def test_disabled_records_planner_meta(self):
        from core.orchestrator import _maybe_plan_agents

        result = _maybe_plan_agents("test", "s3", {}, ["research_scout"])
        assert result["planner"]["plan_used"] is False
        assert result["planner"]["fallback_used"] is False
        assert result["planner"]["enabled"] is False


class TestMaybePlanAgentsEnabled:
    """When enabled, the planner augments but never removes Governor agents."""

    @pytest.fixture(autouse=True)
    def enable_planner(self):
        old = os.environ.get("AURA_LLM_PLANNER_ENABLED", "")
        os.environ["AURA_LLM_PLANNER_ENABLED"] = "1"
        yield
        if old:
            os.environ["AURA_LLM_PLANNER_ENABLED"] = old
        else:
            os.environ.pop("AURA_LLM_PLANNER_ENABLED", None)

    def mock_planner_plan(self, primary="research_scout", secondary=None, **kw):
        """Return a mock AgentPlan with valid agents."""
        from core.planning.schemas import AgentPlan
        defaults = dict(
            primary_agent=primary,
            secondary_agents=secondary or [],
            requires_verifier=True,
            risk_level="medium",
            confidence="medium",
        )
        defaults.update(kw)
        return AgentPlan(**defaults)

    def test_planner_augments_governor_agents(self):
        """Planner adds agents but never removes Governor's."""
        from core.orchestrator import _maybe_plan_agents

        gov_ordered = ["research_scout"]
        gov_decision = {"selected_agents": ["research_scout"]}

        with mock.patch("core.planning.propose_agent_plan") as mock_propose:
            mock_propose.return_value = self.mock_planner_plan("research_scout")
            with mock.patch("core.planning.validate_agent_plan") as mock_validate:
                from core.planning.schemas import ValidatedAgentPlan
                mock_validate.return_value = ValidatedAgentPlan(
                    ok=True,
                    selected_agents=["research_scout", "grant_architect", "scientific_verifier"],
                    risk_level="medium",
                    requires_verifier=True,
                    requires_human_review=False,
                )
                result = _maybe_plan_agents(
                    "research and draft grant on CRISPR", "s4", gov_decision, gov_ordered,
                )

        assert "research_scout" in result["augmented_ordered"], "Must preserve Governor agents"
        assert result["planner"]["enabled"] is True
        assert result["planner"]["plan_used"] is True

    def test_planner_never_removes_governor_agents(self):
        """Even if the planner omits a Governor agent, it stays."""
        from core.orchestrator import _maybe_plan_agents

        gov_ordered = ["research_scout", "patent_intelligence", "founder_innovation"]
        gov_decision = {"selected_agents": list(gov_ordered)}

        with mock.patch("core.planning.propose_agent_plan") as mock_propose:
            # Planner only picks research_scout — but patent and founder must stay
            mock_propose.return_value = self.mock_planner_plan("research_scout")
            with mock.patch("core.planning.validate_agent_plan") as mock_validate:
                from core.planning.schemas import ValidatedAgentPlan
                mock_validate.return_value = ValidatedAgentPlan(
                    ok=True,
                    selected_agents=["research_scout", "scientific_verifier"],
                    risk_level="medium",
                    requires_verifier=True,
                )
                result = _maybe_plan_agents(
                    "research task", "s5", gov_decision, gov_ordered,
                )

        for gov_agent in gov_ordered:
            assert gov_agent in result["augmented_ordered"], (
                f"Governor agent '{gov_agent}' was removed by planner"
            )

    def test_planner_fallback_on_low_confidence(self):
        """Low-confidence plans trigger fallback."""
        from core.orchestrator import _maybe_plan_agents

        gov_ordered = ["research_scout"]
        gov_decision = {"selected_agents": ["research_scout"]}

        with mock.patch("core.planning.propose_agent_plan") as mock_propose:
            mock_propose.return_value = self.mock_planner_plan(
                primary="hacker_agent", confidence="low",
            )
            with mock.patch("core.planning.validate_agent_plan") as mock_validate:
                from core.planning.schemas import ValidatedAgentPlan
                mock_validate.return_value = ValidatedAgentPlan(
                    ok=False,
                    selected_agents=[],
                    risk_level="low",
                    requires_verifier=True,
                    validation_errors=["Unknown agent: hacker_agent"],
                )
                result = _maybe_plan_agents(
                    "dangerous request", "s6", gov_decision, gov_ordered,
                )

        assert result["planner"]["fallback_used"] is True
        assert "research_scout" in result["augmented_ordered"]

    def test_planner_non_fatal_on_crash(self):
        """If the planner throws, the orchestrator continues with Governor agents."""
        from core.orchestrator import _maybe_plan_agents

        gov_ordered = ["research_scout", "scientific_verifier"]
        gov_decision = {"selected_agents": ["research_scout"]}

        with mock.patch("core.planning.propose_agent_plan",
                        side_effect=RuntimeError("LLM server exploded")):
            result = _maybe_plan_agents("test", "s7", gov_decision, gov_ordered)

        assert "research_scout" in result["augmented_ordered"]
        assert result["planner"]["enabled"] is True
        assert result["planner"]["fallback_used"] is True


class TestRunAuraCoreWithPlanner:
    """End-to-end: run_aura_core with planner enabled."""

    @pytest.fixture(autouse=True)
    def enable_planner(self):
        old = os.environ.get("AURA_LLM_PLANNER_ENABLED", "")
        os.environ["AURA_LLM_PLANNER_ENABLED"] = "1"
        yield
        if old:
            os.environ["AURA_LLM_PLANNER_ENABLED"] = old
        else:
            os.environ.pop("AURA_LLM_PLANNER_ENABLED", None)

    def test_result_contains_planner_metadata(self):
        """run_aura_core result must include llm_agent_planner key."""
        from core.orchestrator import run_aura_core

        with mock.patch("core.planning.propose_agent_plan") as mock_propose:
            from core.planning.schemas import AgentPlan
            mock_propose.return_value = AgentPlan(
                primary_agent="research_scout",
                requires_verifier=True,
                risk_level="low",
                confidence="medium",
            )
            with mock.patch("core.planning.validate_agent_plan") as mock_validate:
                from core.planning.schemas import ValidatedAgentPlan
                mock_validate.return_value = ValidatedAgentPlan(
                    ok=True,
                    selected_agents=["research_scout", "scientific_verifier"],
                    risk_level="low",
                    requires_verifier=True,
                    requires_human_review=False,
                )
                with mock.patch("agents.strategic_governor.run") as mock_gov:
                    mock_gov.return_value = {
                        "selected_agents": ["research_scout"],
                        "agent_configs": {},
                        "workflow_sequence": [],
                        "research_scout_mode": "ideation",
                        "risk_level": "low",
                        "blocked_actions": [],
                        "evidence_requirement": "low",
                        "requires_approval": False,
                        "memory_policy": {"retrieve_memory": True, "allow_memory_write": False, "memory_write_requires_approval": True},
                        "self_evolution_policy": {"run": False, "reason": "test"},
                    }
                    with mock.patch("core.orchestrator._run_specialist_step") as mock_step:
                        mock_step.return_value = {
                            "ok": True, "findings": [], "claims": [],
                            "verification": {"route": "approve", "checks": []},
                        }
                        result = run_aura_core("test research task")

        assert "llm_agent_planner" in result
        planner = result["llm_agent_planner"]
        assert "enabled" in planner
        assert "selected_agents" in planner

    def test_planner_disabled_no_live_llm(self):
        """When disabled (default), run_aura_core works without planner."""
        os.environ.pop("AURA_LLM_PLANNER_ENABLED", None)
        from core.orchestrator import run_aura_core

        with mock.patch("agents.strategic_governor.run") as mock_gov:
            mock_gov.return_value = {
                "selected_agents": ["research_scout"],
                "agent_configs": {},
                "workflow_sequence": [],
                "research_scout_mode": "ideation",
                "risk_level": "low",
                "blocked_actions": [],
                "evidence_requirement": "low",
                "requires_approval": False,
                "memory_policy": {"retrieve_memory": True, "allow_memory_write": False, "memory_write_requires_approval": True},
                "self_evolution_policy": {"run": False, "reason": "test"},
            }
            with mock.patch("core.orchestrator._run_specialist_step") as mock_step:
                mock_step.return_value = {
                    "ok": True, "findings": [], "claims": [],
                    "verification": {"route": "approve", "checks": []},
                }
                with mock.patch("core.orchestrator._run_holistic_verifier") as mock_hol:
                    mock_hol.return_value = {
                        "route": "approve", "ok": True,
                        "summary": "test", "checks": [],
                    }
                    result = run_aura_core("test task")

        assert "llm_agent_planner" in result
        assert result["llm_agent_planner"]["enabled"] is False
        assert "errors" in result
