from __future__ import annotations

import os
import traceback
from typing import Any

from core.permissions import (
    requires_human_approval,
    log_approval_event,
    gate_recommended_actions,
    normalize_action_classes,
)
from core.registry import AGENT_REGISTRY, AgentSpec, SPECIAL_AGENT_NAMES
import agents.strategic_governor as gov_module
import agents.scientific_verifier as verifier_module
import agents.self_evolution_engine as evolution_module


# ---------------------------------------------------------------------------
# Patent‑trigger detection
# ---------------------------------------------------------------------------

_PATENT_KEYWORDS = [
    "patent",
    "ip landscape",
    "freedom to operate",
    "commercial white",
    "commercialization strategy",
    "founder analysis",
    "startup pathway",
    "technology translation",
    "market entry",
    "ip positioning",
    "commercial white space",
    "spinout",
    "claim differentiation",
    "underexplored claim",
]


def _patent_needed(user_input: str) -> bool:
    lower = user_input.lower()
    return any(kw in lower for kw in _PATENT_KEYWORDS)


# ---------------------------------------------------------------------------
# Advisory LLM Agent Planner (Stage 2 — orchestrator integration)
# ---------------------------------------------------------------------------
# The planner is an OPTIONAL advisory layer.  When AURA_LLM_PLANNER_ENABLED=1
# the Governor's decision is augmented with an LLM-proposed agent plan that
# is validated against hard safety policy before any agent executes.
#
# LLM proposes → policy validates → orchestrator executes → verifier judges.
# The planner can ADD agents but NEVER remove Governor-selected agents, and
# it can NEVER disable verification, weaken safety, or bypass draft persistence.

def _maybe_plan_agents(
    user_input: str,
    session_id: str | None,
    governor_decision: dict,
    governor_ordered: list[str],
) -> dict[str, Any]:
    """Optionally run the LLM Agent Planner to augment agent selection.

    Returns a dict with ``augmented_ordered`` (final agent list) and planner
    metadata.  When the planner is disabled, fails, or throws an exception,
    the Governor's original ordered list is returned unchanged.
    """
    from core.planning import (
        propose_agent_plan,
        validate_agent_plan,
        safe_fallback_plan,
        is_planner_enabled,
    )
    from core.planning.schemas import PlanningContext
    from core.planning import audit as plan_audit

    meta: dict[str, Any] = {
        "enabled": False,
        "plan_used": False,
        "fallback_used": False,
        "selected_agents": list(governor_ordered),
        "helper_agents": [],
        "external_mcp": [],
        "risk_level": None,
        "requires_verifier": True,
        "requires_human_review": False,
        "warnings": [],
    }

    if not is_planner_enabled():
        plan_audit.log_planner_disabled(session_id, "AURA_LLM_PLANNER_ENABLED != 1")
        return {"augmented_ordered": list(governor_ordered), "planner": meta}

    meta["enabled"] = True

    try:
        # 1. Build context from Governor decision
        ctx = PlanningContext(
            user_prompt=user_input,
            session_id=session_id,
            governor_decision=governor_decision,
            risk_hints=[governor_decision.get("risk_level", "low") or "low"],
            policy_hints=[
                f"blocked_actions={governor_decision.get('blocked_actions', [])}",
                f"requires_approval={governor_decision.get('requires_approval', False)}",
            ],
        )

        # 2. Propose
        plan_audit.log_planner_requested(session_id, plan_audit._hash(user_input))
        raw_plan = propose_agent_plan(ctx)
        raw_hash = plan_audit._hash(raw_plan.model_dump_json())

        if raw_plan.confidence == "low" and raw_plan.warnings:
            plan_audit.log_planner_failed(
                session_id,
                "; ".join(raw_plan.warnings),
                raw_plan_hash=raw_hash,
            )

        # 3. Validate
        validated = validate_agent_plan(raw_plan, ctx)
        plan_audit.log_plan_validated(
            session_id, raw_plan.plan_id, validated.ok,
            validated.validation_errors, validated.validation_warnings,
            fallback_used=False,
        )

        # 4. Fallback if validation failed or confidence too low
        if not validated.ok or raw_plan.confidence == "low":
            validated = safe_fallback_plan(user_input, governor_decision=governor_decision)
            plan_audit.log_fallback_used(
                session_id,
                f"Validation ok={validated.ok}, confidence={raw_plan.confidence}",
                validated.selected_agents,
            )
            meta["fallback_used"] = True
        else:
            meta["plan_used"] = True
            plan_audit.log_planner_succeeded(session_id, raw_plan.plan_id, raw_hash, raw_plan)
    except Exception as exc:
        # Planner crashed — use deterministic fallback, never break pipeline.
        plan_audit.log_planner_failed(session_id, str(exc))
        plan_audit.log_fallback_used(
            session_id, f"Planner crashed: {exc}", list(governor_ordered),
        )
        validated = safe_fallback_plan(user_input, governor_decision=governor_decision)
        meta["fallback_used"] = True
        meta["warnings"].append(f"Planner crashed, used fallback: {exc}")

    # 5. Merge: Governor agents + planner agents, preserving Governor primacy
    #    The planner may ADD agents but NEVER remove Governor-selected agents.
    merged = dict.fromkeys(governor_ordered)
    for agent in validated.selected_agents:
        merged[agent] = None
    augmented = [a for a in _CANONICAL_AGENT_ORDER if a in merged]
    # Append any remaining agents the canonical order doesn't know about
    for a in merged:
        if a not in augmented:
            augmented.append(a)

    # 6. Populate metadata
    meta["selected_agents"] = augmented
    meta["helper_agents"] = validated.helper_agents
    meta["external_mcp"] = validated.external_mcp
    meta["risk_level"] = validated.risk_level
    meta["requires_verifier"] = validated.requires_verifier
    meta["requires_human_review"] = validated.requires_human_review
    meta["warnings"] = validated.validation_warnings

    return {"augmented_ordered": augmented, "planner": meta}


# ---------------------------------------------------------------------------
# Execution-plan resolution
# ---------------------------------------------------------------------------

# Dependency-aware canonical order — agents that feed into others must
# appear first.  SINGLE SOURCE OF TRUTH: core.aura_principles
# .CANONICAL_AGENT_ORDER, imported so the Governor and orchestrator can
# never disagree (review findings 6 + 7).
from core.aura_principles import CANONICAL_AGENT_ORDER as _CANONICAL_AGENT_ORDER
CANONICAL_ORDER: list[str] = list(_CANONICAL_AGENT_ORDER)


def _canonicalize_order(ordered: list[str]) -> list[str]:
    """Reorder `ordered` to match CANONICAL_ORDER.

    Tail ordering (orchestration-owned special agents):
      ... specialists ... → unknown agents → scientific_verifier
      → self_evolution_engine

    ``scientific_verifier`` runs after the specialists it reviews;
    ``self_evolution_engine`` is the session-level reflection step and
    therefore must be the ABSOLUTE last entry (after the verifier).
    Previously self_evolution_engine was treated as an "unknown" agent
    and could land before scientific_verifier, contradicting the
    execution semantics.
    """
    # Pull the two orchestration-owned tail agents out; re-attach them
    # in the correct order at the end.
    has_verifier = "scientific_verifier" in ordered
    has_evolution = "self_evolution_engine" in ordered
    body = [
        a for a in ordered
        if a not in ("scientific_verifier", "self_evolution_engine")
    ]

    # Reorder the body: known specialists in canonical order, then any
    # unknown agents (preserving their relative order).
    reordered = [a for a in CANONICAL_ORDER if a in body]
    unknown = [a for a in body if a not in CANONICAL_ORDER]
    reordered.extend(unknown)

    if has_verifier:
        reordered.append("scientific_verifier")
    if has_evolution:
        reordered.append("self_evolution_engine")  # always absolute-last
    return reordered


def _resolve_execution_plan(decision: dict) -> tuple[list[str], str, dict]:
    """Derive ordered agent list, scout mode, and per-agent configs from decision.

    Returns (ordered_agents, scout_mode, agent_configs).

    Workflow order from the LLM is accepted as a *suggestion*, but the final
    agent sequence is always canonicalised so that downstream agents cannot
    execute before their upstream dependencies.
    """
    workflow = decision.get("workflow_sequence") or []
    selected = list(decision.get("selected_agents") or [])
    agent_configs = decision.get("agent_configs") or {}

    if workflow:
        ordered: list[str] = []
        for step in workflow:
            agent = step.get("agent", "") if isinstance(step, dict) else getattr(step, "agent", "")
            if agent and agent != "strategic_governor" and agent not in ordered:
                ordered.append(agent)

        # Union: any selected_agent missing from the workflow is appended
        missing = [a for a in selected
                   if a not in ordered and a != "strategic_governor"]
        if missing:
            if "scientific_verifier" in ordered:
                idx = ordered.index("scientific_verifier")
                ordered = ordered[:idx] + missing + ordered[idx:]
            else:
                if "self_evolution_engine" in ordered:
                    idx = ordered.index("self_evolution_engine")
                    ordered = ordered[:idx] + missing + ordered[idx:]
                else:
                    ordered.extend(missing)

        # Always apply canonical ordering (issue 6)
        ordered = _canonicalize_order(ordered)

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

        scout_mode = _upgrade_scout_mode_for_evidence_heavy_tasks(
            scout_mode, decision, ordered,
        )
        return ordered, scout_mode, agent_configs

    # Legacy path: use selected_agents + research_scout_mode.
    # Defect 1: the legacy path must canonicalise the order the same way as
    # the workflow_sequence path so upstream evidence producers (research_scout,
    # patent_intelligence) always precede their consumers (grant_architect,
    # founder_innovation, etc.).
    scout_mode = decision.get("research_scout_mode", "ideation") or "ideation"
    ordered = [a for a in selected if a != "strategic_governor"]
    ordered = _canonicalize_order(ordered)
    scout_mode = _upgrade_scout_mode_for_evidence_heavy_tasks(
        scout_mode, decision, ordered,
    )
    return ordered, scout_mode, agent_configs


