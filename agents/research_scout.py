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
    deep_research     Full deep research capability (new)
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timezone
from typing import Any

from core.llm import ask_json
from core.memory import retrieve_relevant_memory
from core.normalization import ensure_str_list as _coerce_str_list
from core.schemas import (
    ClaimEvidenceMap,
    OpportunityCluster,
    ResearchGapCandidate,
    ResearchScoutOutput,
    TopPaper,
)
import config

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
    "deep_research": [
        "deep research", "deep dive", "thorough research", "comprehensive",
        "in-depth", "detailed report", "exhaustive",
    ],
}

_ALL_KNOWN_MODES = set(_MODE_KEYWORDS) | {"paper_intake", "trend_monitor", "reviewer_attack_scan"}


def _resolve_mode(user_input: str, governor_mode: str) -> str:
    """Resolve the Scout mode, honouring an EXPLICIT Governor assignment.

    Phase 2 (goal A) — cross-agent mode consistency
    ------------------------------------------------
    Previously user-phrasing inference always won, so the Governor could
    assign ``deep_research`` while the Scout silently ran ``gap_analysis``
    (the two modules iterate different keyword orderings).  That drift made
    orchestration metadata disagree with what the Scout actually executed.

    New contract:
      * If the Governor explicitly assigned a *real* mode (any known mode
        other than the ``ideation`` default / ``none`` / empty sentinel),
        the Scout MUST honour it — no re-inference.
      * Only when no explicit mode was provided (``""`` / ``"none"`` /
        the bare ``ideation`` default) does the Scout infer from the
        user's phrasing, falling back to ``ideation``.

    ``ideation`` is treated as the non-explicit default because the
    orchestrator + registry collapse a missing / ``none`` Governor mode to
    ``ideation`` before the Scout sees it, so it cannot be distinguished
    from an explicit ideation choice — and inference is the safe behaviour
    for that ambiguous case.
    """
    gm = (governor_mode or "").strip().lower()
    # Honour an explicit, real Governor-assigned mode.
    if gm in _ALL_KNOWN_MODES and gm != "ideation":
        return gm
    # No explicit mode → infer from the user's phrasing.
    lower = user_input.lower()
    for mode, keywords in _MODE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return mode
    return "ideation"


def _make_session_id(user_input: str) -> str:
    today = date.today().isoformat()
    return hashlib.sha256(f"{user_input}{today}".encode()).hexdigest()[:10]


# ---------------------------------------------------------------------------
# Session chaining helpers — lineage-safe (defect 13)
# ---------------------------------------------------------------------------
# Previously a single global file ``last_scan_session.json`` recorded the
# most recent literature scan; gap_analysis and grant_opportunity loaded that
# session unconditionally, even when the user's current request was about an
# unrelated topic.  That allowed "the previous TADF literature scan" to be
# attached to "Identify the gap in the lithium-ion battery field".
#
# Phase 3 design:
#   * The session store now keeps a SHORT history of recent scans, each
#     tagged with its originating ``user_input`` and a small keyword set.
#   * Gap / grant modes pass their current ``user_input`` to
#     ``_find_matching_scan_session`` which only returns a session ID when
#     the keywords overlap meaningfully.  Otherwise gap / grant analysis
#     falls back to ``_make_session_id(user_input)`` and hits the global
#     paper memory (or returns the explicit "no scan available" message).
#   * Tests can also force-attach a session via
#     ``context["literature_scan_session_id"]`` (explicit override > heuristic).

_SCAN_SESSION_HISTORY_PATH = config.BASE_DIR / "data" / "scan_session_history.json"
_SCAN_HISTORY_LIMIT = 12
# Trivial stop-words removed before keyword matching.
_TOPIC_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "with",
    "this", "that", "these", "those", "is", "are", "was", "were", "be",
    "find", "search", "papers", "paper", "scan", "literature", "recent",
    "latest", "review", "analysis", "analyze", "analyse", "explore",
    "identify", "show", "list", "give", "me", "my", "i", "we",
})


def _topic_keywords(text: str) -> set[str]:
    """Extract a small set of normalised content keywords from *text*.

    Includes a tiny plural-stripping step so "emitters" and "emitter"
    collapse to the same keyword — necessary so a literature_scan on
    "TADF red emitters" can be reused by a gap analysis phrased as
    "gap in TADF emitter research".
    """
    import re
    if not text:
        return set()
    tokens = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    out: set[str] = set()
    for t in tokens:
        if t in _TOPIC_STOPWORDS:
            continue
        # Crude singularisation: strip trailing "s" / "es" on long-enough tokens.
        if len(t) > 4 and t.endswith("es") and not t.endswith("ees"):
            t = t[:-2]
        elif len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.add(t)
    return out


def _save_scan_session_id(session_id: str, user_input: str = "") -> None:
    """Append a session record to the history.

    Defect 13: the record carries the originating user_input + keywords so
    later gap/grant calls can decide whether reuse is safe.
    """
    _SCAN_SESSION_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    history = _read_scan_session_history()
    history = [h for h in history if h.get("session_id") != session_id]
    history.append({
        "session_id": session_id,
        "user_input": (user_input or "")[:400],
        "keywords": sorted(_topic_keywords(user_input))[:25],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    history = history[-_SCAN_HISTORY_LIMIT:]
    _SCAN_SESSION_HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False), encoding="utf-8",
    )


