"""
Tests for the upgraded AURA Scientific Verifier.

All tests monkeypatch core/llm.py — no Ollama or internet required.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_PRIOR_OUTPUTS = {
    "strategic_governor": {
        "task_type": "research_analysis",
        "risk_level": "low",
        "rationale": "Explore TADF OLED opportunity.",
        "requires_approval": False,
        "selected_agents": ["research_scout", "scientific_verifier"],
        "research_scout_mode": "ideation",
    },
    "research_scout": {
        "mode": "ideation",
        "summary": "TADF-lanthanide red OLEDs show great promise for photobiomodulation.",
        "findings": [
            "Red-NIR TADF emitters can achieve >20% EQE.",
            "Lanthanide complexes extend emission into the NIR window.",
        ],
        "risks": ["Device lifetime unproven."],
        "recommended_actions": ["Prepare grant proposal.", "Contact collaborator at University X."],
        "confidence": "medium",
        "literature_scan_used": False,
        "top_papers": [],
        "research_gap_candidate": "No published device combining TADF sensitisation with Yb(III) NIR emission for wound healing.",
        "report_paths": [],
    },
}

LIT_SCAN_PRIOR_OUTPUTS = {
    **MINIMAL_PRIOR_OUTPUTS,
    "research_scout": {
        **MINIMAL_PRIOR_OUTPUTS["research_scout"],
        "mode": "literature_scan",
        "literature_scan_used": True,
        "top_papers": [
            {
                "title": "Efficient red TADF OLED with exciplex host",
                "source": "openalex",
                "total_score": 8.2,
                "recommended_action": "use_for_grant",
                "commentary": "Reports 18% EQE at 630 nm.",
                "evidence_gaps": ["No operational lifetime data."],
            }
        ],
    },
}

GOOD_LLM_RESPONSE = {
    "overall_assessment": "acceptable",
    "claim_checks": [
        {
            "claim": "Red-NIR TADF emitters can achieve >20% EQE.",
            "claim_type": "novelty",
            "support_status": "partially_supported",
            "severity": "medium",
            "confidence": 0.6,
            "evidence_needed": ["Peer-reviewed device data at >620 nm with >20% EQE."],
            "correction": "Qualify to 'select TADF emitters have demonstrated >20% EQE' and cite specific papers.",
        },
        {
            "claim": "No published device combining TADF sensitisation with Yb(III) NIR emission for wound healing.",
            "claim_type": "novelty",
            "support_status": "unverifiable",
            "severity": "high",
            "confidence": 0.4,
            "evidence_needed": ["Systematic literature search in Web of Science and Scopus."],
            "correction": "Replace with 'to the best of our knowledge' and add a literature search caveat.",
        },
    ],
    "methodology_risks": ["No experimental timeline or resource estimate provided."],
    "novelty_risks": ["EQE claim may refer to green/yellow TADF, not red/NIR."],
    "citation_risks": [],
    "grant_risks": ["Photobiomodulation application is speculative without device characterisation data."],
    "action_governance_risks": ["Contacting collaborator requires human approval."],
    "required_human_approvals": ["Contact collaborator at University X"],
    "revision_instructions": [
        "Add specific literature citations for the EQE claim.",
        "Qualify the gap claim with a literature search caveat.",
        "Remove 'great promise' without quantitative support.",
    ],
    "final_recommendation": "revise",
    "route": "revise",
}

RESPONSE_WITH_BAD_ENUMS = {
    "overall_assessment": "EXCELLENT",        # invalid — should be coerced
    "claim_checks": [
        {
            "claim": "Some claim",
            "claim_type": "unknown_type",     # invalid
            "support_status": "maybe",        # invalid
            "severity": "extreme",            # invalid
            "confidence": 1.5,               # out of range
            "evidence_needed": [],
            "correction": "",
        }
    ],
    "methodology_risks": [],
    "novelty_risks": [],
    "citation_risks": [],
    "grant_risks": [],
    "action_governance_risks": [],
    "required_human_approvals": [],
    "revision_instructions": [],
    "final_recommendation": "maybe_revise",   # invalid
    "route": "unknown_route",                 # invalid
}


# ---------------------------------------------------------------------------
# _extract_structured_content
# ---------------------------------------------------------------------------

def test_extract_structured_content_finds_claims():
    from agents.scientific_verifier import _extract_structured_content
    structured, truncated = _extract_structured_content(MINIMAL_PRIOR_OUTPUTS)
    assert isinstance(structured["claims"], list)
    assert len(structured["claims"]) >= 2
    assert any("TADF" in c or "lanthanide" in c.lower() for c in structured["claims"])
    assert structured["scout_mode"] == "ideation"
    assert structured["requires_approval_flagged_by_governor"] is False


def test_extract_structured_content_includes_gap_candidate():
    from agents.scientific_verifier import _extract_structured_content
    structured, _ = _extract_structured_content(MINIMAL_PRIOR_OUTPUTS)
    assert structured["research_gap_candidate"] != ""
    assert any("[gap_claim]" in c for c in structured["claims"])


def test_extract_structured_content_includes_cited_papers():
    from agents.scientific_verifier import _extract_structured_content
    structured, _ = _extract_structured_content(LIT_SCAN_PRIOR_OUTPUTS)
    assert len(structured["cited_papers"]) == 1
    assert structured["cited_papers"][0]["source"] == "openalex"


def test_extract_structured_content_empty_inputs():
    from agents.scientific_verifier import _extract_structured_content
    structured, truncated = _extract_structured_content({})
    assert isinstance(structured["claims"], list)
    assert truncated is False


# ---------------------------------------------------------------------------
# _safe_parse_report — enum coercion and fallback
# ---------------------------------------------------------------------------

def test_safe_parse_coerces_invalid_enums():
    from agents.scientific_verifier import _safe_parse_report
    report = _safe_parse_report(RESPONSE_WITH_BAD_ENUMS, truncated=False)
    # Invalid overall_assessment -> "incomplete"
    assert report.overall_assessment == "incomplete"
    # Invalid route -> "revise"
    assert report.route == "revise"
    # Invalid final_recommendation -> "needs_more_evidence"
    assert report.final_recommendation == "needs_more_evidence"
    # Invalid claim_type -> "mechanism"
    assert report.claim_checks[0].claim_type == "mechanism"
    # Invalid support_status -> "unverifiable"
    assert report.claim_checks[0].support_status == "unverifiable"
    # Invalid severity -> "low"
    assert report.claim_checks[0].severity == "low"
    # Confidence clamped to [0, 1]
    assert 0.0 <= report.claim_checks[0].confidence <= 1.0


_RESPONSE_WITH_UNSUPPORTED = {
    **GOOD_LLM_RESPONSE,
    "claim_checks": [
        {
            "claim": "TADF-lanthanide OLEDs have already been demonstrated at 20% EQE.",
            "claim_type": "novelty",
            "support_status": "unsupported",    # explicitly unsupported
            "severity": "high",
            "confidence": 0.8,
            "evidence_needed": ["Published EQE data for Yb TADF OLED."],
            "correction": "Remove until device data is available.",
        },
        {
            "claim": "Grant funding is available for this topic.",
            "claim_type": "grant",
            "support_status": "unverifiable",
            "severity": "medium",
            "confidence": 0.5,
            "evidence_needed": ["Grant call reference."],
            "correction": "Qualify with specific funding body.",
        },
    ],
}


def test_safe_parse_populates_compat_fields():
    from agents.scientific_verifier import _safe_parse_report
    report = _safe_parse_report(_RESPONSE_WITH_UNSUPPORTED, truncated=False)
    # unsupported_claims is derived from claim_checks with status "unsupported" or "contradicted"
    assert len(report.unsupported_claims) == 1
    assert "TADF-lanthanide" in report.unsupported_claims[0]
    # High severity corrections propagated into flat corrections list
    assert len(report.corrections) >= 1
    assert any("device data" in c.lower() for c in report.corrections)


# ---------------------------------------------------------------------------
# _incomplete_fallback — safe failure must never return "acceptable"
# ---------------------------------------------------------------------------

def test_incomplete_fallback_is_not_acceptable():
    from agents.scientific_verifier import _incomplete_fallback
    report = _incomplete_fallback("JSON parse error")
    assert report.overall_assessment not in ("acceptable", "strong")
    assert report.route == "human_review"
    assert report.final_recommendation == "needs_more_evidence"
    assert len(report.revision_instructions) >= 1


# ---------------------------------------------------------------------------
# run() integration (LLM mocked)
# ---------------------------------------------------------------------------

def test_run_returns_required_fields():
    with patch("agents.scientific_verifier.ask_json", return_value=GOOD_LLM_RESPONSE):
        from agents.scientific_verifier import run
        result = run("Explore red TADF OLED", MINIMAL_PRIOR_OUTPUTS)

    required_keys = [
        "overall_assessment", "claim_checks", "methodology_risks",
        "novelty_risks", "citation_risks", "grant_risks",
        "action_governance_risks", "required_human_approvals",
        "revision_instructions", "final_recommendation", "route",
        "verified_at", "model_used", "truncated",
        "unsupported_claims", "corrections", "risks",
    ]
    for key in required_keys:
        assert key in result, f"Missing key: {key}"


def test_run_audit_metadata_populated():
    with patch("agents.scientific_verifier.ask_json", return_value=GOOD_LLM_RESPONSE):
        from agents.scientific_verifier import run
        result = run("Explore red TADF OLED", MINIMAL_PRIOR_OUTPUTS)
    assert result["verified_at"] != ""
    assert result["model_used"] != ""


def test_run_with_evidence_pack():
    evidence_pack = {
        "top_papers": LIT_SCAN_PRIOR_OUTPUTS["research_scout"]["top_papers"],
        "sources_used": ["openalex"],
        "profile_topics": ["TADF", "OLED", "red-NIR emission"],
    }
    with patch("agents.scientific_verifier.ask_json", return_value=GOOD_LLM_RESPONSE):
        from agents.scientific_verifier import run
        result = run("Find TADF papers", LIT_SCAN_PRIOR_OUTPUTS, evidence_pack=evidence_pack)
    assert "openalex" in result.get("evidence_sources_checked", [])


def test_run_llm_parse_failure_returns_incomplete():
    """If ask_json raises, the fallback must be 'incomplete', not 'acceptable'."""
    with patch("agents.scientific_verifier.ask_json", side_effect=ValueError("LLM JSON parse error")):
        # Repair also fails
        with patch("agents.scientific_verifier.ask_llm", side_effect=RuntimeError("Repair also failed")):
            from agents.scientific_verifier import run
            result = run("Test failure path", MINIMAL_PRIOR_OUTPUTS)

    assert result["overall_assessment"] == "incomplete"
    assert result["route"] == "human_review"
    assert result["final_recommendation"] == "needs_more_evidence"
    # Verify it did NOT silently pass as acceptable
    assert result["overall_assessment"] != "acceptable"


def test_run_claim_checks_populated():
    with patch("agents.scientific_verifier.ask_json", return_value=GOOD_LLM_RESPONSE):
        from agents.scientific_verifier import run
        result = run("Explore TADF", MINIMAL_PRIOR_OUTPUTS)

    assert len(result["claim_checks"]) == 2
    first = result["claim_checks"][0]
    assert first["claim_type"] == "novelty"
    assert first["support_status"] == "partially_supported"
    assert first["severity"] == "medium"
    assert 0.0 <= first["confidence"] <= 1.0


def test_run_human_approval_detected():
    """Action requiring contact author should appear in required_human_approvals."""
    with patch("agents.scientific_verifier.ask_json", return_value=GOOD_LLM_RESPONSE):
        from agents.scientific_verifier import run
        result = run("Explore TADF", MINIMAL_PRIOR_OUTPUTS)

    assert len(result["required_human_approvals"]) >= 1
    assert any("collaborator" in a.lower() or "contact" in a.lower()
               for a in result["required_human_approvals"])


def test_run_with_empty_prior_outputs():
    """Verifier should not crash on empty inputs."""
    minimal_response = {
        "overall_assessment": "incomplete",
        "claim_checks": [],
        "methodology_risks": [],
        "novelty_risks": [],
        "citation_risks": [],
        "grant_risks": [],
        "action_governance_risks": [],
        "required_human_approvals": [],
        "revision_instructions": ["No content to verify."],
        "final_recommendation": "needs_more_evidence",
        "route": "revise",
    }
    with patch("agents.scientific_verifier.ask_json", return_value=minimal_response):
        from agents.scientific_verifier import run
        result = run("", {})
    assert "overall_assessment" in result


# ---------------------------------------------------------------------------
# Backward compat — orchestrator smoke test still passes
# ---------------------------------------------------------------------------

def test_run_backward_compat_fields_present():
    """Fields used by the original orchestrator smoke test must still exist."""
    with patch("agents.scientific_verifier.ask_json", return_value=GOOD_LLM_RESPONSE):
        from agents.scientific_verifier import run
        result = run("Test", MINIMAL_PRIOR_OUTPUTS)

    for field in ("overall_assessment", "unsupported_claims", "assumptions",
                  "risks", "corrections", "final_recommendation"):
        assert field in result, f"Backward-compat field missing: {field}"
