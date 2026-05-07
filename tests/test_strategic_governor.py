import pytest
from unittest.mock import patch

from agents.strategic_governor import (
    _enforce_safety,
    _enforce_evidence_depth,
    _derive_backward_compat,
    run,
    ALLOWED_AGENTS,
)
from core.schemas import GovernorDecision, MemoryPolicy, SelfEvolutionPolicy, WorkflowStep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_decision(**kwargs) -> GovernorDecision:
    defaults = dict(
        task_type="research_scan",
        priority="medium",
        selected_agents=["research_scout", "scientific_verifier", "self_evolution_engine"],
        research_scout_mode="literature_scan",
        requires_approval=False,
        approval_reason="",
        risk_level="low",
        rationale="Test.",
        autonomy_level="L2",
        external_consequence="none",
        evidence_requirement="medium",
        mission_alignment_score=0.7,
        strategic_value_score=0.6,
        urgency_score=0.4,
        should_this_be_done="yes",
        workflow_sequence=[],
        agent_configs={},
        task_decomposition=[],
        blocked_actions=[],
        memory_policy=MemoryPolicy(),
        self_evolution_policy=SelfEvolutionPolicy(run=True, reason="Test."),
    )
    defaults.update(kwargs)
    return GovernorDecision(**defaults)


_MOCK_LLM_RESEARCH = {
    "task_type": "research_scan",
    "priority": "medium",
    "risk_level": "low",
    "mission_alignment_score": 0.9,
    "strategic_value_score": 0.8,
    "urgency_score": 0.3,
    "should_this_be_done": "yes",
    "autonomy_level": "L2",
    "external_consequence": "none",
    "evidence_requirement": "medium",
    "requires_approval": False,
    "approval_reason": "",
    "blocked_actions": [],
    "selected_agents": ["research_scout", "scientific_verifier", "self_evolution_engine"],
    "research_scout_mode": "literature_scan",
    "workflow_sequence": [
        {"agent": "memory_retriever", "purpose": "load profile", "mode": "targeted"},
        {"agent": "research_scout", "purpose": "search literature", "mode": "literature_scan"},
        {"agent": "scientific_verifier", "purpose": "verify claims", "mode": "standard"},
        {"agent": "self_evolution_engine", "purpose": "extract lessons", "mode": "standard"},
    ],
    "agent_configs": {
        "research_scout": {"mode": "literature_scan", "recency_window": "24 months", "max_papers": 10},
        "scientific_verifier": {"strictness": "standard", "check_citations": True, "check_methodology": True, "check_overclaiming": True},
    },
    "task_decomposition": ["Search literature", "Score papers", "Identify gap", "Verify claims"],
    "memory_policy": {"retrieve_memory": True, "allow_memory_write": True, "memory_write_requires_approval": False},
    "self_evolution_policy": {"run": True, "reason": "Research session with durable lessons."},
    "rationale": "User wants literature scan on TADF OLEDs.",
}

_MOCK_LLM_GRANT = {
    **_MOCK_LLM_RESEARCH,
    "task_type": "grant_strategy",
    "evidence_requirement": "ultra",
    "strategic_value_score": 0.95,
    "workflow_sequence": [
        {"agent": "memory_retriever", "purpose": "load prior proposals", "mode": "targeted"},
        {"agent": "research_scout", "purpose": "identify novelty gap", "mode": "ideation"},
        {"agent": "scientific_verifier", "purpose": "stress-test claims", "mode": "strict"},
        {"agent": "self_evolution_engine", "purpose": "extract grant lessons", "mode": "standard"},
    ],
    "rationale": "User wants grant strategy.",
}

_MOCK_LLM_TRIVIAL = {
    **_MOCK_LLM_RESEARCH,
    "task_type": "admin",
    "priority": "low",
    "mission_alignment_score": 0.1,
    "strategic_value_score": 0.05,
    "should_this_be_done": "maybe",
    "autonomy_level": "L1",
    "evidence_requirement": "low",
    "workflow_sequence": [],
    "self_evolution_policy": {"run": False, "reason": "Trivial admin task — no durable lessons expected."},
    "rationale": "Trivial task.",
}

