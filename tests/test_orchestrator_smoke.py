import pytest
from unittest.mock import patch


MOCK_GOVERNOR = {
    # Core routing (backward-compat)
    "task_type": "research_analysis",
    "priority": "medium",
    "selected_agents": ["research_scout", "scientific_verifier", "self_evolution_engine"],
    "research_scout_mode": "ideation",
    "requires_approval": False,
    "approval_reason": "",
    "risk_level": "low",
    "rationale": "Mock decision.",
    # New fields
    "mission_alignment_score": 0.8,
    "strategic_value_score": 0.7,
    "urgency_score": 0.5,
    "should_this_be_done": "yes",
    "autonomy_level": "L2",
    "external_consequence": "none",
    "evidence_requirement": "medium",
    "blocked_actions": [],
    "workflow_sequence": [],     # empty → falls back to selected_agents
    "agent_configs": {},
    "task_decomposition": [],
    "memory_policy": {"retrieve_memory": True, "allow_memory_write": True, "memory_write_requires_approval": False},
    "self_evolution_policy": {"run": True, "reason": "Mock session."},
}

MOCK_SCOUT = {
    "agent_name": "research_scout",
    "mode": "ideation",
    "summary": "Mock scout output",
    "opportunity_map": [],
    "top_papers": [],
    "claim_evidence_map": [],
    "research_gap_candidates": [],
    "research_gap_candidate": "",
    "novelty_risks": [],
    "methodology_risks": [],
    "grant_angles": [],
    "collaboration_targets": [],
    "kill_criteria": [],
    "findings": [],
    "risks": [],
    "recommended_actions": [],
    "queries_used": [],
    "queries_recommended_next": [],
    "search_queries": [],
    "confidence": "medium",
    "evidence_quality": "moderate",
    "requires_scientific_verification": True,
    "literature_scan_used": False,
    "claims_for_verification": [],
    "partial_results": False,
    "failed_stage": "",
    "recovery_action": "",
    "report_paths": [],
}

MOCK_VERIFIER = {
    "overall_assessment": "acceptable",
    "claim_checks": [],
    "methodology_risks": [],
    "novelty_risks": [],
    "citation_risks": [],
    "grant_risks": [],
    "action_governance_risks": [],
    "required_human_approvals": [],
    "revision_instructions": [],
    "final_recommendation": "revise",
    "route": "revise",
    "verified_at": "2025-01-01T00:00:00+00:00",
    "model_used": "qwen3:8b",
    "truncated": False,
    "evidence_sources_checked": [],
    # backward-compat flat fields
    "unsupported_claims": [],
    "assumptions": [],
    "risks": [],
    "corrections": [],
}

MOCK_EVOLUTION = {
    # New structured fields
    "session_assessment": "Session completed successfully.",
    "failure_modes": [],
    "lesson_details": [],
    "memory_update_proposals": [],
    "workflow_update_proposals": [],
    "rubric_update_proposals": [],
    "profile_update_proposals": [],
    "next_experiments": [],
    "human_approval_required": False,
    "do_not_learn": [],
    # Backward-compat flat fields
    "what_worked": ["governor routing"],
    "what_failed_or_was_weak": [],
    "reusable_lessons": [],
    "memory_updates": [],
    "workflow_improvements": [],
    "suggested_profile_updates": [],
}


def test_orchestrator_returns_all_agents(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")
    monkeypatch.setattr(config, "REFLECTION_PATH", tmp_path / "reflections.jsonl")
    monkeypatch.setattr(config, "APPROVAL_LOG_PATH", tmp_path / "approval_log.jsonl")
    monkeypatch.setattr(config, "RESEARCH_DB_PATH", tmp_path / "research_memory.db")

    with patch("agents.strategic_governor.run", return_value=MOCK_GOVERNOR):
        with patch("agents.research_scout.run", return_value=MOCK_SCOUT):
            with patch("agents.scientific_verifier.run", return_value=MOCK_VERIFIER):
                with patch("agents.self_evolution_engine.run", return_value=MOCK_EVOLUTION):
                    from core.orchestrator import run_aura_core
                    result = run_aura_core("Analyse TADF OLED opportunity")

    assert "strategic_governor" in result
    assert "research_scout" in result
    assert "scientific_verifier" in result
    assert "self_evolution_engine" in result
    assert result["strategic_governor"]["task_type"] == "research_analysis"


def test_orchestrator_passes_scout_mode(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")
    monkeypatch.setattr(config, "REFLECTION_PATH", tmp_path / "reflections.jsonl")
    monkeypatch.setattr(config, "APPROVAL_LOG_PATH", tmp_path / "approval_log.jsonl")
    monkeypatch.setattr(config, "RESEARCH_DB_PATH", tmp_path / "research_memory.db")

    lit_governor = {**MOCK_GOVERNOR, "research_scout_mode": "literature_scan"}
    captured = {}

    def mock_scout(user_input, context, mode):
        captured["mode"] = mode
        return {**MOCK_SCOUT, "mode": mode}

    with patch("agents.strategic_governor.run", return_value=lit_governor):
        with patch("agents.research_scout.run", side_effect=mock_scout):
            with patch("agents.scientific_verifier.run", return_value=MOCK_VERIFIER):
                with patch("agents.self_evolution_engine.run", return_value=MOCK_EVOLUTION):
                    from core.orchestrator import run_aura_core
                    run_aura_core("Find recent TADF papers on arXiv")

    assert captured.get("mode") == "literature_scan"


def test_orchestrator_handles_agent_failure(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")
    monkeypatch.setattr(config, "REFLECTION_PATH", tmp_path / "reflections.jsonl")
    monkeypatch.setattr(config, "APPROVAL_LOG_PATH", tmp_path / "approval_log.jsonl")
    monkeypatch.setattr(config, "RESEARCH_DB_PATH", tmp_path / "research_memory.db")

    with patch("agents.strategic_governor.run", side_effect=RuntimeError("Governor crashed")):
        with patch("agents.self_evolution_engine.run", return_value=MOCK_EVOLUTION):
            from core.orchestrator import run_aura_core
            result = run_aura_core("Test failure handling")

    assert "errors" in result
    assert len(result["errors"]) >= 1
