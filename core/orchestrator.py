from __future__ import annotations

import traceback
from typing import Any

from core.permissions import requires_human_approval, log_approval_event
import agents.strategic_governor as gov_module
import agents.research_scout as scout_module
import agents.scientific_verifier as verifier_module
import agents.self_evolution_engine as evolution_module


def _resolve_execution_plan(decision: dict) -> tuple[list[str], str, dict]:
    """Derive ordered agent list, scout mode, and per-agent configs from decision.

    Returns (ordered_agents, scout_mode, agent_configs).
    Prefers workflow_sequence when present; falls back to selected_agents + research_scout_mode.
    """
    workflow = decision.get("workflow_sequence") or []
    agent_configs = decision.get("agent_configs") or {}

    if workflow:
        # Extract agents in order (skip strategic_governor itself)
        ordered: list[str] = []
        for step in workflow:
            agent = step.get("agent", "") if isinstance(step, dict) else getattr(step, "agent", "")
            if agent and agent != "strategic_governor" and agent not in ordered:
                ordered.append(agent)

        # research_scout_mode at the top level wins when explicitly set;
        # fall back to the workflow step's mode only when it is absent or "none".
        top_level_mode = (decision.get("research_scout_mode") or "").strip()
        if top_level_mode and top_level_mode != "none":
            scout_mode = top_level_mode
        else:
            scout_mode = "ideation"
            for step in workflow:
                agent = step.get("agent", "") if isinstance(step, dict) else getattr(step, "agent", "")
                mode = step.get("mode", "") if isinstance(step, dict) else getattr(step, "mode", "")
                if agent == "research_scout" and mode:
                    scout_mode = mode
                    break

        return ordered, scout_mode, agent_configs

    # Legacy path: use selected_agents + research_scout_mode
    selected = list(decision.get("selected_agents") or [])
    scout_mode = decision.get("research_scout_mode", "ideation") or "ideation"
    return selected, scout_mode, agent_configs


def _should_run_evolution(decision: dict) -> bool:
    """Consult self_evolution_policy; default True for backward compat."""
    policy = decision.get("self_evolution_policy") or {}
    if isinstance(policy, dict):
        return bool(policy.get("run", True))
    # Pydantic model case (shouldn't reach here after model_dump, but be safe)
    return getattr(policy, "run", True)


def _build_evidence_pack(scout_output: dict | None, decision: dict) -> dict:
    """Build a structured evidence pack from Research Scout output for the verifier."""
    if not scout_output:
        return {}

    top_papers = scout_output.get("top_papers", [])
    sources_used: list[str] = []
    if scout_output.get("literature_scan_used"):
        for p in top_papers:
            src = p.get("source", "")
            if src and src not in sources_used:
                sources_used.append(src)

    # Load profile topics for verifier context
    profile_topics: list[str] = []
    try:
        from integrations.research_evolution.profile import load_research_profile
        profile = load_research_profile()
        profile_topics = profile.get("research_topics", [])[:10]
    except Exception:
        pass

    return {
        "top_papers": top_papers,
        "sources_used": sources_used,
        "profile_topics": profile_topics,
        "scout_mode": scout_output.get("mode", ""),
        "scout_confidence": scout_output.get("confidence", ""),
    }


def _handle_verifier_route(route: str, user_input: str, decision: dict) -> None:
    """Log routing decisions from the verifier. Re-invocation deferred to Phase 2."""
    if route in ("human_review", "reject"):
        log_approval_event({
            "trigger": "verifier_route",
            "route": route,
            "user_input": user_input,
            "governor_task_type": decision.get("task_type", ""),
        })