def _read_scan_session_history() -> list[dict]:
    if not _SCAN_SESSION_HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(_SCAN_SESSION_HISTORY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        # Backward-compat: tolerate the old single-record format.
        if isinstance(data, dict) and data.get("session_id"):
            return [data]
    except Exception:
        return []
    return []


def _find_matching_scan_session(user_input: str, *, min_overlap: int = 2) -> str | None:
    """Return a session_id from the history whose user_input overlaps the
    current ``user_input`` by at least ``min_overlap`` keywords.

    Returns ``None`` when no plausible match is found — the caller MUST
    treat that as "no scan available" rather than silently reusing the
    most recent global scan.
    """
    current = _topic_keywords(user_input)
    if not current:
        return None
    best: tuple[int, str, str] | None = None   # (overlap, session_id, created_at)
    for record in _read_scan_session_history():
        kws = set(record.get("keywords") or [])
        overlap = len(current & kws)
        if overlap < min_overlap:
            continue
        created = record.get("created_at", "")
        candidate = (overlap, record.get("session_id", ""), created)
        if best is None or candidate > best:
            best = candidate
    if best is None:
        return None
    return best[1] or None


def _resolve_session_for_followup(user_input: str, context: dict) -> tuple[str | None, str]:
    """Pick a session_id for gap / grant analysis.

    Priority:
      1. Explicit ``context["literature_scan_session_id"]`` (caller override).
      2. Lineage-safe keyword match against the scan history.
      3. ``None`` — caller should fall back to global paper memory.

    Returns ``(session_id, source_label)`` where source_label is one of
    ``"context_override" | "lineage_match" | "no_match"`` so callers can
    surface lineage in the output.
    """
    override = context.get("literature_scan_session_id") if isinstance(context, dict) else None
    if isinstance(override, str) and override.strip():
        return override.strip(), "context_override"
    matched = _find_matching_scan_session(user_input)
    if matched:
        return matched, "lineage_match"
    return None, "no_match"


# --- Backward-compat shim ---------------------------------------------------
# Some legacy tests call ``_load_scan_session_id()`` directly.  We keep the
# name but make it deliberately INERT — it always returns None.  Defect 13
# requires callers to use ``_resolve_session_for_followup`` instead.

def _load_scan_session_id() -> str | None:
    """Deprecated — always returns None.  Use ``_resolve_session_for_followup``
    (defect 13) for lineage-safe session reuse.
    """
    return None


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
        print("[Research Scout] Planning queries via LLM ...", flush=True)
        raw = ask_json(QUERY_PLANNER_PROMPT, user_prompt, temperature=0.15)
        if isinstance(raw, dict) and "broad_queries" in raw:
            return raw
        return fallback
    except Exception:
        return fallback


def _flatten_queries(plan: dict, max_total: int = 10) -> list[str]:
    """Flatten a planner's bucketed queries into a single ordered list.

    Defect 12: previously this iterated ``plan.get(key, [])`` directly,
    which meant:
      * a string value (LLM mistake) was iterated CHARACTER-BY-CHARACTER
        and produced 50+ single-letter "queries",
      * non-string list members (dicts, ints, None) crashed ``q.strip()``.

    The function now validates that:
      * ``plan`` is a dict,
      * each bucket is a list (a bare string is wrapped into ``[string]``,
        anything else is dropped),
      * each list item is a non-empty string after stripping.

    Out-of-range / malformed members are skipped silently — the planner's
    overall LLM call already has its own fallback.
    """
    if not isinstance(plan, dict):
        return []
    seen: set[str] = set()
    flat: list[str] = []
    order = [
        "broad_queries", "mechanism_queries", "material_queries",
        "device_queries", "application_queries", "grant_angle_queries",
        "negative_control_queries",
    ]
    for key in order:
        bucket = plan.get(key, [])
        # Defect 12: protect against the LLM emitting a string instead of a list.
        if isinstance(bucket, str):
            bucket = [bucket]
        elif not isinstance(bucket, list):
            continue   # drop anything that isn't a list or string

        for raw in bucket:
            # Defect 12: protect against non-string list members.
            if not isinstance(raw, str):
                continue
            q = raw.strip()
            if not q or q in seen:
                continue
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
    print("[Research Scout] Ideation mode — analysing idea ...", flush=True)
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
        print("[Research Scout] Ideation complete.", flush=True)
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
    print("[Research Scout] Loading research profile ...", flush=True)
    try:
        profile = load_research_profile()
    except Exception as exc:
        errors.append(f"Profile load failed: {exc}")
        profile = {}
    topics: list[str] = profile.get("research_topics", ["OLED", "TADF", "organic semiconductor"])

    # 2. Plan queries
    print("[Research Scout] Planning search queries ...", flush=True)
    query_plan: dict[str, list[str]] = {}
    try:
        query_plan = _plan_queries(user_input, topics)
    except Exception as exc:
        errors.append(f"Query planner failed: {exc}")
        query_plan = {"broad_queries": topics[:4]}

    flat_queries = _flatten_queries(query_plan, max_total=10)

    # 3. Discover papers — now receives source error observability
    print(f"[Research Scout] Discovering papers ({len(flat_queries)} queries) ...", flush=True)
    papers: list[dict] = []
    detailed_source_errors: list[dict] = []
    try:
        disc_result = discover_papers(flat_queries or topics, user_input)
        papers = disc_result.get("papers", [])
        source_errors = disc_result.get("source_errors", [])
        if source_errors:
            errors.append(f"Source API failures: {len(source_errors)} records")
            # preserve structured error details for transparency
            detailed_source_errors = source_errors
    except Exception as exc:
        failed_stage = "paper_discovery"
        errors.append(f"Paper discovery failed: {exc}")

    # 4. Score papers
    if papers:
        print(f"[Research Scout] Scoring {len(papers)} papers ...", flush=True)
        scored: list[dict] = []
        try:
            scored = score_papers_integration(profile, papers)
        except Exception as exc:
            failed_stage = failed_stage or "paper_scoring"
            errors.append(f"Paper scoring failed: {exc}")
    else:
        scored = []

    # 5. Save (now returns a summary dict)
    save_summary = {}
    if scored:
        print("[Research Scout] Saving scored papers to database ...", flush=True)
        try:
            save_summary = save_scored_papers(scored, session_id=session_id)
        except Exception as exc:
            errors.append(f"Paper save failed: {exc}")

    # 6. Retrieve top papers
    print("[Research Scout] Retrieving top papers ...", flush=True)
    top_papers_dicts: list[dict] = []
    _used_cache_fallback = False
    try:
        top_papers_dicts = get_top_papers_for_session(limit=8, session_id=session_id)
        if not top_papers_dicts:
            top_papers_dicts = get_top_papers_for_session(limit=8, global_memory=True)
            if top_papers_dicts and not scored:
                _used_cache_fallback = True
    except Exception as exc:
        failed_stage = failed_stage or "top_paper_retrieval"
        errors.append(f"Top paper retrieval failed: {exc}")

    # 7. Claim extraction
    claim_maps: list[ClaimEvidenceMap] = []
    if top_papers_dicts:
        print("[Research Scout] Extracting claims from top papers ...", flush=True)
        try:
            claim_maps = _extract_top_paper_claims(top_papers_dicts, cap=3)
        except Exception as exc:
            errors.append(f"Claim extraction failed: {exc}")

    # 8. Gap analysis
    gap_raw: dict = {}
    gap_obj: ResearchGapCandidate | None = None
    gap_candidate_str = ""
    if top_papers_dicts:
        print("[Research Scout] Performing gap analysis ...", flush=True)
        try:
            gap_raw = generate_research_gap_analysis(top_papers_dicts, profile, user_input)
            gap_obj = _build_rich_gap(gap_raw)
            gap_candidate_str = gap_obj.gap_statement
        except Exception as exc:
            errors.append(f"Gap analysis failed: {exc}")

    # 9. Opportunity map
    print("[Research Scout] Building opportunity map ...", flush=True)
    opportunity_map = _build_opportunity_map(top_papers_dicts)

    # 10. Weekly brief (only when the user prompt asks for one)
    try:
        brief_path = generate_weekly_brief_if_requested(user_input, top_papers_dicts, profile)
        if brief_path:
            report_paths.append(brief_path)
    except Exception as exc:
        errors.append(f"Weekly brief failed: {exc}")

    # 10b. ALWAYS save a literature-scan report (defect: previously the
    # markdown writer only fired when the prompt contained one of four
    # magic keywords — "weekly brief" / "research brief" / "weekly
    # report" / "weekly summary".  Any other literature-scan prompt
    # produced 31+ scored papers that lived only in the SQLite DB +
    # the scrolling console output, with no human-readable artefact.
    # Now every literature_scan run writes a timestamped report.)
    try:
        scan_report_path = _save_literature_scan_report(
            user_input=user_input,
            session_id=session_id,
            top_papers=top_papers_dicts,
            gap_raw=gap_raw,
            opportunity_map=opportunity_map,
            queries_used=flat_queries,
            source_errors=detailed_source_errors,
            errors=errors,
        )
        if scan_report_path:
            report_paths.append(scan_report_path)
    except Exception as exc:
        errors.append(f"Literature-scan report save failed: {exc}")

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
    if save_summary:
        findings.append(
            f"Paper save: {save_summary.get('saved', 0)} saved, {save_summary.get('failed', 0)} failed"
        )
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
    if detailed_source_errors:
        # surface first few source errors as structured findings
        for err in detailed_source_errors[:3]:
            findings.append(
                f"Source error: {err.get('source_error', 'unknown')[:120]}"
            )

    result = ResearchScoutOutput(
        mode="literature_scan",
        summary=summary,
        opportunity_map=opportunity_map,
        top_papers=_format_top_papers(top_papers_dicts),
        claim_evidence_map=claim_maps,
        research_gap_candidates=[gap_obj] if gap_obj else [],
        research_gap_candidate=gap_candidate_str,
        # Defensive flattening: ``gap_raw.get(...)`` may return either a
        # string or a list (the LLM is inconsistent).  Wrapping a list
        # in ``[that_list]`` produces a NESTED list and fails Pydantic's
        # ``list[str]`` validation — which blanks the entire Scout
        # output and reaches the China architect as zero evidence.
        # ``_coerce_str_list`` flattens either shape to a clean
        # ``list[str]``.
        novelty_risks=_coerce_str_list(
            (gap_raw or {}).get("what_is_not_new"), max_items=2,
        ),
        methodology_risks=_coerce_str_list(
            (gap_raw or {}).get("risks_or_weaknesses"), max_items=2,
        ),
        grant_angles=grant_angles,
        collaboration_targets=_coerce_str_list(
            (gap_raw or {}).get("collaboration_angle"), max_items=4,
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
    # ---- Persist session ID + user_input for lineage-safe chaining (defect 13)
    try:
        _save_scan_session_id(session_id, user_input=user_input)
    except Exception:
        pass
    print("[Research Scout] Literature scan completed.", flush=True)
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


def _save_literature_scan_report(
    *,
    user_input: str,
    session_id: str,
    top_papers: list[dict],
    gap_raw: dict | None,
    opportunity_map,
    queries_used: list[str],
    source_errors: list[dict],
    errors: list[str],
) -> str:
    """Write a human-readable literature-scan report to ``reports/``.

    Always written for every literature_scan run (regardless of magic
    keywords in the prompt) so the user has a durable artefact
    summarising the 5-provider search (OpenAlex / arXiv / Crossref /
    Semantic Scholar / Europe PMC).

    Returns the relative path string, or ``""`` if writing failed.
    """
    from datetime import datetime, timezone
    import config as _config
    from core.path_safety import unique_filename_stamp

    # Phase 2 (goal F): microsecond + UUID suffix so two scans in the same
    # second do not overwrite each other.
    ts = unique_filename_stamp(utc=True)
    out_dir = _config.REPORT_DIR / "literature_scans"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"literature_scan_{ts}.md"

    # Provider coverage
    provider_counts: dict[str, int] = {}
    for p in top_papers or []:
        if isinstance(p, dict):
            src = (p.get("source") or "unknown").lower()
            provider_counts[src] = provider_counts.get(src, 0) + 1

    L: list[str] = []
    L.append(f"# Literature Scan — {(user_input or '(no query)').strip()[:160]}\n")
    L.append(f"_Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')} · "
             f"session: `{session_id}`_\n")
    L.append("## Summary\n")
    L.append(f"- **Papers retrieved:** {len(top_papers)}")
    if provider_counts:
        L.append("- **Provider coverage:** "
                 + ", ".join(f"{k}={v}" for k, v in sorted(provider_counts.items())))
    else:
        L.append("- **Provider coverage:** _(none — all 5 providers returned zero papers)_")
    L.append(f"- **Queries issued:** {len(queries_used)}")
    if errors:
        L.append(f"- **Warnings:** {len(errors)}")
    L.append("")

    if queries_used:
        L.append("## Queries used\n")
        for q in queries_used:
            L.append(f"- `{q}`")
        L.append("")

    if top_papers:
        L.append("## Top papers (scored)\n")
        for i, p in enumerate(top_papers[:25], start=1):
            if not isinstance(p, dict):
                continue
            title = (p.get("title") or "(untitled)").strip()
            src = p.get("source") or "?"
            year = (p.get("published_date") or "")[:4]
            doi = p.get("doi") or ""
            url = p.get("url") or ""
            score = p.get("score") or p.get("relevance_score") or ""
            link = f"DOI: {doi}" if doi else (f"URL: {url}" if url else "")
            L.append(f"### [{i}] {title}")
            meta = f"- **Source:** {src}" + (f" · {year}" if year else "")
            if score:
                meta += f" · **Score:** {score}"
            L.append(meta)
            if link:
                L.append(f"- {link}")
            abstract = (p.get("abstract") or "").strip()
            if abstract:
                L.append(f"- **Abstract:** {abstract[:600]}{'…' if len(abstract) > 600 else ''}")
            L.append("")
    else:
        L.append("## Top papers\n")
        L.append("_(none returned by the scoring stage)_\n")

    if gap_raw:
        L.append("## Gap analysis\n")
        for key, label in [
            ("possible_research_question", "Possible research question"),
            ("what_is_known", "What is known"),
            ("what_is_not_new", "What is NOT new"),
            ("what_is_missing", "What is missing"),
            ("risks_or_weaknesses", "Risks / weaknesses"),
            ("collaboration_angle", "Collaboration angle"),
            ("primary_grant_angle", "Primary grant angle"),
        ]:
            v = gap_raw.get(key)
            if v:
                if isinstance(v, list):
                    L.append(f"**{label}:**")
                    for item in v:
                        L.append(f"- {item}")
                else:
                    L.append(f"**{label}:** {v}")
                L.append("")

    if opportunity_map:
        L.append("## Opportunity map\n")
        try:
            for cluster in (opportunity_map or [])[:8]:
                # OpportunityCluster Pydantic; tolerate dict too.
                name = getattr(cluster, "cluster_name", None) or \
                       (cluster.get("cluster_name") if isinstance(cluster, dict) else "")
                summary = getattr(cluster, "summary", None) or \
                          (cluster.get("summary") if isinstance(cluster, dict) else "")
                if name:
                    L.append(f"- **{name}** — {summary or ''}")
        except Exception:
            pass
        L.append("")

    if source_errors:
        L.append("## Provider errors\n")
        for err in source_errors[:10]:
            if isinstance(err, dict):
                L.append(f"- {err.get('source_error', str(err))}")
            else:
                L.append(f"- {err}")
        L.append("")

    if errors:
        L.append("## Warnings\n")
        for w in errors[:20]:
            L.append(f"- {w}")
        L.append("")

    try:
        md_path.write_text("\n".join(L), encoding="utf-8")
        return str(md_path.relative_to(_config.BASE_DIR))
    except Exception:
        return ""


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
    print("[Research Scout] Gap analysis mode — retrieving top papers ...", flush=True)
    from integrations.research_evolution import get_top_papers_for_session
    from integrations.research_evolution.profile import load_research_profile

    errors: list[str] = []
    # Defect 13: lineage-safe session resolution.  We only inherit a prior
    # literature_scan session when it matches the current user_input or the
    # caller explicitly attached one in context.
    chained_session_id, session_source = _resolve_session_for_followup(user_input, context)
    session_id = chained_session_id or _make_session_id(user_input)

    try:
        profile = load_research_profile()
    except Exception as exc:
        profile = {}
        errors.append(f"Profile load: {exc}")

    top_papers_dicts: list[dict] = []
    try:
        top_papers_dicts = get_top_papers_for_session(limit=10, session_id=session_id)
        if not top_papers_dicts and chained_session_id is not None:
            # Lineage hit but produced no rows — try the global memory only
            # as a last resort and record the fallback.
            top_papers_dicts = get_top_papers_for_session(limit=10, global_memory=True)
            errors.append(
                f"Lineage session {chained_session_id} returned no papers; "
                "fell back to global memory."
            )
        elif not top_papers_dicts:
            # No prior scan we trust — surface this explicitly rather than
            # silently scraping unrelated old sessions.
            errors.append(
                "No matching prior literature_scan session for this topic; "
                "global paper memory used as fallback only."
            )
            top_papers_dicts = get_top_papers_for_session(limit=10, global_memory=True)
    except Exception as exc:
        errors.append(f"Paper retrieval: {exc}")

    if not top_papers_dicts:
        # Defect 3: failure paths must NOT inherit the schema's "moderate"
        # default — set evidence_quality explicitly.
        return ResearchScoutOutput(
            mode="gap_analysis",
            summary=(
                "No papers available for gap analysis. Run a literature "
                "scan on this topic first."
            ),
            confidence="low",
            evidence_quality="none",
            partial_results=True,
            failed_stage="top_paper_retrieval",
            recovery_action="retry_search",
            risks=errors + [f"session_source={session_source}"],
        ).model_dump()

    print("[Research Scout] Running gap analysis LLM ...", flush=True)
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

    print("[Research Scout] Gap analysis completed.", flush=True)
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
    print("[Research Scout] Grant opportunity mode — retrieving top papers ...", flush=True)
    from integrations.research_evolution import get_top_papers_for_session
    from integrations.research_evolution.profile import load_research_profile

    errors: list[str] = []
    # Defect 13: lineage-safe session resolution (see _run_gap_analysis).
    chained_session_id, session_source = _resolve_session_for_followup(user_input, context)
    session_id = chained_session_id or _make_session_id(user_input)

    try:
        profile = load_research_profile()
    except Exception as exc:
        profile = {}
        errors.append(f"Profile load: {exc}")

    top_papers_dicts: list[dict] = []
    try:
        top_papers_dicts = get_top_papers_for_session(limit=10, session_id=session_id)
        if not top_papers_dicts and chained_session_id is not None:
            top_papers_dicts = get_top_papers_for_session(limit=10, global_memory=True)
            errors.append(
                f"Lineage session {chained_session_id} returned no papers; "
                "fell back to global memory."
            )
        elif not top_papers_dicts:
            errors.append(
                "No matching prior literature_scan session for this topic; "
                "global paper memory used as fallback only."
            )
            top_papers_dicts = get_top_papers_for_session(limit=10, global_memory=True)
    except Exception as exc:
        errors.append(f"Paper retrieval: {exc}")

    grant_papers = [p for p in top_papers_dicts if p.get("recommended_action") == "use_for_grant"]
    pool = grant_papers[:8] or top_papers_dicts[:8]

    if not pool:
        # Defect 3: failure paths must NOT inherit the schema's "moderate"
        # default — set evidence_quality explicitly.
        return ResearchScoutOutput(
            mode="grant_opportunity",
            summary="No papers available. Run a literature scan first.",
            confidence="low",
            evidence_quality="none",
            partial_results=True,
            failed_stage="top_paper_retrieval",
            recovery_action="retry_search",
            risks=errors,
        ).model_dump()

    print("[Research Scout] Running grant opportunity LLM ...", flush=True)
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

    print("[Research Scout] Grant analysis completed.", flush=True)
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
        # Same defensive coercion as the literature_scan path: the LLM
        # may return nested lists for ``reviewer_objections``, which
        # would break Pydantic's ``list[str]`` validation.
        methodology_risks=_coerce_str_list(
            raw.get("reviewer_objections"), max_items=4,
        ),
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
    # Defect 3: not-implemented stubs MUST surface evidence_quality="none",
    # never let the schema's "moderate" default leak through.
    return ResearchScoutOutput(
        mode="paper_intake",
        summary="Paper intake mode is planned for Phase 2.",
        confidence="low",
        evidence_quality="none",
        partial_results=True,
        failed_stage="not_implemented",
        recovery_action="manual_review",
    ).model_dump()


def _run_trend_monitor(user_input: str, context: dict) -> dict:
    return ResearchScoutOutput(
        mode="trend_monitor",
        summary="Trend monitor mode is planned for Phase 2.",
        confidence="low",
        evidence_quality="none",
        partial_results=True,
        failed_stage="not_implemented",
        recovery_action="manual_review",
    ).model_dump()


def _run_reviewer_attack_scan(user_input: str, context: dict) -> dict:
    return ResearchScoutOutput(
        mode="reviewer_attack_scan",
        summary="Reviewer attack scan is planned for Phase 2.",
        confidence="low",
        evidence_quality="none",
        partial_results=True,
        failed_stage="not_implemented",
        recovery_action="manual_review",
    ).model_dump()


# ---------------------------------------------------------------------------
# Deep Research mode
# ---------------------------------------------------------------------------

def _run_deep_research(user_input: str, context: dict) -> dict:
    """Run the Deep Research mission and return a validated ResearchScoutOutput.

    Phase 3 fixes:
      * Defect 4: mock-mode evidence cannot be classified as strong/high.
      * Defect 9: result is normalised through ``ResearchScoutOutput`` —
        no more raw ``deep_research_result`` injected on a bare dict.
      * Defect 11: report-generation failure propagates as
        ``partial_results=True`` + ``failed_stage="report_generation"``.
        The summary cannot claim "Deep research completed" when the
        report stage actually failed.
    """
    from qwen_evolver.deep_research.orchestrator import run_research
    from qwen_evolver.deep_research.schemas import ResearchMission, ResearchDepth

    print("[Research Scout] Deep Research mode activated.", flush=True)
    depth_raw = (context.get("requested_depth") or "standard").lower()
    try:
        depth = ResearchDepth(depth_raw)
    except ValueError:
        depth = ResearchDepth.standard

    mission = ResearchMission(
        original_user_request=user_input,
        interpreted_objective=user_input,
        requested_depth=depth,
    )
    result = run_research(mission)
    if not isinstance(result, dict):
        result = {}

    # ---- Derive quality indicators ---------------------------------------
    evidence_pack = result.get("evidence_pack") or {}
    if not isinstance(evidence_pack, dict):
        evidence_pack = {}
    verification = result.get("verification") or {}
    if not isinstance(verification, dict):
        verification = {}
    sources = evidence_pack.get("sources") if isinstance(evidence_pack.get("sources"), list) else []
    source_count = len(sources)
    report_path = result.get("report_path", "") or ""

    # Defect 4: detect mock-mode from the orchestrator's propagated flags.
    mock_mode_used = bool(result.get("mock_mode_used"))
    provider_warnings = list(result.get("provider_warnings") or [])

    # Defect 11: detect report-generation failure.
    report_generation_failed = bool(result.get("report_generation_failed"))
    report_status = result.get("report_status", "")

    # Evidence-quality logic, mock-aware.
    if mock_mode_used:
        # Defect 4: mock evidence is NEVER strong, NEVER high-confidence.
        evidence_quality = "weak"
    elif source_count >= 5:
        evidence_quality = "strong"
    elif source_count >= 2:
        evidence_quality = "moderate"
    else:
        evidence_quality = "weak"

    verif_decision = (verification.get("decision") or "").strip().lower()
    if mock_mode_used:
        # Defect 4: any "approve" on mock evidence is illusory — cap at medium.
        confidence = "low"
    elif verif_decision == "approve":
        confidence = "high"
    elif verif_decision == "revise":
        confidence = "medium"
    else:
        confidence = "low"

    # Defect 11: aggregate partial / failed indicators across the run.
    partial_results = (
        source_count == 0
        or verif_decision == "human_review"
        or report_generation_failed
        or mock_mode_used
    )
    failed_stage = ""
    if report_generation_failed:
        failed_stage = "report_generation"
    elif source_count == 0:
        failed_stage = "no_sources_fetched"
    elif verif_decision == "human_review":
        failed_stage = "verification_human_review"
    elif mock_mode_used:
        failed_stage = "mock_provider_used"

    # Honest summary text: never claim "Deep research completed" when a stage
    # actually failed.
    if report_generation_failed:
        summary = (
            f"Deep research completed with report-generation FAILURE "
            f"({report_status}). Mission: {mission.mission_id}."
        )
    elif source_count == 0:
        summary = (
            f"Deep research run produced no sources (mission {mission.mission_id})."
        )
    elif mock_mode_used:
        summary = (
            f"Deep research completed using MOCK provider — results are "
            f"SYNTHETIC. Mission: {mission.mission_id}."
        )
    else:
        summary = (
            f"Deep research completed. Mission: {mission.mission_id}."
        )

    # Populate claims_for_verification from extracted evidence claims.
    evidence_claims_raw = evidence_pack.get("evidence_claims") or []
    claims_for_verification: list[str] = []
    if isinstance(evidence_claims_raw, list):
        for c in evidence_claims_raw[:12]:
            if isinstance(c, dict):
                txt = c.get("claim_text") or ""
                if txt:
                    claims_for_verification.append(txt)
            elif isinstance(c, str) and c.strip():
                claims_for_verification.append(c.strip())

    # Risks: surface provider warnings + verification risks/contradictions.
    risks: list[str] = list(provider_warnings)
    verif_risks = verification.get("risks") or []
    if isinstance(verif_risks, list):
        risks.extend(str(r) for r in verif_risks[:5] if r)
    verif_contradictions = verification.get("contradictions") or []
    if isinstance(verif_contradictions, list):
        for c in verif_contradictions[:5]:
            if c:
                risks.append(f"Verifier contradiction: {c}")
    if report_generation_failed:
        risks.append(f"Report generation failed ({report_status}).")

    findings = [
        f"Mission ID: {mission.mission_id}",
        f"Research question: {evidence_pack.get('research_question', user_input)}",
    ]

    # Defect 9: validate through Pydantic so the schema owns the contract.
    return ResearchScoutOutput(
        mode="deep_research",
        summary=summary,
        findings=findings,
        top_papers=[],
        risks=risks,
        recommended_actions=[],
        confidence=confidence,
        evidence_quality=evidence_quality,
        requires_scientific_verification=True,
        literature_scan_used=False,
        claims_for_verification=claims_for_verification,
        partial_results=partial_results,
        failed_stage=failed_stage,
        recovery_action="manual_review" if report_generation_failed else "",
        report_paths=[report_path] if report_path else [],
        deep_research_result=result,
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
    "deep_research":      _run_deep_research,
}


# ---------------------------------------------------------------------------
# Phase 4: optional local-literature folder ingestion.
# ---------------------------------------------------------------------------
# When the controller opts in (context["ask_local_folders"]=True or env var
# AURA_LOCAL_FOLDERS_ENABLED=1), the first invocation of Research Scout in
# a session asks the user once whether they want to attach a local
# literature folder.  The agent NEVER calls input() — it returns a
# ``needs_user_input`` payload that the controller must satisfy on a
# follow-up call (passing the answer in ``context["user_responses"]``).
# When ingestion is enabled, the local chunks are retrieved alongside
# normal results and surfaced in ``local_literature_evidence`` +
# ``local_document_ingestion_summary``.

def _format_local_evidence_block(
    refs: list, *, kind: str = "literature",
) -> str:
    """Render retrieved local-document excerpts into a prompt-ready block.

    Phase 2 Defect 5/6: this block is INJECTED INTO THE LLM PROMPT before
    generation so the model actually reasons over the local evidence.
    Excerpts carry safe_reference + extraction_quality so the LLM can
    cite and hedge appropriately.
    """
    if not refs:
        return ""
    header = (
        "User-supplied LOCAL LITERATURE evidence (extracted from a folder; "
        "treat as user-provided, not externally verified):"
        if kind == "literature"
        else
        "User-supplied LOCAL PATENT evidence (extracted from a folder; "
        "treat as user-provided, NOT a verified patent record):"
    )
    lines = [header]
    for i, ref in enumerate(refs, start=1):
        if hasattr(ref, "model_dump"):
            r = ref.model_dump()
        elif isinstance(ref, dict):
            r = ref
        else:
            continue
        safe = r.get("safe_reference") or r.get("file_name") or "(unknown)"
        loc = r.get("location_hint") or ""
        quality = r.get("extraction_quality") or "good"
        excerpt = (r.get("excerpt") or "")[:600]
        lines.append(
            f"\n[{i}] {safe}"
            + (f" ({loc})" if loc else "")
            + f" — extraction_quality={quality}"
        )
        if excerpt:
            lines.append(f"    {excerpt}")
    lines.append(
        "\nThese excerpts are unverified user-supplied material.  Treat "
        "them as background context.  Do NOT cite them as if they were "
        "externally verified literature."
    )
    return "\n".join(lines)


def _maybe_handle_local_folder(
    user_input: str,
    context: dict,
    *,
    agent: str,
    resolved_mode: str,
) -> tuple[dict | None, dict]:
    """Return ``(prompt_response_or_None, extras_for_context_and_output)``.

    * ``prompt_response`` is a non-None dict when the agent needs to short-
      circuit and return a ``needs_user_input`` payload to the controller.
    * ``extras`` (returned dict) carries:
        - ``local_literature_evidence``        list[dict] — retrieved refs
        - ``local_document_ingestion_summary`` dict        — for the output
        - ``local_evidence_prompt_block``      str         — for the LLM prompt
                                                              (defect 5)
    """
    from core import local_documents as ld

    if not isinstance(context, dict):
        context = {}

    session_id = context.get("session_id") or ""
    if not isinstance(session_id, str) or not session_id:
        # No session — silently disable the feature.  An orchestrator that
        # cares about local folders MUST allocate a session id.
        return None, {}

    if not ld.is_opt_in_enabled(context):
        return None, {}

    # Absorb any pre-supplied response from the controller.
    user_responses = context.get("user_responses") or {}
    if isinstance(user_responses, dict) and agent in user_responses:
        ld.absorb_user_response(session_id, agent, user_responses.get(agent))

    if ld.needs_prompt(session_id, agent):
        prompt = ld.build_prompt_request(session_id, agent).model_dump()
        # Return a short-circuit payload that the caller embeds in the
        # ResearchScoutOutput.
        return {
            "needs_user_input": prompt,
            "mode": resolved_mode,
            "summary": (
                "Research Scout paused to ask the user whether to attach "
                "a local literature folder."
            ),
            "partial_results": True,
            "failed_stage": "awaiting_user_input",
            "evidence_quality": "none",
            "confidence": "low",
        }, {}

    pref = ld.get_preference(session_id, agent)
    if pref.state != "enabled" or not pref.folder_path:
        # User declined — nothing to ingest.
        return None, {}

    try:
        summary = ld.ingest_folder(session_id, agent, pref.folder_path)
    except Exception as exc:
        # Defensive — pipeline.ingest_folder is documented as never-raises,
        # but we still fail closed.
        return None, {
            "local_literature_evidence": [],
            "local_document_ingestion_summary": {
                "used": False,
                "failure_reason": f"ingest_folder raised: {exc}",
                "partial_results": True,
            },
            "local_evidence_prompt_block": "",
        }

    refs = ld.retrieve_literature_evidence(session_id, user_input, top_k=6)
    refs_dicts = [r.model_dump() for r in refs]
    return None, {
        "local_literature_evidence": refs_dicts,
        "local_document_ingestion_summary": summary.model_dump(),
        # Defect 5: this block is the actual prompt-injection payload.
        "local_evidence_prompt_block":
            _format_local_evidence_block(refs, kind="literature"),
    }


def _maybe_attach_local_evidence_to_dict(
    base: dict,
    extras: dict,
) -> dict:
    """Merge ``local_*`` extras into a Scout output dict safely."""
    if not isinstance(base, dict) or not extras:
        return base
    base = dict(base)
    if "local_literature_evidence" in extras:
        base["local_literature_evidence"] = list(extras["local_literature_evidence"])
    if "local_document_ingestion_summary" in extras:
        base["local_document_ingestion_summary"] = dict(extras["local_document_ingestion_summary"])
    # Evidence-quality honesty (Section E/G):
    # never inflate based on local docs.  If local extraction was partial /
    # poor / none, force at least one risk note and mark partial_results.
    summary = base.get("local_document_ingestion_summary") or {}
    if summary.get("used"):
        if summary.get("partial_results"):
            base["partial_results"] = True
            base.setdefault("risks", []).append(
                "Local-folder ingestion partial — see local_document_ingestion_summary."
            )
        hint = summary.get("evidence_quality_hint", "none")
        if hint in ("poor", "none"):
            base.setdefault("risks", []).append(
                f"Local-folder ingestion evidence quality is '{hint}'; "
                "do not treat local documents as verified evidence."
            )
    return base


def run(user_input: str, context: dict, mode: str = "ideation") -> dict:
    resolved = _resolve_mode(user_input, mode)
    print(f"[Research Scout] Activated mode: {resolved}", flush=True)

    # Phase 4 hook: optional local literature folder.
    prompt_payload, extras = _maybe_handle_local_folder(
        user_input, context or {}, agent="research_scout", resolved_mode=resolved,
    )
    if prompt_payload is not None:
        return ResearchScoutOutput(
            mode=resolved,
            summary=prompt_payload.get("summary", ""),
            partial_results=True,
            failed_stage=prompt_payload.get("failed_stage", "awaiting_user_input"),
            evidence_quality="none",
            confidence="low",
            needs_user_input=prompt_payload.get("needs_user_input"),
            recovery_action="await_user_response",
        ).model_dump()

    # Defect 5: inject the local-evidence prompt block into the LLM-visible
    # input BEFORE the mode handler builds its prompt.  Every mode in this
    # module ultimately interpolates ``user_input`` into the user prompt,
    # so appending the local block here is the smallest reliable hook.
    # The block is also stashed on context for explicit consumers.
    effective_user_input = user_input
    local_block = extras.get("local_evidence_prompt_block") or ""
    if local_block:
        effective_user_input = (
            f"{user_input}\n\n=== LOCAL LITERATURE EVIDENCE (user-supplied) ===\n"
            f"{local_block}\n"
            f"=== END LOCAL LITERATURE EVIDENCE ===\n"
        )
        if isinstance(context, dict):
            context = dict(context)
            context["local_evidence_prompt_block"] = local_block

    handler = _MODE_DISPATCH.get(resolved, _run_ideation)
    try:
        out = handler(effective_user_input, context)
    except Exception as exc:
        # Defect 10: a crashed Research Scout MUST NOT be read downstream as
        # moderate evidence by schema fallback default.  Set evidence_quality
        # to "none" and confidence to "low" explicitly so the verifier and
        # learning gates fail closed.
        return ResearchScoutOutput(
            mode=resolved,
            summary=f"Research Scout failed in mode '{resolved}': {exc}",
            confidence="low",
            evidence_quality="none",
            partial_results=True,
            failed_stage="unhandled_exception",
            recovery_action="manual_review",
            risks=[str(exc)],
        ).model_dump()

    out = _maybe_attach_local_evidence_to_dict(out, extras)

    # Phase 3 (MCP): optionally APPEND external MCP evidence as
    # external/unverified context.  OFF by default; never substitutes the
    # scholarly source search above, and never treated as primary literature.
    try:
        from core.mcp import integration as _mcp_int
        _sid = (context or {}).get("session_id")
        gathered = _mcp_int.gather_research_evidence(user_input, _sid, mode=resolved)
        # Also consult the AI Co-Scientist (open-coscientist) when the request
        # is hypothesis-generation-oriented.  OFF unless enabled + approved;
        # output is SPECULATIVE (hypothesis_signal), still Verifier-gated.
        hyp = _mcp_int.maybe_gather_hypotheses(user_input, _sid)
        _mcp_int.attach_to_output(out, _mcp_int.merge_gathered(gathered, hyp))
    except Exception:  # noqa: BLE001 — MCP must never break the Scout
        pass

    return out


# ---------------------------------------------------------------------------
# Rigorous local test harness (uses Ollama / qwen2.5:8b for LLM calls)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os
    import sys
    import json

    from integrations.research_evolution.literature_memory import init_research_db

    # Ensure DB tables exist before running the pipeline
    init_research_db()

    # ----- Parse --model MODEL_NAME and --api-key API_KEY from command line -----
    model_name = None
    api_key = None
    args = sys.argv[1:]
    remaining = []

    i = 0
    while i < len(args):
        if args[i] == "--model":
            if i + 1 < len(args):
                model_name = args[i + 1]
                i += 2
                continue
            else:
                print("Error: --model requires an argument", file=sys.stderr)
                sys.exit(1)
        elif args[i] == "--api-key":
            if i + 1 < len(args):
                api_key = args[i + 1]
                i += 2
                continue
            else:
                print("Error: --api-key requires an argument", file=sys.stderr)
                sys.exit(1)
        else:
            remaining.append(args[i])
            i += 1

    if model_name:
        os.environ["LLM_MODEL"] = model_name
        print(f"Using model: {model_name}")

    if api_key:
        os.environ["LLM_API_KEY"] = api_key
        print("API key supplied (via LLM_API_KEY).")

    prompt = " ".join(remaining) if remaining else "perform a literature scan on TADF OLED red emitters"
    context = {}  # can be extended with governor parameters if needed

    print(f"Running Research Scout (mode=literature_scan) with prompt:\n  {prompt}\n")
    result = run(prompt, context, mode="literature_scan")
    print(json.dumps(result, indent=2, ensure_ascii=False))