_MOCK_LLM_COMMUNICATION = {
    **_MOCK_LLM_RESEARCH,
    "task_type": "communication",
    "autonomy_level": "L4",
    "external_consequence": "medium",
    "requires_approval": True,
    "approval_reason": "Drafting email to collaborator — requires human review before sending.",
    "risk_level": "medium",
    "self_evolution_policy": {"run": True, "reason": "Communication lesson."},
    "rationale": "Draft email.",
}


# ---------------------------------------------------------------------------
# _enforce_safety
# ---------------------------------------------------------------------------

class TestEnforceSafety:
    def test_send_email_escalates_to_l5(self):
        d = _make_decision(autonomy_level="L2", requires_approval=False)
        result = _enforce_safety(d, "send email to professor Smith about collaboration")
        assert result.autonomy_level == "L5"
        assert result.requires_approval is True

    def test_send_email_escalates_risk_to_high(self):
        d = _make_decision(autonomy_level="L2", risk_level="low")
        result = _enforce_safety(d, "send email to my collaborator")
        assert result.risk_level in ("high", "critical")

    def test_submit_grant_escalates_to_l5(self):
        d = _make_decision(autonomy_level="L3")
        result = _enforce_safety(d, "submit grant to EPSRC portal")
        assert result.autonomy_level == "L5"
        assert result.requires_approval is True

    def test_delete_file_escalates_to_l5_critical(self):
        d = _make_decision(autonomy_level="L2", risk_level="low")
        result = _enforce_safety(d, "delete file old_data.csv")
        assert result.autonomy_level == "L5"
        assert result.risk_level == "critical"

    def test_modify_profile_escalates_to_l4(self):
        d = _make_decision(autonomy_level="L2")
        result = _enforce_safety(d, "modify profile to add photovoltaics")
        level = int(result.autonomy_level[1:]) if result.autonomy_level.startswith("L") else 0
        assert level >= 4

    def test_safe_input_unchanged(self):
        d = _make_decision(autonomy_level="L2", requires_approval=False, risk_level="low")
        result = _enforce_safety(d, "find recent TADF papers on arXiv")
        assert result.autonomy_level == "L2"
        assert result.requires_approval is False

    def test_l5_without_approval_gets_approval_set(self):
        d = _make_decision(autonomy_level="L5", requires_approval=False)
        result = _enforce_safety(d, "some normal text that happens to be L5 level")
        assert result.requires_approval is True


# ---------------------------------------------------------------------------
# _enforce_evidence_depth
# ---------------------------------------------------------------------------

class TestEnforceEvidenceDepth:
    def test_grant_keyword_raises_to_high(self):
        d = _make_decision(evidence_requirement="low")
        result = _enforce_evidence_depth(d, "help me write a grant proposal for EPSRC")
        assert result.evidence_requirement in ("high", "ultra")

    def test_paper_keyword_raises_to_high(self):
        d = _make_decision(evidence_requirement="low")
        result = _enforce_evidence_depth(d, "review my paper manuscript")
        assert result.evidence_requirement in ("high", "ultra")

    def test_casual_question_unchanged(self):
        d = _make_decision(evidence_requirement="low")
        result = _enforce_evidence_depth(d, "what is TADF?")
        assert result.evidence_requirement == "low"

    def test_already_ultra_stays_ultra(self):
        d = _make_decision(evidence_requirement="ultra")
        result = _enforce_evidence_depth(d, "quick question")
        assert result.evidence_requirement == "ultra"


# ---------------------------------------------------------------------------
# _derive_backward_compat
# ---------------------------------------------------------------------------

