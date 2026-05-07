from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import config


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def generate_weekly_brief(top_papers: list[dict], profile: dict) -> str:
    topics = ", ".join(profile.get("research_topics", [])[:6])
    date = _today()
    lines = [
        f"# AURA Weekly Research Brief — {date}",
        "",
        f"**Research Topics:** {topics}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        f"This brief covers {len(top_papers)} top-scored papers from recent OpenAlex and arXiv searches.",
        "",
        "---",
        "",
        "## Top Papers",
        "",
    ]
    for i, p in enumerate(top_papers[:8], 1):
        lines += [
            f"### {i}. {p.get('title', 'Untitled')}",
            f"- **Source:** {p.get('source', '?')} | **Score:** {p.get('total_score', 0):.2f}",
            f"- **Action:** `{p.get('recommended_action', '?')}`",
            f"- **URL:** {p.get('url', '')}",
            f"- **Commentary:** {p.get('agent_commentary', '')}",
            "",
        ]
    lines += [
        "---",
        "",
        "## Research Gap Candidate",
        "",
        "_(Run gap analysis for detailed candidate)_",
        "",
        "---",
        "",
        "## High-Leverage Action",
        "",
        "Review the top read_now and use_for_grant papers to identify the strongest proposal angle.",
        "",
    ]
    return "\n".join(lines)


def save_report(report_name: str, content: str) -> str:
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.REPORT_DIR / report_name
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(path)
