from __future__ import annotations

from core.llm import ask_json
from integrations.research_evolution.profile import (
    load_research_profile,
    sanitize_profile_update,
)

SYSTEM_PROMPT = """You are an AURA research profile advisor.
Based on the top papers and user research profile, suggest how to evolve the research profile.

Return strict JSON with this schema:
{
  "suggested_new_topics": [string, ...],
  "topics_to_deprioritise": [string, ...],
  "weight_adjustments": {string: float},
  "new_watchlist_researchers": [string, ...],
  "new_negative_filters": [string, ...],
  "rationale": string
}

Be conservative. Only suggest truly new directions supported by the papers.
Never suggest removing protected OLED/TADF/organic semiconductor topics.
Weight adjustments must be small (max +/-0.05 per dimension)."""


def generate_profile_feedback(top_papers: list[dict], profile: dict) -> str:
    paper_titles = [p.get("title", "Untitled") for p in top_papers[:6]]
    user_prompt = (
        f"Current topics: {', '.join(profile.get('research_topics', [])[:8])}\n\n"
        f"Top papers: {'; '.join(paper_titles)}\n\n"
        "Suggest profile evolution as strict JSON."
    )
    try:
        result = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.15)
        return str(result)
    except Exception as exc:
        return f"Profile feedback generation failed: {exc}"


def evolve_profile_from_feedback(
    feedback_text: str,
    require_approval: bool = True,
) -> dict:
    if require_approval:
        return {
            "status": "draft_only",
            "message": "Profile update drafted but NOT applied. Requires explicit user approval.",
            "proposed_changes": feedback_text,
        }
    # If approval explicitly given (require_approval=False), apply changes
    try:
        import json
        proposed = json.loads(feedback_text) if isinstance(feedback_text, str) else feedback_text
        current = load_research_profile()
        sanitized = sanitize_profile_update(proposed, current)
        from integrations.research_evolution.profile import save_research_profile
        save_research_profile(sanitized)
        return {"status": "applied", "message": "Profile updated.", "changes": sanitized}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
