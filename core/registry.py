"""
AURA Agent Registry — single source of truth for which agents exist, what they
do, what autonomy they default to, and whether the verifier must run after them.

The orchestrator discovers agents through this registry. It never imports a
specific specialist module. Adding a Phase 2 agent means:
    1. Implement the agent in agents/<name>.py with a run() function.
    2. Set implemented=True on its AgentSpec entry below.
    3. Provide a handler closure that adapts run() to (user_input, context) -> dict.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# Defer agent imports to handler closures so test patches (which target
# agents.<name>.run) are picked up at call time, not registry-load time.


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

def _AgentSpec_factory(*args, **kwargs) -> "AgentSpec":
    """Defect 23 — tolerate legacy ``default_autonomy``/``can_use_tools``
    kwargs from older fixtures by silently dropping them before the real
    dataclass constructor runs.  Those fields were never enforced; keeping
    them would be misleading registry metadata."""
    kwargs.pop("default_autonomy", None)
    kwargs.pop("can_use_tools", None)
    return _AgentSpec_base(*args, **kwargs)


@dataclass(frozen=True)
class _AgentSpec_base:
    """Agent registry entry.

    Defect 23 — only fields with REAL runtime enforcement are kept here:

      * ``requires_verification``      — read by orchestrator to fire the
                                          Scientific Verifier after the agent.
      * ``can_create_external_action`` — read by orchestrator to strip
                                          external-facing action_class entries.
      * ``timeout_seconds``            — soft (non-preemptive) timeout
                                          enforced by ``_run_handler_with_soft_timeout``.
      * ``implemented``                — gates the registry's specialist loop.

    The earlier ``default_autonomy`` and ``can_use_tools`` fields were
    declared but never read by any code path.  They have been removed to
    keep registry governance truthful — Phase 1 defect 23.  Legacy kwargs
    using those names are accepted (and ignored) via the public
    ``AgentSpec(...)`` factory below.
    """
    name: str
    description: str
    handler: Optional[Callable[[str, dict], dict]]  # (user_input, context) -> dict
    requires_verification: bool = False
    can_create_external_action: bool = False
    timeout_seconds: int = 180
    implemented: bool = True


# Public symbol — calls go through the factory so old kwargs don't break.
AgentSpec = _AgentSpec_factory


# ---------------------------------------------------------------------------
# Handlers — thin closures so unittest.mock.patch on agents.<x>.run still works
# ---------------------------------------------------------------------------

def _scout_handler(user_input: str, context: dict) -> dict:
    import agents.research_scout as scout_module
    mode = context.get("research_scout_mode", "ideation") or "ideation"
    return scout_module.run(user_input, context=context, mode=mode)


def _grant_architect_handler(user_input: str, context: dict) -> dict:
    import agents.grant_architect as grant_module
    return grant_module.run(user_input, context=context)


def _china_grant_architect_handler(user_input: str, context: dict) -> dict:
    """China-tailored Grant Architect sub-mode.

    The China code now lives INSIDE ``agents.grant_architect`` as
    ``run_china`` — the two modes share one auditable codepath rather
    than living in parallel module trees.  Bounded extension: never
    replaces the general Grant Architect, and CAN consume its output as
    a starting backbone IF supplied — though in default routing the
    Strategic Governor demotes the general grant_architect when this
    sub-mode is selected, so the backbone is usually absent and the
    architect drafts from Scout + the China blueprint directly.
    Contract enforced by
    ``core.aura_principles.assert_china_grant_draft_contract``.
    """
    import agents.grant_architect as grant_module
    return grant_module.run_china(user_input, context=context)


def _teaching_mentor_handler(user_input: str, context: dict) -> dict:
    import agents.teaching_mentor as teaching_module
    return teaching_module.run(user_input, context=context)


def _lab_data_analyst_handler(user_input: str, context: dict) -> dict:
    import agents.lab_data_analyst as lab_module
    return lab_module.run(user_input, context=context)


def _influence_public_communication_handler(user_input: str, context: dict) -> dict:
    import agents.influence_public_communication as influence_module
    return influence_module.run(user_input, context=context)


def _collaboration_operator_handler(user_input: str, context: dict) -> dict:
    import agents.collaboration_operator as collab_module
    return collab_module.run(user_input, context=context)


def _founder_innovation_handler(user_input: str, context: dict) -> dict:
    import agents.founder_innovation as founder_module
    return founder_module.run(user_input, context=context)


def _patent_intelligence_handler(user_input: str, context: dict) -> dict:
    import agents.patent_intelligence as patent_module
    return patent_module.run(user_input, context=context)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

AGENT_REGISTRY: dict[str, AgentSpec] = {
    # --- Phase 1: implemented ---
    "research_scout": AgentSpec(
        name="research_scout",
        description="Opportunity intelligence: ideation, literature scan, gap analysis, grant_opportunity.",
        handler=_scout_handler,
        default_autonomy="L2",
        requires_verification=True,
        can_use_tools=True,
        can_create_external_action=False,
        # literature_scan mode runs query-planner + paper discovery (10
        # queries × N providers) + LLM-based scoring of ~50 papers + gap
        # analysis.  The default 180 s budget is too tight for that on
        # remote reasoning models; bump to 1800 s so a real run can finish
        # comfortably even on slower thinking models.  Ideation mode is
        # much cheaper and finishes well under this.
        timeout_seconds=1800,
    ),

    # --- Phase 1: implemented but invoked specially by the orchestrator ---
    # (verifier and self-evolution have non-uniform call signatures and run
    #  outside the regular specialist loop)
    "scientific_verifier": AgentSpec(
        name="scientific_verifier",
        description="Claim-level verifier — runs after each requires_verification specialist.",
        handler=None,
        default_autonomy="L1",
        requires_verification=False,
    ),
    "self_evolution_engine": AgentSpec(
        name="self_evolution_engine",
        description="Session-level lesson extraction and governance.",
        handler=None,
        default_autonomy="L1",
        requires_verification=False,
    ),

    # --- Phase 2 Wave 1: implemented ---
    "grant_architect": AgentSpec(
        name="grant_architect",
        description="Convert research-scout outputs or user-provided opportunities into draft proposal logic, with verifier review applied after generation.",
        handler=_grant_architect_handler,
        default_autonomy="L3",
        requires_verification=True,
        can_create_external_action=True,    # drafts proposals — never submits
        implemented=True,
    ),
    "china_grant_architect": AgentSpec(
        name="china_grant_architect",
        description=(
            "China-tailored grant proposal architect. Specialised submodule "
            "of the general grant_architect: consumes Scout output "
            "(including local-document evidence), and CAN consume general "
            "Grant Architect output as a backbone IF supplied — though in "
            "default routing the Governor demotes the general grant_architect "
            "when this agent is selected, so it usually drafts from Scout + "
            "the China blueprint directly.  Produces a 24-section China "
            "proposal draft with 5-reviewer simulation, deterministic "
            "competitiveness score, and weakness-repair plan.  approval_level "
            "is locked to draft_only — module can never submit or alter "
            "official files.  Always reviewed by Scientific Verifier."
        ),
        handler=_china_grant_architect_handler,
        default_autonomy="L3",
        requires_verification=True,
        can_create_external_action=True,    # drafts proposals — never submits
        implemented=True,
        # Chunked drafting issues 5 LLM calls (framing + 3 section chunks +
        # reviewer simulation).  At 30-40 s per call on remote thinking
        # models, the default 180 s soft timeout is far too tight — bump
        # to 1800 s (matches research_scout) so a real run can finish.
        timeout_seconds=1800,
    ),
    "teaching_mentor": AgentSpec(
        name="teaching_mentor",
        description="Convert research into teaching material, quizzes, rubrics.",
        handler=_teaching_mentor_handler,
        default_autonomy="L2",
        requires_verification=True,
        implemented=True,
    ),

    # --- Phase 2 Wave 2: implemented ---
    "lab_data_analyst": AgentSpec(
        name="lab_data_analyst",
        description="Local data-analysis planning, plotting, reproducibility checks. Read-only — never modifies raw data.",
        handler=_lab_data_analyst_handler,
        default_autonomy="L2",
        requires_verification=True,
        can_use_tools=True,
        can_create_external_action=False,    # planning only — no destructive ops
        implemented=True,
    ),
    "influence_public_communication": AgentSpec(
        name="influence_public_communication",
        description="Public-facing communication drafts, narrative angles, outreach language. Drafts only — never publishes.",
        handler=_influence_public_communication_handler,
        default_autonomy="L3",
        requires_verification=True,
        can_create_external_action=True,    # drafts public posts — never publishes
        implemented=True,
    ),
    # --- Phase 2 Wave 3: implemented ---
    "collaboration_operator": AgentSpec(
        name="collaboration_operator",
        description="Suggest collaborators, draft outreach emails / agendas, organize collaboration logic. Drafts only — never sends or schedules.",
        handler=_collaboration_operator_handler,
        default_autonomy="L3",
        requires_verification=True,
        can_create_external_action=True,    # drafts emails — never sends
        implemented=True,
    ),
    "founder_innovation": AgentSpec(
        name="founder_innovation",
        description="Commercialization pathways, product hypotheses, validation steps. Strategic analysis only — never legal/financial/IP advice.",
        handler=_founder_innovation_handler,
        default_autonomy="L2",
        requires_verification=True,
        can_create_external_action=False,
        implemented=True,
        # Commercialization analysis produces ~4-8 KB of structured JSON
        # (scorecard, IP considerations, market assumptions, validation
        # experiments, 90-day plan, key_risks, etc.).  On thinking models
        # this can run 5-15 minutes — bump to 1200 s.
        timeout_seconds=1200,
    ),

    # --- Patent Intelligence (Stage 1 — provider-neutral web reconnaissance) ---
    "patent_intelligence": AgentSpec(
        name="patent_intelligence",
        description=(
            "Stage 1 patent-landscape reconnaissance using a provider-neutral "
            "web-search subsystem (SearXNG, a no-key web provider such as "
            "google_web_no_key / duckduckgo_html, or mock) to discover publicly "
            "indexed patent pages on patents.google.com, patentscope.wipo.int, "
            "and uspto.gov. Web-scraped, NOT API-verified, non-exhaustive. NOT "
            "legal advice and NOT a freedom-to-operate analysis."
        ),
        handler=_patent_intelligence_handler,
        default_autonomy="L2",
        requires_verification=True,
        can_use_tools=True,
        can_create_external_action=False,
        implemented=True,
        # The rigorous claim-centric pipeline (Algorithms 1-4 of
        # revised_patent_analysis_rigorous.docx) issues 1 topic-decompose
        # call + ~N/batch_size batched extractions + N relevance scorings.
        # On a 14-patent COLD corpus (no cache) that can take 200-300s on
        # deepseek-v4-flash.  Subsequent runs hit the per-patent profile
        # cache and finish in 30-60s.  1200s is the comfortable cold-cache
        # ceiling.
        timeout_seconds=1200,
    ),

    # --- Pre-registered governor names that are not Phase 2 specialists ---
    "memory_retriever": AgentSpec(
        name="memory_retriever",
        description="Profile and prior-memory retrieval pre-step.",
        handler=None,
        default_autonomy="L0",
        implemented=False,
    ),
    "human_approval_governor": AgentSpec(
        name="human_approval_governor",
        description="Approval routing meta-agent.",
        handler=None,
        default_autonomy="L0",
        implemented=False,
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Names invoked specially by the orchestrator (not via the specialist loop)
SPECIAL_AGENT_NAMES: frozenset[str] = frozenset({
    "scientific_verifier",
    "self_evolution_engine",
    "memory_retriever",
    "human_approval_governor",
    "strategic_governor",
})


def get_spec(name: str) -> Optional[AgentSpec]:
    return AGENT_REGISTRY.get(name)


def implemented_specialists() -> list[str]:
    """Names of specialists that run via the regular specialist loop."""
    return [
        n for n, s in AGENT_REGISTRY.items()
        if s.implemented and s.handler is not None and n not in SPECIAL_AGENT_NAMES
    ]


def is_implemented(name: str) -> bool:
    spec = AGENT_REGISTRY.get(name)
    return bool(spec and spec.implemented and spec.handler is not None)
