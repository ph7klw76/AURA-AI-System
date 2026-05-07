"""
AURA Research Scout — Opportunity Intelligence Agent.

Modes:
    ideation          Structured analysis of a research idea with kill criteria.
    literature_scan   Full pipeline: query-plan → search → score → claims → gap → map.
    gap_analysis      Deep gap analysis from already-stored session or global papers.
    grant_opportunity Grant-focused analysis: funding angles, claim hierarchy, risk.
    paper_intake      [Phase 2 stub]
    trend_monitor     [Phase 2 stub]
    reviewer_attack_scan  [Phase 2 stub]
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from typing import Any

from core.llm import ask_json
from core.memory import retrieve_relevant_memory
from core.schemas import (
    ClaimEvidenceMap,
    OpportunityCluster,
    ResearchGapCandidate,
    ResearchScoutOutput,
    TopPaper,
)

# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------

_MODE_KEYWORDS: dict[str, list[str]] = {
    "gap_analysis": [
        "gap analysis", "research gap", "identify gap", "what is the gap",
        "where is the gap", "gap in the literature",
    ],
    "grant_opportunity": [
        "grant opportunity", "funding angle", "grant-relevant",
        "write a grant", "grant call", "grant application",
    ],
    "literature_scan": [
        "find papers", "search papers", "recent papers", "literature scan",
        "arxiv", "openalex", "weekly brief", "top papers", "score papers",
        "paper ranking", "latest papers", "literature review",
    ],
    "ideation": [
        "research idea", "proposal concept", "hypothesis", "grant angle",
        "scientific strategy", "evaluate this idea", "explore",
    ],
}

_ALL_KNOWN_MODES = set(_MODE_KEYWORDS) | {"paper_intake", "trend_monitor", "reviewer_attack_scan"}


def _resolve_mode(user_input: str, governor_mode: str) -> str:
    """User phrasing always takes priority; governor_mode is the fallback."""
    lower = user_input.lower()
    for mode, keywords in _MODE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return mode
    if governor_mode in _ALL_KNOWN_MODES:
        return governor_mode
    return "ideation"


def _make_session_id(user_input: str) -> str:
    today = date.today().isoformat()
    return hashlib.sha256(f"{user_input}{today}".encode()).hexdigest()[:10]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _compute_evidence_quality(top_papers: list[dict]) -> str:
    n = len(top_papers)
    if n == 0:
        return "weak"
    peer_reviewed = sum(
        1 for p in top_papers
        if p.get("source") == "openalex" and int(p.get("cited_by_count") or 0) > 5
    )
    if n >= 6 and peer_reviewed >= 3:
        return "strong"
    if n >= 3:
        return "moderate"
    return "weak"


def _format_top_papers(top_papers_dicts: list[dict]) -> list[TopPaper]:
    papers: list[TopPaper] = []
    now = datetime.now(timezone.utc).isoformat()
    for p in top_papers_dicts[:8]:
        km = p.get("key_metrics")
        if not isinstance(km, dict):
            km = {}
        papers.append(TopPaper(
            title=p.get("title", ""),
            source=p.get("source", ""),
            published_date=p.get("published_date", ""),
            total_score=float(p.get("total_score", 0.0)),
            recommended_action=p.get("recommended_action", "save_for_later"),
            url=p.get("url", ""),
            commentary=p.get("agent_commentary", ""),
            evidence_gaps=(
                p.get("evidence_gaps", []) if isinstance(p.get("evidence_gaps"), list) else []
            ),
            doi=p.get("doi", ""),
            cited_by_count=int(p.get("cited_by_count") or 0),
            publication_type=_infer_pub_type(p),
            abstract_available=bool(p.get("abstract", "")),
            retrieved_at=now,
            key_metrics=km,
        ))
    return papers


def _infer_pub_type(paper: dict) -> str:
    src = paper.get("source", "")
    if src == "arxiv":
        return "preprint"
    if src == "openalex":
        return "journal"
    return "unknown"


def _build_opportunity_map(top_papers: list[dict]) -> list[OpportunityCluster]:
    """
    Python-level clustering by recommended_action — no extra LLM call.
    Groups papers into action-driven clusters.
    """
    clusters: dict[str, list[str]] = {}
    for p in top_papers:
        action = p.get("recommended_action", "save_for_later")
        clusters.setdefault(action, []).append(p.get("title", "Untitled")[:80])

    action_labels = {
        "use_for_grant":  "Grant-Ready Papers",
        "read_now":       "High-Priority Reading",
        "contact_author": "Collaboration Leads",
        "use_for_teaching": "Teaching & Outreach Papers",
        "save_for_later": "Background Literature",
        "use_for_linkedin": "Public Communication Opportunities",
    }
    result: list[OpportunityCluster] = []
    for action, titles in clusters.items():
        if action == "ignore" or not titles:
            continue
        top_scores = [
            float(p.get("total_score", 0.0))
            for p in top_papers
            if p.get("recommended_action") == action
        ]
        avg_score = round(sum(top_scores) / len(top_scores), 2) if top_scores else 0.0
        result.append(OpportunityCluster(
            cluster_name=action_labels.get(action, action.replace("_", " ").title()),
            core_papers=titles[:5],
            strategic_value=avg_score,
            next_action=f"Review the {action.replace('_', ' ')} papers above.",
        ))
    result.sort(key=lambda c: c.strategic_value, reverse=True)
    return result


def _build_rich_gap(gap_raw: dict) -> ResearchGapCandidate:
    return ResearchGapCandidate(
        gap_statement=gap_raw.get("gap_statement") or gap_raw.get("best_research_gap_candidate", ""),
        supporting_papers=gap_raw.get("supporting_papers", []) or gap_raw.get("evidence_from_papers", []),
        contradicting_or_overlap_papers=gap_raw.get("contradicting_or_overlap_papers", []),
        why_gap_exists=gap_raw.get("why_gap_exists", ""),
        why_gap_matters=gap_raw.get("why_gap_matters", ""),
        what_is_new=gap_raw.get("what_is_new", ""),
        what_is_not_new=gap_raw.get("what_is_not_new", ""),
        minimum_evidence_needed=gap_raw.get("minimum_evidence_needed", []),
        proposal_angle=gap_raw.get("proposal_angle") or gap_raw.get("possible_grant_angle", ""),
        paper_angle=gap_raw.get("paper_angle", ""),
        risk_level=gap_raw.get("risk_level", "medium"),
    )


def _build_verifier_package(
    claim_maps: list[ClaimEvidenceMap],
    gap: ResearchGapCandidate | None,
    recommended_actions: list[str],
) -> list[str]:
    claims: list[str] = []
    for cm in claim_maps:
        for c in cm.main_claims[:3]:
            claims.append(f"[paper: {cm.paper_title[:50]}] {c}")
    if gap and gap.gap_statement:
        claims.append(f"[gap_novelty] {gap.what_is_new}")
        claims.append(f"[gap_statement] {gap.gap_statement}")
        if gap.proposal_angle:
            claims.append(f"[grant_claim] {gap.proposal_angle}")
    for a in recommended_actions:
        lower_a = a.lower()
        if any(kw in lower_a for kw in ("email", "contact", "submit", "publish", "send")):
            claims.append(f"[action_claim] {a}")
    return [c for c in claims if c][:20]


# ---------------------------------------------------------------------------
# Claim extraction (LLM, capped to top 3 papers)
# ---------------------------------------------------------------------------

CLAIM_EXTRACTION_PROMPT = """\
You are an OLED/photophysics paper analyst. Extract structured scientific content from the paper below.

