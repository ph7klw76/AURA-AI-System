"""Verify the LLM planner CANNOT break AURA integrity.

All AURA safety invariants must remain intact regardless of planner output.
"""

from __future__ import annotations

import os

import pytest
from core.planning.schemas import AgentPlan, PlanningContext
from core.planning.policy import validate_agent_plan


def _plan(**kw) -> AgentPlan:
    return AgentPlan(**kw)


class TestVerifierCannotBeDisabled:
    def test_plan_says_verifier_false_policy_forces_true(self):
        plan = _plan(
            primary_agent="research_scout",
            requires_verifier=False,
            confidence="high",  # confident but wrong
        )
        ctx = PlanningContext(user_prompt="Analyze scientific evidence for CRISPR efficacy.")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_verifier is True
        assert "scientific_verifier" in result.selected_agents

    def test_external_mcp_forces_verifier(self):
        plan = _plan(
            primary_agent="research_scout",
            external_mcp=["local_deep_research"],
            requires_verifier=False,
        )
        ctx = PlanningContext(user_prompt="do research")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_verifier is True

    def test_task_agents_force_verifier(self):
        plan = _plan(
            primary_agent="research_scout",
            helper_agents=["claim_extractor"],
            requires_verifier=False,
        )
        ctx = PlanningContext(user_prompt="process data")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_verifier is True

    def test_medium_risk_forces_verifier(self):
        plan = _plan(
            primary_agent="research_scout",
            risk_level="medium",
            requires_verifier=False,
        )
        ctx = PlanningContext(user_prompt="some task")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_verifier is True

    def test_high_risk_forces_verifier(self):
        plan = _plan(
            primary_agent="patent_intelligence",
            risk_level="high",
            requires_verifier=False,
        )
        ctx = PlanningContext(user_prompt="patent analysis")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_verifier is True


class TestHumanReviewCannotBeBypassed:
    def test_patent_forces_human_review(self):
        plan = _plan(
            primary_agent="patent_intelligence",
            risk_level="medium",
            requires_human_review=False,
        )
        ctx = PlanningContext(user_prompt="file a patent for cure for cancer")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_human_review is True

    def test_legal_forces_human_review(self):
        plan = _plan(
            primary_agent="research_scout",
            risk_level="low",
            requires_human_review=False,
        )
        ctx = PlanningContext(user_prompt="legal advice for patent filing")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_human_review is True

    def test_clinical_forces_human_review(self):
        plan = _plan(
            primary_agent="research_scout",
            risk_level="low",
            requires_human_review=False,
        )
        ctx = PlanningContext(user_prompt="clinical trial results analysis")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_human_review is True

    def test_high_risk_forces_human_review(self):
        plan = _plan(
            primary_agent="research_scout",
            risk_level="high",
            requires_human_review=False,
        )
        ctx = PlanningContext(user_prompt="dangerous research")
        result = validate_agent_plan(plan, ctx)
        assert result.requires_human_review is True


class TestBlockedActionsAlwaysPresent:
    def test_submit_grant_blocked(self):
        plan = _plan(primary_agent="grant_architect", requires_verifier=True)
        ctx = PlanningContext(user_prompt="draft grant")
        result = validate_agent_plan(plan, ctx)
        assert "submit_grant" in result.blocked_actions
        assert "send_email" in result.blocked_actions
        assert "github_write" in result.blocked_actions
        assert "memory_write" in result.blocked_actions
        assert "self_evolution_approve" in result.blocked_actions

    def test_even_with_empty_blocked_actions(self):
        plan = _plan(
            primary_agent="research_scout",
            blocked_actions=[],
            requires_verifier=True,
        )
        ctx = PlanningContext(user_prompt="test")
        result = validate_agent_plan(plan, ctx)
        # Always-blocked set should be present
        assert len(result.blocked_actions) >= len({"send_email", "github_write", "memory_write",
                                                    "profile_write", "self_evolution_approve",
                                                    "submit_grant", "file_patent"})


class TestCannotInventPrivilegedAgents:
    def test_autonomous_coder_blocked(self):
        plan = _plan(primary_agent="autonomous_coder")
        ctx = PlanningContext(user_prompt="write code")
        result = validate_agent_plan(plan, ctx)
        assert result.ok is False

    def test_shell_executor_blocked(self):
        plan = _plan(primary_agent="shell_executor")
        ctx = PlanningContext(user_prompt="run command")
        result = validate_agent_plan(plan, ctx)
        assert result.ok is False

    def test_memory_writer_blocked(self):
        plan = _plan(primary_agent="memory_writer")
        ctx = PlanningContext(user_prompt="save this")
        result = validate_agent_plan(plan, ctx)
        assert result.ok is False
