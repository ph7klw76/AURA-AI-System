"""
Tests that paper scoring routes all LLM calls through core.llm.ask_json
and that no direct Ollama calls exist in paper_scoring.py.
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from integrations.research_evolution.paper_scoring import (
    score_paper,
    score_papers,
    calculate_total_score,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PROFILE = {
    "research_topics": ["TADF", "OLED", "red-NIR emission", "lanthanide complex"],
    "scoring_weights": {
        "relevance": 0.30,
        "novelty": 0.22,
        "grant_potential": 0.18,
        "collaboration_potential": 0.12,
        "industry_potential": 0.08,
        "teaching_public_value": 0.10,
    },
}

_PAPER = {
    "title": "Efficient Red TADF OLED with Record EQE",
    "source": "arxiv",
    "abstract": "We report a red-emitting TADF OLED achieving an EQE of 25% at 640 nm.",
    "published_date": "2024-01-15",
    "authors": ["Smith J", "Jones A"],
    "cited_by_count": 12,
    "unique_key": "abc123test",
}

_MOCK_SCORE = {
    "relevance": 8.5,
    "novelty": 7.0,
    "grant_potential": 7.5,
    "collaboration_potential": 6.0,
    "industry_potential": 7.0,
    "teaching_public_value": 5.0,
    "feasibility": 7.0,
    "risk": 4.0,
    "oled_device_usefulness": 8.0,
    "tadf_mechanism_relevance": 8.5,
    "red_nir_emission_relevance": 9.0,
    "lanthanide_relevance": 3.0,
    "experimental_feasibility": 7.0,
    "agent_commentary": "Strong red-emitting TADF OLED with credible EQE.",
    "evidence_gaps": ["No independent replication.", "Roll-off data absent."],
    "recommended_action": "read_now",
    "recommended_use": "cite_in_grant",
    "opportunity_type": "proposal",
    "key_metrics": {
        "EQE_percent": 25.0,
        "emission_wavelength_nm": 640,
        "PLQY_percent": None,
        "luminance_cd_m2": None,
        "turn_on_voltage_V": None,
        "DELTA_EST_eV": None,
        "operational_lifetime_hours": None,
        "host_dopant_system": None,
        "device_architecture": None,
        "roll_off": None,
    },
}


# ---------------------------------------------------------------------------
# Architecture: no direct Ollama in paper_scoring.py
# ---------------------------------------------------------------------------

def test_paper_scoring_has_no_direct_ollama_import():
    import config
    scoring_path = (
        Path(config.__file__).parent
        / "integrations" / "research_evolution" / "paper_scoring.py"
    )
    content = scoring_path.read_text(encoding="utf-8")
    assert "import ollama" not in content, "paper_scoring.py must not import ollama directly"
    assert "ollama.chat" not in content, "paper_scoring.py must not call ollama.chat directly"


def test_paper_scoring_imports_ask_json_from_core_llm():
    import config
    scoring_path = (
        Path(config.__file__).parent
        / "integrations" / "research_evolution" / "paper_scoring.py"
    )
    content = scoring_path.read_text(encoding="utf-8")
    assert "from core.llm import ask_json" in content, (
        "paper_scoring.py must import ask_json from core.llm"
    )


# ---------------------------------------------------------------------------
# Routing: score_paper calls ask_json
# ---------------------------------------------------------------------------

def test_score_paper_calls_ask_json_once():
    """score_paper must call core.llm.ask_json exactly once per paper."""
    with patch("integrations.research_evolution.paper_scoring.ask_json",
               return_value=_MOCK_SCORE) as mock_ask:
        score_paper(_PROFILE, _PAPER)
    assert mock_ask.call_count == 1


def test_score_paper_does_not_call_ollama_directly():
    """Ensure no fallback path goes to ollama.chat."""
    import ollama as _ollama_mod
    original_chat = _ollama_mod.chat
    calls = []

    def spy_chat(*args, **kwargs):
        calls.append((args, kwargs))
        return original_chat(*args, **kwargs)

    _ollama_mod.chat = spy_chat
    try:
        with patch("integrations.research_evolution.paper_scoring.ask_json",
                   return_value=_MOCK_SCORE):
            score_paper(_PROFILE, _PAPER)
    finally:
        _ollama_mod.chat = original_chat

    assert calls == [], "score_paper must not call ollama.chat directly"


# ---------------------------------------------------------------------------
# Output correctness
# ---------------------------------------------------------------------------

def test_score_paper_returns_recommended_action():
    with patch("integrations.research_evolution.paper_scoring.ask_json",
               return_value=_MOCK_SCORE):
        result = score_paper(_PROFILE, _PAPER)
    assert result["recommended_action"] == "read_now"


def test_score_paper_coerces_all_dimensions_to_float():
    with patch("integrations.research_evolution.paper_scoring.ask_json",
               return_value=_MOCK_SCORE):
        result = score_paper(_PROFILE, _PAPER)
    for dim in ["relevance", "novelty", "grant_potential", "collaboration_potential",
                "industry_potential", "teaching_public_value", "feasibility", "risk"]:
        assert isinstance(result[dim], float), f"'{dim}' should be float"


def test_score_paper_key_metrics_is_dict():
    with patch("integrations.research_evolution.paper_scoring.ask_json",
               return_value=_MOCK_SCORE):
        result = score_paper(_PROFILE, _PAPER)
    assert isinstance(result["key_metrics"], dict)


def test_score_paper_coerces_invalid_recommended_action():
    bad = {**_MOCK_SCORE, "recommended_action": "launch_rocket"}
    with patch("integrations.research_evolution.paper_scoring.ask_json", return_value=bad):
        result = score_paper(_PROFILE, _PAPER)
    assert result["recommended_action"] == "save_for_later"


def test_score_paper_coerces_invalid_recommended_use():
    bad = {**_MOCK_SCORE, "recommended_use": "write_tweet"}
    with patch("integrations.research_evolution.paper_scoring.ask_json", return_value=bad):
        result = score_paper(_PROFILE, _PAPER)
    assert result["recommended_use"] == "background_reading"


def test_score_paper_coerces_non_dict_key_metrics():
    bad = {**_MOCK_SCORE, "key_metrics": "EQE=25%"}
    with patch("integrations.research_evolution.paper_scoring.ask_json", return_value=bad):
        result = score_paper(_PROFILE, _PAPER)
    assert isinstance(result["key_metrics"], dict)


# ---------------------------------------------------------------------------
# Fallback on LLM failure
# ---------------------------------------------------------------------------

def test_score_paper_fallback_on_llm_failure():
    with patch("integrations.research_evolution.paper_scoring.ask_json",
               side_effect=RuntimeError("LLM unavailable")):
        result = score_paper(_PROFILE, _PAPER)
    assert result["recommended_action"] == "save_for_later"
    assert result["agent_commentary"] == "Score not available."
    assert isinstance(result["evidence_gaps"], list)
    assert len(result["evidence_gaps"]) > 0


def test_score_paper_fallback_contains_error_message():
    with patch("integrations.research_evolution.paper_scoring.ask_json",
               side_effect=ValueError("JSON parse error")):
        result = score_paper(_PROFILE, _PAPER)
    # evidence_gaps should mention the error
    combined = " ".join(result.get("evidence_gaps", []))
    assert "error" in combined.lower() or "parse" in combined.lower() or "llm" in combined.lower()


# ---------------------------------------------------------------------------
# calculate_total_score
# ---------------------------------------------------------------------------

def test_total_score_in_valid_range():
    total = calculate_total_score(_PROFILE, _MOCK_SCORE)
    assert 0.0 <= total <= 10.0


def test_total_score_is_float():
    total = calculate_total_score(_PROFILE, _MOCK_SCORE)
    assert isinstance(total, float)


def test_total_score_higher_for_better_paper():
    low_score = {**_MOCK_SCORE, "relevance": 2.0, "novelty": 2.0, "grant_potential": 2.0}
    high_score = {**_MOCK_SCORE, "relevance": 9.0, "novelty": 9.0, "grant_potential": 9.0}
    assert calculate_total_score(_PROFILE, high_score) > calculate_total_score(_PROFILE, low_score)


# ---------------------------------------------------------------------------
# score_papers (batch)
# ---------------------------------------------------------------------------

def test_score_papers_skips_source_error_papers():
    papers = [
        _PAPER,
        {"source_error": "OpenAlex timeout"},
        {"source_errors": [{"source_error": "arXiv down"}]},
    ]
    with patch("integrations.research_evolution.paper_scoring.ask_json",
               return_value=_MOCK_SCORE):
        results = score_papers(_PROFILE, papers)
    assert len(results) == 1
    assert results[0]["title"] == _PAPER["title"]


def test_score_papers_sorted_descending_by_total_score():
    paper_a = {**_PAPER, "unique_key": "aaa", "title": "Paper A"}
    paper_b = {**_PAPER, "unique_key": "bbb", "title": "Paper B"}
    low_score = {**_MOCK_SCORE, "relevance": 2.0, "novelty": 2.0}
    high_score = {**_MOCK_SCORE, "relevance": 9.0, "novelty": 9.0}

    responses = iter([high_score, low_score])

    with patch("integrations.research_evolution.paper_scoring.ask_json",
               side_effect=lambda *a, **kw: next(responses)):
        results = score_papers(_PROFILE, [paper_a, paper_b])

    assert results[0]["total_score"] >= results[-1]["total_score"]


def test_score_papers_merges_paper_and_score_fields():
    with patch("integrations.research_evolution.paper_scoring.ask_json",
               return_value=_MOCK_SCORE):
        results = score_papers(_PROFILE, [_PAPER])
    assert results[0]["title"] == _PAPER["title"]   # from paper
    assert results[0]["relevance"] == _MOCK_SCORE["relevance"]  # from score
    assert "total_score" in results[0]