Return strict JSON with EXACTLY this schema:
{
  "paper_title": "...",
  "main_claims": ["up to 3 main claims stated in the abstract"],
  "evidence_used": ["experimental or computational evidence cited"],
  "methods": ["techniques used: e.g. TDDFT, CV, transient PL, device fabrication"],
  "key_metrics": {
    "emission_wavelength_nm": null,
    "EQE_percent": null,
    "PLQY_percent": null,
    "luminance_cd_m2": null,
    "turn_on_voltage_V": null,
    "DELTA_EST_eV": null,
    "operational_lifetime_hours": null,
    "host_dopant_system": null,
    "device_architecture": null,
    "roll_off": null
  },
  "limitations": ["stated or obvious limitations"],
  "what_it_supports_for_user": ["what this paper supports for an OLED/TADF researcher"],
  "what_it_does_not_support": ["what it cannot be used to claim"]
}

Only extract values explicitly stated. Set null for metrics not mentioned. Do not invent anything."""


def _extract_claims_from_paper(paper: dict) -> ClaimEvidenceMap:
    user_prompt = (
        f"Paper title: {paper.get('title', 'Untitled')}\n"
        f"Source: {paper.get('source', '?')} | Published: {paper.get('published_date', '?')}\n"
        f"Authors: {', '.join((paper.get('authors') or [])[:3])}\n\n"
        f"Abstract:\n{paper.get('abstract', 'No abstract.')[:1200]}\n\n"
        "Extract and return strict JSON."
    )
    try:
        raw = ask_json(CLAIM_EXTRACTION_PROMPT, user_prompt, temperature=0.0)
        km = raw.get("key_metrics")
        if not isinstance(km, dict):
            km = {}
        return ClaimEvidenceMap(
            paper_title=raw.get("paper_title") or paper.get("title", ""),
            main_claims=raw.get("main_claims", [])[:4],
            evidence_used=raw.get("evidence_used", [])[:4],
            methods=raw.get("methods", [])[:4],
            key_metrics=km,
            limitations=raw.get("limitations", [])[:4],
            what_it_supports_for_user=raw.get("what_it_supports_for_user", [])[:4],
            what_it_does_not_support=raw.get("what_it_does_not_support", [])[:4],
        )
    except Exception as exc:
        return ClaimEvidenceMap(
            paper_title=paper.get("title", "Untitled"),
            limitations=[f"Claim extraction failed: {exc}"],
        )


def _extract_top_paper_claims(top_papers: list[dict], cap: int = 3) -> list[ClaimEvidenceMap]:
    priority = [p for p in top_papers if p.get("abstract", "")]
    return [_extract_claims_from_paper(p) for p in priority[:cap]]


# ---------------------------------------------------------------------------
# Query planner
# ---------------------------------------------------------------------------

QUERY_PLANNER_PROMPT = """\
You are a research query planner for an OLED/TADF/photophysics/organic-electronics research group.
Given the user's request and their profile topics, generate targeted search queries.

