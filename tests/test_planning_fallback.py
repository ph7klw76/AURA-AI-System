"""Test deterministic fallback routing."""
from __future__ import annotations

from core.planning.fallback import safe_fallback_plan


class TestFallback:
    def test_research_routes_to_scout(self):
        p = safe_fallback_plan("search the literature on OLED efficiency")
        assert p.ok
        assert "research_scout" in p.selected_agents

    def test_grant_routes_to_grant_architect(self):
        p = safe_fallback_plan("draft an ERC grant proposal")
        assert p.ok
        assert "grant_architect" in p.selected_agents

    def test_china_grant_routes_to_china_architect(self):
        p = safe_fallback_plan("write an NSFC China grant for perovskite research")
        assert p.ok
        assert "china_grant_architect" in p.selected_agents

    def test_patent_routes_to_patent_intelligence(self):
        p = safe_fallback_plan("analyze patent landscape for mRNA vaccines")
        assert p.ok
        assert "patent_intelligence" in p.selected_agents

    def test_commercialization_routes_to_founder(self):
        p = safe_fallback_plan("create a startup business model for our technology")
        assert p.ok
        assert "founder_innovation" in p.selected_agents

    def test_teaching_routes_to_teaching_mentor(self):
        p = safe_fallback_plan("teach me about CRISPR mechanics")
        assert p.ok
        assert "teaching_mentor" in p.selected_agents

    def test_data_analysis_routes_to_lab_analyst(self):
        p = safe_fallback_plan("analyze the qPCR data from experiment #42")
        assert p.ok
        assert "lab_data_analyst" in p.selected_agents

    def test_collaboration_routes_to_operator(self):
        p = safe_fallback_plan("draft outreach agenda for collaboration with MIT")
        assert p.ok
        assert "collaboration_operator" in p.selected_agents

    def test_public_comms_routes_to_influence(self):
        p = safe_fallback_plan("write a press release about our breakthrough")
        assert p.ok
        assert "influence_public_communication" in p.selected_agents

    def test_unclear_task_is_conservative(self):
        p = safe_fallback_plan("help me with something")
        assert p.ok
        assert "research_scout" in p.selected_agents
        assert "scientific_verifier" in p.selected_agents

    def test_patent_task_forces_verifier_and_human_review(self):
        p = safe_fallback_plan("file a patent for our new drug delivery system")
        assert p.ok
        assert p.requires_verifier is True
        assert p.requires_human_review is True
        assert "scientific_verifier" in p.selected_agents

    def test_grant_task_forces_verifier(self):
        p = safe_fallback_plan("draft an ERC starting grant proposal")
        assert p.ok
        assert p.requires_verifier is True
        assert "scientific_verifier" in p.selected_agents

    def test_respects_governor_decision(self):
        gov = {
            "selected_agents": ["research_scout", "founder_innovation", "scientific_verifier"],
            "risk_level": "medium",
            "evidence_requirement": "source_level_evidence",
        }
        p = safe_fallback_plan("anything", governor_decision=gov)
        assert p.ok
        assert "research_scout" in p.selected_agents
        assert "founder_innovation" in p.selected_agents
        assert "scientific_verifier" in p.selected_agents

    def test_fallback_marks_itself(self):
        p = safe_fallback_plan("some random task")
        assert p.fallback_used is True

    def test_governor_fallback_also_marked(self):
        gov = {"selected_agents": ["research_scout"]}
        p = safe_fallback_plan("anything", governor_decision=gov)
        assert p.fallback_used is True
