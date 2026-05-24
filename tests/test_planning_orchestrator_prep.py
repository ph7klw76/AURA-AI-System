"""Verify planner package does NOT break the orchestrator (Stage 1 — no integration).

These tests confirm that importing the planning package has zero side effects
on the orchestrator and existing agents.
"""

from __future__ import annotations

import sys


class TestNoOrchestratorInterference:
    """Planning package must not import or modify the orchestrator."""

    def test_planner_does_not_touch_orchestrator(self):
        """Import planning — ensure orchestrator is untouched."""
        # Capture current attributes of orchestrator module if loaded
        import core.orchestrator as orch

        attrs_before = set(dir(orch))

        # Import planning
        import core.planning  # noqa: F811

        attrs_after = set(dir(orch))
        assert attrs_before == attrs_after, (
            f"Orchestrator attributes changed! Added: {attrs_after - attrs_before}, "
            f"Removed: {attrs_before - attrs_after}"
        )

    def test_existing_agents_import_unaffected(self):
        """All existing agents must import cleanly after importing planning."""
        import core.planning  # noqa: F401

        from agents.research_scout import run  # noqa: F401
        from agents.grant_architect import run as g  # noqa: F401
        from agents.china_grant_architect import run as cg  # noqa: F401
        from agents.teaching_mentor import run as t  # noqa: F401
        from agents.lab_data_analyst import run as l  # noqa: F401
        from agents.founder_innovation import run as f  # noqa: F401
        from agents.patent_intelligence import run as p  # noqa: F401
        from agents.collaboration_operator import run as co  # noqa: F401
        from agents.influence_public_communication import run as i  # noqa: F401
        from agents.strategic_governor import run as sg  # noqa: F401
        from agents.scientific_verifier import run as sv  # noqa: F401
        from agents.self_evolution_engine import run as se  # noqa: F401
        # If we got here, all imports succeeded
        assert True

    def test_planner_import_only_additive(self):
        """Planning module should not patch or monkey-patch anything."""
        import core.planning  # noqa: F401
        # Check that core.llm still works
        from core.llm import ask_json
        assert callable(ask_json)

    def test_planner_does_not_register_as_agent(self):
        """The planner is NOT an agent — it should not be in AGENT_REGISTRY."""
        from core.registry import AGENT_REGISTRY
        assert "llm_agent_planner" not in AGENT_REGISTRY
        assert "planning" not in AGENT_REGISTRY


class TestStage1NoOrchestratorIntegration:
    """Stage 1 must NOT have any orchestrator integration code."""

    def test_no_planner_in_orchestrator_code(self):
        """Verify orchestrator.py does not reference the planner."""
        with open("core/orchestrator.py") as f:
            text = f.read()
        assert "maybe_plan_agents" not in text, (
            "Stage 1 must NOT have orchestrator integration"
        )
        assert "from core.planning" not in text, (
            "Stage 1 must NOT import planning in orchestrator"
        )

    def test_planner_works_standalone(self):
        """The entire pipeline works standalone without orchestrator."""
        from core.planning.schemas import AgentPlan, PlanningContext
        from core.planning.policy import validate_agent_plan
        from core.planning.fallback import safe_fallback_plan

        # Propose (mocked)
        plan = AgentPlan(
            primary_agent="research_scout",
            requires_verifier=True,
            risk_level="low",
        )
        # Validate
        ctx = PlanningContext(user_prompt="research task")
        result = validate_agent_plan(plan, ctx)
        assert result.ok is True
        assert "research_scout" in result.selected_agents

        # Fallback
        fb = safe_fallback_plan("grant proposal")
        assert fb.ok is True