Return strict JSON with EXACTLY these keys (each value is a list of 1–3 query strings):
{
  "broad_queries": [],
  "mechanism_queries": [],
  "material_queries": [],
  "device_queries": [],
  "application_queries": [],
  "grant_angle_queries": [],
  "negative_control_queries": []
}

negative_control_queries should ask: "Has this already been done, and who has done something closest?"
These reveal novelty risks and prevent overclaiming.
Keep every query short (under 10 words). Do not repeat topics verbatim."""


def _plan_queries(user_input: str, topics: list[str]) -> dict[str, list[str]]:
    user_prompt = (
        f"User request: {user_input}\n\n"
        f"Profile topics: {', '.join(topics[:8])}\n\n"
        "Generate the query plan as strict JSON."
    )
    fallback = {
        "broad_queries": topics[:3],
        "mechanism_queries": ["TADF photophysics RISC", "ΔEST singlet triplet organic"],
        "material_queries": ["TADF emitter red NIR", "lanthanide complex OLED"],
        "device_queries": ["OLED device efficiency stability", "red OLED EQE luminance"],
        "application_queries": [],
        "grant_angle_queries": ["organic electronics UKRI grant", "OLED biomedical application funding"],
        "negative_control_queries": ["existing red NIR OLED TADF review", "lanthanide OLED prior art"],
    }
    lower = user_input.lower()
    if "photobiomodulation" in lower or "wound" in lower or "therapy" in lower:
        fallback["application_queries"] = [
            "photobiomodulation 630 nm 850 nm wavelength",
            "LED phototherapy biomedical wearable",
        ]
    try:
        raw = ask_json(QUERY_PLANNER_PROMPT, user_prompt, temperature=0.15)
        if isinstance(raw, dict) and "broad_queries" in raw:
            return raw
        return fallback
    except Exception:
        return fallback


def _flatten_queries(plan: dict[str, list[str]], max_total: int = 10) -> list[str]:
    seen: set[str] = set()
    flat: list[str] = []
    # Priority order: broad first, negative last
    order = [
        "broad_queries", "mechanism_queries", "material_queries",
        "device_queries", "application_queries", "grant_angle_queries",
        "negative_control_queries",
    ]
    for key in order:
        for q in plan.get(key, []):
            q = q.strip()
            if q and q not in seen:
                seen.add(q)
                flat.append(q)
            if len(flat) >= max_total:
                return flat
    return flat


# ---------------------------------------------------------------------------
# Mode: ideation
# ---------------------------------------------------------------------------

IDEATION_SYSTEM_PROMPT = """\
You are the AURA Research Scout in ideation mode.
You are working with an expert researcher in organic semiconductors, OLED, TADF, photophysics,
lanthanide complexes, and biomedical applications of red/NIR light.

Your role: analyse the research idea and identify whether it is scientifically defensible,
strategically useful, fundable, and worth acting on.