def run_aura_core(user_input: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "user_input": user_input,
        "strategic_governor": {},
        "research_scout": None,
        "scientific_verifier": None,
        "self_evolution_engine": {},
        "errors": [],
    }

    # Step 1: Strategic Governor
    try:
        decision = gov_module.run(user_input)
        result["strategic_governor"] = decision
    except Exception as exc:
        result["errors"].append({"agent": "strategic_governor", "error": str(exc)})
        result["strategic_governor"] = {
            "task_type": "unknown",
            "priority": "medium",
            "selected_agents": ["scientific_verifier", "self_evolution_engine"],
            "research_scout_mode": "none",
            "requires_approval": True,
            "approval_reason": "Governor failed — human review required before consequential action.",
            "risk_level": "medium",
            "autonomy_level": "L1",
            "external_consequence": "none",
            "evidence_requirement": "high",
            "mission_alignment_score": 0.0,
            "strategic_value_score": 0.0,
            "urgency_score": 0.0,
            "should_this_be_done": "maybe",
            "workflow_sequence": [],
            "agent_configs": {},
            "task_decomposition": [],
            "blocked_actions": ["All consequential actions blocked — governor failed."],
            "memory_policy": {"retrieve_memory": True, "allow_memory_write": False, "memory_write_requires_approval": True},
            "self_evolution_policy": {"run": True, "reason": "Log governor failure."},
            "rationale": f"Fallback: governor failed — {exc}",
        }
        decision = result["strategic_governor"]

    # Step 2: Log approval if governor or permission check requires it
    needs_approval, approval_reason = requires_human_approval(user_input)
    if needs_approval or decision.get("requires_approval"):
        log_approval_event({
            "user_input": user_input,
            "reason": approval_reason or decision.get("approval_reason", ""),
            "decision": decision,
        })

    # Resolve execution plan from workflow_sequence or selected_agents
    ordered_agents, scout_mode, agent_configs = _resolve_execution_plan(decision)
    enriched_context = {**decision, "agent_configs": agent_configs}

    # Step 3: Research Scout
    if "research_scout" in ordered_agents:
        try:
            scout_out = scout_module.run(user_input, context=enriched_context, mode=scout_mode)
            result["research_scout"] = scout_out
        except Exception as exc:
            tb = traceback.format_exc()
            result["errors"].append({"agent": "research_scout", "error": str(exc), "traceback": tb})
            result["research_scout"] = {
                "agent_name": "research_scout",
                "mode": scout_mode,
                "summary": f"Research Scout failed: {exc}",
                "findings": [],
                "risks": [],
                "recommended_actions": [],
                "confidence": "low",
                "search_queries": [],
                "literature_scan_used": False,
                "top_papers": [],
                "research_gap_candidate": "",
                "report_paths": [],
            }

    # Step 4: Scientific Verifier
    if "scientific_verifier" in ordered_agents:
        try:
            prior_outputs = {
                "strategic_governor": result["strategic_governor"],
                "research_scout": result.get("research_scout"),
            }
            # Build evidence pack from scout output and profile
            evidence_pack = _build_evidence_pack(result.get("research_scout"), decision)

            verification = verifier_module.run(
                user_input,
                prior_outputs,
                evidence_pack=evidence_pack,
            )
            result["scientific_verifier"] = verification

            # Handle verifier routing (log only in Phase 1 — no re-invocation yet)
            route = verification.get("route", "revise")
            _handle_verifier_route(route, user_input, decision)

        except Exception as exc:
            tb = traceback.format_exc()
            result["errors"].append({"agent": "scientific_verifier", "error": str(exc), "traceback": tb})
            # Fail safely — "incomplete" not "acceptable"
            result["scientific_verifier"] = {
                "overall_assessment": "incomplete",
                "claim_checks": [],
                "methodology_risks": [],
                "novelty_risks": [],
                "citation_risks": [],
                "grant_risks": [],
                "action_governance_risks": [],
                "required_human_approvals": [],
                "revision_instructions": ["Verifier crashed — do not use prior outputs without manual review."],
                "final_recommendation": "needs_more_evidence",
                "route": "human_review",
                "unsupported_claims": [],
                "assumptions": [],
                "risks": [f"Verifier failed: {exc}"],
                "corrections": ["Manual review required."],
            }

    # Step 5: Self-Evolution Engine (runs when policy allows)
    if not _should_run_evolution(decision):
        result["self_evolution_engine"] = {
            "session_assessment": "Self-evolution skipped per governor policy.",
            "failure_modes": [], "lesson_details": [], "memory_update_proposals": [],
            "workflow_update_proposals": [], "rubric_update_proposals": [],
            "profile_update_proposals": [], "next_experiments": [],
            "human_approval_required": False, "do_not_learn": [],
            "what_worked": [], "what_failed_or_was_weak": [], "reusable_lessons": [],
            "memory_updates": [], "workflow_improvements": [], "suggested_profile_updates": [],
        }
    else:
        try:
            evolution_out = evolution_module.run(
                user_input,
                result,
                verifier_report=result.get("scientific_verifier"),
            )
            result["self_evolution_engine"] = evolution_out
        except Exception as exc:
            result["errors"].append({"agent": "self_evolution_engine", "error": str(exc)})
            result["self_evolution_engine"] = {
                "what_worked": [],
                "what_failed_or_was_weak": [str(exc)],
                "reusable_lessons": [],
                "memory_updates": [],
                "workflow_improvements": [],
                "suggested_profile_updates": [],
            }

    return result
