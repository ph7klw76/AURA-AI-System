from __future__ import annotations

import json

from core.llm import ask_json

SYSTEM_PROMPT = """\
You are an expert research strategist for an OLED/TADF/photophysics/organic-electronics group.
Based ONLY on the provided top papers and research profile, identify the most promising research gap.

Return strict JSON with EXACTLY this schema — no additional keys:
{
  "gap_statement": "One clear, specific gap statement.",
  "supporting_papers": ["Paper title or index that supports this gap"],
  "contradicting_or_overlap_papers": ["Paper title or index that partially covers this gap"],
  "why_gap_exists": "Why has this not been solved yet?",
  "why_gap_matters": "Scientific and societal importance.",
  "what_is_new": "What would be genuinely novel about addressing it?",
  "what_is_not_new": "What aspects already exist in the literature and must NOT be overclaimed as new.",
  "minimum_evidence_needed": ["List of specific experiments or data needed to close the gap"],
  "proposal_angle": "How to frame this as a grant proposal.",
  "paper_angle": "How to frame this as a journal paper.",
  "risk_level": "low | medium | high",
  "best_research_gap_candidate": "Same as gap_statement — for backward compatibility.",
  "evidence_from_papers": ["Brief evidence statements from the papers above"],
  "why_user_is_positioned": "Why this research group is well positioned.",
  "possible_research_question": "A specific, answerable research question.",
  "possible_grant_angle": "Same as proposal_angle — for backward compatibility.",
  "collaboration_angle": "Who to collaborate with and why.",
  "industry_angle": "Relevance to industry partners.",
  "teaching_or_linkedin_angle": "How to communicate this to students or public.",
  "risks_or_weaknesses": "Key risks or weaknesses in pursuing this gap.",
  "next_action": "The single most important next step."
}

Critical rules:
- Do NOT invent papers, data, citations, or experimental results.
- Only reference papers that appear in the provided top_papers list.
- what_is_not_new is mandatory — leave nothing unchallenged.
- The gap must be fundable, scientifically rigorous, and experimentally tractable."""


def generate_research_gap_analysis(
    top_papers: list[dict],
    profile: dict,
    user_context: str | None = None,
) -> dict:
    if not top_papers:
        return {
            "gap_statement": "Insufficient papers for gap analysis.",
            "best_research_gap_candidate": "Insufficient papers for gap analysis.",
            "what_is_not_new": "Unable to assess — no papers provided.",
            "evidence_from_papers": [],
            "next_action": "Run a literature scan first.",
            "risk_level": "high",
        }

    paper_summaries = []
    for i, p in enumerate(top_papers[:8], 1):
        metrics_str = ""
        km = p.get("key_metrics") or {}
        if isinstance(km, dict) and km:
            kv = [(k, v) for k, v in km.items() if v is not None][:4]
            if kv:
                metrics_str = " | metrics: " + ", ".join(f"{k}={v}" for k, v in kv)
        paper_summaries.append(
            f"{i}. [{p.get('source', '?')}] {p.get('title', 'Untitled')}"
            f" (score={p.get('total_score', 0):.2f}"
            f", action={p.get('recommended_action', '?')}"
            f"{metrics_str}) — {(p.get('agent_commentary') or '')[:200]}"
        )

    user_prompt = (
        f"Research profile topics: {', '.join(profile.get('research_topics', [])[:8])}\n\n"
        f"User context: {user_context or 'General literature scan.'}\n\n"
        f"Top papers:\n" + "\n".join(paper_summaries) + "\n\n"
        "Identify the best research gap and return as strict JSON."
    )

    fallback = {
        "gap_statement": "Gap analysis unavailable — insufficient data or LLM error.",
        "best_research_gap_candidate": "Gap analysis unavailable — insufficient data or LLM error.",
        "what_is_not_new": "Unable to assess — LLM call failed.",
        "evidence_from_papers": [],
        "next_action": "Review top papers manually.",
        "risk_level": "high",
    }
    try:
        result = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.2)
        # Ensure backward-compat key exists
        if "best_research_gap_candidate" not in result:
            result["best_research_gap_candidate"] = result.get("gap_statement", "")
        return result
    except Exception as exc:
        fallback["next_action"] += f" LLM error: {exc}"
        return fallback
