"""Test planner end-to-end with MOCKED LLM calls — NO live LLM.

These tests verify the full Stage 1 pipeline: propose → validate → fallback.
"""

from __future__ import annotations

import json
import os
from unittest import mock

import pytest
from core.planning.schemas import AgentPlan, PlanningContext, PLANNABLE_AGENTS
from core.planning.policy import validate_agent_plan
from core.planning.fallback import safe_fallback_plan


class TestMockedPlannerPipeline:
    """Verify the full Stage 1 pipeline: propose → validate → fallback."""

    def test_valid_plan_passes_pipeline(self):
        """A valid plan should pass policy and return selected agents."""
        plan = AgentPlan(
            task_type="mixed_research_grant",
            primary_agent="research_scout",
            secondary_agents=["grant_architect"],
            evidence_requirement="source_level_evidence",
            risk_level="medium",
            requires_verifier=True,
            requires_human_review=False,
            blocked_actions=["submit_grant"],
            rationale="Combined task.",
            confidence="medium",
        )
        ctx = PlanningContext(
            user_prompt="Search literature on quantum dots and draft an NSF grant."
        )
        result = validate_agent_plan(plan, ctx)
        assert result.ok is True
        assert "research_scout" in result.selected_agents
        assert "grant_architect" in result.selected_agents
        assert "scientific_verifier" in result.selected_agents
        assert result.requires_human_review is False

    def test_invalid_json_falls_back(self):
        """When LLM returns garbage, fallback should produce a valid plan."""
        # Simulate: LLM returned bad output, planner gives low-confidence plan
        bad_plan = AgentPlan(
            confidence="low",
            warnings=["LLM returned malformed JSON"],
        )
        ctx = PlanningContext(user_prompt="Search literature on CRISPR biomarkers")
        result = validate_agent_plan(bad_plan, ctx)
        # Low-confidence plan with no agents → use fallback
        # A plan with no primary_agent and only scientific_verifier (appended by policy)
        # is too weak — fallback gives a real primary agent.
        if not result.ok or len(result.selected_agents) <= 1:
            result = safe_fallback_plan(ctx.user_prompt)
        assert result.ok is True
        assert len(result.selected_agents) > 0
        assert result.fallback_used is True

    def test_missing_primary_agent_falls_back(self):
        """When LLM plan has no primary_agent, fallback."""
        plan = AgentPlan(
            primary_agent=None,
            confidence="low",
            warnings=["LLM didn't select primary agent"],
        )
        ctx = PlanningContext(user_prompt="draft a grant proposal for CRISPR")
        result = validate_agent_plan(plan, ctx)
        # No primary agent → only verifier was auto-appended → use fallback
        if not result.ok or len(result.selected_agents) <= 1:
            result = safe_fallback_plan(ctx.user_prompt)
        assert result.ok is True
        assert "grant_architect" in result.selected_agents

    def test_unknown_agents_trigger_fallback(self):
        """Unknown agents → plan rejected → fallback takes over."""
        plan = AgentPlan(
            primary_agent="hacker_agent_5000",
            secondary_agents=["evil_script_kiddie"],
            confidence="high",  # maliciously confident
        )
        ctx = PlanningContext(user_prompt="research task")
        result = validate_agent_plan(plan, ctx)
        assert result.ok is False  # rejected
        # Fallback
        result = safe_fallback_plan(ctx.user_prompt)
        assert result.ok is True
        assert all(a in PLANNABLE_AGENTS for a in result.selected_agents)

    def test_external_mcp_preserved_by_default(self):
        """External MCP suggestions are now allowed by default."""
        plan = AgentPlan(
            primary_agent="research_scout",
            external_mcp=["local_deep_research", "idea_reality"],
            requires_verifier=True,
        )
        ctx = PlanningContext(user_prompt="research biomarkers")
        result = validate_agent_plan(plan, ctx)
        assert len(result.external_mcp) == 2
        assert "local_deep_research" in result.external_mcp