Return strict JSON with EXACTLY this schema:
{
  "summary": "2-3 sentence synthesis of the opportunity",
  "core_hypothesis": "The central testable scientific hypothesis",
  "scientific_mechanism": "The proposed physical/chemical mechanism",
  "why_now": "Why is this idea timely? What recent advances enable it?",
  "nearest_prior_work": ["Most relevant existing work — be specific"],
  "novelty_risk": "What prior work already covers parts of this idea?",
  "minimum_literature_needed": ["Specific papers or topics to search before proceeding"],
  "minimum_experiment_needed": ["Specific experiments needed to test the core hypothesis"],
  "grant_angle": "How to frame this for a grant panel in 2 sentences",
  "grant_angles": ["List of 2-3 specific funding angles"],
  "collaboration_targets": ["Specific collaborator profiles or institutions needed"],
  "kill_criteria": ["Conditions under which this idea should be paused or abandoned"],
  "research_gap_candidate": "The primary research gap this idea addresses",
  "findings": ["Key insights from this analysis"],
  "risks": ["Scientific, technical, or strategic risks"],
  "recommended_actions": ["Specific next steps"],
  "novelty_risks": ["Ways in which novelty may be overstated"],
  "methodology_risks": ["Experimental or computational risks"],
  "search_queries": ["Specific queries for OpenAlex/arXiv follow-up"],
  "queries_recommended_next": ["Additional queries for a follow-up literature scan"],
  "confidence": "low | medium | high"
}