class TestDeriveBackwardCompat:
    def test_derives_selected_agents_from_workflow_when_empty(self):
        d = _make_decision(
            selected_agents=[],
            workflow_sequence=[
                WorkflowStep(agent="research_scout", purpose="search", mode="ideation"),
                WorkflowStep(agent="scientific_verifier", purpose="verify", mode="standard"),
                WorkflowStep(agent="self_evolution_engine", purpose="learn", mode="standard"),
            ],
        )
        result = _derive_backward_compat(d)
        assert "research_scout" in result.selected_agents
        assert "scientific_verifier" in result.selected_agents

    def test_adds_self_evolution_when_policy_says_run(self):
        d = _make_decision(
            selected_agents=["research_scout"],
            self_evolution_policy=SelfEvolutionPolicy(run=True),
        )
        result = _derive_backward_compat(d)
        assert "self_evolution_engine" in result.selected_agents

    def test_removes_self_evolution_when_policy_says_no_run(self):
        d = _make_decision(
            selected_agents=["research_scout", "self_evolution_engine"],
            self_evolution_policy=SelfEvolutionPolicy(run=False),
        )
        result = _derive_backward_compat(d)
        assert "self_evolution_engine" not in result.selected_agents

    def test_derives_scout_mode_from_workflow(self):
        d = _make_decision(
            research_scout_mode="none",
            workflow_sequence=[
                WorkflowStep(agent="research_scout", purpose="scan", mode="literature_scan"),
            ],
        )
        result = _derive_backward_compat(d)
        assert result.research_scout_mode == "literature_scan"

    def test_unknown_agents_filtered_out(self):
        d = _make_decision(selected_agents=["research_scout", "nonexistent_agent"])
        result = _derive_backward_compat(d)
        assert "nonexistent_agent" not in result.selected_agents
        assert "research_scout" in result.selected_agents

    def test_does_not_duplicate_self_evolution(self):
        d = _make_decision(
            selected_agents=["research_scout", "self_evolution_engine"],
            self_evolution_policy=SelfEvolutionPolicy(run=True),
        )
        result = _derive_backward_compat(d)
        assert result.selected_agents.count("self_evolution_engine") == 1


# ---------------------------------------------------------------------------
# run() — integration with mocked LLM
# ---------------------------------------------------------------------------

def _monkeypatch_paths(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "MEMORY_PATH", tmp_path / "memories.jsonl")
    monkeypatch.setattr(config, "REFLECTION_PATH", tmp_path / "reflections.jsonl")


