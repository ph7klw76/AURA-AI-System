"""Test planning policy validation — all 15 policy rules."""
from __future__ import annotations

import os

import pytest
from core.planning.schemas import AgentPlan, PlanningContext
from core.planning.policy import validate_agent_plan, ALWAYS_BLOCKED


class TestPolicyValidation:
    def test_valid_plan_passes(self):
        plan = AgentPlan(
            task_type="research",
            primary_agent="research_scout",
            secondary_agents=["grant_architect"],
            risk_level="medium",
            requires_verifier=True,
        )
        ctx = PlanningContext(user_prompt="Search literature on CRISPR and draft a grant")
        result = validate_agent_plan(plan, ctx)
        assert result.ok is True
        assert "research_scout" in result.selected_agents
        assert "grant_architect" in result.selected_agents

    def test_unknown_primary_agent_blocked(self):
        plan = AgentPlan(primary_agent="evil_bot")
        ctx = PlanningContext(user_prompt="test")
        result = validate_agent_plan(plan, ctx)
        assert result.ok is False
        assert any("evil_bot" in e for e in result.validation_errors)

    def test_unknown_secondary_agent_blocked(self):
        plan = AgentPlan(
            primary_agent="research_scout",
            secondary_agents=["hacker_agent"],
        )
        ctx = PlanningContext(user_prompt="test")
        result = validate_agent_plan(plan, ctx)
        assert result.ok is False
        assert any("hacker_agent" in e for e in result.validation_errors)

    def test_governor_blocked_as_execution_agent(self):
        plan = AgentPlan(primary_agent="strategic_governor")
        ctx = PlanningContext(user_prompt="test")
        result = validate_agent_plan(plan, ctx)
        assert result.ok is False
        assert "strategic_governor" not in result.selected_agents

    def test_verifier_forced_on_scientific_claims(self):
        plan = AgentPlan(
            primary_agent="research_scout",
            requires_verifier=False,
        )
        ctx = PlanningContext(user_prompt="We found evidence that this drug mechanism works.")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_verifier is True
        assert "scientific_verifier" in result.selected_agents

    def test_verifier_not_forced_without_evidence(self):
        plan = AgentPlan(
            task_type="teaching",
            primary_agent="teaching_mentor",
            requires_verifier=False,
        )
        ctx = PlanningContext(user_prompt="Teach me about quantum dots.")
        result = validate_agent_plan(plan, ctx)
        # No scientific claims in prompt → verifier may stay off
        assert result.ok is True

    def test_high_risk_forces_human_review(self):
        plan = AgentPlan(
            primary_agent="patent_intelligence",
            risk_level="high",
            requires_human_review=False,
        )
        ctx = PlanningContext(user_prompt="File a patent for our novel OLED structure.")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_human_review is True

    def test_patent_task_forces_human_review(self):
        plan = AgentPlan(
            primary_agent="patent_intelligence",
            risk_level="medium",
            requires_human_review=False,
        )
        ctx = PlanningContext(user_prompt="Evaluate the patent landscape for this invention.")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_human_review is True

    def test_external_mcp_blocked_by_default(self):
        plan = AgentPlan(
            primary_agent="research_scout",
            external_mcp=["local_deep_research"],
            requires_verifier=True,
        )
        ctx = PlanningContext(user_prompt="Research on biomarkers")
        result = validate_agent_plan(plan, ctx)
        # External MCP blocked by default → stripped
        assert result.external_mcp == []

    def test_external_mcp_allowed_when_enabled(self):
        os.environ["AURA_LLM_PLANNER_ALLOW_EXTERNAL_MCP"] = "1"
        try:
            plan = AgentPlan(
                primary_agent="research_scout",
                external_mcp=["local_deep_research"],
                requires_verifier=True,
            )
            ctx = PlanningContext(user_prompt="Research on biomarkers")
            result = validate_agent_plan(plan, ctx)
            assert "local_deep_research" in result.external_mcp
        finally:
            os.environ.pop("AURA_LLM_PLANNER_ALLOW_EXTERNAL_MCP", None)

    def test_task_agents_blocked_by_default(self):
        plan = AgentPlan(
            primary_agent="research_scout",
            helper_agents=["claim_extractor"],
            requires_verifier=True,
        )
        ctx = PlanningContext(user_prompt="extract claims")
        result = validate_agent_plan(plan, ctx)
        assert result.helper_agents == []

    def test_always_blocked_actions_in_result(self):
        plan = AgentPlan(
            primary_agent="research_scout",
            blocked_actions=[],  # plan says nothing blocked
            requires_verifier=True,
        )
        ctx = PlanningContext(user_prompt="test")
        result = validate_agent_plan(plan, ctx)
        # Always-blocked set should appear
        for ba in ["send_email", "github_write", "memory_write", "self_evolution_approve"]:
            assert ba in result.blocked_actions, f"Missing always-blocked: {ba}"

    def test_low_confidence_warns(self):
        plan = AgentPlan(
            primary_agent="research_scout",
            confidence="low",
            risk_level="medium",
            requires_verifier=True,
        )
        ctx = PlanningContext(user_prompt="science task")
        result = validate_agent_plan(plan, ctx)
        assert any("low" in w.lower() for w in result.validation_warnings)

    def test_mixed_task_valid_plan(self):
        """Full happy-path: research + grant + innovation."""
        plan = AgentPlan(
            task_type="mixed_research_grant_innovation",
            primary_agent="research_scout",
            secondary_agents=["grant_architect", "founder_innovation"],
            helper_agents=["query_variant_generator"],
            external_mcp=[],
            evidence_requirement="source_level_evidence",
            risk_level="medium",
            requires_verifier=True,
            requires_human_review=False,
            blocked_actions=["submit_grant", "send_email", "file_patent"],
            rationale="Mixed task combines literature, grant framing, and market assessment.",
            confidence="medium",
        )
        ctx = PlanningContext(
            user_prompt="Identify novel biomarkers for Alzheimer's, draft an ERC grant, "
                       "and assess commercialisation potential."
        )
        result = validate_agent_plan(plan, ctx)
        assert result.ok is True
        assert "research_scout" in result.selected_agents
        assert "grant_architect" in result.selected_agents
        assert "founder_innovation" in result.selected_agents
        assert "scientific_verifier" in result.selected_agents

    def test_self_evolution_allowed_in_plan(self):
        """self_evolution_engine IS a plannable agent — it may be selected."""
        plan = AgentPlan(
            primary_agent="research_scout",
            secondary_agents=["self_evolution_engine"],
            requires_verifier=True,
        )
        ctx = PlanningContext(user_prompt="Improve AURA's research patterns")
        result = validate_agent_plan(plan, ctx)
        assert "self_evolution_engine" in result.selected_agents