Be evidence-aware. Do not overstate novelty.
Kill criteria are mandatory — include at least 2."""


def _run_ideation(user_input: str, context: dict) -> dict:
    memories = retrieve_relevant_memory(user_input, limit=5)
    memory_text = "\n".join(m.get("content", "") for m in memories) if memories else "No relevant memories."

    user_prompt = (
        f"User request:\n{user_input}\n\n"
        f"Governor context:\n{context}\n\n"
        f"Relevant AURA memories:\n{memory_text}\n\n"
        "Analyse this research idea and return your Scout output as strict JSON."
    )
    try:
        raw = ask_json(IDEATION_SYSTEM_PROMPT, user_prompt, temperature=0.2)
        gap = raw.get("research_gap_candidate", "")
        gap_obj = ResearchGapCandidate(
            gap_statement=gap,
            what_is_not_new=raw.get("novelty_risk", ""),
            proposal_angle=raw.get("grant_angle", ""),
            minimum_evidence_needed=raw.get("minimum_literature_needed", [])[:3],
        )
        claims_for_verification = [
            raw.get("core_hypothesis", ""),
            raw.get("scientific_mechanism", ""),
            raw.get("research_gap_candidate", ""),
        ] + [f"[grant] {a}" for a in raw.get("grant_angles", [])[:2]]
        claims_for_verification = [c for c in claims_for_verification if c]

        out = ResearchScoutOutput(
            mode="ideation",
            summary=raw.get("summary", ""),
            findings=raw.get("findings", []),
            risks=raw.get("risks", []),
            novelty_risks=raw.get("novelty_risks", []),
            methodology_risks=raw.get("methodology_risks", []),
            grant_angles=raw.get("grant_angles", []),
            collaboration_targets=raw.get("collaboration_targets", []),
            kill_criteria=raw.get("kill_criteria", []),
            recommended_actions=raw.get("recommended_actions", []),
            research_gap_candidate=gap,
            research_gap_candidates=[gap_obj],
            search_queries=raw.get("search_queries", []),
            queries_used=[],
            queries_recommended_next=raw.get("queries_recommended_next", []),
            confidence=raw.get("confidence", "medium"),
            evidence_quality="weak",
            requires_scientific_verification=True,
            literature_scan_used=False,
            claims_for_verification=claims_for_verification,
        )
        return out.model_dump()
    except Exception as exc:
        return ResearchScoutOutput(
            mode="ideation",
            summary=f"Ideation analysis incomplete: {exc}",
            confidence="low",
            partial_results=True,
            failed_stage="llm_ideation",
            recovery_action="retry_search",
        ).model_dump()


# ---------------------------------------------------------------------------
# Mode: literature_scan
# ---------------------------------------------------------------------------

def _run_literature_scan(user_input: str, context: dict) -> dict:
    from integrations.research_evolution import (
        discover_papers,
        score_papers_integration,
        save_scored_papers,
        get_top_papers_for_session,
        generate_research_gap_analysis,
        generate_weekly_brief_if_requested,
    )
    from integrations.research_evolution.profile import load_research_profile

    errors: list[str] = []
    failed_stage = ""
    report_paths: list[str] = []
    session_id = _make_session_id(user_input)

    # 1. Load profile
    try:
        profile = load_research_profile()
    except Exception as exc:
        errors.append(f"Profile load failed: {exc}")
        profile = {}
    topics: list[str] = profile.get("research_topics", ["OLED", "TADF", "organic semiconductor"])

    # 2. Plan queries
    query_plan: dict[str, list[str]] = {}
    try:
        query_plan = _plan_queries(user_input, topics)
    except Exception as exc:
        errors.append(f"Query planner failed: {exc}")
        query_plan = {"broad_queries": topics[:4]}

    flat_queries = _flatten_queries(query_plan, max_total=10)

    # 3. Discover papers using planned queries
    papers: list[dict] = []
    try:
        papers = discover_papers(flat_queries or topics, user_input)
    except Exception as exc:
        failed_stage = "paper_discovery"
        errors.append(f"Paper discovery failed: {exc}")

    # 4. Score papers
    scored: list[dict] = []
    if papers:
        try:
            scored = score_papers_integration(profile, papers)
        except Exception as exc:
            failed_stage = failed_stage or "paper_scoring"
            errors.append(f"Paper scoring failed: {exc}")

    # 5. Save with session tag
    if scored:
        try:
            save_scored_papers(scored, session_id=session_id)
        except Exception as exc:
            errors.append(f"Paper save failed: {exc}")

    # 6. Retrieve top papers for THIS session (falls back to global if session empty)
    top_papers_dicts: list[dict] = []
    _used_cache_fallback = False
    try:
        top_papers_dicts = get_top_papers_for_session(limit=8, session_id=session_id)
        if not top_papers_dicts:
            top_papers_dicts = get_top_papers_for_session(limit=8, global_memory=True)
            # Signal that new APIs returned nothing and we're serving stale cache
            if top_papers_dicts and not scored:
                _used_cache_fallback = True
    except Exception as exc:
        failed_stage = failed_stage or "top_paper_retrieval"
        errors.append(f"Top paper retrieval failed: {exc}")

    # 7. Claim extraction from top 3 papers
    claim_maps: list[ClaimEvidenceMap] = []
    if top_papers_dicts:
        try:
            claim_maps = _extract_top_paper_claims(top_papers_dicts, cap=3)
        except Exception as exc:
            errors.append(f"Claim extraction failed: {exc}")

    # 8. Rich gap analysis
    gap_raw: dict = {}
    gap_obj: ResearchGapCandidate | None = None
    gap_candidate_str = ""
    if top_papers_dicts:
        try:
            gap_raw = generate_research_gap_analysis(top_papers_dicts, profile, user_input)
            gap_obj = _build_rich_gap(gap_raw)
            gap_candidate_str = gap_obj.gap_statement
        except Exception as exc:
            errors.append(f"Gap analysis failed: {exc}")

    # 9. Opportunity map (Python-level, no extra LLM)
    opportunity_map = _build_opportunity_map(top_papers_dicts)

    # 10. Weekly brief
    try:
        brief_path = generate_weekly_brief_if_requested(user_input, top_papers_dicts, profile)
        if brief_path:
            report_paths.append(brief_path)
    except Exception as exc:
        errors.append(f"Weekly brief failed: {exc}")

    # 11. Build verifier package
    recommended_actions = _build_recommended_actions(
        top_papers_dicts, gap_obj, report_paths, errors
    )
    claims_for_verification = _build_verifier_package(claim_maps, gap_obj, recommended_actions)

    # 12. Findings and quality
    findings = [
        f"Session ID: {session_id}",
        f"Queries used: {', '.join(flat_queries[:5])}",
        f"Papers discovered: {len(papers)}, scored: {len(scored)}, retrieved: {len(top_papers_dicts)}",
    ]
    if gap_candidate_str:
        findings.append(f"Gap candidate: {gap_candidate_str[:120]}")
    if gap_raw.get("what_is_not_new"):
        findings.append(f"Already known: {str(gap_raw['what_is_not_new'])[:120]}")

    evidence_quality = _compute_evidence_quality(top_papers_dicts)
    if _used_cache_fallback:
        confidence = "low"
    else:
        confidence = "high" if len(top_papers_dicts) >= 5 else ("medium" if top_papers_dicts else "low")

    grant_angles: list[str] = []
    if gap_raw.get("proposal_angle") or gap_raw.get("possible_grant_angle"):
        grant_angles.append(gap_raw.get("proposal_angle") or gap_raw.get("possible_grant_angle", ""))
    if gap_raw.get("industry_angle"):
        grant_angles.append(f"Industry: {gap_raw['industry_angle']}")

    summary = (
        f"Literature scan complete. {len(papers)} papers discovered, "
        f"{len(scored)} scored, {len(top_papers_dicts)} retrieved. "
        f"Evidence quality: {evidence_quality}. "
        f"Session: {session_id}."
    )
    if errors:
        summary += f" Warnings: {len(errors)}."

    result = ResearchScoutOutput(
        mode="literature_scan",
        summary=summary,
        opportunity_map=opportunity_map,
        top_papers=_format_top_papers(top_papers_dicts),
        claim_evidence_map=claim_maps,
        research_gap_candidates=[gap_obj] if gap_obj else [],
        research_gap_candidate=gap_candidate_str,
        novelty_risks=[gap_raw.get("what_is_not_new", "")][:2] if gap_raw else [],
        methodology_risks=[gap_raw.get("risks_or_weaknesses", "")][:2] if gap_raw else [],
        grant_angles=grant_angles,
        collaboration_targets=(
            [gap_raw.get("collaboration_angle", "")] if gap_raw.get("collaboration_angle") else []
        ),
        findings=findings,
        risks=errors[:5],
        recommended_actions=recommended_actions,
        queries_used=flat_queries,
        search_queries=flat_queries,
        queries_recommended_next=_suggest_followup_queries(gap_raw, profile),
        confidence=confidence,
        evidence_quality=evidence_quality,
        requires_scientific_verification=True,
        literature_scan_used=True,
        claims_for_verification=claims_for_verification,
        partial_results=bool(failed_stage) or _used_cache_fallback,
        failed_stage=failed_stage,
        recovery_action="retry_search" if failed_stage == "paper_discovery" else "",
        report_paths=report_paths,
    )
    return result.model_dump()


def _build_recommended_actions(
    top_papers: list[dict],
    gap: ResearchGapCandidate | None,
    report_paths: list[str],
    errors: list[str],
) -> list[str]:
    actions: list[str] = []
    grant_papers = [p for p in top_papers if p.get("recommended_action") == "use_for_grant"]
    if grant_papers:
        actions.append(
            f"Review {len(grant_papers)} grant-relevant paper(s) for proposal framing."
        )
    if gap and gap.gap_statement:
        actions.append("Use gap candidate as the central claim in your next proposal draft.")
    if gap and gap.what_is_not_new:
        actions.append(
            f"Address prior art before claiming novelty: {gap.what_is_not_new[:100]}"
        )
    if gap and gap.minimum_evidence_needed:
        actions.append(
            f"Gather minimum evidence: {'; '.join(gap.minimum_evidence_needed[:2])}"
        )
    actions.append("Run Scientific Verifier on gap claims and paper commentaries.")
    if report_paths:
        actions.append(f"See saved reports: {', '.join(report_paths)}")
    if errors:
        actions.append(f"Note: {len(errors)} pipeline warning(s) — check partial_results.")
    return actions[:8]


def _suggest_followup_queries(gap_raw: dict, profile: dict) -> list[str]:
    queries: list[str] = []
    if gap_raw.get("possible_research_question"):
        q = str(gap_raw["possible_research_question"])[:80]
        queries.append(q)
    topics = profile.get("research_topics", [])
    for t in topics[:2]:
        queries.append(f"{t} review 2023 2024")
    return queries[:4]


# ---------------------------------------------------------------------------
# Mode: gap_analysis
# ---------------------------------------------------------------------------

GAP_ANALYSIS_SYSTEM_PROMPT = """\
You are the AURA Research Scout in gap analysis mode.
Your job is to deeply analyse the provided top papers and identify ALL significant research gaps.