# Tasks that require literature evidence to avoid `human_review` route on
# every verifier pass.  Self-Evolution Engine has repeatedly flagged
# ``grant_strategy`` as "needs a pre-ideation literature scan"; encode
# that lesson here so users don't have to phrase it manually.
_EVIDENCE_HEAVY_TASKS: frozenset[str] = frozenset({
    "grant_strategy",
    "grant_proposal",
})
_EVIDENCE_HEAVY_DOWNSTREAM_AGENTS: frozenset[str] = frozenset({
    "grant_architect",
    # China sub-mode of grant_architect — same evidence requirements:
    # without literature_scan, references_used is always empty and
    # every section's [N] citations are unresolved.  Adds a SECOND
    # safety net on top of the Governor's own mode upgrade, so even
    # if the Governor LLM bypasses the keyword pairing rule (e.g.
    # selects china_grant_architect directly without triggering the
    # _keyword_specialist_agents code path), the orchestrator still
    # upgrades Scout's mode.
    "china_grant_architect",
})


def _upgrade_scout_mode_for_evidence_heavy_tasks(
    scout_mode: str,
    decision: dict,
    ordered: list[str],
) -> str:
    """Force ``research_scout`` into ``literature_scan`` for evidence-heavy
    tasks like grant proposals.

    Rationale: ``ideation`` mode produces no top_papers, so every claim is
    unverifiable, every claim_check is ``support_status=unverifiable``,
    and the verifier route is forced to ``human_review`` — even when the
    underlying draft is fine.  Upgrading to ``literature_scan`` lets the
    verifier route to ``approve``/``revise``/``retrieve_more_evidence``
    based on real evidence.

    Only triggered when:
      * ``decision.task_type`` (or ``decision.task``) is in
        ``_EVIDENCE_HEAVY_TASKS``, OR
      * a downstream agent in ``_EVIDENCE_HEAVY_DOWNSTREAM_AGENTS`` is
        present (e.g. grant_architect), AND
      * the current mode is the default ``ideation`` (we respect any
        explicit override).
    """
    if scout_mode != "ideation":
        return scout_mode
    if "research_scout" not in ordered:
        return scout_mode
    # Opt-out toggle (default ON).  When AURA_GRANT_FORCE_LITERATURE_SCAN=0
    # the pre-upgrade is disabled, so a grant flow can legitimately start
    # in ``ideation`` and exercise the retrieve_more_evidence ->
    # literature_scan RETRY path.  Production keeps the upgrade on (it
    # guarantees grant claims are backed by real papers); the retry-loop
    # unit tests turn it off to test the retry mechanism in isolation.
    if os.getenv("AURA_GRANT_FORCE_LITERATURE_SCAN", "1").strip() == "0":
        return scout_mode
    task = ""
    for key in ("task_type", "task", "task_classification"):
        candidate = decision.get(key)
        if isinstance(candidate, str) and candidate.strip():
            task = candidate.strip().lower()
            break
    task_matches = task in _EVIDENCE_HEAVY_TASKS
    downstream_matches = any(
        a in _EVIDENCE_HEAVY_DOWNSTREAM_AGENTS for a in ordered
    )
    if task_matches or downstream_matches:
        print(
            f"[orchestrator] upgrading Research Scout mode "
            f"'ideation' -> 'literature_scan' "
            f"(task={task or 'unknown'}, "
            f"downstream={[a for a in ordered if a in _EVIDENCE_HEAVY_DOWNSTREAM_AGENTS]}).",
            flush=True,
        )
        return "literature_scan"
    return scout_mode


def _should_run_evolution(decision: dict) -> bool:
    """Consult self_evolution_policy; default True for backward compat."""
    policy = decision.get("self_evolution_policy") or {}
    if isinstance(policy, dict):
        return bool(policy.get("run", True))
    return getattr(policy, "run", True)


# ---------------------------------------------------------------------------
# Evidence pack for the verifier
# ---------------------------------------------------------------------------

def _project_local_evidence_ref(e: dict) -> dict:
    """Project a ``LocalEvidenceRef``-shaped dict to the verifier-facing form.

    Phase 2 Defect 8: we MUST NOT strip the very text the verifier needs to
    inspect.  Preserve excerpt, chunk_index, document_id, retrieval score,
    and (truncated for length) extraction warnings.
    """
    if not isinstance(e, dict):
        return {}
    return {
        "evidence_id":         e.get("evidence_id", ""),
        "document_id":         e.get("document_id", ""),
        "source_type":         e.get("source_type", ""),
        "file_name":           e.get("file_name", ""),
        "safe_reference":      e.get("safe_reference", ""),
        "location_hint":       e.get("location_hint", ""),
        "chunk_index":         int(e.get("chunk_index", 0) or 0),
        "extraction_quality":  e.get("extraction_quality", "good"),
        "retrieval_score":     float(e.get("score", 0.0) or 0.0),
        # Defect 8: the excerpt is the audit surface — KEEP IT.
        "excerpt":             (e.get("excerpt") or "")[:1200],
    }


def _project_local_ingestion_summary(summary: dict) -> dict:
    """Slim summary that still tells the verifier whether ingestion was
    partial / truncated / OCR'd / synthetic, without dumping every file.
    """
    if not isinstance(summary, dict):
        return {}
    discovery = summary.get("discovery") or {}
    extractions = summary.get("extractions") or []
    ocr_used = any(
        isinstance(ex, dict) and ex.get("extraction_method") == "ocr"
        for ex in extractions
    )
    return {
        "used":                  bool(summary.get("used", False)),
        "evidence_quality_hint": summary.get("evidence_quality_hint", "none"),
        "partial_results":       bool(summary.get("partial_results", False)),
        "chunks_indexed":        int(summary.get("chunks_indexed", 0) or 0),
        "files_supported":       int(discovery.get("files_supported", 0) or 0),
        "extraction_failures":   int(discovery.get("extraction_failures", 0) or 0),
        "scan_truncated":        bool(discovery.get("scan_truncated", False)),
        "max_files_applied":     int(discovery.get("max_files_applied", 0) or 0),
        "omitted_count":         int(discovery.get("omitted_count", 0) or 0),
        "ocr_used":              ocr_used,
        "folder_path_present":   bool(summary.get("folder_path")),
        "notes":                 list(summary.get("notes") or [])[:8],
    }


def _local_evidence_summary_for_verifier(
    scout_output: dict | None,
    result: dict | None = None,
) -> dict:
    """Extract local-document provenance + EXCERPTS for the verifier (defect 8).

    Pulls ``local_literature_evidence`` from research_scout AND
    ``local_patent_evidence`` from a sibling patent_intelligence specialist.
    Each evidence ref retains its excerpt + chunk_index + retrieval_score so
    the verifier can audit the supporting text directly.
    """
    out: dict = {}
    if isinstance(scout_output, dict):
        lit = scout_output.get("local_literature_evidence") or []
        lit_summary = scout_output.get("local_document_ingestion_summary") or {}
        if lit or lit_summary:
            out["local_literature_evidence"] = [
                _project_local_evidence_ref(e) for e in lit if isinstance(e, dict)
            ]
            out["local_literature_ingestion_summary"] = (
                _project_local_ingestion_summary(lit_summary)
            )

    if isinstance(result, dict):
        patent_output = (result.get("specialists") or {}).get("patent_intelligence")
        if isinstance(patent_output, dict):
            pat = patent_output.get("local_patent_evidence") or []
            pat_summary = patent_output.get("local_document_ingestion_summary") or {}
            if pat or pat_summary:
                out["local_patent_evidence"] = [
                    _project_local_evidence_ref(e) for e in pat if isinstance(e, dict)
                ]
                out["local_patent_ingestion_summary"] = (
                    _project_local_ingestion_summary(pat_summary)
                )
    return out


