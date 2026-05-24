"""Test memory-service extractor — deterministic candidate extraction."""
from __future__ import annotations

import pytest
from core.memory_service.extractor import extract_memory_candidates_from_session
from core.memory_service.schemas import MemoryCandidate


def _make_result(**overrides) -> dict:
    base: dict = {
        "strategic_governor": {},
        "specialists": {},
        "verifications": {},
        "task_agent_results": [],
        "llm_agent_planner": {},
        "external_mcp_evidence": None,
    }
    base.update(overrides)
    return base


class TestExtractUserPreferences:
    def test_extracts_explicit_preference(self):
        r = _make_result(verifications={"s": {"verifier_route": "approve"}})
        cands = extract_memory_candidates_from_session(
            r, session_id="s1", user_input="I prefer publication-quality README docs.",
        )
        prefs = [c for c in cands if c.memory_type == "user_preference"]
        assert len(prefs) >= 1
        assert prefs[0].content.get("preference") != ""

    def test_ignores_transient_chat(self):
        r = _make_result()
        cands = extract_memory_candidates_from_session(
            r, session_id="s1", user_input="What is CRISPR?",
        )
        prefs = [c for c in cands if c.memory_type == "user_preference"]
        assert len(prefs) == 0


class TestExtractProjectDecisions:
    def test_extracts_governor_rationale(self):
        r = _make_result(
            strategic_governor={
                "rationale": "Use PostgreSQL for the research database — it has better JSON support.",
            },
        )
        cands = extract_memory_candidates_from_session(r, session_id="s1")
        decs = [c for c in cands if c.memory_type == "project_decision"]
        assert len(decs) >= 1
        assert "PostgreSQL" in str(decs[0].content)

    def test_ignores_short_rationale(self):
        r = _make_result(strategic_governor={"rationale": "ok"})
        cands = extract_memory_candidates_from_session(r, session_id="s1")
        decs = [c for c in cands if c.memory_type == "project_decision"]
        assert len(decs) == 0


class TestExtractEvidenceMemory:
    def test_extracts_verifier_approved_evidence(self):
        r = _make_result(
            verifications={
                "research_scout": {
                    "verifier_route": "approve",
                    "evidence_status": "verified",
                    "claims": ["CRISPR-Cas9 shows promise for biomarker detection"],
                },
            },
        )
        cands = extract_memory_candidates_from_session(r, session_id="s1")
        evs = [c for c in cands if c.memory_type == "evidence_memory"]
        assert len(evs) >= 1
        assert evs[0].verifier_route == "approve"
        assert evs[0].requires_verifier is True

    def test_skips_rejected_evidence(self):
        r = _make_result(
            verifications={
                "research_scout": {
                    "verifier_route": "reject",
                    "claims": ["bad claim"],
                },
            },
        )
        cands = extract_memory_candidates_from_session(r, session_id="s1")
        evs = [c for c in cands if c.memory_type == "evidence_memory"]
        assert len(evs) == 0


class TestExtractTaskAgentPatterns:
    def test_extracts_useful_task_agent(self):
        r = _make_result(
            task_agent_results=[
                {
                    "ok": True,
                    "role": "reviewer_objection_mapper",
                    "summary": "Mapped 3 objections to grant sections.",
                    "confidence": "medium",
                    "requires_verification": True,
                    "requires_human_approval": True,
                },
            ],
        )
        cands = extract_memory_candidates_from_session(r, session_id="s1")
        ta = [c for c in cands if c.memory_type == "task_agent_memory"]
        assert len(ta) >= 1
        assert ta[0].requires_human_review is True

    def test_ignores_failed_task_agent(self):
        r = _make_result(
            task_agent_results=[
                {"ok": False, "role": "bad_agent", "summary": ""},
            ],
        )
        cands = extract_memory_candidates_from_session(r, session_id="s1")
        ta = [c for c in cands if c.memory_type == "task_agent_memory"]
        assert len(ta) == 0


class TestExtractPlannerPatterns:
    def test_extracts_planner_routing(self):
        r = _make_result(
            llm_agent_planner={
                "plan_used": True,
                "selected_agents": ["research_scout", "grant_architect"],
                "fallback_used": False,
            },
        )
        cands = extract_memory_candidates_from_session(r, session_id="s1")
        pp = [c for c in cands if c.memory_type == "planner_memory"]
        assert len(pp) >= 1
        assert pp[0].requires_human_review is True
        assert pp[0].confidence == "low"

    def test_ignores_fallback_planner(self):
        r = _make_result(
            llm_agent_planner={
                "plan_used": False,
                "fallback_used": True,
            },
        )
        cands = extract_memory_candidates_from_session(r, session_id="s1")
        pp = [c for c in cands if c.memory_type == "planner_memory"]
        assert len(pp) == 0


class TestExtractMCPToolMemory:
    def test_extracts_useful_mcp_tool(self):
        r = _make_result(
            external_mcp_evidence={
                "local-deep-research": {"ok": True, "summary": "Found 5 sources."},
            },
        )
        cands = extract_memory_candidates_from_session(r, session_id="s1")
        mcp = [c for c in cands if c.memory_type == "mcp_tool_memory"]
        assert len(mcp) >= 1
        assert mcp[0].confidence == "low"

    def test_extracts_failed_mcp_tool(self):
        r = _make_result(
            external_mcp_evidence={
                "bad-server": {"ok": False, "error": "Connection refused"},
            },
        )
        cands = extract_memory_candidates_from_session(r, session_id="s1")
        mcp = [c for c in cands if c.memory_type == "mcp_tool_memory"]
        assert len(mcp) >= 1
        assert mcp[0].content.get("useful") is False


class TestEmptyResult:
    def test_empty_result_no_candidates(self):
        cands = extract_memory_candidates_from_session({})
        assert cands == []

    def test_malformed_result_no_crash(self):
        cands = extract_memory_candidates_from_session(None)
        assert cands == []