Return strict JSON:
{
  "summary": "2-3 sentence synthesis of the gap landscape",
  "primary_gap": {
    "gap_statement": "...",
    "what_is_not_new": "...",
    "minimum_evidence_needed": [],
    "proposal_angle": "...",
    "paper_angle": "...",
    "risk_level": "low | medium | high",
    "supporting_papers": [],
    "contradicting_or_overlap_papers": []
  },
  "secondary_gaps": [
    {"gap_statement": "...", "risk_level": "...", "proposal_angle": "..."}
  ],
  "grant_angles": [],
  "kill_criteria": [],
  "recommended_actions": [],
  "confidence": "low | medium | high"
}

Do NOT invent papers. Only reference papers provided.
what_is_not_new is mandatory."""


def _run_gap_analysis(user_input: str, context: dict) -> dict:
    from integrations.research_evolution import get_top_papers_for_session
    from integrations.research_evolution.profile import load_research_profile

    errors: list[str] = []
    session_id = _make_session_id(user_input)

    try:
        profile = load_research_profile()
    except Exception as exc:
        profile = {}
        errors.append(f"Profile load: {exc}")

    top_papers_dicts: list[dict] = []
    try:
        top_papers_dicts = get_top_papers_for_session(limit=10, session_id=session_id)
        if not top_papers_dicts:
            top_papers_dicts = get_top_papers_for_session(limit=10, global_memory=True)
    except Exception as exc:
        errors.append(f"Paper retrieval: {exc}")

    if not top_papers_dicts:
        return ResearchScoutOutput(
            mode="gap_analysis",
            summary="No papers available for gap analysis. Run a literature scan first.",
            confidence="low",
            partial_results=True,
            failed_stage="top_paper_retrieval",
            recovery_action="retry_search",
            risks=errors,
        ).model_dump()

    paper_summaries = "\n".join(
        f"{i}. [{p.get('source','?')}] {p.get('title','?')}"
        f" (score={p.get('total_score',0):.2f}) — {(p.get('agent_commentary','') or '')[:150]}"
        for i, p in enumerate(top_papers_dicts[:8], 1)
    )
    user_prompt = (
        f"User context: {user_input}\n\n"
        f"Profile topics: {', '.join(profile.get('research_topics', [])[:6])}\n\n"
        f"Top papers:\n{paper_summaries}\n\n"
        "Identify all gaps and return strict JSON."
    )
    try:
        raw = ask_json(GAP_ANALYSIS_SYSTEM_PROMPT, user_prompt, temperature=0.15)
    except Exception as exc:
        raw = {}
        errors.append(f"Gap LLM failed: {exc}")

    primary = raw.get("primary_gap", {})
    secondary = raw.get("secondary_gaps", [])

    primary_obj = ResearchGapCandidate(
        gap_statement=primary.get("gap_statement", ""),
        supporting_papers=primary.get("supporting_papers", []),
        contradicting_or_overlap_papers=primary.get("contradicting_or_overlap_papers", []),
        what_is_not_new=primary.get("what_is_not_new", ""),
        minimum_evidence_needed=primary.get("minimum_evidence_needed", []),
        proposal_angle=primary.get("proposal_angle", ""),
        paper_angle=primary.get("paper_angle", ""),
        risk_level=primary.get("risk_level", "medium"),
    )
    secondary_objs = [
        ResearchGapCandidate(
            gap_statement=s.get("gap_statement", ""),
            proposal_angle=s.get("proposal_angle", ""),
            risk_level=s.get("risk_level", "medium"),
        )
        for s in (secondary or [])[:3]
    ]

    return ResearchScoutOutput(
        mode="gap_analysis",
        summary=raw.get("summary", f"Gap analysis over {len(top_papers_dicts)} papers."),
        top_papers=_format_top_papers(top_papers_dicts),
        research_gap_candidates=[primary_obj] + secondary_objs,
        research_gap_candidate=primary_obj.gap_statement,
        grant_angles=raw.get("grant_angles", []),
        kill_criteria=raw.get("kill_criteria", []),
        recommended_actions=raw.get("recommended_actions", []),
        findings=[
            f"Primary gap: {primary_obj.gap_statement[:120]}",
            f"Already known: {primary_obj.what_is_not_new[:120]}",
            f"Secondary gaps found: {len(secondary_objs)}",
        ],
        risks=errors,
        confidence=raw.get("confidence", "medium"),
        evidence_quality=_compute_evidence_quality(top_papers_dicts),
        requires_scientific_verification=True,
        literature_scan_used=True,
        partial_results=bool(errors),
    ).model_dump()


# ---------------------------------------------------------------------------
# Mode: grant_opportunity
# ---------------------------------------------------------------------------

GRANT_OPPORTUNITY_PROMPT = """\
You are the AURA Research Scout in grant opportunity mode.
Your role is to identify the strongest grant-fundable angle from the provided papers and profile.