def _external_mcp_for_verifier(
    scout_output: dict | None,
    result: dict | None = None,
) -> list[dict]:
    """Collect external MCP evidence (with provenance + limitations) so the
    Scientific Verifier can see it.

    Phase 3 (MCP): external MCP evidence is SECONDARY/SUPPORTING context only.
    Each projected record keeps provider/tool/confidence/mock/limitations and a
    truncated content excerpt so the verifier can weigh it appropriately and
    never mistake it for verified primary literature.
    """
    out: list[dict] = []

    def _project(rec: dict) -> dict:
        content = rec.get("content")
        if isinstance(content, (dict, list)):
            import json as _json
            excerpt = _json.dumps(content, default=str)[:1200]
        else:
            excerpt = str(content or "")[:1200]
        return {
            "provider": rec.get("provider", ""),
            "tool_name": rec.get("tool_name", ""),
            "result_type": rec.get("result_type", ""),
            "confidence_hint": rec.get("confidence_hint", "low"),
            "mock_mode": bool(rec.get("mock_mode", False)),
            "verified_by_aura": bool(rec.get("verified_by_aura", False)),
            "sources": list(rec.get("sources") or [])[:25],
            "limitations": list(rec.get("limitations") or []),
            "excerpt": excerpt,
        }

    # Dedup sources by identity: research_scout is ALSO stored under
    # specialists["research_scout"], so naive scanning double-counts.
    sources: list = []
    seen_ids: set[int] = set()

    def _add(src) -> None:
        if isinstance(src, dict) and id(src) not in seen_ids:
            seen_ids.add(id(src))
            sources.append(src)

    if isinstance(scout_output, dict):
        _add(scout_output)
    if isinstance(result, dict):
        for v in (result.get("specialists") or {}).values():
            _add(v)
    for src in sources:
        recs = src.get("external_mcp_evidence")
        if isinstance(recs, list):
            for r in recs:
                if isinstance(r, dict):
                    out.append(_project(r))
    return out


def _build_evidence_pack(
    scout_output: dict | None,
    decision: dict,
    result: dict | None = None,
) -> dict:
    """Build a structured evidence pack from Research Scout output for the verifier."""
    if not scout_output:
        # Even with no scout output we may still want to surface local-patent
        # evidence from a sibling specialist + external MCP evidence.
        local_extras = _local_evidence_summary_for_verifier(None, result)
        ext = _external_mcp_for_verifier(None, result)
        if ext:
            local_extras = dict(local_extras)
            local_extras["external_mcp_evidence"] = ext
        return local_extras if local_extras else {}

    # ---- deep-research path (issue 12) ----
    if scout_output.get("mode") == "deep_research":
        from core import normalization as _norm
        dr_result = scout_output.get("deep_research_result") or {}
        evidence_pack_data = dr_result.get("evidence_pack") or {}
        # Defect 27: sources may be malformed.
        sources = _norm.ensure_dict_list(evidence_pack_data.get("sources"))
        top_papers = [
            {
                "title": _norm.ensure_str(s.get("title")),
                "source": _norm.ensure_str(s.get("provider"), default="deep_research"),
                "total_score": 0.0,
                "url": _norm.ensure_str(s.get("url")),
            }
            for s in sources
        ]
        sources_used = list({
            _norm.ensure_str(s.get("provider")) for s in sources
            if _norm.ensure_str(s.get("provider"))
        })
        sc_confidence = evidence_pack_data.get("confidence_summary") or "medium"
        pack = {
            "top_papers": top_papers,
            "sources_used": sources_used,
            "profile_topics": [],
            "scout_mode": "deep_research",
            "scout_confidence": sc_confidence,
        }
        pack.update(_local_evidence_summary_for_verifier(scout_output, result))
        ext = _external_mcp_for_verifier(scout_output, result)
        if ext:
            pack["external_mcp_evidence"] = ext
        return pack

    # ---- standard literature-scan path ----
    # Defect 27: top_papers may arrive as a string / dict / None from a
    # misbehaving Scout. Normalize to list[dict] before iterating, and
    # ignore non-dict entries instead of crashing on ``.get``.
    from core import normalization as _norm
    top_papers = _norm.ensure_dict_list(scout_output.get("top_papers"))
    sources_used: list[str] = []
    if scout_output.get("literature_scan_used"):
        for p in top_papers:
            src = _norm.ensure_str(p.get("source"))
            if src and src not in sources_used:
                sources_used.append(src)

    profile_topics: list[str] = []
    try:
        from integrations.research_evolution.profile import load_research_profile
        profile = load_research_profile()
        profile_topics = profile.get("research_topics", [])[:10]
    except Exception:
        pass

    pack = {
        "top_papers": top_papers,
        "sources_used": sources_used,
        "profile_topics": profile_topics,
        "scout_mode": scout_output.get("mode", ""),
        "scout_confidence": scout_output.get("confidence", ""),
    }
    pack.update(_local_evidence_summary_for_verifier(scout_output, result))
    ext = _external_mcp_for_verifier(scout_output, result)
    if ext:
        pack["external_mcp_evidence"] = ext
    return pack


def _handle_verifier_route(route: str, user_input: str, decision: dict) -> None:
    """Log routing decisions from the verifier. Re-invocation deferred to Phase 2."""
    if route in ("human_review", "reject"):
        log_approval_event({
            "trigger": "verifier_route",
            "route": route,
            "user_input": user_input,
            "governor_task_type": decision.get("task_type", ""),
        })


# ---------------------------------------------------------------------------
# Specialist runner — single entry point for any registry-backed agent
# ---------------------------------------------------------------------------

def _crash_fallback(spec: AgentSpec, exc: Exception) -> dict:
    """Uniform fallback record when a specialist crashes."""
    return {
        "agent_name": spec.name,
        "schema_version": 1,
        "summary": f"{spec.name} failed: {exc}",
        "findings": [],
        "assumptions": [],
        "risks": [f"{spec.name} crashed: {exc}"],
        "recommended_actions": [],
        "claims_for_verification": [],
        "evidence_level": "none",
        "confidence": "low",
        "approval_level": "none",
        "partial_results": True,
        "failed_stage": "agent_run",
    }


def _not_implemented_record(spec: AgentSpec) -> dict:
    """Placeholder when the governor selected an agent that has no handler yet."""
    return {
        "agent_name": spec.name,
        "schema_version": 1,
        "summary": f"{spec.name} not yet implemented (Phase 2 placeholder).",
        "findings": [],
        "assumptions": [],
        "risks": [],
        "recommended_actions": [],
        "claims_for_verification": [],
        "evidence_level": "none",
        "confidence": "low",
        "approval_level": "none",
        "partial_results": True,
        "failed_stage": "not_implemented",
    }


def _gate_specialist_actions(
    output: dict,
    spec: AgentSpec,
    user_input: str,
) -> list[dict]:
    """Apply ACTION_POLICY to a specialist's recommended_actions in place.

    Stripped 'never' actions are removed entirely. 'approval_required' actions
    are kept but logged. Returns the list of actions that need approval.
    """
    if not isinstance(output, dict):
        return []
    actions = output.get("recommended_actions", [])
    kept, needs_approval, blocked = gate_recommended_actions(actions)

    output["recommended_actions"] = kept
    if blocked:
        risks = list(output.get("risks", []))
        for b in blocked:
            risks.append(
                f"Blocked by ACTION_POLICY: {b.get('description','')[:120]} "
                f"(class={b.get('action_class','?')})"
            )
        output["risks"] = risks
    if needs_approval:
        for action in needs_approval:
            log_approval_event({
                "trigger": "action_policy",
                "agent": spec.name,
                "action": action,
                "user_input": user_input,
            })
    return needs_approval


def _build_agent_context(
    *,
    decision: dict,
    agent_configs: dict,
    scout_mode: str,
    result: dict,
    extra: dict | None = None,
) -> dict:
    """Build a context dict that every specialist receives.

    Includes the governor decision, its own result path, and the current state
    of all specialists, research scout, and per-specialist verifications.
    """
    ctx: dict[str, Any] = {
        **decision,                          # top‑level governor fields (e.g. task_type)
        "strategic_governor": decision,      # nested key for agents that expect it
        "agent_configs": agent_configs,
        "research_scout_mode": scout_mode,
        "research_scout": result.get("research_scout"),
        "specialists": dict(result.get("specialists", {})),
        "verifications": dict(result.get("verifications", {})),  # issue 7
        # Phase 4: agents use session_id to key local-document preferences.
        "session_id": result.get("session_id", ""),
    }
    if extra:
        ctx.update(extra)
    return ctx


def _run_verifier_for_specialist(
    spec_name: str,
    spec_output: dict,
    user_input: str,
    decision: dict,
    result: dict,
) -> dict:
    """Run the verifier against a single specialist output.

    Defect 1: the current specialist output is INJECTED into ``specialists``
    (and into ``research_scout`` when applicable) before the verifier sees
    the payload.  Previously the orchestrator called this BEFORE writing
    spec_output back to ``result["specialists"]``, so the verifier audited
    a session view that did NOT contain the output it was supposed to
    verify.
    """
    current_specialists = {
        k: dict(v) if isinstance(v, dict) else v
        for k, v in (result.get("specialists") or {}).items()
    }
    # Defect 1: ensure the current spec's output is present in the payload.
    current_specialists[spec_name] = spec_output

    scout_for_verifier = result.get("research_scout")
    if spec_name == "research_scout":
        scout_for_verifier = spec_output

    prior_outputs = {
        "strategic_governor": decision,
        "specialists": current_specialists,
        "research_scout": scout_for_verifier,
    }

    evidence_pack = _build_evidence_pack(scout_for_verifier, decision, result)
    import time as _time
    print(f"[scientific_verifier] starting for {spec_name} "
          f"(model {__import__('config').get_model_name()}) ...", flush=True)
    _started = _time.monotonic()
    try:
        out = verifier_module.run(user_input, prior_outputs,
                                  evidence_pack=evidence_pack)
        print(f"[scientific_verifier] completed in "
              f"{_time.monotonic() - _started:.1f}s "
              f"(route={out.get('route','?')}).", flush=True)
        return out
    except Exception:
        print(f"[scientific_verifier] failed after "
              f"{_time.monotonic() - _started:.1f}s.", flush=True)
        raise


