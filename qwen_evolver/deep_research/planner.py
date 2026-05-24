"""
Deep Research Planner — uses LLM to turn a ResearchMission into a ResearchPlan.
"""

from __future__ import annotations

from core.llm import ask_json
from .schemas import ResearchMission, ResearchPlan, ResearchBranch

PLANNER_PROMPT = """\
You are a research planner for AURA Deep Research.
Given a research mission, produce a detailed plan.

Return strict JSON:
{
  "main_question": "...",
  "subquestions": ["..."],
  "initial_queries": ["...", ...],
  "search_branches": [
    {
      "branch_name": "...",
      "branch_goal": "...",
      "branch_queries": ["...", ...],
      "priority": 1
    }
  ],
  "inclusion_criteria": [],
  "exclusion_criteria": [],
  "success_criteria": [],
  "stop_conditions": [],
  "expected_outputs": []
}

Be concrete. Include at least two search branches."""

def plan_from_mission(mission: ResearchMission) -> ResearchPlan:
    try:
        raw = ask_json(
            PLANNER_PROMPT,
            f"Mission: {mission.interpreted_objective or mission.original_user_request}\n"
            f"Depth: {mission.requested_depth.value}\n"
            f"Domain hints: {mission.domain}",
            temperature=0.2,
        )
        branches = [
            ResearchBranch(
                branch_name=b.get("branch_name", ""),
                branch_goal=b.get("branch_goal", ""),
                branch_queries=b.get("branch_queries", []),
                priority=b.get("priority", 0),
            )
            for b in raw.get("search_branches", [])[:5]
        ]
        return ResearchPlan(
            main_question=raw.get("main_question", ""),
            subquestions=raw.get("subquestions", []),
            initial_queries=raw.get("initial_queries", []),
            search_branches=branches,
            inclusion_criteria=raw.get("inclusion_criteria", []),
            exclusion_criteria=raw.get("exclusion_criteria", []),
            success_criteria=raw.get("success_criteria", []),
            stop_conditions=raw.get("stop_conditions", []),
            expected_outputs=raw.get("expected_outputs", []),
        )
    except Exception:
        # fallback plan
        return ResearchPlan(
            main_question=mission.original_user_request,
            initial_queries=[mission.original_user_request],
        )