Return strict JSON:
{
  "summary": "...",
  "primary_grant_angle": "Clear 2-sentence grant framing",
  "secondary_grant_angles": [],
  "key_claims": ["Claims that would convince a grant panel"],
  "evidence_supporting_claims": ["Which papers support each claim"],
  "gaps_to_fill": ["What experiments are still needed"],
  "reviewer_objections": ["Likely objections from grant reviewers"],
  "collaboration_needed": ["Specific collaborator profiles"],
  "industry_relevance": "...",
  "timeline_estimate": "...",
  "kill_criteria": [],
  "grant_angles": [],
  "recommended_actions": [],
  "confidence": "low | medium | high"
}

Be realistic. Do not overstate the readiness of the work.
Reviewer objections are mandatory — include at least 3."""


def _run_grant_opportunity(user_input: str, context: dict) -> dict:
    from integrations.research_evolution import get_top_papers_for_session
    from integrations.research_evolution.profile import load_research_profile

    errors: list[str] = []
    session_id = _make_session_id(user_input)

    try:
        profile = load_research_profile()
    except Exception as exc:
        profile = {}
        errors.append(f"Profile load: {exc}")

    top_papers_dicts: list[dict] = []
    try:
        top_papers_dicts = get_top_papers_for_session(limit=10, session_id=session_id)
        if not top_papers_dicts:
            top_papers_dicts = get_top_papers_for_session(limit=10, global_memory=True)
    except Exception as exc:
        errors.append(f"Paper retrieval: {exc}")

    grant_papers = [p for p in top_papers_dicts if p.get("recommended_action") == "use_for_grant"]
    pool = grant_papers[:8] or top_papers_dicts[:8]

    if not pool:
        return ResearchScoutOutput(
            mode="grant_opportunity",
            summary="No papers available. Run a literature scan first.",
            confidence="low",
            partial_results=True,
            failed_stage="top_paper_retrieval",
            recovery_action="retry_search",
            risks=errors,
        ).model_dump()

    paper_summaries = "\n".join(
        f"{i}. {p.get('title','?')} (score={p.get('total_score',0):.2f}) — {(p.get('agent_commentary','') or '')[:150]}"
        for i, p in enumerate(pool, 1)
    )
    user_prompt = (
        f"User context: {user_input}\n\n"
        f"Profile topics: {', '.join(profile.get('research_topics', [])[:6])}\n\n"
        f"Top papers (grant-relevant):\n{paper_summaries}\n\n"
        "Identify the strongest grant opportunity and return strict JSON."
    )
    try:
        raw = ask_json(GRANT_OPPORTUNITY_PROMPT, user_prompt, temperature=0.15)
    except Exception as exc:
        raw = {}
        errors.append(f"Grant LLM failed: {exc}")

    return ResearchScoutOutput(
        mode="grant_opportunity",
        summary=raw.get("summary", f"Grant analysis over {len(pool)} papers."),
        top_papers=_format_top_papers(pool),
        grant_angles=raw.get("grant_angles") or [raw.get("primary_grant_angle", "")],
        kill_criteria=raw.get("kill_criteria", []),
        recommended_actions=raw.get("recommended_actions", []),
        findings=(
            [f"Primary grant angle: {raw.get('primary_grant_angle', '')[:120]}"]
            + [f"Objection: {o}" for o in raw.get("reviewer_objections", [])[:3]]
        ),
        risks=errors,
        methodology_risks=raw.get("reviewer_objections", [])[:4],
        collaboration_targets=raw.get("collaboration_needed", []),
        confidence=raw.get("confidence", "medium"),
        evidence_quality=_compute_evidence_quality(pool),
        requires_scientific_verification=True,
        literature_scan_used=True,
        partial_results=bool(errors),
    ).model_dump()


# ---------------------------------------------------------------------------
# Phase 2 stubs
# ---------------------------------------------------------------------------

def _run_paper_intake(user_input: str, context: dict) -> dict:
    return ResearchScoutOutput(
        mode="paper_intake",
        summary="Paper intake mode is planned for Phase 2.",
        confidence="low",
        partial_results=True,
        failed_stage="not_implemented",
        recovery_action="manual_review",
    ).model_dump()


def _run_trend_monitor(user_input: str, context: dict) -> dict:
    return ResearchScoutOutput(
        mode="trend_monitor",
        summary="Trend monitor mode is planned for Phase 2.",
        confidence="low",
        partial_results=True,
        failed_stage="not_implemented",
        recovery_action="manual_review",
    ).model_dump()


def _run_reviewer_attack_scan(user_input: str, context: dict) -> dict:
    return ResearchScoutOutput(
        mode="reviewer_attack_scan",
        summary="Reviewer attack scan is planned for Phase 2.",
        confidence="low",
        partial_results=True,
        failed_stage="not_implemented",
        recovery_action="manual_review",
    ).model_dump()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_MODE_DISPATCH = {
    "ideation":           _run_ideation,
    "literature_scan":    _run_literature_scan,
    "gap_analysis":       _run_gap_analysis,
    "grant_opportunity":  _run_grant_opportunity,
    "paper_intake":       _run_paper_intake,
    "trend_monitor":      _run_trend_monitor,
    "reviewer_attack_scan": _run_reviewer_attack_scan,
}


def run(user_input: str, context: dict, mode: str = "ideation") -> dict:
    resolved = _resolve_mode(user_input, mode)
    handler = _MODE_DISPATCH.get(resolved, _run_ideation)
    try:
        return handler(user_input, context)
    except Exception as exc:
        return ResearchScoutOutput(
            mode=resolved,
            summary=f"Research Scout failed in mode '{resolved}': {exc}",
            confidence="low",
            partial_results=True,
            failed_stage="unhandled_exception",
            recovery_action="manual_review",
            risks=[str(exc)],
        ).model_dump()
