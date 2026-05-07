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


def discover_papers(topics: list[str], user_input: str = "") -> list[dict]:
    raw = search_all_sources(topics, max_per_topic=3)
    return [p for p in raw if "source_error" not in p and "source_errors" not in p]


def score_papers_integration(profile: dict, papers: list[dict]) -> list[dict]:
    return score_papers(profile, papers)


def save_scored_papers(scored: list[dict], session_id: str = "") -> None:
    init_research_db()
    for paper in scored:
        try:
            save_scored_paper(paper, session_id=session_id)
        except Exception:
            pass


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
        from datetime import datetime, timezone
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        content = generate_weekly_brief(top_papers, profile)
        path = save_report(f"weekly_brief_{date}.md", content)
        return path
    return None
