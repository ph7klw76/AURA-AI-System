import pytest
from unittest.mock import patch

from agents.self_evolution_engine import (
    _extract_session_content,
    _check_verifier_quality,
    _classify_failure_modes,
    _save_approved_lessons,
    run,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VERIFIER_REJECT = {
    "route": "reject",
    "overall_assessment": "weak",
    "final_recommendation": "Major revision required.",
    "claim_checks": [
        {
            "claim": "EQE of 30% achieved",
            "claim_type": "performance",
            "support_status": "unsupported",
            "severity": "critical",
            "confidence": 0.9,
            "evidence_needed": ["Independent replication"],
            "correction": "No evidence in cited papers supports 30% EQE.",
        },
        {
            "claim": "Novel emitter design",
            "claim_type": "novelty",
            "support_status": "partially_supported",
            "severity": "high",
            "confidence": 0.7,
            "evidence_needed": [],
            "correction": "Similar designs reported in 2023.",
        },
    ],
    "revision_instructions": ["Provide primary data for EQE claim.", "Cite prior art for emitter design."],
    "required_human_approvals": ["High-risk novelty claim requires expert sign-off."],
    "methodology_risks": [],
    "novelty_risks": [],
    "citation_risks": [],
    "grant_risks": [],
    "action_governance_risks": [],
    "unsupported_claims": [],
    "assumptions": [],
    "risks": [],
    "corrections": [],
}

_SCOUT_PARTIAL = {
    "mode": "literature_scan",
    "confidence": "low",
    "evidence_quality": "weak",
    "partial_results": True,
    "failed_stage": "paper_scoring",
    "top_papers": [],
    "research_gap_candidates": [],
    "literature_scan_used": False,
}

_ALL_OUTPUTS_FULL = {
    "user_input": "Analyse TADF OLED opportunity",
    "strategic_governor": {
        "task_type": "research_analysis",
        "risk_level": "low",
        "research_scout_mode": "ideation",
    },
    "research_scout": {
        "mode": "ideation",
        "confidence": "medium",
        "evidence_quality": "moderate",
        "partial_results": False,
        "failed_stage": "",
        "top_papers": [{"title": "Paper A"}, {"title": "Paper B"}],
        "research_gap_candidates": [{"gap_statement": "Gap 1"}],
        "literature_scan_used": True,
    },
    "scientific_verifier": _VERIFIER_REJECT,
    "errors": [],
}

_MOCK_LLM_RESPONSE = {
    "session_assessment": "Good session with evidence quality concerns.",
    "failure_modes": ["overclaimed_novelty"],
    "lesson_details": [
        {
            "lesson": "Always verify EQE claims against primary literature before including in reports.",
            "failure_type": "overclaimed_novelty",
            "confidence": 0.85,
            "scope": "domain",
            "evidence_basis": "Verifier flagged unsupported EQE claim at critical severity.",
            "risk_if_applied": "low",
            "save_decision": "save_now",
            "applies_to_modes": ["ideation", "literature_scan"],
        },
        {
            "lesson": "Session used wrong paper source.",
            "failure_type": "scope_mismatch",
            "confidence": 0.3,
            "scope": "session",
            "evidence_basis": "Single session observation.",
            "risk_if_applied": "low",
            "save_decision": "discard",
            "applies_to_modes": [],
        },
    ],
    "memory_update_proposals": ["EQE claims require primary data support."],
    "workflow_update_proposals": ["Add novelty pre-check before verifier."],
    "rubric_update_proposals": [],
    "profile_update_proposals": [],
    "next_experiments": [
        {
            "description": "Scan recent TADF EQE papers on arXiv.",
            "motivation": "Establish EQE baseline.",
            "expected_outcome": "Clear EQE range for target emitters.",
            "agent_mode": "literature_scan",
            "priority": "high",
        }
    ],
    "human_approval_required": False,
    "do_not_learn": [],
    "what_worked": ["Governor routing was correct."],
    "what_failed_or_was_weak": ["EQE claim was unsupported."],
    "reusable_lessons": ["Always verify EQE claims against primary literature."],
    "memory_updates": ["EQE claims require primary data support."],
    "workflow_improvements": ["Add novelty pre-check before verifier."],
    "suggested_profile_updates": [],
}


# ---------------------------------------------------------------------------
# _extract_session_content
# ---------------------------------------------------------------------------

class TestExtractSessionContent:
    def test_extracts_governor_fields(self):
        result = _extract_session_content(_ALL_OUTPUTS_FULL)
        gov = result["governor"]
        assert gov["task_type"] == "research_analysis"
        assert gov["risk_level"] == "low"
        assert gov["scout_mode"] == "ideation"

    def test_extracts_scout_fields(self):
        result = _extract_session_content(_ALL_OUTPUTS_FULL)
        scout = result["scout"]
        assert scout["mode"] == "ideation"
        assert scout["confidence"] == "medium"
        assert scout["top_paper_count"] == 2
        assert scout["gap_candidate_count"] == 1
        assert scout["literature_scan_used"] is True
        assert scout["partial_results"] is False

    def test_extracts_verifier_route(self):
        result = _extract_session_content(_ALL_OUTPUTS_FULL)
        verifier = result["verifier"]
        assert verifier["route"] == "reject"
        assert verifier["overall_assessment"] == "weak"
        assert verifier["claim_count"] == 2

    def test_counts_claim_severity(self):
        result = _extract_session_content(_ALL_OUTPUTS_FULL)
        sev = result["verifier"]["claim_severity_counts"]
        assert sev.get("critical", 0) == 1
        assert sev.get("high", 0) == 1

    def test_extracts_pipeline_errors(self):
        outputs_with_errors = {
            **_ALL_OUTPUTS_FULL,
            "errors": [{"agent": "research_scout", "error": "API timeout"}],
        }
        result = _extract_session_content(outputs_with_errors)
        assert result["pipeline_errors"][0]["agent"] == "research_scout"

    def test_handles_none_components_gracefully(self):
        minimal = {
            "strategic_governor": None,
            "research_scout": None,
            "scientific_verifier": None,
            "errors": [],
        }
        result = _extract_session_content(minimal)
        assert result["governor"]["task_type"] == ""
        assert result["scout"]["confidence"] == "medium"
        assert result["verifier"]["route"] == ""


# ---------------------------------------------------------------------------
# _check_verifier_quality
# ---------------------------------------------------------------------------

class TestCheckVerifierQuality:
    def test_reject_route_produces_criticism(self):
        criticisms = _check_verifier_quality(_VERIFIER_REJECT)
        assert any("REJECTED" in c for c in criticisms)

    def test_high_severity_claims_produce_criticisms(self):
        criticisms = _check_verifier_quality(_VERIFIER_REJECT)
        assert any("CRITICAL" in c or "HIGH" in c for c in criticisms)

    def test_revision_instructions_included(self):
        criticisms = _check_verifier_quality(_VERIFIER_REJECT)
        assert any("EQE claim" in c for c in criticisms)

    def test_human_review_route_message(self):
        report = {**_VERIFIER_REJECT, "route": "human_review"}
        criticisms = _check_verifier_quality(report)
        assert any("HUMAN REVIEW" in c for c in criticisms)

    def test_none_report_returns_empty(self):
        assert _check_verifier_quality(None) == []

    def test_empty_dict_returns_empty(self):
        assert _check_verifier_quality({}) == []


# ---------------------------------------------------------------------------
# _classify_failure_modes
# ---------------------------------------------------------------------------

class TestClassifyFailureModes:
    def test_partial_execution_from_partial_results(self):
        session = _extract_session_content({
            **_ALL_OUTPUTS_FULL,
            "research_scout": _SCOUT_PARTIAL,
        })
        failures = _classify_failure_modes(session)
        assert "partial_execution" in failures

    def test_low_confidence_classified(self):
        session = _extract_session_content({
            **_ALL_OUTPUTS_FULL,
            "research_scout": _SCOUT_PARTIAL,
        })
        failures = _classify_failure_modes(session)
        assert "low_confidence" in failures

    def test_verifier_reject_classified(self):
        session = _extract_session_content(_ALL_OUTPUTS_FULL)
        failures = _classify_failure_modes(session)
        assert "verifier_reject" in failures

    def test_verifier_human_review_classified(self):
        session = _extract_session_content({
            **_ALL_OUTPUTS_FULL,
            "scientific_verifier": {**_VERIFIER_REJECT, "route": "human_review"},
        })
        failures = _classify_failure_modes(session)
        assert "verifier_human_review" in failures

    def test_overclaimed_novelty_from_high_severity_claims(self):
        session = _extract_session_content(_ALL_OUTPUTS_FULL)
        failures = _classify_failure_modes(session)
        assert "overclaimed_novelty" in failures

    def test_no_false_positives_on_clean_session(self):
        clean_outputs = {
            "strategic_governor": {"task_type": "research_analysis", "risk_level": "low", "research_scout_mode": "ideation"},
            "research_scout": {
                "mode": "ideation", "confidence": "high", "evidence_quality": "strong",
                "partial_results": False, "failed_stage": "", "top_papers": [],
                "research_gap_candidates": [], "literature_scan_used": False,
            },
            "scientific_verifier": {
                "route": "approve", "overall_assessment": "strong",
                "claim_checks": [], "revision_instructions": [],
                "required_human_approvals": [],
            },
            "errors": [],
        }
        session = _extract_session_content(clean_outputs)
        failures = _classify_failure_modes(session)
        assert failures == []


# ---------------------------------------------------------------------------
# _save_approved_lessons
# ---------------------------------------------------------------------------

class TestSaveApprovedLessons:
    def _make_lesson(self, save_decision, confidence, risk):
        return {
            "lesson": "A reusable lesson about TADF emitter characterisation.",
            "failure_type": "overclaimed_novelty",
            "confidence": confidence,
            "scope": "domain",
            "evidence_basis": "Verifier flagged unsupported claim.",
            "risk_if_applied": risk,
            "save_decision": save_decision,
            "applies_to_modes": ["ideation"],
        }

    def test_saves_save_now_low_risk_high_confidence(self, tmp_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")
        monkeypatch.setattr(config, "REFLECTION_PATH", tmp_path / "reflections.jsonl")

        lessons = [self._make_lesson("save_now", 0.80, "low")]
        saved = _save_approved_lessons(lessons)
        assert saved == 1

    def test_does_not_save_needs_review(self, tmp_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")
        monkeypatch.setattr(config, "REFLECTION_PATH", tmp_path / "reflections.jsonl")

        lessons = [self._make_lesson("needs_review", 0.80, "low")]
        saved = _save_approved_lessons(lessons)
        assert saved == 0

    def test_does_not_save_discard(self, tmp_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")

        lessons = [self._make_lesson("discard", 0.90, "low")]
        saved = _save_approved_lessons(lessons)
        assert saved == 0

    def test_does_not_save_low_confidence(self, tmp_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")

        lessons = [self._make_lesson("save_now", 0.60, "low")]
        saved = _save_approved_lessons(lessons)
        assert saved == 0

    def test_does_not_save_high_risk(self, tmp_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")

        lessons = [self._make_lesson("save_now", 0.85, "high")]
        saved = _save_approved_lessons(lessons)
        assert saved == 0

    def test_saves_multiple_qualifying_lessons(self, tmp_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")

        lessons = [
            self._make_lesson("save_now", 0.80, "low"),
            self._make_lesson("save_now", 0.90, "low"),
            self._make_lesson("needs_review", 0.80, "low"),
        ]
        saved = _save_approved_lessons(lessons)
        assert saved == 2


# ---------------------------------------------------------------------------
# run() integration
# ---------------------------------------------------------------------------

def _monkeypatch_paths(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")
    monkeypatch.setattr(config, "REFLECTION_PATH", tmp_path / "reflections.jsonl")
    monkeypatch.setattr(config, "APPROVAL_LOG_PATH", tmp_path / "approval_log.jsonl")
    monkeypatch.setattr(config, "RESEARCH_DB_PATH", tmp_path / "research_memory.db")
    monkeypatch.setattr(config, "PERFORMANCE_LOG_PATH", tmp_path / "performance_log.jsonl")


class TestRunFunction:
    def test_returns_new_schema_fields(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.self_evolution_engine.ask_json", return_value=_MOCK_LLM_RESPONSE):
            result = run("Analyse TADF OLED opportunity", _ALL_OUTPUTS_FULL, verifier_report=_VERIFIER_REJECT)

        assert "session_assessment" in result
        assert "failure_modes" in result
        assert "lesson_details" in result
        assert "next_experiments" in result
        assert "profile_update_proposals" in result
        assert "human_approval_required" in result

    def test_backward_compat_flat_fields_present(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.self_evolution_engine.ask_json", return_value=_MOCK_LLM_RESPONSE):
            result = run("Analyse TADF OLED opportunity", _ALL_OUTPUTS_FULL)

        assert "what_worked" in result
        assert "what_failed_or_was_weak" in result
        assert "reusable_lessons" in result
        assert "memory_updates" in result
        assert "workflow_improvements" in result
        assert "suggested_profile_updates" in result

    def test_failure_modes_merged_with_pre_classified(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        # LLM returns only overclaimed_novelty; pre-classify should also add verifier_reject
        with patch("agents.self_evolution_engine.ask_json", return_value=_MOCK_LLM_RESPONSE):
            result = run("Analyse TADF OLED opportunity", _ALL_OUTPUTS_FULL, verifier_report=_VERIFIER_REJECT)

        # Should contain both the LLM-identified and pre-classified failures
        assert "verifier_reject" in result["failure_modes"]

    def test_llm_parse_error_produces_graceful_fallback(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.self_evolution_engine.ask_json", side_effect=RuntimeError("LLM down")):
            result = run("Analyse TADF OLED opportunity", _ALL_OUTPUTS_FULL)

        assert "session_assessment" in result
        assert any("parse error" in s.lower() or "llm down" in s.lower()
                   for s in result.get("what_failed_or_was_weak", []))
        # Should still have pre-classified failures
        assert isinstance(result["failure_modes"], list)

    def test_verifier_criticisms_extracted_when_report_passed(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        captured_prompt = {}

        def mock_ask_json(system, user_prompt, temperature=0.15):
            captured_prompt["prompt"] = user_prompt
            return _MOCK_LLM_RESPONSE

        with patch("agents.self_evolution_engine.ask_json", side_effect=mock_ask_json):
            run("Test", _ALL_OUTPUTS_FULL, verifier_report=_VERIFIER_REJECT)

        assert "REJECTED" in captured_prompt.get("prompt", "") or "Verifier" in captured_prompt.get("prompt", "")

    def test_no_verifier_report_still_works(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.self_evolution_engine.ask_json", return_value=_MOCK_LLM_RESPONSE):
            result = run("Analyse TADF OLED opportunity", _ALL_OUTPUTS_FULL, verifier_report=None)

        assert "session_assessment" in result

    def test_user_feedback_included_in_prompt(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        captured_prompt = {}

        def mock_ask_json(system, user_prompt, temperature=0.15):
            captured_prompt["prompt"] = user_prompt
            return _MOCK_LLM_RESPONSE

        with patch("agents.self_evolution_engine.ask_json", side_effect=mock_ask_json):
            run("Test", _ALL_OUTPUTS_FULL, user_feedback="The gap analysis was too broad.")

        assert "too broad" in captured_prompt.get("prompt", "")

    def test_performance_log_written(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        perf_path = tmp_path / "performance_log.jsonl"

        with patch("agents.self_evolution_engine.ask_json", return_value=_MOCK_LLM_RESPONSE):
            run("Analyse TADF OLED opportunity", _ALL_OUTPUTS_FULL)

        assert perf_path.exists()
        import json
        entry = json.loads(perf_path.read_text(encoding="utf-8").strip().splitlines()[0])
        assert "session_assessment" in entry
        assert "failure_modes" in entry
        assert "verifier_route" in entry

    def test_lesson_details_schema_valid(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.self_evolution_engine.ask_json", return_value=_MOCK_LLM_RESPONSE):
            result = run("Analyse TADF", _ALL_OUTPUTS_FULL)

        for ld in result.get("lesson_details", []):
            assert "lesson" in ld
            assert "save_decision" in ld
            assert ld["save_decision"] in ("save_now", "needs_review", "discard")
            assert 0.0 <= float(ld.get("confidence", 0.5)) <= 1.0

    def test_next_experiments_schema_valid(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.self_evolution_engine.ask_json", return_value=_MOCK_LLM_RESPONSE):
            result = run("Analyse TADF", _ALL_OUTPUTS_FULL)

        for exp in result.get("next_experiments", []):
            assert "description" in exp
            assert "priority" in exp
            assert exp["priority"] in ("low", "medium", "high")