def _run_handler_with_soft_timeout(
    spec: AgentSpec,
    user_input: str,
    context: dict,
) -> dict:
    """Invoke ``spec.handler`` under a NON-PREEMPTIVE soft timeout.

    Defect 22 — truthful semantics
    --------------------------------
    Python cannot forcibly kill a running thread, so the underlying
    handler keeps executing until it returns of its own accord.  What this
    function DOES is:

      * dispatch the handler on a background thread,
      * if ``spec.timeout_seconds`` elapses with no result, RAISE
        ``TimeoutError`` so the orchestrator's crash-fallback path
        produces a structured failure record on the caller's side,
      * call ``future.cancel()`` purely as a "do not start if not yet
        scheduled" hint — it does NOT interrupt work already in progress.

    In short: the orchestrator returns promptly to the caller, but the
    underlying agent may keep running in the background and complete
    after the timeout.  Tests should assert "the orchestrator returns
    within timeout" — they MUST NOT assert "the agent stops within
    timeout", because that guarantee is not implementable in pure Python
    without subprocess isolation.

    PROCESS-EXIT CAVEAT (review finding 3)
    --------------------------------------
    The background worker runs on a ``ThreadPoolExecutor`` thread, which
    is NOT a daemon thread.  ``pool.shutdown(wait=False)`` lets THIS
    function return immediately, but CPython will still wait for the
    in-flight worker to finish at interpreter exit (the executor
    registers an ``atexit`` hook that joins outstanding worker threads).
    So after a soft timeout:
      * the orchestrator regains control promptly (good for UX),
      * but the orphaned task keeps running, and
      * ``python``/the CLI will not fully exit until that task returns.
    If you need genuine killability (hard deadline, bounded process
    lifetime), move long-running agent execution to SUBPROCESS
    isolation — threads cannot be force-terminated in pure Python.
    """
    import concurrent.futures
    import time as _time
    timeout = max(1, int(getattr(spec, "timeout_seconds", 180) or 180))
    # UX: tell the user which agent is currently running so a long LLM
    # call doesn't look like a hang.  We always print to stdout (the CLI
    # consumes it directly); tests don't depend on this text.
    print(f"[{spec.name}] starting (soft timeout {timeout}s, model "
          f"{__import__('config').get_model_name()}) ...", flush=True)
    _started = _time.monotonic()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(spec.handler, user_input, context)
    try:
        result_value = future.result(timeout=timeout)
        print(f"[{spec.name}] completed in "
              f"{_time.monotonic() - _started:.1f}s.", flush=True)
    except concurrent.futures.TimeoutError as exc:
        future.cancel()                       # advisory — see docstring
        # IMPORTANT: shutdown(wait=False) so the orchestrator returns to
        # the caller PROMPTLY.  The handler may keep running on the
        # (NON-daemon) ThreadPoolExecutor worker — interpreter exit will
        # still join it.  See the PROCESS-EXIT CAVEAT in the docstring.
        pool.shutdown(wait=False)
        print(f"[{spec.name}] soft-timed-out after "
              f"{_time.monotonic() - _started:.1f}s.", flush=True)
        raise TimeoutError(
            f"{spec.name} did not return within its {timeout}s soft "
            "timeout (background work may still be running)"
        ) from exc
    else:
        pool.shutdown(wait=False)
        return result_value


# Back-compat alias — old call sites + tests may import the original name.
_run_handler_with_timeout = _run_handler_with_soft_timeout


# Defect 8: when can_create_external_action is False, any specialist action
# that proposes external-facing work must be ESCALATED to the policy gate
# rather than allowed to surface as `auto`.  We map these action_classes to
# "approval_required" before policy classification by re-classifying them
# in-place on the agent output.
_EXTERNAL_FACING_ACTION_CLASSES: frozenset[str] = frozenset({
    # Drafts of external-facing output.
    "draft_email", "draft_post", "draft_proposal",
    # Actual external sends / publications / shares.
    "send_email", "send_invitation", "publish_content",
    "share_data_externally",
    # External contact / coordination.
    "contact_author", "contact_investors", "schedule_meeting",
    # External submissions + commitments.
    "submit_grant", "submit_proposal", "official_commitment",
    "sign_agreement", "sign_nda", "represent_user_legally",
    # External consequential / financial / legal actions.
    "file_patent", "incorporate_company", "register_company",
    "accept_funding", "make_financial_decision", "execute_trade",
})


def _enforce_external_action_gate(output: dict, spec: AgentSpec) -> None:
    """If ``spec.can_create_external_action`` is False, strip any actions
    whose class implies external-facing output.

    Phase 1 (goal 4): the action's ``action_class`` is INFERRED first
    (via ``normalize_action_classes``) so free-text string actions and
    weakly-structured dicts (no explicit class) can no longer bypass the
    registry restriction.  After normalization every action is a dict
    with a concrete ``action_class``.
    """
    if getattr(spec, "can_create_external_action", False):
        return
    if not isinstance(output, dict):
        return
    raw_actions = output.get("recommended_actions") or []
    if not isinstance(raw_actions, list):
        return
    # Infer action_class for every action (string OR weak dict) BEFORE
    # deciding what to strip.
    actions = normalize_action_classes(raw_actions)
    filtered = []
    stripped = []
    for a in actions:
        cls = a.get("action_class", "")
        if cls in _EXTERNAL_FACING_ACTION_CLASSES:
            stripped.append(a)
            continue
        filtered.append(a)
    # Always write back the normalized list (now dicts with classes) so a
    # downstream consumer never re-sees an un-classed free-text action.
    output["recommended_actions"] = filtered
    if stripped:
        risks = list(output.get("risks", []))
        for s in stripped:
            risks.append(
                "Stripped by registry policy: "
                f"{spec.name}.can_create_external_action=False blocks "
                f"action_class={s.get('action_class','?')!r} "
                f"({s.get('description','')[:80]})"
            )
        output["risks"] = risks


def _run_specialist_step(
    spec: AgentSpec,
    user_input: str,
    context: dict,
    result: dict,
) -> dict:
    """Run one specialist + (optional) verifier-after. Returns the specialist output."""
    if not spec.implemented or spec.handler is None:
        output = _not_implemented_record(spec)
    else:
        try:
            # Defect 22: soft (non-preemptive) timeout from AgentSpec.
            output = _run_handler_with_soft_timeout(spec, user_input, context)
        except TimeoutError as exc:
            result["errors"].append({
                "agent": spec.name,
                "error": f"timeout: {exc}",
                "timeout_seconds": getattr(spec, "timeout_seconds", 180),
            })
            output = _crash_fallback(spec, exc)
        except Exception as exc:
            tb = traceback.format_exc()
            result["errors"].append({
                "agent": spec.name, "error": str(exc), "traceback": tb,
            })
            output = _crash_fallback(spec, exc)

    # Defect 8: enforce can_create_external_action BEFORE the ACTION_POLICY
    # gate so registry policy is the first filter applied.
    _enforce_external_action_gate(output, spec)

    # Apply ACTION_POLICY before anyone consults the actions
    _gate_specialist_actions(output, spec, user_input)

    # Defect 4: do NOT run the per-spec verifier when the agent paused
    # for user input — there is nothing meaningful to verify yet.
    if _output_is_awaiting_input(output):
        return output

    # Verifier-after pattern
    if spec.requires_verification and spec.implemented and spec.handler is not None:
        try:
            verification = _run_verifier_for_specialist(
                spec.name, output, user_input, result["strategic_governor"], result,
            )
            result["verifications"][spec.name] = verification
            _handle_verifier_route(
                verification.get("route", "revise"),
                user_input,
                result["strategic_governor"],
            )
        except Exception as exc:
            result["errors"].append({
                "agent": "scientific_verifier",
                "for_specialist": spec.name,
                "error": str(exc),
            })
            result["verifications"][spec.name] = {
                "overall_assessment": "incomplete",
                "route": "human_review",
                "final_recommendation": "needs_more_evidence",
                "risks": [f"Verifier failed for {spec.name}: {exc}"],
            }

    return output


# ---------------------------------------------------------------------------
# Holistic session‑wide verifier
# ---------------------------------------------------------------------------

