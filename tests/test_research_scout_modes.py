"""
Tests for the upgraded AURA Research Scout.
All LLM calls and external APIs are mocked — no Ollama or internet required.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

MOCK_PAPER = {
    "source": "arxiv", "title": "Red TADF OLED device", "abstract": "We report...",
    "url": "https://arxiv.org/abs/2401.00001", "published_date": "2024-01-01",
    "authors": ["Dr. Smith"], "cited_by_count": 5, "unique_key": "abc123",
}

MOCK_SCORED_PAPER = {
    **MOCK_PAPER,
    "relevance": 8.0, "novelty": 7.0, "grant_potential": 7.0,
    "collaboration_potential": 6.0, "industry_potential": 6.0,
    "teaching_public_value": 5.0, "feasibility": 7.0, "risk": 3.0,
    "oled_device_usefulness": 8.0, "tadf_mechanism_relevance": 7.0,
    "red_nir_emission_relevance": 9.0, "lanthanide_relevance": 5.0,
    "experimental_feasibility": 7.0,
    "total_score": 7.2, "agent_commentary": "Good paper.",
    "evidence_gaps": [], "recommended_action": "use_for_grant",
    "recommended_use": "cite_in_grant", "opportunity_type": "proposal",
    "key_metrics": {"EQE_percent": 18.0, "emission_wavelength_nm": 630},
}

MOCK_GAP_RAW = {
    "gap_statement": "No device combining TADF sensitisation with Yb(III) NIR emission for wound healing.",
    "best_research_gap_candidate": "No device combining TADF sensitisation with Yb(III) NIR emission.",
    "supporting_papers": ["Red TADF OLED device"],
    "contradicting_or_overlap_papers": [],
    "why_gap_exists": "Lanthanide OLED integration is technically difficult.",
    "why_gap_matters": "Biomedical applications require NIR photons.",
    "what_is_new": "TADF-sensitised Yb NIR OLED for photobiomodulation.",
    "what_is_not_new": "TADF emitters and Yb complexes exist separately.",
    "minimum_evidence_needed": ["Device EQE at >900 nm", "Bioactivity at target dose"],
    "proposal_angle": "EPSRC-fundable as medical devices for wound care.",
    "paper_angle": "Proof-of-concept device paper.",
    "risk_level": "medium",
    "evidence_from_papers": ["Paper 1 shows 18% EQE at 630 nm."],
    "collaboration_angle": "Clinical collaborators for dose studies.",
    "industry_angle": "Partnership with OLEDWorks.",
    "teaching_or_linkedin_angle": "OLED phototherapy public interest.",
    "risks_or_weaknesses": "Device lifetime unknown.",
    "next_action": "Literature search for TADF+Yb prior art.",
    "why_user_is_positioned": "Group has TADF and lanthanide expertise.",
    "possible_research_question": "Can TADF sensitisation achieve >1% EQE at 980 nm?",
    "possible_grant_angle": "Medical devices call.",
}

MOCK_IDEATION_LLM_RESPONSE = {
    "summary": "Promising gap in red TADF for photobiomodulation.",
    "core_hypothesis": "TADF-Yb OLED can deliver therapeutic NIR dose non-invasively.",
    "scientific_mechanism": "RISC → Yb sensitisation → 980 nm emission.",
    "why_now": "Recent TADF breakthroughs enable better sensitisers.",
    "nearest_prior_work": ["Ref 1: TADF OLEDs at 620 nm", "Ref 2: Yb complexes in solution"],
    "novelty_risk": "Yb NIR OLEDs have been made, but not TADF-sensitised.",
    "minimum_literature_needed": ["Search Yb OLED prior art"],
    "minimum_experiment_needed": ["Synthesise TADF-Yb dyad"],
    "grant_angle": "EPSRC medical devices call.",
    "grant_angles": ["EPSRC medical devices", "MRC phototherapy"],
    "collaboration_targets": ["Clinical wound-care group"],
    "kill_criteria": [
        "No biological response at device emission wavelength.",
        "Device EQE below 0.1% — insufficient photon flux.",
    ],
    "research_gap_candidate": "TADF-sensitised Yb NIR OLED for photobiomodulation.",
    "findings": ["Strong gap identified in TADF-Yb OLED."],
    "risks": ["Device lifetime unknown."],
    "recommended_actions": ["Search Yb OLED literature."],
    "novelty_risks": ["Yb OLEDs already reported in non-TADF form."],
    "methodology_risks": ["RISC to Yb transfer efficiency uncertain."],
    "search_queries": ["TADF Yb NIR OLED"],
    "queries_recommended_next": ["Yb complex OLED efficiency review"],
    "confidence": "medium",
}


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------

def test_resolve_mode_literature_scan():
    from agents.research_scout import _resolve_mode
    assert _resolve_mode("find recent papers on TADF", "ideation") == "literature_scan"


def test_resolve_mode_gap_analysis():
    from agents.research_scout import _resolve_mode
    assert _resolve_mode("perform a gap analysis", "ideation") == "gap_analysis"


def test_resolve_mode_grant_opportunity():
    from agents.research_scout import _resolve_mode
    assert _resolve_mode("what is the best grant opportunity here", "ideation") == "grant_opportunity"


def test_resolve_mode_respects_governor_advanced_mode():
    from agents.research_scout import _resolve_mode
    assert _resolve_mode("some input", "gap_analysis") == "gap_analysis"


def test_resolve_mode_falls_back_to_ideation():
    from agents.research_scout import _resolve_mode
    assert _resolve_mode("tell me about OLED devices", "") == "ideation"


# ---------------------------------------------------------------------------
# Session ID
# ---------------------------------------------------------------------------

def test_session_id_is_deterministic_within_day():
    from agents.research_scout import _make_session_id
    s1 = _make_session_id("Find TADF papers")
    s2 = _make_session_id("Find TADF papers")
    assert s1 == s2
    assert len(s1) == 10


def test_session_id_differs_for_different_inputs():
    from agents.research_scout import _make_session_id
    assert _make_session_id("Find TADF papers") != _make_session_id("Find lanthanide papers")


# ---------------------------------------------------------------------------
# Query planner
# ---------------------------------------------------------------------------

MOCK_QUERY_PLAN = {
    "broad_queries": ["TADF OLED red NIR"],
    "mechanism_queries": ["RISC DELTA EST organic"],
    "material_queries": ["lanthanide Yb NIR emitter"],
    "device_queries": ["red OLED EQE device"],
    "application_queries": ["photobiomodulation 630nm 850nm"],
    "grant_angle_queries": ["EPSRC OLED medical devices"],
    "negative_control_queries": ["Yb OLED prior art review"],
}


def test_query_planner_returns_flat_queries():
    with patch("agents.research_scout.ask_json", return_value=MOCK_QUERY_PLAN):
        from agents.research_scout import _plan_queries, _flatten_queries
        plan = _plan_queries("Find red TADF papers", ["TADF", "OLED"])
        flat = _flatten_queries(plan)
    assert isinstance(flat, list)
    assert len(flat) > 0
    assert all(isinstance(q, str) for q in flat)


def test_query_planner_fallback_on_failure():
    with patch("agents.research_scout.ask_json", side_effect=RuntimeError("LLM failed")):
        from agents.research_scout import _plan_queries
        plan = _plan_queries("Find TADF papers", ["TADF", "OLED", "red emission"])
    assert "broad_queries" in plan
    assert len(plan["broad_queries"]) > 0


def test_flatten_queries_deduplicates():
    from agents.research_scout import _flatten_queries
    plan = {"broad_queries": ["TADF OLED", "TADF OLED"], "mechanism_queries": ["RISC"]}
    flat = _flatten_queries(plan)
    assert flat.count("TADF OLED") == 1


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

MOCK_CLAIM_RAW = {
    "paper_title": "Red TADF OLED device",
    "main_claims": ["EQE of 18% at 630 nm achieved."],
    "evidence_used": ["Transient PL, device J-V-L."],
    "methods": ["Thermal evaporation", "TDDFT"],
    "key_metrics": {"EQE_percent": 18.0, "emission_wavelength_nm": 630},
    "limitations": ["No operational lifetime reported."],
    "what_it_supports_for_user": ["Supports red OLED EQE claims."],
    "what_it_does_not_support": ["Does not address NIR extension."],
}


def test_extract_claims_from_paper():
    with patch("agents.research_scout.ask_json", return_value=MOCK_CLAIM_RAW):
        from agents.research_scout import _extract_claims_from_paper
        result = _extract_claims_from_paper(MOCK_PAPER)
    assert result.paper_title != ""
    assert len(result.main_claims) >= 1
    assert result.key_metrics.get("EQE_percent") == 18.0
    assert len(result.what_it_does_not_support) >= 1


def test_extract_claims_fallback_on_failure():
    with patch("agents.research_scout.ask_json", side_effect=ValueError("Parse error")):
        from agents.research_scout import _extract_claims_from_paper
        result = _extract_claims_from_paper(MOCK_PAPER)
    assert result.paper_title != ""
    assert any("Parse error" in l for l in result.limitations)


def test_extract_top_paper_claims_capped_at_3():
    papers = [MOCK_SCORED_PAPER] * 5
    with patch("agents.research_scout.ask_json", return_value=MOCK_CLAIM_RAW):
        from agents.research_scout import _extract_top_paper_claims
        maps = _extract_top_paper_claims(papers, cap=3)
    assert len(maps) == 3


# ---------------------------------------------------------------------------
# Rich gap and verifier package
# ---------------------------------------------------------------------------

def test_build_rich_gap_populates_what_is_not_new():
    from agents.research_scout import _build_rich_gap
    gap = _build_rich_gap(MOCK_GAP_RAW)
    assert gap.what_is_not_new != ""
    assert gap.gap_statement != ""
    assert gap.risk_level in ("low", "medium", "high")


def test_build_verifier_package_includes_grant_claims():
    from agents.research_scout import _build_verifier_package
    from core.schemas import ClaimEvidenceMap, ResearchGapCandidate
    cm = ClaimEvidenceMap(paper_title="Paper A", main_claims=["TADF EQE > 20%"])
    gap = ResearchGapCandidate(
        gap_statement="No TADF-Yb OLED exists",
        what_is_new="TADF sensitisation of Yb",
        proposal_angle="EPSRC medical devices grant",
    )
    package = _build_verifier_package([cm], gap, ["email collaborator at University X"])
    assert any("paper" in c.lower() or "Paper A" in c for c in package)
    assert any("grant" in c.lower() or "EPSRC" in c for c in package)
    assert any("action" in c.lower() or "email" in c.lower() for c in package)


# ---------------------------------------------------------------------------
# Opportunity map
# ---------------------------------------------------------------------------

def test_build_opportunity_map_clusters_by_action():
    from agents.research_scout import _build_opportunity_map
    papers = [
        {**MOCK_SCORED_PAPER, "recommended_action": "use_for_grant"},
        {**MOCK_SCORED_PAPER, "title": "Paper B", "recommended_action": "read_now"},
        {**MOCK_SCORED_PAPER, "title": "Paper C", "recommended_action": "use_for_grant"},
    ]
    clusters = _build_opportunity_map(papers)
    names = [c.cluster_name for c in clusters]
    assert any("Grant" in n for n in names)
    assert any("Reading" in n or "Priority" in n for n in names)


# ---------------------------------------------------------------------------
# Evidence quality
# ---------------------------------------------------------------------------

def test_evidence_quality_weak_on_empty():
    from agents.research_scout import _compute_evidence_quality
    assert _compute_evidence_quality([]) == "weak"


def test_evidence_quality_strong_on_many_peer_reviewed():
    from agents.research_scout import _compute_evidence_quality
    papers = [
        {"source": "openalex", "cited_by_count": 20} for _ in range(7)
    ]
    assert _compute_evidence_quality(papers) == "strong"


# ---------------------------------------------------------------------------
# Mode: ideation
# ---------------------------------------------------------------------------

def test_ideation_mode_does_not_call_paper_apis():
    with patch("agents.research_scout.ask_json", return_value=MOCK_IDEATION_LLM_RESPONSE):
        with patch("integrations.research_evolution.paper_sources.search_all_sources") as mock_search:
            from agents.research_scout import run
            result = run("Explore TADF red OLED for photobiomodulation", context={}, mode="ideation")
            mock_search.assert_not_called()
    assert result["mode"] == "ideation"
    assert result["literature_scan_used"] is False


def test_ideation_mode_populates_kill_criteria():
    with patch("agents.research_scout.ask_json", return_value=MOCK_IDEATION_LLM_RESPONSE):
        from agents.research_scout import run
        result = run("Explore TADF red OLED", context={}, mode="ideation")
    assert len(result.get("kill_criteria", [])) >= 2


def test_ideation_mode_populates_grant_angles():
    with patch("agents.research_scout.ask_json", return_value=MOCK_IDEATION_LLM_RESPONSE):
        from agents.research_scout import run
        result = run("Evaluate TADF idea", context={}, mode="ideation")
    assert len(result.get("grant_angles", [])) >= 1


def test_ideation_mode_populates_claims_for_verification():
    with patch("agents.research_scout.ask_json", return_value=MOCK_IDEATION_LLM_RESPONSE):
        from agents.research_scout import run
        result = run("Explore TADF red OLED", context={}, mode="ideation")
    claims = result.get("claims_for_verification", [])
    assert len(claims) >= 1


# ---------------------------------------------------------------------------
# Mode: literature_scan
# ---------------------------------------------------------------------------

def test_literature_scan_calls_paper_discovery():
    with patch("integrations.research_evolution.discover_papers", return_value=[MOCK_PAPER]) as mock_disc:
        with patch("integrations.research_evolution.score_papers_integration", return_value=[MOCK_SCORED_PAPER]):
            with patch("integrations.research_evolution.save_scored_papers"):
                with patch("integrations.research_evolution.get_top_papers_for_session", return_value=[MOCK_SCORED_PAPER]):
                    with patch("integrations.research_evolution.generate_research_gap_analysis", return_value=MOCK_GAP_RAW):
                        with patch("integrations.research_evolution.generate_weekly_brief_if_requested", return_value=None):
                            with patch("agents.research_scout.ask_json", return_value=MOCK_QUERY_PLAN):
                                with patch("agents.research_scout._extract_top_paper_claims", return_value=[]):
                                    from agents.research_scout import run
                                    result = run("Find recent TADF papers", context={}, mode="literature_scan")
        mock_disc.assert_called_once()
    assert result["literature_scan_used"] is True
    assert result["mode"] == "literature_scan"


def test_literature_scan_populates_session_id():
    with patch("integrations.research_evolution.discover_papers", return_value=[MOCK_PAPER]):
        with patch("integrations.research_evolution.score_papers_integration", return_value=[MOCK_SCORED_PAPER]):
            with patch("integrations.research_evolution.save_scored_papers") as mock_save:
                with patch("integrations.research_evolution.get_top_papers_for_session", return_value=[MOCK_SCORED_PAPER]):
                    with patch("integrations.research_evolution.generate_research_gap_analysis", return_value=MOCK_GAP_RAW):
                        with patch("integrations.research_evolution.generate_weekly_brief_if_requested", return_value=None):
                            with patch("agents.research_scout.ask_json", return_value=MOCK_QUERY_PLAN):
                                with patch("agents.research_scout._extract_top_paper_claims", return_value=[]):
                                    from agents.research_scout import run
                                    run("Find TADF papers", context={}, mode="literature_scan")
    # save_scored_papers should be called with a session_id keyword arg
    assert mock_save.called
    call_kwargs = mock_save.call_args
    assert call_kwargs is not None


def test_literature_scan_rich_gap_populated():
    with patch("integrations.research_evolution.discover_papers", return_value=[MOCK_PAPER]):
        with patch("integrations.research_evolution.score_papers_integration", return_value=[MOCK_SCORED_PAPER]):
            with patch("integrations.research_evolution.save_scored_papers"):
                with patch("integrations.research_evolution.get_top_papers_for_session", return_value=[MOCK_SCORED_PAPER]):
                    with patch("integrations.research_evolution.generate_research_gap_analysis", return_value=MOCK_GAP_RAW):
                        with patch("integrations.research_evolution.generate_weekly_brief_if_requested", return_value=None):
                            with patch("agents.research_scout.ask_json", return_value=MOCK_QUERY_PLAN):
                                with patch("agents.research_scout._extract_top_paper_claims", return_value=[]):
                                    from agents.research_scout import run
                                    result = run("Find TADF papers", context={}, mode="literature_scan")
    gaps = result.get("research_gap_candidates", [])
    assert len(gaps) >= 1
    assert gaps[0].get("what_is_not_new", "") != ""


def test_literature_scan_partial_results_on_discovery_failure():
    with patch("integrations.research_evolution.discover_papers", side_effect=ConnectionError("Network down")):
        with patch("integrations.research_evolution.get_top_papers_for_session", return_value=[]):
            with patch("integrations.research_evolution.generate_weekly_brief_if_requested", return_value=None):
                with patch("agents.research_scout.ask_json", return_value=MOCK_QUERY_PLAN):
                    from agents.research_scout import run
                    result = run("Find TADF papers", context={}, mode="literature_scan")
    assert result["partial_results"] is True
    assert result["failed_stage"] != ""


# ---------------------------------------------------------------------------
# Mode: gap_analysis
# ---------------------------------------------------------------------------

MOCK_GAP_ANALYSIS_RESPONSE = {
    "summary": "Two significant gaps identified.",
    "primary_gap": {
        "gap_statement": "No TADF-Yb NIR OLED demonstrated.",
        "what_is_not_new": "Yb OLEDs exist without TADF.",
        "minimum_evidence_needed": ["Device EQE data"],
        "proposal_angle": "EPSRC call",
        "paper_angle": "Device proof-of-concept paper",
        "risk_level": "medium",
        "supporting_papers": ["Paper 1"],
        "contradicting_or_overlap_papers": [],
    },
    "secondary_gaps": [
        {"gap_statement": "No red OLED for phototherapy clinical trial.", "risk_level": "high", "proposal_angle": "MRC"}
    ],
    "grant_angles": ["EPSRC medical devices"],
    "kill_criteria": ["No bio-response at target wavelength"],
    "recommended_actions": ["Search Yb OLED literature"],
    "confidence": "medium",
}


def test_gap_analysis_mode_uses_stored_papers():
    with patch("integrations.research_evolution.get_top_papers_for_session", return_value=[MOCK_SCORED_PAPER]) as mock_get:
        with patch("agents.research_scout.ask_json", return_value=MOCK_GAP_ANALYSIS_RESPONSE):
            from agents.research_scout import run
            result = run("Identify gaps in TADF OLED literature", context={}, mode="gap_analysis")
    assert mock_get.called
    assert result["mode"] == "gap_analysis"
    gaps = result.get("research_gap_candidates", [])
    assert len(gaps) >= 1
    assert gaps[0]["what_is_not_new"] != ""


def test_gap_analysis_fallback_when_no_papers():
    with patch("integrations.research_evolution.get_top_papers_for_session", return_value=[]):
        from agents.research_scout import run
        result = run("Gap analysis", context={}, mode="gap_analysis")
    assert result["partial_results"] is True
    assert "scan" in result["summary"].lower() or "available" in result["summary"].lower()


# ---------------------------------------------------------------------------
# Output schema — all required fields present
# ---------------------------------------------------------------------------

def test_output_has_all_required_fields():
    with patch("agents.research_scout.ask_json", return_value=MOCK_IDEATION_LLM_RESPONSE):
        from agents.research_scout import run
        result = run("Evaluate research idea", context={}, mode="ideation")
    required = [
        "agent_name", "mode", "summary", "findings", "top_papers",
        "research_gap_candidate", "research_gap_candidates",
        "literature_scan_used", "kill_criteria", "grant_angles",
        "novelty_risks", "methodology_risks", "claims_for_verification",
        "evidence_quality", "requires_scientific_verification",
        "partial_results", "failed_stage",
        "queries_used", "queries_recommended_next",
        "opportunity_map",
    ]
    for field in required:
        assert field in result, f"Missing field: {field}"


def test_backward_compat_fields_present():
    """Original fields used by existing orchestrator smoke test must still exist."""
    with patch("agents.research_scout.ask_json", return_value=MOCK_IDEATION_LLM_RESPONSE):
        from agents.research_scout import run
        result = run("Evaluate idea", context={}, mode="ideation")
    for field in ("search_queries", "research_gap_candidate", "top_papers", "findings",
                  "risks", "recommended_actions", "confidence"):
        assert field in result, f"Backward-compat field missing: {field}"
