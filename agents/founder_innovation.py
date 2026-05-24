from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from core.llm import ask_json
from core.memory import retrieve_relevant_memory
from core.schemas import (
    FounderInnovationOutput, KeyRisk, RecommendedAction, SpecialistBaseOutput,
)
import config


# ---------------------------------------------------------------------------
# Helper: store a reflection record for self-improvement
# ---------------------------------------------------------------------------

REFLECT_PATH = config.BASE_DIR / "data" / "reflections" / "founder_reflections.jsonl"


def _store_reflection(record: dict) -> None:
    REFLECT_PATH.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    with open(REFLECT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Comprehensive analysis prompt — covers ALL required capabilities
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """\
You are a Founder / Innovation Analyst inside AURA, a self-evolving research-strategy system.

Given a technology concept, perform a rigorous, evidence-grounded commercialization analysis.
Your output must be strict JSON with the sections listed below.

Required sections:

1. innovation_thesis               — One sentence describing the core innovation.
2. product_hypothesis              — What product or service could be built.
3. target_users_or_customers       — List of potential customer segments or user profiles.
4. problem_customer_fit            — What problem does this solve for those customers?
5. possible_value_proposition      — Why would a customer choose this over alternatives?
6. technical_moat                  — What protects this innovation from easy copying?
7. ip_considerations               — Patent, trade secret, or other IP angles (strategic only, NOT legal advice).
8. market_assumptions              — Key assumptions about market size, growth, adoption, willingness-to-pay.
9. commercialization_pathways      — Ordered list of possible routes (startup, licensing, partnership, grant-to-company, academic spin-off, etc.).
10. validation_experiments          — What experiments would de-risk the most fragile assumptions?
11. business_model_options          — Possible revenue models (device sale, subscription, licensing, service, platform, etc.).
12. key_risks                       — List of STRUCTURED RISK OBJECTS (NOT plain strings). Each object MUST contain:
                                          {
                                            "category":    "scientific | scale_up | regulatory | ip | market | capital | execution | other",
                                            "description": "one-sentence description",
                                            "severity":    "low | medium | high",
                                            "likelihood":  "low | medium | high",
                                            "mitigation":  "proposed mitigation"
                                          }
13. regulatory_or_ethical_considerations — List of relevant regulatory hurdles or ethical issues.
14. next_90_day_plan                — Highest-leverage actions for the next 90 days (each with a short description).
15. legal_financial_disclaimer      — Always set to: "This is strategic analysis, not legal, financial, investment, or IP advice."
16. approval_required_before_external_commitment — Boolean, always true.
17. scorecard                       — List of objects with keys: criterion, score (1-10), confidence (low/medium/high), and evidence.
18. recommendation                  — Object with keys: category (one of pursue_aggressively, pursue_with_milestone_gating, partner_rather_than_found, license_rather_than_build, continue_research_before_commercialization, monitor_only, reject_archive), rationale, next_milestone, expected_upside, major_caveats.
19. pathway_comparison              — List of objects, each with keys: pathway, rationale, capital_intensity (low/medium/high), time_to_market, dependency_risk (low/medium/high), suitability_score (1-10).
20. market_signals                  — Object with keys: demand_indicators, adoption_signals, funding_signals, policy_signals, confidence (low/medium/high).
21. ip_landscape                    — Object with keys: novelty_score (1-10), congestion_score (1-10), blocking_risk (low/medium/high), white_space_notes, assignee_map, confidence.
22. techno_economic                 — Object with keys: cost_drivers, revenue_assumptions, break_even_conditions, sensitivity_drivers, scenario_summary.
23. risk_register                   — List of risk objects (same as key_risks but in structured form with category, description, severity, likelihood, mitigation, next_evidence_required).
24. strategic_fit                   — Object with keys: alignment_score (1-10), mission_fit, resource_leverage, opportunity_cost.
25. next_actions                    — List of objects with keys: action, priority (high/medium/low), timescale (30d/60d/90d).
26. memo_sections                   — Object containing the raw text for each section of a formal commercialization memo: executive_summary, technology_concept, problem_opportunity, why_now, evidence_base, market_attractiveness, competitive_landscape, ip_defensibility, business_model_possibilities, commercialization_pathways, techno_economic_logic, risk_register_summary, strategic_fit, recommendation_memo, next_90_day_plan.

Use the provided context (if any) as a starting point.
Be precise. Distinguish facts from assumptions. Avoid hype.

Return strict JSON only."""


# ---------------------------------------------------------------------------
# Output formatting helpers
# ---------------------------------------------------------------------------

def _format_quick_triage(analysis: dict) -> str:
    """Defect 2: read key_risks as structured objects only.

    The schema is now ``list[KeyRisk]`` so every entry is guaranteed to be a
    dict (after Pydantic coercion).  Defensive against missing/empty lists.
    """
    rec = analysis.get("recommendation", {}) or {}
    scorecard = analysis.get("scorecard", []) or []
    scores = [s.get("score", 5) for s in scorecard if isinstance(s, dict)]
    avg = (sum(scores) / len(scores)) if scores else 5.0

    risks = analysis.get("key_risks") or []
    top_risk_desc = "N/A"
    if risks:
        first = risks[0]
        if isinstance(first, dict):
            top_risk_desc = first.get("description") or "N/A"
        elif isinstance(first, str):  # legacy fallback only
            top_risk_desc = first

    return (
        f"**Quick Triage**\n\n"
        f"Opportunity: {analysis.get('innovation_thesis', '')}\n"
        f"Score: {avg:.1f}/10 (confidence: {rec.get('confidence', 'medium')})\n"
        f"Recommendation: {rec.get('category', '')}\n"
        f"Top risk: {top_risk_desc}\n"
        f"Next step: {rec.get('next_milestone', '')}"
    )


def _format_scorecard(scorecard: list) -> str:
    lines = ["| Criterion | Score | Confidence | Evidence |", "| --- | --- | --- | --- |"]
    for item in scorecard or []:
        if not isinstance(item, dict):
            continue
        evidence = (item.get("evidence") or "")[:80]
        lines.append(
            f"| {item.get('criterion', '')} | {item.get('score', '')} | "
            f"{item.get('confidence', '')} | {evidence} |"
        )
    return "\n".join(lines)


def _extract_recommended_actions(analysis: dict) -> list[dict]:
    """Build recommended_actions from analysis output.

    Defect 7: free-text actions MUST NOT be coerced to ``action_class="draft_text"``
    here — they're left without an action_class so the policy gate can classify
    them from their raw text. Only dict actions that ALREADY carry a
    declared action_class keep it.
    """
    raw = analysis.get("next_actions", []) or analysis.get("recommended_actions", []) or []
    actions: list[dict] = []
    for a in raw:
        if isinstance(a, str):
            # Leave action_class UNSET so permissions._infer_action_class_from_text
            # gets to inspect the actual sentence (e.g., "file a patent" →
            # action_class="file_patent").
            actions.append({"description": a, "rationale": ""})
        elif isinstance(a, dict):
            d = dict(a)
            if "description" not in d:
                d["description"] = d.get("action") or "No description"
            # NOTE: do NOT inject a default action_class here either.
            actions.append(d)
    return actions


def _normalise_key_risks(raw: Any) -> list[dict]:
    """Always return ``list[dict]`` matching ``KeyRisk`` shape.

    LLMs sometimes still emit plain strings even when the prompt asks for
    objects. We map those to the structured shape so the formatter and
    downstream consumers never need to special-case strings.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for r in raw:
        if isinstance(r, str) and r.strip():
            out.append({
                "category": "other",
                "description": r.strip(),
                "severity": "medium",
                "likelihood": "medium",
                "mitigation": "",
            })
        elif isinstance(r, dict):
            d = dict(r)
            # alias migration
            if "description" not in d:
                d["description"] = d.get("risk") or d.get("name") or ""
            d.setdefault("category", "other")
            d.setdefault("severity", "medium")
            d.setdefault("likelihood", "medium")
            d.setdefault("mitigation", "")
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# Patent context extraction — uses ONLY the upstream patent_intelligence
# output already present in context["specialists"].  Defect 5: this agent
# MUST NOT call patent_intelligence.run() itself.
# ---------------------------------------------------------------------------

def _extract_patent_context(context: dict) -> tuple[dict, str]:
    """Return ``(patent_output, prompt_snippet)``.

    Pulls the upstream patent_intelligence output from context.specialists.
    If none is present, returns an empty dict and a snippet noting that no
    patent context was available.  Reads the authoritative field names
    (apparent_theme_clusters, possible_white_space, overlap_risks) — NOT
    the obsolete top_patent_clusters / white_space_opportunities /
    crowded_areas (defect 4).
    """
    specialists = context.get("specialists") or {}
    if not isinstance(specialists, dict):
        return {}, "Patent landscape data: (no upstream patent_intelligence output available)\n"
    patent_output = specialists.get("patent_intelligence")
    if not isinstance(patent_output, dict):
        return {}, "Patent landscape data: (no upstream patent_intelligence output available)\n"

    # Read the actual emitted fields from PatentIntelligenceOutput.
    theme_clusters = patent_output.get("apparent_theme_clusters") or []
    white_space = patent_output.get("possible_white_space") or []
    overlap_risks = patent_output.get("overlap_risks") or []
    landscape_summary = patent_output.get("apparent_landscape_summary") or ""
    frequent_assignees = patent_output.get("frequent_assignees_or_applicants") or []
    mock_mode_used = bool(patent_output.get("mock_mode_used"))

    def _brief(items, key=None, limit=4):
        out = []
        for it in items[:limit]:
            if isinstance(it, dict):
                out.append(it.get(key) or it.get("cluster_name") or it.get("direction") or "")
            elif isinstance(it, str):
                out.append(it)
        return "; ".join(s for s in out if s)

    snippet_lines = ["Patent landscape data (Stage 1 web reconnaissance):"]
    if mock_mode_used:
        snippet_lines.append(
            "  [WARNING] Patent intelligence ran in MOCK MODE — results are SYNTHETIC."
        )
    if landscape_summary:
        snippet_lines.append(f"  Apparent landscape summary: {landscape_summary[:300]}")
    if theme_clusters:
        snippet_lines.append(
            f"  Apparent theme clusters: {_brief(theme_clusters, 'cluster_name')}"
        )
    if white_space:
        snippet_lines.append(
            f"  Possible white-space (hedge claims): {_brief(white_space, 'direction')}"
        )
    if overlap_risks:
        snippet_lines.append(
            f"  Overlap risks: {_brief(overlap_risks)}"
        )
    if frequent_assignees:
        snippet_lines.append(
            f"  Frequent assignees/applicants: {', '.join(frequent_assignees[:5])}"
        )
    if len(snippet_lines) == 1:
        snippet_lines.append("  (No structured patent fields populated.)")
    snippet_lines.append(
        "  NOTE: Patent intelligence is Stage-1 web reconnaissance only. "
        "Treat all white-space claims as tentative."
    )
    return patent_output, "\n".join(snippet_lines) + "\n"


# ---------------------------------------------------------------------------
# Main agent entry point
# ---------------------------------------------------------------------------

def run(user_input: str, context: dict) -> dict:
    """
    Founder / Innovation Agent – structured commercialization analysis.
    Returns a dict validated against FounderInnovationOutput.

    Defect 5: this agent never invokes other agents.  It consumes
    upstream outputs from ``context["specialists"]`` only.  The orchestrator
    is the single authority for execution order.
    """
    errors: list[str] = []
    analysis_raw: dict = {}
    memories: list[str] = []

    # 1. Retrieve relevant memory.
    try:
        mems = retrieve_relevant_memory(user_input, limit=3)
        memories = [m.get("content", "") for m in mems] if mems else []
    except Exception as exc:
        errors.append(f"Memory retrieval failed: {exc}")

    # 2. Patent landscape — consume upstream output only (defect 5).
    patent_output, patent_summary = _extract_patent_context(context)

    # 2b. Phase 3 (MCP): optional idea-reality market/competition signal.
    # OFF by default.  Treated ONLY as a market/competition signal for
    # duplicate-risk / adjacent-project / pivot / validation prompts — NEVER
    # as scientific evidence and NEVER as legal/financial/investment/IP advice.
    _mcp_gathered: dict = {"records": [], "warnings": []}
    _mcp_signal_block = ""
    try:
        from core.mcp import integration as _mcp_int
        _mcp_gathered = _mcp_int.gather_idea_signal(
            user_input, (context or {}).get("session_id"),
        )
        if _mcp_gathered.get("records"):
            lines = [
                "External market/competition SIGNAL (unverified, NOT scientific "
                "evidence; use only for duplicate-risk, adjacent projects, pivot "
                "prompts, and validation experiments):",
            ]
            for rec in _mcp_gathered["records"][:3]:
                content = rec.get("content")
                lines.append(f"  - [{rec.get('provider')}::{rec.get('result_type')}] "
                             f"{str(content)[:400]}")
            _mcp_signal_block = "\n".join(lines) + "\n\n"
    except Exception:  # noqa: BLE001 — MCP must never break the agent
        _mcp_gathered = {"records": [], "warnings": []}

    # 3. Build a rich user prompt with gathered context.
    memory_text = "\n".join(memories[:3]) if memories else "No prior similar analyses found."

    user_prompt = (
        f"User technology concept: {user_input}\n\n"
        f"Relevant memories:\n{memory_text}\n\n"
        f"{patent_summary}\n"
        f"{_mcp_signal_block}"
    )

    # --- Inject verifier revision instructions if present (retry context) ---
    verifier_instructions = context.get("verifier_revision_instructions")
    if isinstance(verifier_instructions, list) and verifier_instructions:
        user_prompt += (
            "Verifier Revision Instructions (address each before finalising):\n"
            + "\n".join(f"  - {v}" for v in verifier_instructions[:8])
            + "\n\n"
        )
    verifier_corrections = context.get("verifier_corrections")
    if isinstance(verifier_corrections, list) and verifier_corrections:
        user_prompt += (
            "Verifier Corrections (mandatory fixes):\n"
            + "\n".join(f"  * {c}" for c in verifier_corrections[:5])
            + "\n\n"
        )
    verifier_risks = context.get("verifier_risks")
    if isinstance(verifier_risks, list) and verifier_risks:
        user_prompt += (
            "Verifier Risks to Mitigate:\n"
            + "\n".join(f"  ! {r}" for r in verifier_risks[:5])
            + "\n\n"
        )

    user_prompt += (
        "Perform commercialization analysis and return the structured JSON as per the "
        "instructions. Remember: key_risks MUST be a list of structured objects, "
        "not plain strings."
    )

    # 4. Call LLM.
    analysis_succeeded = False
    try:
        analysis_raw = ask_json(ANALYSIS_PROMPT, user_prompt, temperature=0.15)
        if isinstance(analysis_raw, dict) and analysis_raw:
            analysis_succeeded = True
        else:
            raise ValueError("LLM did not return a usable dictionary")
    except Exception as exc:
        errors.append(f"LLM analysis failed: {exc}")
        analysis_raw = {
            "innovation_thesis": f"Analysis failed: {exc}",
            "recommendation": {"category": "monitor_only", "rationale": "error", "next_milestone": ""},
        }

    # 5. Build output.
    def _s(v, default=""):
        return v if v else default
    def _slist(v, default=None):
        if default is None:
            default = []
        return v if isinstance(v, list) else default

    # Fix D: 200 chars cut the innovation thesis mid-word ("...near-in").
    # 600 keeps the CLI panel concise without truncating real content.
    summary = _s(analysis_raw.get("innovation_thesis", ""), "No thesis generated")[:600]
    findings = [analysis_raw.get("problem_customer_fit", "")]
    structured_key_risks = _normalise_key_risks(analysis_raw.get("key_risks"))
    if not structured_key_risks:
        structured_key_risks = [{
            "category": "other",
            "description": "No risks identified",
            "severity": "medium",
            "likelihood": "medium",
            "mitigation": "",
        }]
    risk_descriptions = [
        r.get("description", "") for r in structured_key_risks if r.get("description")
    ]
    actions = _extract_recommended_actions(analysis_raw)

    # 6. Determine evidence_level.
    evidence_level = "weak"
    if analysis_succeeded and (analysis_raw.get("scorecard") or analysis_raw.get("innovation_thesis")):
        evidence_level = "moderate"

    output: dict[str, Any] = {
        "agent_name": "founder_innovation",
        "schema_version": 1,
        "summary": summary,
        "findings": findings,
        "assumptions": analysis_raw.get("market_assumptions", []),
        "risks": risk_descriptions,
        "recommended_actions": actions,
        "claims_for_verification": [],
        "evidence_level": evidence_level,
        "confidence": analysis_raw.get("recommendation", {}).get("confidence", "medium"),
        "approval_level": "draft_only",
        "partial_results": bool(errors),
        "failed_stage": "analysis" if errors else "",
        # Rich specialist fields required by schema and formatter:
        "innovation_thesis": _s(analysis_raw.get("innovation_thesis", "")),
        "product_hypothesis": _s(analysis_raw.get("product_hypothesis", "")),
        "target_users_or_customers": _slist(analysis_raw.get("target_users_or_customers")),
        "problem_customer_fit": _s(analysis_raw.get("problem_customer_fit", "")),
        "possible_value_proposition": _s(analysis_raw.get("possible_value_proposition", "")),
        "technical_moat": _s(analysis_raw.get("technical_moat", "")),
        "ip_considerations": _slist(analysis_raw.get("ip_considerations")),
        "market_assumptions": _slist(analysis_raw.get("market_assumptions")),
        "commercialization_pathways": _slist(analysis_raw.get("commercialization_pathways")),
        "validation_experiments": _slist(analysis_raw.get("validation_experiments")),
        "business_model_options": _slist(analysis_raw.get("business_model_options")),
        # Defect 2: structured KeyRisk objects, not plain strings.
        "key_risks": structured_key_risks,
        "regulatory_or_ethical_considerations": _slist(analysis_raw.get("regulatory_or_ethical_considerations")),
        "next_90_day_plan": _slist(analysis_raw.get("next_90_day_plan")),
        "legal_financial_disclaimer": _s(
            analysis_raw.get("legal_financial_disclaimer",
                             "This is strategic analysis, not legal, financial, investment, or IP advice.")
        ),
        "approval_required_before_external_commitment": True,
        # Extra fields for downstream consumption.
        "analysis": analysis_raw,
        "quick_triage": _format_quick_triage(analysis_raw),
        "scorecard_table": _format_scorecard(analysis_raw.get("scorecard", [])),
    }

    # 7. Validate against the output schema.
    try:
        validated = FounderInnovationOutput.model_validate(output)
        result = validated.model_dump()
    except ValidationError as ve:
        # Defect 3: schema validation failure MUST set truthful failure
        # markers — not silently report partial_results=False.
        errors.append(f"Output schema validation failed: {ve}")
        output["partial_results"] = True
        output["failed_stage"] = "schema_validation"
        output["risks"] = list(output.get("risks", [])) + [
            f"Schema validation failed: {ve.__class__.__name__}"
        ]
        result = output

    # 8. Store reflection.
    try:
        _store_reflection({
            "task": user_input,
            "recommendation": _s(analysis_raw.get("recommendation", {}).get("category", "")),
            "confidence": result.get("confidence", "medium"),
            "errors": errors,
            "patent_context_present": bool(patent_output),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        errors.append(f"Reflection storage failed: {exc}")

    if errors:
        result.setdefault("risks", [])
        for e in errors:
            if e not in result["risks"]:
                result["risks"].append(e)

    # Attach external market/competition signal (post-dump; unverified).
    try:
        from core.mcp import integration as _mcp_int
        _mcp_int.attach_to_output(result, _mcp_gathered)
    except Exception:  # noqa: BLE001
        pass

    return result