def _run_holistic_verifier(
    user_input: str,
    decision: dict,
    result: dict,
) -> dict | None:
    """Run a single verification over *all* specialist outputs.

    This is the true session‑level verifier that feeds the retry loop
    and the human‑readable final verdict.
    """
    prior_outputs = {
        "strategic_governor": result["strategic_governor"],
        "research_scout": result.get("research_scout"),
        "specialists": result.get("specialists", {}),
    }
    evidence_pack = _build_evidence_pack(
        result.get("research_scout"), decision, result,
    )
    import time as _time
    print(f"[scientific_verifier] starting holistic session-wide pass "
          f"(model {__import__('config').get_model_name()}) ...", flush=True)
    _started = _time.monotonic()
    try:
        holistic = verifier_module.run(user_input, prior_outputs, evidence_pack=evidence_pack)
        print(f"[scientific_verifier] holistic pass completed in "
              f"{_time.monotonic() - _started:.1f}s "
              f"(route={holistic.get('route','?')}).", flush=True)
        _handle_verifier_route(
            holistic.get("route", "revise"), user_input, decision,
        )
        return holistic
    except Exception as exc:
        result["errors"].append({
            "agent": "scientific_verifier",
            "error": f"Holistic verification failed: {exc}",
        })
        return None


# ---------------------------------------------------------------------------
# Aggregate verifier route — worst-case across all specialisms
# ---------------------------------------------------------------------------

_ROUTE_PRIORITY = {
    "reject": 5,
    "human_review": 4,
    "retrieve_more_evidence": 3,
    "revise": 2,
    "approve": 1,
}

# Defect 8: explicit allowlist of routes for which the orchestrator is
# permitted to persist specialist drafts.  Anything outside this set —
# missing, empty, None, retrieve_more_evidence, human_review, reject, or a
# verifier-failure marker — fails closed.
SAFE_PERSIST_ROUTES: frozenset[str] = frozenset({"approve", "revise"})


def _failure_safe_per_spec_verification(spec_name: str, reason: str) -> dict:
    """Schema-shaped placeholder used when a per-specialist verification can
    no longer be trusted (e.g., the specialist was replaced during retry and
    we cannot or did not recompute its verification successfully).

    Route is forced to ``human_review`` so it cannot pass downstream
    persistence / learning gates.
    """
    return {
        "overall_assessment": "incomplete",
        "route": "human_review",
        "final_recommendation": "needs_more_evidence",
        "risks": [f"Per-specialist verification invalidated for '{spec_name}': {reason}"],
        "claim_checks": [],
        "revision_instructions": [],
        "contradictions": [],
        "unsupported_claims": [],
        "corrections": [],
        "assumptions": [],
        "stale_after_retry": True,
        "failed": True,
        "failure_reason": reason[:240],
    }


def _aggregate_verification_result(result: dict) -> dict:
    """Compute the single worst-case verifier from all per-specialist verifications.

    Returns a synthetic dict that mimics a verifier report.
    """
    verifications = result.get("verifications") or {}
    if not isinstance(verifications, dict) or not verifications:
        return {}
    worst_route = "approve"
    worst_score = 0
    for spec_name, verdict in verifications.items():
        if not isinstance(verdict, dict):
            continue
        route = (verdict.get("route") or "").strip().lower()
        score = _ROUTE_PRIORITY.get(route, 0)
        if score > worst_score:
            worst_score = score
            worst_route = route
    for spec_name, verdict in verifications.items():
        if not isinstance(verdict, dict):
            continue
        if (verdict.get("route") or "").strip().lower() == worst_route:
            return {
                "overall_assessment": verdict.get("overall_assessment", "incomplete"),
                "route": worst_route,
                "final_recommendation": verdict.get("final_recommendation", "needs_more_evidence"),
                "revision_instructions": list(verdict.get("revision_instructions", [])),
                "risks": list(verdict.get("risks", [])) + [
                    f"Aggregate worst-case from '{spec_name}' (route {worst_route})"
                ],
                "claim_checks": list(verdict.get("claim_checks", [])),
                "corrections": list(verdict.get("corrections", [])),
                "aggregate_source": spec_name,
            }
    return {}


def _combine_with_specialist_verdicts(
    holistic: dict | None,
    result: dict,
) -> dict | None:
    """Combine the holistic verifier verdict with all per-specialist verdicts.

    Defect 7: a per-specialist reject (or human_review) must NOT be silently
    overridden by a holistic approve.  This function takes the worst-case
    route across the holistic verdict and every per-specialist verification,
    and returns a verdict carrying that worst route.

    When the holistic verdict is already the worst, the holistic dict is
    returned (with an annotated risk for transparency).  Otherwise, a
    derived dict is built that:
        * uses the worst route,
        * preserves the holistic verdict's claim_checks (so retry logic can
          still operate on them),
        * appends the escalating specialist's revision_instructions/risks,
        * records the source specialist for auditability.
    """
    if not isinstance(holistic, dict):
        holistic = {}
    verifications = result.get("verifications") or {}
    if not isinstance(verifications, dict):
        verifications = {}

    holistic_route = (holistic.get("route") or "").strip().lower()
    worst_route = holistic_route or "approve"
    worst_score = _ROUTE_PRIORITY.get(worst_route, 0)
    worst_source: str | None = None

    for spec_name, verdict in verifications.items():
        if not isinstance(verdict, dict):
            continue
        spec_route = (verdict.get("route") or "").strip().lower()
        if not spec_route:
            continue
        spec_score = _ROUTE_PRIORITY.get(spec_route, 0)
        if spec_score > worst_score:
            worst_score = spec_score
            worst_route = spec_route
            worst_source = spec_name

    # No escalation needed — keep the holistic verdict as-is.
    if worst_source is None:
        if not holistic:
            return None
        holistic.setdefault("verdict_source", "holistic")
        return holistic

    # Escalation needed — build a combined verdict honouring the worst route.
    spec_verdict = verifications.get(worst_source, {}) or {}
    combined: dict = dict(holistic) if holistic else {}
    combined["route"] = worst_route
    combined["overall_assessment"] = spec_verdict.get(
        "overall_assessment",
        combined.get("overall_assessment", "incomplete"),
    )
    combined["final_recommendation"] = spec_verdict.get(
        "final_recommendation",
        combined.get("final_recommendation", "needs_more_evidence"),
    )
    combined["revision_instructions"] = list(
        combined.get("revision_instructions", []) or []
    ) + list(spec_verdict.get("revision_instructions", []) or [])

    # Defect B (Phase 2): the final verification object must carry enough
    # evidence to EXPLAIN the escalated route.  Preserve BOTH the holistic
    # claim_checks AND the escalating specialist's claim_checks, tagging
    # each with its ``source_agent`` so a reader can attribute every check.
    def _tag_checks(checks, source_agent: str) -> list:
        tagged = []
        for c in (checks or []):
            if isinstance(c, dict):
                c = dict(c)
                c.setdefault("source_agent", source_agent)
            tagged.append(c)
        return tagged

    combined["claim_checks"] = (
        _tag_checks(combined.get("claim_checks", []), "holistic")
        + _tag_checks(spec_verdict.get("claim_checks", []), worst_source)
    )
    combined["corrections"] = list(combined.get("corrections", []) or []) + list(
        spec_verdict.get("corrections", []) or []
    )

    escalation_rationale = (
        f"Holistic verdict '{holistic_route or '(none)'}' escalated to "
        f"'{worst_route}' by per-specialist verification of '{worst_source}'."
    )
    combined["risks"] = list(combined.get("risks", []) or []) + list(
        spec_verdict.get("risks", []) or []
    ) + [escalation_rationale]

    combined["verdict_source"] = f"holistic+specialist:{worst_source}"
    # ``source_agent`` is the canonical metadata field the spec calls for;
    # ``escalated_by`` is kept as a back-compat alias.
    combined["source_agent"] = worst_source
    combined["escalated_by"] = worst_source
    combined["escalated_from_route"] = holistic_route or ""
    combined["escalation_rationale"] = escalation_rationale
    return combined


# ---------------------------------------------------------------------------
# Auto-retry loop on verifier feedback
# ---------------------------------------------------------------------------

_RETRY_DEFAULTS = {
    "enabled_env_var":            "AURA_AUTO_RETRIEVE_EVIDENCE",
    "max_retries_env_var":        "AURA_MAX_RETRIES",
    "max_retries_default":        5,
    "max_retries_hard_cap":       6,
    "max_revise_env_var":         "AURA_MAX_REVISE_ITERATIONS",
    "max_revise_iterations":      4,
    "max_revise_iterations_cap":  5,
}

_BAD_ROUTES = {"retrieve_more_evidence", "revise"}


def _fingerprint_revisions(verifier: dict) -> str:
    import hashlib
    parts = []
    parts.append(str(verifier.get("route", "")))
    for s in (verifier.get("revision_instructions") or []):
        parts.append(str(s).strip().lower())
    for c in (verifier.get("claim_checks") or []):
        if isinstance(c, dict):
            parts.append(
                f"{c.get('severity', '')}:"
                f"{c.get('support_status', '')}:"
                f"{str(c.get('correction', '')).strip().lower()[:80]}"
            )
    blob = "|".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _auto_retrieve_evidence_enabled() -> bool:
    return os.getenv(_RETRY_DEFAULTS["enabled_env_var"], "1") != "0"


