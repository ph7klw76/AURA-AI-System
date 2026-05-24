"""Test planning schemas — Pydantic models."""
from __future__ import annotations

import pytest
from core.planning.schemas import (
    AgentPlan, ValidatedAgentPlan, PlanningContext, PlannerDecisionRecord,
    PLANNABLE_AGENTS, PLANNABLE_HELPER_TEMPLATES, PLANNABLE_MCP_PROVIDERS,
)


class TestAgentPlan:
    def test_default_plan_is_safe(self):
        p = AgentPlan()
        assert p.requires_verifier is True
        assert p.requires_human_review is False
        assert p.risk_level == "low"
        assert p.confidence == "medium"

    def test_full_plan_construction(self):
        p = AgentPlan(
            task_type="research",
            primary_agent="research_scout",
            secondary_agents=["grant_architect", "scientific_verifier"],
            helper_agents=["query_variant_generator"],
            external_mcp=["local_deep_research"],
            evidence_requirement="source_level_evidence",
            risk_level="medium",
            requires_verifier=True,
            requires_human_review=False,
            blocked_actions=["submit_grant"],
            rationale="Mixed task.",
            confidence="medium",
        )
        assert p.primary_agent == "research_scout"
        assert len(p.secondary_agents) == 2

    def test_plan_generates_unique_ids(self):
        p1 = AgentPlan()
        p2 = AgentPlan()
        assert p1.plan_id != p2.plan_id


class TestValidatedAgentPlan:
    def test_ok_plan_transparent(self):
        p = AgentPlan(primary_agent="research_scout")
        v = ValidatedAgentPlan(
            ok=True, plan=p,
            selected_agents=["research_scout", "scientific_verifier"],
            risk_level="low",
        )
        assert v.ok is True
        assert v.plan is not None
        assert len(v.selected_agents) == 2

    def test_rejected_plan_no_plan_leaked(self):
        v = ValidatedAgentPlan(
            ok=False,
            validation_errors=["Unknown agent: evil_bot"],
            risk_level="low",
        )
        assert v.ok is False
        assert v.plan is None
        assert len(v.validation_errors) == 1


class TestPlanningContext:
    def test_default_context_populates_available(self):
        ctx = PlanningContext(user_prompt="test")
        assert len(ctx.available_agents) > 0
        assert "research_scout" in ctx.available_agents
        assert "strategic_governor" not in ctx.available_agents

    def test_custom_context(self):
        ctx = PlanningContext(
            user_prompt="custom",
            governor_decision={"selected_agents": ["research_scout"]},
            risk_hints=["high risk"],
        )
        assert ctx.governor_decision is not None
        assert len(ctx.risk_hints) == 1


class TestRegistries:
    def test_plannable_agents_excludes_governor(self):
        assert "strategic_governor" not in PLANNABLE_AGENTS

    def test_plannable_agents_includes_all_specialists(self):
        for agent in ["research_scout", "grant_architect", "founder_innovation",
                      "patent_intelligence", "scientific_verifier", "self_evolution_engine"]:
            assert agent in PLANNABLE_AGENTS, f"Missing: {agent}"

    def test_helper_templates_complete(self):
        assert "claim_extractor" in PLANNABLE_HELPER_TEMPLATES
        assert "reviewer_objection_mapper" in PLANNABLE_HELPER_TEMPLATES

    def test_mcp_providers_complete(self):
        assert "local_deep_research" in PLANNABLE_MCP_PROVIDERS
        assert "idea_reality" in PLANNABLE_MCP_PROVIDERS