class TestRunFunction:
    def test_returns_all_new_schema_fields(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", return_value=_MOCK_LLM_RESEARCH):
            result = run("Find recent TADF OLED papers")

        assert "task_type" in result
        assert "mission_alignment_score" in result
        assert "strategic_value_score" in result
        assert "urgency_score" in result
        assert "should_this_be_done" in result
        assert "autonomy_level" in result
        assert "evidence_requirement" in result
        assert "workflow_sequence" in result
        assert "agent_configs" in result
        assert "task_decomposition" in result
        assert "memory_policy" in result
        assert "self_evolution_policy" in result
        assert "blocked_actions" in result

    def test_backward_compat_fields_present(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", return_value=_MOCK_LLM_RESEARCH):
            result = run("Find recent TADF OLED papers")

        assert "selected_agents" in result
        assert "research_scout_mode" in result
        assert "requires_approval" in result
        assert "risk_level" in result

    def test_research_scan_task_type(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", return_value=_MOCK_LLM_RESEARCH):
            result = run("Find recent TADF OLED papers")
        assert result["task_type"] == "research_scan"

    def test_grant_strategy_gets_high_evidence(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", return_value=_MOCK_LLM_GRANT):
            result = run("Help me develop a grant proposal for red/NIR OLED photobiomodulation")
        assert result["task_type"] == "grant_strategy"
        assert result["evidence_requirement"] in ("high", "ultra")

    def test_trivial_task_evolution_skipped(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", return_value=_MOCK_LLM_TRIVIAL):
            result = run("List my files")
        policy = result.get("self_evolution_policy") or {}
        if isinstance(policy, dict):
            assert policy.get("run") is False
        else:
            assert policy.get("run") is False

    def test_self_evolution_engine_removed_from_agents_when_not_run(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        mock = {**_MOCK_LLM_TRIVIAL, "selected_agents": ["research_scout", "self_evolution_engine"]}
        with patch("agents.strategic_governor.ask_json", return_value=mock):
            result = run("List my files")
        assert "self_evolution_engine" not in result["selected_agents"]

    def test_send_email_safety_override(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        # Even if LLM says L2, Python override must escalate for send email
        low_risk_mock = {**_MOCK_LLM_RESEARCH, "autonomy_level": "L2", "requires_approval": False}
        with patch("agents.strategic_governor.ask_json", return_value=low_risk_mock):
            result = run("send email to Prof Johnson about our TADF results")
        assert result["autonomy_level"] == "L5"
        assert result["requires_approval"] is True

    def test_workflow_sequence_parsed_correctly(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", return_value=_MOCK_LLM_RESEARCH):
            result = run("Find recent papers")
        workflow = result["workflow_sequence"]
        assert len(workflow) >= 1
        first = workflow[0]
        # After model_dump(), WorkflowStep becomes a dict
        if isinstance(first, dict):
            assert "agent" in first
        else:
            assert hasattr(first, "agent")

    def test_parse_error_fallback_is_conservative(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", side_effect=RuntimeError("LLM down")):
            result = run("Analyse TADF opportunity")

        assert result["requires_approval"] is True
        assert result["risk_level"] in ("medium", "high", "critical")
        assert result["autonomy_level"] in ("L0", "L1")

    def test_parse_error_fallback_does_not_include_research_scout(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", side_effect=RuntimeError("LLM down")):
            result = run("Analyse TADF opportunity")
        # Fallback should NOT include research_scout (conservative — stop and wait)
        assert "research_scout" not in result["selected_agents"]

    def test_selected_agents_only_known_agents(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        mock = {**_MOCK_LLM_RESEARCH, "selected_agents": ["research_scout", "unknown_agent_xyz"]}
        with patch("agents.strategic_governor.ask_json", return_value=mock):
            result = run("Test")
        assert "unknown_agent_xyz" not in result["selected_agents"]

    def test_grant_keyword_raises_evidence_requirement(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        # LLM returns low evidence_requirement, Python should raise it
        mock = {**_MOCK_LLM_RESEARCH, "evidence_requirement": "low", "task_type": "research_scan"}
        with patch("agents.strategic_governor.ask_json", return_value=mock):
            result = run("evaluate my grant proposal for ERC funding")
        assert result["evidence_requirement"] in ("high", "ultra")

    def test_memory_policy_fields_present(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", return_value=_MOCK_LLM_RESEARCH):
            result = run("Find papers")
        mp = result["memory_policy"]
        if isinstance(mp, dict):
            assert "retrieve_memory" in mp
            assert "allow_memory_write" in mp
            assert "memory_write_requires_approval" in mp

    def test_communication_task_has_approval(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", return_value=_MOCK_LLM_COMMUNICATION):
            result = run("Draft a collaboration email to Prof Kim at Seoul National University")
        assert result["requires_approval"] is True

    def test_mission_alignment_scores_are_floats(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", return_value=_MOCK_LLM_RESEARCH):
            result = run("Find TADF papers")
        assert isinstance(result["mission_alignment_score"], float)
        assert isinstance(result["strategic_value_score"], float)
        assert isinstance(result["urgency_score"], float)

    def test_should_this_be_done_valid_value(self, tmp_path, monkeypatch):
        _monkeypatch_paths(monkeypatch, tmp_path)
        with patch("agents.strategic_governor.ask_json", return_value=_MOCK_LLM_RESEARCH):
            result = run("Evaluate TADF idea")
        assert result["should_this_be_done"] in ("yes", "maybe", "no")