def _max_retries() -> int:
    try:
        val = int(os.getenv(
            _RETRY_DEFAULTS["max_retries_env_var"],
            str(_RETRY_DEFAULTS["max_retries_default"]),
        ))
    except (TypeError, ValueError):
        val = _RETRY_DEFAULTS["max_retries_default"]
    return max(0, min(val, _RETRY_DEFAULTS["max_retries_hard_cap"]))


def _max_revise_iterations() -> int:
    try:
        val = int(os.getenv(
            _RETRY_DEFAULTS["max_revise_env_var"],
            str(_RETRY_DEFAULTS["max_revise_iterations"]),
        ))
    except (TypeError, ValueError):
        val = _RETRY_DEFAULTS["max_revise_iterations"]
    return max(0, min(val, _RETRY_DEFAULTS["max_revise_iterations_cap"]))


def _retry_would_help(*args, **kwargs) -> bool:
    # unused stub kept for backward compatibility
    return False


def _next_retry_strategy(
    *,
    ordered_agents: list[str],
    current_scout_mode: str,
    verifier_route: str,
    strategies_used: list[str],
    revision_instructions: list[str],
    revise_iterations_used: int = 0,
    last_revision_fingerprint: str = "",
    current_revision_fingerprint: str = "",
) -> str | None:
    route = (verifier_route or "").strip().lower()
    if (
        route == "retrieve_more_evidence"
        and "literature_scan" not in strategies_used
        and "research_scout" in ordered_agents
        and (current_scout_mode or "").strip().lower() != "literature_scan"
    ):
        return "literature_scan"
    if (
        route == "revise"
        and bool(revision_instructions)
        and revise_iterations_used < _max_revise_iterations()
        and (
            last_revision_fingerprint == ""
            or last_revision_fingerprint != current_revision_fingerprint
        )
    ):
        return "revise_with_instructions"
    return None


def _run_retry_pass(
    *,
    strategy: str,
    user_input: str,
    decision: dict,
    ordered_agents: list[str],
    agent_configs: dict,
    result: dict,
    iteration: int,
    scout_mode_override: str | None = None,
    cause_verifier: dict | None = None,   # issues 10/11 — the verifier that triggered this retry
) -> None:
    if iteration == 1:
        result["pre_retry_verifier"] = dict(result.get("scientific_verifier") or {})
        result["pre_retry_specialists"] = {
            k: dict(v) if isinstance(v, dict) else v
            for k, v in (result.get("specialists") or {}).items()
        }

    # Use the cause verifier for revision instructions — ignore stale per-agent verifications.
    revision_instructions = list((cause_verifier or {}).get("revision_instructions") or [])
    corrections = list((cause_verifier or {}).get("corrections") or [])
    risks = list((cause_verifier or {}).get("risks") or [])

    for agent_name in ordered_agents:
        if agent_name in SPECIAL_AGENT_NAMES:
            continue
        spec = AGENT_REGISTRY.get(agent_name)
        if spec is None or not (spec.implemented and spec.handler is not None):
            continue

        base_ctx = _build_agent_context(
            decision=decision,
            agent_configs=agent_configs,
            scout_mode=scout_mode_override or "",
            result=result,
        )

        if strategy == "literature_scan":
            base_ctx["research_scout_mode"] = "literature_scan"
            base_ctx["retry_reason"] = "verifier_route=retrieve_more_evidence"
        elif strategy == "revise_with_instructions":
            base_ctx["retry_reason"] = "verifier_route=revise"
            base_ctx["verifier_revision_instructions"] = revision_instructions
            base_ctx["verifier_corrections"] = corrections
            base_ctx["verifier_risks"] = risks
            base_ctx["scientific_verifier"] = dict(cause_verifier) if cause_verifier else {}

        base_ctx["retry_iteration"] = iteration
        base_ctx["retry_strategy"] = strategy

        try:
            # Defect (review finding 2): retry passes MUST honour the
            # same soft-timeout budget as the normal path, otherwise a
            # retry can run unbounded and undermine the registry's
            # timeout policy.
            new_output = _run_handler_with_soft_timeout(
                spec, user_input, base_ctx,
            )
        except TimeoutError as exc:
            result["errors"].append({
                "agent": agent_name,
                "error": f"retry pass timeout: {exc}",
                "timeout_seconds": getattr(spec, "timeout_seconds", 180),
                "retry_iteration": iteration,
                "retry_strategy": strategy,
            })
            continue
        except Exception as exc:
            tb = traceback.format_exc()
            result["errors"].append({
                "agent": agent_name,
                "error": f"retry pass crashed: {exc}",
                "traceback": tb,
                "retry_iteration": iteration,
                "retry_strategy": strategy,
            })
            continue

        # Defect (review finding 1): apply the SAME safety gates, in the
        # SAME order, as _run_specialist_step.  Previously the retry pass
        # only ran _gate_specialist_actions, so an agent with
        # can_create_external_action=False could keep prohibited
        # external-facing actions on a retry that were stripped on the
        # first pass.
        _enforce_external_action_gate(new_output, spec)
        _gate_specialist_actions(new_output, spec, user_input)
        if isinstance(new_output, dict):
            new_output["retry_iteration"] = iteration
            new_output["retry_strategy"] = strategy
        result["specialists"][spec.name] = new_output
        if spec.name == "research_scout":
            result["research_scout"] = new_output

        # Defect 2: the prior per-specialist verification was computed against
        # the OLD spec output and is now stale.  The defect spec accepts
        # "recomputed OR invalidated"; we choose **invalidation** because:
        #   - The holistic verifier re-run at the end of this retry pass
        #     audits the NEW specialist outputs (defect 1 ensures the
        #     verifier sees the current spec_output in its payload).
        #   - Invalidation avoids issuing an extra LLM call per replaced
        #     specialist on every retry iteration.
        # Either way, the verifications dict MUST NOT retain a verdict that
        # no longer corresponds to the current specialist output.
        stale_verdict = result["verifications"].pop(spec.name, None)
        if isinstance(stale_verdict, dict) and stale_verdict.get("route"):
            # Record the invalidation so the audit trail explains why a
            # previously-stored per-spec verdict disappeared.
            result.setdefault("invalidated_verifications", []).append({
                "agent": spec.name,
                "retry_iteration": iteration,
                "retry_strategy": strategy,
                "former_route": stale_verdict.get("route"),
            })

    try:
        prior_outputs = {
            "strategic_governor": result["strategic_governor"],
            "research_scout": result.get("research_scout"),
            "specialists": result["specialists"],
        }
        evidence_pack = _build_evidence_pack(result.get("research_scout"), decision, result)
        new_verification = verifier_module.run(
            user_input, prior_outputs, evidence_pack=evidence_pack
        )
        new_verification["retry_iteration"] = iteration
        new_verification["retry_strategy"] = strategy
        result["scientific_verifier"] = new_verification
        _handle_verifier_route(
            new_verification.get("route", "revise"),
            user_input,
            decision,
        )
    except Exception as exc:
        result["errors"].append({
            "agent": "scientific_verifier",
            "error": f"retry pass crashed: {exc}",
            "retry_iteration": iteration,
            "retry_strategy": strategy,
        })


def _maybe_run_retry_loop(
    *,
    user_input: str,
    decision: dict,
    ordered_agents: list[str],
    scout_mode: str,
    agent_configs: dict,
    result: dict,
) -> None:
    max_n = _max_retries()
    if max_n == 0:
        return

    strategies_used: list[str] = []
    revise_iterations_used: int = 0
    current_scout_mode = scout_mode
    last_revision_fingerprint: str = ""
    history: list[dict] = []

    while result.get("retry_count", 0) < max_n:
        verifier = result.get("scientific_verifier") or {}
        route = (verifier.get("route") or "").strip().lower()
        if route not in _BAD_ROUTES:
            break

        current_fp = _fingerprint_revisions(verifier)
        revision_instructions = list((verifier.get("revision_instructions") or []))

        strategy = _next_retry_strategy(
            ordered_agents=ordered_agents,
            current_scout_mode=current_scout_mode,
            verifier_route=route,
            strategies_used=strategies_used,
            revision_instructions=revision_instructions,
            revise_iterations_used=revise_iterations_used,
            last_revision_fingerprint=last_revision_fingerprint,
            current_revision_fingerprint=current_fp,
        )
        if strategy is None:
            break

        next_iteration = result.get("retry_count", 0) + 1
        route_before = route
        fp_before = current_fp

        # Capture the verifier that *caused* this retry (issue 10)
        cause = dict(verifier)

        _run_retry_pass(
            strategy=strategy,
            user_input=user_input,
            decision=decision,
            ordered_agents=ordered_agents,
            agent_configs=agent_configs,
            result=result,
            iteration=next_iteration,
            scout_mode_override=current_scout_mode,
            cause_verifier=cause,
        )

        result["retry_count"] = next_iteration
        strategies_used.append(strategy)
        result["retry_strategies_used"] = list(strategies_used)
        result["retry_reason"] = f"strategy={strategy}"

        if strategy == "literature_scan":
            current_scout_mode = "literature_scan"
        if strategy == "revise_with_instructions":
            revise_iterations_used += 1
            last_revision_fingerprint = current_fp

        new_verifier = result.get("scientific_verifier") or {}
        new_route = (new_verifier.get("route") or "").strip().lower()
        new_fp = _fingerprint_revisions(new_verifier)
        history.append({
            "iteration": next_iteration,
            "strategy": strategy,
            "route_before": route_before,
            "route_after": new_route,
            "fingerprint_before": fp_before,
            "fingerprint_after": new_fp,
            "num_revision_instructions": len(revision_instructions),
            "revise_iterations_used": revise_iterations_used,
        })
        result["retry_history"] = history

    result["revise_iterations_used"] = revise_iterations_used


