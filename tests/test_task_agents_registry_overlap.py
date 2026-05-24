"""Test overlap detection — broad tasks must route to existing AURA agents."""
from __future__ import annotations

import pytest
from core.task_agents.registry import (
    find_existing_agent_for_task,
    is_allowed_task_agent_role,
    is_forbidden_task_agent_role,
)


class TestOverlapDetection:
    @pytest.mark.parametrize("role,subtask,expected", [
        ("helper", "literature search for CRISPR papers", "research_scout"),
        ("assistant", "please verify these claims about the data", "scientific_verifier"),
        ("writer", "draft a grant proposal on AI drug discovery", "grant_architect"),
        ("analyst", "analyze the patent landscape for mRNA vaccines", "patent_intelligence"),
        ("helper", "create a commercialization strategy for this idea", "founder_innovation"),
        ("assistant", "make a teaching plan for quantum computing", "teaching_mentor"),
    ])
    def test_broad_tasks_route_to_existing(self, role, subtask, expected):
        result = find_existing_agent_for_task(role, subtask)
        assert result == expected, f"Expected '{expected}' for '{subtask}', got '{result}'"

    @pytest.mark.parametrize("role,subtask", [
        ("claim_extractor", "extract claims from this paragraph"),
        ("evidence_table_formatter", "format these evidence records into a table"),
        ("query_variant_generator", "generate alternative search queries for 'CRISPR'"),
        ("repo_issue_classifier", "classify this GitHub issue by AURA module"),
        ("mcp_result_normalizer", "normalize this MCP output into evidence records"),
    ])
    def test_narrow_tasks_no_overlap(self, role, subtask):
        result = find_existing_agent_for_task(role, subtask)
        assert result is None, f"Got unexpected overlap='{result}' for '{subtask}'"

    def test_patent_triggers_patent_intelligence(self):
        assert find_existing_agent_for_task("helper", "freedom to operate analysis") == "patent_intelligence"

    def test_competitor_triggers_founder_innovation(self):
        assert find_existing_agent_for_task("helper", "analyze competitors in this market") == "founder_innovation"

    def test_collaboration_triggers_collaboration_operator(self):
        assert find_existing_agent_for_task("helper", "write outreach draft for collaboration") == "collaboration_operator"

    def test_explanation_triggers_teaching_mentor(self):
        assert find_existing_agent_for_task("helper", "create an explanation of gene editing") == "teaching_mentor"

    def test_data_analysis_triggers_lab_data_analyst(self):
        assert find_existing_agent_for_task("helper", "data analysis of experiment results") == "lab_data_analyst"

    def test_memory_update_triggers_self_evolution(self):
        assert find_existing_agent_for_task("helper", "profile update for research_scout") == "self_evolution_engine"

    def test_routing_triggers_strategic_governor(self):
        assert find_existing_agent_for_task("helper", "routing decision for grant task") == "strategic_governor"


class TestAllowedRoles:
    def test_allowed_roles(self):
        for role in ["claim_extractor", "evidence_table_formatter", "query_variant_generator",
                     "mcp_result_normalizer", "repo_issue_classifier", "competitor_name_extractor",
                     "reviewer_objection_mapper", "risk_register_builder", "test_case_suggester"]:
            assert is_allowed_task_agent_role(role), f"'{role}' should be allowed"

    def test_forbidden_roles(self):
        for role in ["research_scout_clone", "verifier_clone", "grant_architect_clone",
                     "autonomous_coder_agent", "shell_executor_agent", "memory_writer_agent"]:
            assert is_forbidden_task_agent_role(role), f"'{role}' should be forbidden"

    def test_unknown_role_not_allowed(self):
        assert not is_allowed_task_agent_role("random_helper")
        assert not is_allowed_task_agent_role("")
