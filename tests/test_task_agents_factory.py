"""Test factory — proposal logic for task agents."""
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


class TestFactoryBlocksOverlap:
    @pytest.mark.parametrize("role,subtask,expected_agent", [
        ("helper", "literature search for novel biomarkers", "research_scout"),
        ("assistant", "verify these claims about quantum materials", "scientific_verifier"),
        ("writer", "draft a grant proposal on drug repurposing", "grant_architect"),
        ("researcher", "patent landscape for CAR-T therapy", "patent_intelligence"),
    ])
    def test_overlap_routes_to_existing(self, role, subtask, expected_agent):
        req = TaskAgentRequest(
            parent_session_id="s1", parent_agent="orchestrator",
            requested_role=role, subtask=subtask,
        )
        dec = propose_task_agent(req)
        assert dec.create_agent is False
        assert dec.use_existing_agent == expected_agent, f"Got {dec.use_existing_agent} for {subtask}"

    def test_narrow_claim_extractor_allowed(self):
        req = TaskAgentRequest(
            parent_session_id="s1", parent_agent="orchestrator",
            requested_role="claim_extractor",
            subtask="extract claims from this research summary paragraph",
        )
        dec = propose_task_agent(req)
        assert dec.create_agent is True, f"Reason: {dec.reason}"
        assert dec.proposed_spec is not None

    def test_forbidden_role_blocked(self):
        req = TaskAgentRequest(
            parent_session_id="s1", parent_agent="orchestrator",
            requested_role="autonomous_coder_agent",
            subtask="write a Python script",
        )
        dec = propose_task_agent(req)
        assert dec.create_agent is False
        assert "forbidden" in dec.reason.lower()

    def test_unknown_role_blocked(self):
        req = TaskAgentRequest(
            parent_session_id="s1", parent_agent="orchestrator",
            requested_role="random_custom_agent",
            subtask="do something",
        )
        dec = propose_task_agent(req)
        assert dec.create_agent is False

    def test_disabled_no_creation(self):
        os.environ["AURA_TASK_AGENTS_ENABLED"] = "0"
        req = TaskAgentRequest(
            parent_session_id="s1", parent_agent="orchestrator",
            requested_role="claim_extractor",
            subtask="extract claims from text",
        )
        dec = propose_task_agent(req)
        assert dec.create_agent is False
        assert "disabled" in dec.reason.lower()
        os.environ["AURA_TASK_AGENTS_ENABLED"] = "1"

    def test_allowed_roles_all_create(self):
        for role in ["evidence_table_formatter", "query_variant_generator",
                     "mcp_result_normalizer", "repo_issue_classifier",
                     "reviewer_objection_mapper", "risk_register_builder"]:
            req = TaskAgentRequest(
                parent_session_id="s1", parent_agent="orchestrator",
                requested_role=role,
                subtask=f"perform {role} on input data",
            )
            dec = propose_task_agent(req)
            assert dec.create_agent is True, f"{role}: {dec.reason}"