# Backward-compat shim
def _retrieve_more_evidence_retry(*args, **kwargs) -> None:
    pass


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _iter_external_mcp_sources(result: dict) -> list[dict]:
    """Return scout + specialist output dicts, deduped by identity.

    ``research_scout`` is also stored under ``specialists["research_scout"]``;
    scanning both naively double-counts its external evidence.
    """
    sources: list[dict] = []
    seen_ids: set[int] = set()

    def _add(src) -> None:
        if isinstance(src, dict) and id(src) not in seen_ids:
            seen_ids.add(id(src))
            sources.append(src)

    _add(result.get("research_scout"))
    for v in (result.get("specialists") or {}).values():
        _add(v)
    return sources


def _collect_external_mcp_records(result: dict) -> list[dict]:
    """Gather external MCP evidence records attached to scout + specialists."""
    records: list[dict] = []
    for src in _iter_external_mcp_sources(result):
        recs = src.get("external_mcp_evidence")
        if isinstance(recs, list):
            records.extend(r for r in recs if isinstance(r, dict))
    return records


def _aggregate_external_mcp_evidence(result: dict) -> dict:
    """Build the compact ``external_mcp_evidence`` summary section + warnings.

    Returns the summary dict (also stored on ``result``).  Empty/unused when
    no external MCP evidence was attached (the default, MCP-disabled case).
    """
    from core.mcp import integration as _mcp_int

    records = _collect_external_mcp_records(result)
    warnings: list[str] = []
    for src in _iter_external_mcp_sources(result):
        w = src.get("external_mcp_warnings")
        if isinstance(w, list):
            warnings.extend(w)
    summary = _mcp_int.summarize_records(records, warnings)
    result["external_mcp_evidence"] = summary
    return summary


def _apply_external_evidence_route_cap(result: dict, summary: dict) -> None:
    """Deterministically CAP (never upgrade) the final verifier route when
    external MCP evidence was used.

    Phase 3 rule: if major claims rely ONLY on external MCP summaries (no
    primary scholarly/local literature), or any external record is mock, an
    ``approve`` route is downgraded to ``revise`` — external MCP output can
    never produce a strong approval on its own.  This NEVER strengthens a
    route.
    """
    if not summary.get("used"):
        return
    verifier = result.get("scientific_verifier")
    if not isinstance(verifier, dict):
        return
    route = (verifier.get("route") or "").strip().lower()
    if route != "approve":
        return  # only ever downgrade; never touch revise/human_review/reject

    scout = result.get("research_scout") or {}
    has_primary = bool(scout.get("top_papers")) or bool(
        scout.get("local_literature_evidence")
    )
    any_mock = summary.get("mock_records", 0) > 0
    relies_only_on_external = not has_primary

    if relies_only_on_external or any_mock:
        verifier["route"] = "revise"
        verifier["final_recommendation"] = verifier.get(
            "final_recommendation", "revise"
        )
        reason = (
            "Route capped approve→revise: major claims rely on UNVERIFIED "
            "external MCP evidence"
            + (" (includes mock/synthetic records)" if any_mock else "")
            + " with no primary literature backing."
        )
        verifier["risks"] = list(verifier.get("risks", []) or []) + [reason]
        verifier["external_evidence_route_capped"] = True


def _output_is_awaiting_input(output: dict | None) -> bool:
    """Phase 1 Defect 4 — detect that a specialist has paused for user input.

    True when EITHER the output carries a ``needs_user_input`` payload OR
    ``failed_stage`` equals ``"awaiting_user_input"``.  Both forms are
    treated as a pause signal so the orchestrator skips downstream stages.
    """
    if not isinstance(output, dict):
        return False
    if output.get("needs_user_input"):
        return True
    if (output.get("failed_stage") or "").strip().lower() == "awaiting_user_input":
        return True
    return False


def _build_paused_result(
    result: dict,
    *,
    paused_by: str,
    pending_output: dict,
    completed_steps: list[str],
) -> dict[str, Any]:
    """Decorate the in-progress ``result`` with Phase 1 pause metadata and
    return it.  Downstream stages (verifier, drafts, self-evolution) are
    deliberately NOT invoked by the caller after this function runs.
    """
    pending_prompt = pending_output.get("needs_user_input") or {
        # Synthetic prompt when the agent only flagged failed_stage but
        # didn't attach a structured payload.
        "target_agent": paused_by,
        "session_id": result.get("session_id", ""),
        "message": (
            f"{paused_by} paused for user input. "
            "Provide a response via run_aura_core(..., user_responses=...)."
        ),
    }
    result["pipeline_status"] = "awaiting_user_input"
    result["paused_by"] = paused_by
    result["pending_prompt"] = pending_prompt
    result["completed_steps"] = list(completed_steps)
    result["drafts_persisted"] = False
    result["drafts_skipped_reason"] = "pipeline paused for user input"
    return result


def _dispatch_task_agent_requests(result: dict, session_id: str) -> None:
    """Dispatch task-agent requests from the Strategic Governor decision.

    Task agents are disabled by default.  When enabled, the Governor may
    include ``task_agent_requests`` in its decision — a list of
    ``{role, subtask, context}`` dicts.  Each is gated through the overlap
    registry + policy validation + runner.  Results are stored in
    ``result["task_agent_results"]`` as auxiliary evidence only and MUST
    pass through the Scientific Verifier before any final use.
    """
    try:
        from core.task_agents import is_task_agents_enabled, maybe_create_task_agent, run_task_agent
        from core.task_agents.policy import max_per_session as _max_per_session
    except ImportError:
        return  # task_agents package not installed — graceful no-op

    if not is_task_agents_enabled():
        return

    decision = result.get("strategic_governor", {}) or {}
    requests = decision.get("task_agent_requests") or []
    if not isinstance(requests, list) or not requests:
        return

    results: list[dict] = result.setdefault("task_agent_results", [])
    cap = _max_per_session()
    created = 0

    for req in requests[:cap]:
        if created >= cap:
            break
        role = (req.get("role") or req.get("requested_role") or "").strip()
        subtask = (req.get("subtask") or "").strip()
        ctx = req.get("context") or {}
        if not role or not subtask:
            continue

        dec = maybe_create_task_agent(
            session_id=session_id,
            parent_agent="orchestrator",
            requested_role=role,
            subtask=subtask,
            context=ctx,
        )

        if dec.create_agent and dec.proposed_spec:
            out = run_task_agent(dec.proposed_spec, ctx)
            results.append({
                "role": role,
                "subtask": subtask,
                "ok": out.ok,
                "summary": out.summary,
                "findings": out.findings,
                "evidence_records": out.evidence_records,
                "claims_for_verification": out.claims_for_verification,
                "limitations": out.limitations,
                "confidence": out.confidence,
                "verified_by_aura": False,
                "requires_verification": True,
            })
            created += 1
        elif dec.use_existing_agent:
            results.append({
                "role": role,
                "subtask": subtask,
                "routed_to": dec.use_existing_agent,
                "reason": dec.reason,
                "ok": True,
                "summary": f"Routed to existing agent: {dec.use_existing_agent}",
                "verified_by_aura": False,
                "requires_verification": True,
            })
        else:
            results.append({
                "role": role,
                "subtask": subtask,
                "ok": False,
                "summary": dec.reason,
                "verified_by_aura": False,
                "requires_verification": True,
            })


