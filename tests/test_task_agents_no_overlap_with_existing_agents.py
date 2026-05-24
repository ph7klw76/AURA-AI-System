"""Verify task agents NEVER replace existing AURA agents."""
from __future__ import annotations

import os

import pytest
from core.task_agents.schemas import TaskAgentRequest
from core.task_agents.factory import propose_task_agent


@pytest.fixture(autouse=True)
def enable_task_agents():
    old = os.environ.get("AURA_TASK_AGENTS_ENABLED", "")
    os.environ["AURA_TASK_AGENTS_ENABLED"] = "1"
    yield
    if old:
        os.environ["AURA_TASK_AGENTS_ENABLED"] = old
    else:
        os.environ.pop("AURA_TASK_AGENTS_ENABLED", None)


class TestNoOverlapWithExistingAgents:
    """Every broad task that belongs to an existing AURA agent MUST NOT create a task agent."""

    def test_cant_replace_governor(self):
        """Routing decision stays with strategic_governor."""
        dec = propose_task_agent(TaskAgentRequest(
            parent_session_id="s1", parent_agent="orch",
            requested_role="helper",
            subtask="classify this research task and route to agents",
        ))
        assert dec.create_agent is False
        assert dec.use_existing_agent == "strategic_governor"

    def test_cant_replace_research_scout(self):
        """Literature search stays with research_scout."""
        dec = propose_task_agent(TaskAgentRequest(
            parent_session_id="s1", parent_agent="orch",
            requested_role="assistant",
            subtask="search the literature on Alzheimer's biomarkers",
        ))
        assert dec.create_agent is False
        assert dec.use_existing_agent == "research_scout"

    def test_cant_replace_grant_architect(self):
        """Grant drafting stays with grant_architect."""
        dec = propose_task_agent(TaskAgentRequest(
            parent_session_id="s1", parent_agent="orch",
            requested_role="writer",
            subtask="draft a grant proposal on AI for drug discovery",
        ))
        assert dec.create_agent is False
        assert dec.use_existing_agent == "grant_architect"

    def test_cant_replace_verifier(self):
        """Verification stays with scientific_verifier."""
        dec = propose_task_agent(TaskAgentRequest(
            parent_session_id="s1", parent_agent="orch",
            requested_role="checker",
            subtask="fact check these claims about clinical trial results",
        ))
        assert dec.create_agent is False
        assert dec.use_existing_agent == "scientific_verifier"

    def test_cant_replace_patent_intelligence(self):
        """Patent analysis stays with patent_intelligence."""
        dec = propose_task_agent(TaskAgentRequest(
            parent_session_id="s1", parent_agent="orch",
            requested_role="analyst",
            subtask="investigate the patent landscape for CRISPR diagnostics",
        ))
        assert dec.create_agent is False
        assert dec.use_existing_agent == "patent_intelligence"

    def test_cant_replace_founder_innovation(self):
        """Commercialization stays with founder_innovation."""
        dec = propose_task_agent(TaskAgentRequest(
            parent_session_id="s1", parent_agent="orch",
            requested_role="strategist",
            subtask="create a commercialization strategy for our RNA platform",
        ))
        assert dec.create_agent is False
        assert dec.use_existing_agent == "founder_innovation"

    def test_cant_replace_teaching_mentor(self):
        """Teaching stays with teaching_mentor."""
        dec = propose_task_agent(TaskAgentRequest(
            parent_session_id="s1", parent_agent="orch",
            requested_role="educator",
            subtask="create teaching material about gene editing",
        ))
        assert dec.create_agent is False
        assert dec.use_existing_agent == "teaching_mentor"

    def test_cant_replace_lab_data_analyst(self):
        """Data analysis stays with lab_data_analyst."""
        dec = propose_task_agent(TaskAgentRequest(
            parent_session_id="s1", parent_agent="orch",
            requested_role="analyst",
            subtask="analyze this data from the qPCR experiment",
        ))
        assert dec.create_agent is False
        assert dec.use_existing_agent == "lab_data_analyst"

    def test_cant_replace_collaboration_operator(self):
        """Collaboration stays with collaboration_operator."""
        dec = propose_task_agent(TaskAgentRequest(
            parent_session_id="s1", parent_agent="orch",
            requested_role="coordinator",
            subtask="draft outreach email for potential collaboration",
        ))
        assert dec.create_agent is False
        assert dec.use_existing_agent == "collaboration_operator"

    def test_cant_replace_self_evolution(self):
        """Memory/profile updates stay with self_evolution_engine."""
        dec = propose_task_agent(TaskAgentRequest(
            parent_session_id="s1", parent_agent="orch",
            requested_role="improver",
            subtask="update memory with lessons from this session",
        ))
        assert dec.create_agent is False
        assert dec.use_existing_agent == "self_evolution_engine"
