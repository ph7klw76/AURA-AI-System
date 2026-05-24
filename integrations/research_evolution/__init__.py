from __future__ import annotations

from integrations.research_evolution.paper_sources import search_all_sources, deduplicate_papers
from integrations.research_evolution.paper_scoring import score_papers
from integrations.research_evolution.literature_memory import (
    save_scored_paper,
    get_top_papers,
    init_research_db,
)
from integrations.research_evolution.gap_analysis import generate_research_gap_analysis
from integrations.research_evolution.reports import generate_weekly_brief, save_report
from integrations.research_evolution.profile_evolution import (
    generate_profile_feedback,
    evolve_profile_from_feedback,
)


def discover_papers(topics: list[str], user_input: str = "") -> dict:
    """Return a dict with 'papers' and 'source_errors'.

    'papers' is the list of successfully retrieved papers (no error keys).
    'source_errors' collects any records that report search API failures.
    This preserves observability for the outer workflow.
    """
    raw = search_all_sources(topics, max_per_topic=3)
    papers = [p for p in raw if "source_error" not in p and "source_errors" not in p]
    errors = [p for p in raw if "source_error" in p or "source_errors" in p]
    return {"papers": papers, "source_errors": errors}


def score_papers_integration(profile: dict, papers: list[dict]) -> list[dict]:
    return score_papers(profile, papers)


def save_scored_papers(scored: list[dict], session_id: str = "") -> dict:
    """Save papers and return a summary dict {saved, failed, errors}.
    Individual save failures are reported instead of being silently swallowed.
    """
    init_research_db()
    saved = 0
    failed = 0
    error_details: list[str] = []
    for paper in scored:
        try:
            save_scored_paper(paper, session_id=session_id)
            saved += 1
        except Exception as exc:
            failed += 1
            error_details.append(f"{paper.get('title', 'Unknown')[:80]}: {exc}")
    return {"saved": saved, "failed": failed, "errors": error_details}


def get_top_papers_for_session(
    limit: int = 8,
    session_id: str = "",
    global_memory: bool = False,
) -> list[dict]:
    return get_top_papers(limit=limit, session_id=session_id or None, global_memory=global_memory)


def generate_weekly_brief_if_requested(
    user_input: str,
    top_papers: list[dict],
    profile: dict,
) -> str | None:
    lower = user_input.lower()
    if any(kw in lower for kw in ["weekly brief", "weekly report", "research brief", "weekly summary"]):
        from core.path_safety import unique_filename_stamp
        # Phase 2 (goal F): a same-day-only name overwrote an earlier brief
        # generated the same day.  Use a microsecond + UUID stamp so each
        # brief is preserved.
        stamp = unique_filename_stamp(utc=True)
        content = generate_weekly_brief(top_papers, profile)
        path = save_report(f"weekly_brief_{stamp}.md", content)
        return path
    return None