def run_aura_core(
    user_input: str,
    *,
    session_id: str | None = None,
    user_responses: dict | None = None,
) -> dict[str, Any]:
    """Run the AURA control plane.

    Phase 1 Defect 2 — resumable signature.  Callers that need to satisfy
    a previous ``needs_user_input`` pause pass the same ``session_id`` back
    in (so the in-memory preference store is reused) plus a
    ``user_responses`` dict mapping agent_name → response payload.

    Phase 1 Defect 4 — when any specialist returns a pause signal the
    pipeline halts immediately: no further specialists, no verifier, no
    draft persistence, no self-evolution.  The returned dict carries
    ``pipeline_status="awaiting_user_input"`` + ``session_id`` +
    ``pending_prompt`` + ``completed_steps``.
    """
    from core import local_documents as _ld
    # Defect 2: reuse the caller-supplied session_id when present so a
    # follow-up call resumes the same preference store.
    if session_id and isinstance(session_id, str):
        active_session_id = session_id
    else:
        active_session_id = _ld.new_session_id()

    # Normalise user_responses so downstream code can rely on the shape.
    if not isinstance(user_responses, dict):
        user_responses = {}

    result: dict[str, Any] = {
        "user_input": user_input,
        "session_id": active_session_id,
        "session_resumed": bool(session_id),
        "user_responses": dict(user_responses),
        "strategic_governor": {},
        "research_scout": None,
        "scientific_verifier": None,
        "self_evolution_engine": {},
        "specialists": {},
        "verifications": {},
        "errors": [],
        "pipeline_status": "in_progress",
    }
    completed_steps: list[str] = []

    # Step 1: Strategic Governor
    try:
        decision = gov_module.run(user_input)
        result["strategic_governor"] = decision
    except Exception as exc:
        result["errors"].append({"agent": "strategic_governor", "error": str(exc)})
        decision = {
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
        result["strategic_governor"] = decision

    if _patent_needed(user_input):
        selected = decision.get("selected_agents", [])
        if "patent_intelligence" not in selected:
            selected.append("patent_intelligence")
            decision["selected_agents"] = selected

    needs_approval, approval_reason = requires_human_approval(user_input)
    if needs_approval or decision.get("requires_approval"):
        log_approval_event({
            "user_input": user_input,
            "reason": approval_reason or decision.get("approval_reason", ""),
            "decision": decision,
        })

    completed_steps.append("strategic_governor")
    ordered_agents, scout_mode, agent_configs = _resolve_execution_plan(decision)

    # ── Advisory LLM Agent Planner (Stage 2, optional) ────────────────────
    # The planner augments agent selection — it may ADD agents but NEVER
    # removes Governor-selected agents.  Disabled by default; non-fatal on
    # failure.  Planner metadata is recorded in result["llm_agent_planner"].
    try:
        planner_result = _maybe_plan_agents(
            user_input, active_session_id, decision, ordered_agents,
        )
        ordered_agents = planner_result["augmented_ordered"]
        result["llm_agent_planner"] = planner_result["planner"]
    except Exception as _plan_exc:
        result["llm_agent_planner"] = {
            "enabled": False,
            "error": f"Planner hook failed (non-fatal): {_plan_exc}",
            "selected_agents": list(ordered_agents),
            "fallback_used": True,
        }
    # ──────────────────────────────────────────────────────────────────────

    # Step 4: Specialist loop (canonical order with full inter-agent context)
    for agent_name in ordered_agents:
        if agent_name in SPECIAL_AGENT_NAMES:
            continue
        spec = AGENT_REGISTRY.get(agent_name)
        if spec is None:
            result["errors"].append({
                "agent": agent_name,
                "error": "Unknown agent — not in registry.",
            })
            continue

        agent_context = _build_agent_context(
            decision=decision,
            agent_configs=agent_configs,
            scout_mode=scout_mode,
            result=result,
            # Defect 2: propagate the resumable user_responses payload so
            # agents that paused on a prior call can absorb the answer.
            extra={"user_responses": dict(user_responses)},
        )
        output = _run_specialist_step(spec, user_input, agent_context, result)
        result["specialists"][spec.name] = output
        if spec.name == "research_scout":
            result["research_scout"] = output
        completed_steps.append(spec.name)

        # Defect 4: PAUSE immediately when this specialist asked the user
        # for input.  No further specialists, no verifier, no drafts, no
        # self-evolution.  The controller resumes by calling run_aura_core
        # again with the same session_id and a populated user_responses.
        if _output_is_awaiting_input(output):
            return _build_paused_result(
                result,
                paused_by=spec.name,
                pending_output=output,
                completed_steps=completed_steps,
            )

    # ── Task-scoped agent integration (Phase 2, optional) ──────────────────
    # Task agents are disabled by default (AURA_TASK_AGENTS_ENABLED=0).
    # When enabled, the Strategic Governor may request narrow helper agents
    # via the ``task_agent_requests`` key in its decision.  Each request is
    # gated through the overlap registry + policy validation + runner, and
    # every result is marked ``verified_by_aura=False`` so the Scientific
    # Verifier (below) is the sole authority that approves them for final use.
    try:
        _dispatch_task_agent_requests(result, session_id)
    except Exception as _ta_exc:
        result["errors"].append({
            "agent": "task_agent_dispatcher",
            "error": f"Task-agent dispatch failed (non-fatal): {_ta_exc}",
        })
    # ────────────────────────────────────────────────────────────────────────

    # Step 5: Run holistic session‑wide verifier (issue 8 & 9)
    holistic = _run_holistic_verifier(user_input, decision, result)
    if holistic:
        result["scientific_verifier"] = holistic

    # Fallback holistic verifier when no specialist ran
    if result["scientific_verifier"] is None and (
        decision.get("evidence_requirement", "low") in ("medium", "high", "ultra")
        or any(v for v in result.get("verifications", {}).values())
    ):
        result["scientific_verifier"] = _run_holistic_verifier(user_input, decision, result)

    # Step 5a: Auto-retry loop — uses the holistic verifier's route directly
    # for strategy decisions (literature_scan / revise_with_instructions).
    # We intentionally do NOT apply the per-spec-escalation combiner here so
    # the retry loop remains observable and predictable based on the
    # holistic verifier's verdict.
    result["retry_count"] = 0
    if (
        _auto_retrieve_evidence_enabled()
        and isinstance(result.get("scientific_verifier"), dict)
    ):
        _maybe_run_retry_loop(
            user_input=user_input,
            decision=decision,
            ordered_agents=ordered_agents,
            scout_mode=scout_mode,
            agent_configs=agent_configs,
            result=result,
        )

    # Defect 7: combine the final holistic verdict with the
    # per-specialist verdicts so a specialist-level reject is not
    # silently overridden by a holistic approve.  This drives the final
    # persistence / learning gates only — it does not re-trigger the
    # retry loop.
    #
    # IMPORTANT (retry interaction): only combine when NO retry ran.
    # After a retry, the retry pass already re-runs a holistic
    # verification over ALL current specialist outputs (see
    # _run_retry_pass), so that post-retry verdict is authoritative.
    # Resurrecting a PRE-retry per-specialist verdict here would apply
    # stale evidence — e.g. a grant_architect "retrieve_more_evidence"
    # from pass 1 incorrectly overriding a converged post-retry
    # "approve" after the scout fetched the missing evidence.
    if result.get("retry_count", 0) == 0:
        combined = _combine_with_specialist_verdicts(
            result.get("scientific_verifier"), result,
        )
        if combined is not None:
            result["scientific_verifier"] = combined

    # Phase 3 (MCP): aggregate any external MCP evidence into the compact
    # summary section, then DETERMINISTICALLY cap the route so external
    # summaries can never produce a strong approval on their own.  This runs
    # BEFORE the persistence gate so a capped route flows through the existing
    # SAFE_PERSIST_ROUTES logic unchanged.
    _external_summary = _aggregate_external_mcp_evidence(result)
    if _external_summary.get("used"):
        _apply_external_evidence_route_cap(result, _external_summary)

    # Defect 8: persistence allowlist.  Drafts may only be saved when the
    # final verifier explicitly produced an affirmative route AND did not
    # report a failure.  Missing/None/empty verifier output, retrieve_more_
    # evidence, human_review, reject, or any failure marker fail closed.
    final_verifier = result.get("scientific_verifier")
    if isinstance(final_verifier, dict) and not final_verifier.get("failed"):
        final_route = (final_verifier.get("route") or "").strip().lower()
        if final_route in SAFE_PERSIST_ROUTES:
            try:
                from core.draft_writer import save_specialist_drafts
                written = save_specialist_drafts(result, user_input=user_input)
                # Phase 2 (goal E): drafts_persisted now TRUTHFULLY reflects a
                # successful persistence (no exception).  Carry the count +
                # paths so callers can verify what actually landed on disk.
                result["drafts_persisted"] = True
                result["drafts_persisted_count"] = len(written)
                result["drafts_persisted_paths"] = [str(p) for p in written]
            except Exception as exc:
                # Persistence failed → fail closed: do NOT claim success.
                result["drafts_persisted"] = False
                result["drafts_skipped_reason"] = f"draft persistence failed: {exc}"
                result["errors"].append({"agent": "draft_writer", "error": str(exc)})
        else:
            result["drafts_persisted"] = False
            result["drafts_skipped_reason"] = (
                f"final route '{final_route or '(missing)'}' not in safe allowlist"
            )
            # Still save the draft under pending_review/ with a loud
            # UNVERIFIED banner so the user can see what was produced.
            # This DOES NOT relax the SAFE_PERSIST_ROUTES contract — the
            # file is clearly segregated and labelled as unverified.
            try:
                from core.draft_writer import save_unverified_drafts
                paths = save_unverified_drafts(result, user_input=user_input)
                if paths:
                    print(
                        f"[draft_writer] {len(paths)} unverified draft(s) "
                        f"saved to pending_review/ (route={final_route}).",
                        flush=True,
                    )
            except Exception as exc:
                result["errors"].append(
                    {"agent": "draft_writer_unverified", "error": str(exc)}
                )
    else:
        result["drafts_persisted"] = False
        result["drafts_skipped_reason"] = (
            "verifier output is None / missing / failure — fail-closed persistence"
        )

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

    # Defect 4: normal completion marker.  Pause path returns earlier with
    # pipeline_status="awaiting_user_input"; this is the success branch.
    if result.get("pipeline_status") == "in_progress":
        result["pipeline_status"] = "complete"
    return result
