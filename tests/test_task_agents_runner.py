"""Test runner — all 10 task-agent types produce safe, unverified output."""
from __future__ import annotations

import pytest
from core.task_agents.schemas import AgentSpec, TaskAgentResult
from core.task_agents.runner import run_task_agent


def _spec(name="claim_extractor"):
    return AgentSpec(
        agent_id=f"ta-{name}", name=name, purpose="test",
        parent_session_id="s1", parent_agent="orch", parent_task="t",
        subtask="st", created_by="orch",
    )


class TestRunnerSafety:
    """All runner outputs must be marked verified_by_aura=False."""

    def test_claim_extractor_unverified(self):
        result = run_task_agent(_spec("claim_extractor"), {
            "text": "We found that CRISPR-Cas9 significantly improves editing efficiency. It is likely that delivery vectors limit in vivo applications."
        })
        assert result.ok is True
        assert result.verified_by_aura is False
        assert result.requires_verification is True
        assert len(result.claims_for_verification) > 0

    def test_claim_extractor_empty_input(self):
        result = run_task_agent(_spec("claim_extractor"), {"text": ""})
        assert result.ok is False

    def test_evidence_table_formatter_unverified(self):
        result = run_task_agent(_spec("evidence_table_formatter"), {
            "evidence_records": [
                {"source": "PubMed", "claim": "X causes Y", "support": "strong"},
                {"source": "arxiv", "claim": "A predicts B", "support": "moderate"},
            ]
        })
        assert result.ok is True
        assert result.verified_by_aura is False
        assert len(result.evidence_records) == 2

    def test_query_variant_generator(self):
        result = run_task_agent(_spec("query_variant_generator"), {
            "topic": "CRISPR gene editing"
        })
        assert result.ok is True
        assert result.verified_by_aura is False
        assert len(result.findings) > 3

    def test_mcp_result_normalizer(self):
        result = run_task_agent(_spec("mcp_result_normalizer"), {
            "mcp_result": {"text": "Research result from PubMed: ...", "data": ["a", "b"]},
            "mcp_server": "test_mcp",
        })
        assert result.ok is True
        assert result.verified_by_aura is False
        assert len(result.evidence_records) > 0

    def test_repo_issue_classifier(self):
        result = run_task_agent(_spec("repo_issue_classifier"), {
            "title": "Bug: literature search returns empty results",
            "body": "When searching for papers on quantum computing, the research_scout returns nothing.",
        })
        assert result.ok is True
        assert result.verified_by_aura is False

    def test_competitor_name_extractor(self):
        result = run_task_agent(_spec("competitor_name_extractor"), {
            "idea_reality_output": 'Competitors include "Acme Corp" and "Beta Ltd". The startup DeepMind is also relevant.',
        })
        assert result.ok is True
        assert result.verified_by_aura is False
        # Should extract at least the quoted names
        names = result.findings
        assert any("Acme Corp" in n for n in names)

    def test_reviewer_objection_mapper(self):
        result = run_task_agent(_spec("reviewer_objection_mapper"), {
            "draft": "This novel approach uses CRISPR-Cas9. The method is significant but the feasibility in vivo is unknown. Budget constraints may limit the study."
        })
        assert result.ok is True
        assert result.verified_by_aura is False
        assert len(result.findings) > 0

    def test_risk_register_builder(self):
        result = run_task_agent(_spec("risk_register_builder"), {
            "project_description": "The project depends on third-party API and has risks around security. Failure to get funding could delay the timeline."
        })
        assert result.ok is True
        assert result.verified_by_aura is False

    def test_test_case_suggester(self):
        result = run_task_agent(_spec("test_case_suggester"), {
            "description": "A function that takes input parameters and returns an output. Should handle edge cases gracefully."
        })
        assert result.ok is True
        assert result.verified_by_aura is False

    def test_local_document_excerpt_summarizer(self):
        result = run_task_agent(_spec("local_document_excerpt_summarizer"), {
            "text": "First sentence. Second sentence with more detail. Third sentence. Fourth sentence about conclusions.",
        })
        assert result.ok is True
        assert result.verified_by_aura is False

    def test_unknown_role_errors(self):
        result = run_task_agent(_spec("nonexistent_agent"), {})
        assert result.ok is False
        assert len(result.errors) > 0

    def test_confidence_is_low_or_medium(self):
        """Task agents should never have high confidence."""
        for role in ["claim_extractor", "query_variant_generator", "repo_issue_classifier"]:
            result = run_task_agent(_spec(role), {"text": "test", "topic": "test", "title": "t", "body": "b"})
            assert result.confidence in ("low", "medium"), f"{role} had confidence {result.confidence}"
