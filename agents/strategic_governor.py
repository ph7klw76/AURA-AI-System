from __future__ import annotations

from core.llm import ask_json
from core.schemas import GovernorDecision, MemoryPolicy, SelfEvolutionPolicy, WorkflowStep

ALLOWED_AGENTS = [
    "memory_retriever",
    "research_scout",
    "grant_architect",
    "china_grant_architect",
    "scientific_verifier",
    "lab_data_analyst",
    "teaching_mentor",
    "influence_public_communication",
    "collaboration_operator",
    "patent_intelligence",
    "founder_innovation",
    "human_approval_governor",
    "self_evolution_engine",
]

# Python-level safety enforcement: (substring, min_autonomy_int, requires_approval, min_risk)
_SAFETY_PATTERNS: list[tuple[str, int, bool, str]] = [
    ("send email",        5, True,  "high"),
    ("email to ",         5, True,  "high"),
    ("reply to ",         5, True,  "high"),
    ("submit grant",      5, True,  "high"),
    ("submit to journal", 5, True,  "high"),
    ("publish paper",     5, True,  "high"),
    ("post on linkedin",  5, True,  "medium"),
    ("post on twitter",   5, True,  "medium"),
    ("delete file",       5, True,  "critical"),
    ("delete folder",     5, True,  "critical"),
    ("modify profile",    4, True,  "medium"),
    ("update profile",    4, True,  "medium"),
    ("contact author",    4, True,  "medium"),
    ("share data",        4, True,  "medium"),
    ("export data",       4, True,  "medium"),
]

# Research/grant keywords that raise evidence_requirement
_HIGH_EVIDENCE_KEYWORDS = [
    "grant", "proposal", "erc", "horizon", "funding application",
    "paper", "manuscript", "journal submission",
]

SYSTEM_PROMPT = """\
You are the AURA Executive Governor — the mission-aware control layer for an AI research assistant.
The user is a photophysics / OLED / TADF / organic electronics researcher.
Core mission: protect and compound the user's research direction toward fundable, rigorous science.

Your role per request:
1. Classify the task and judge its mission relevance.
2. Select agents, order their execution, configure each one.
3. Set evidence depth, autonomy level, and approval gates.
4. Prevent unsafe or off-mission actions.
5. Control memory use and self-evolution.

--- IMPLEMENTED SPECIALISTS (you MAY include these in selected_agents and workflow_sequence) ---
research_scout, grant_architect, china_grant_architect, lab_data_analyst,
teaching_mentor, influence_public_communication, collaboration_operator,
patent_intelligence, founder_innovation

--- WHEN TO USE china_grant_architect vs grant_architect ---
china_grant_architect: ALWAYS pick this (instead of grant_architect) when the
    request mentions China, NSFC, MOST, 国家自然科学基金, "China grant", "China
    sub-mode", "China proposal", a Chinese funder or program (Key Program,
    Excellent Young Scientist, Distinguished Young, Major Research Plan), or
    asks for a proposal in Chinese.  It produces the full 24-section China
    blueprint rendered as the A-P + items 1-36 layout, with 5-reviewer
    simulation and a deterministic 100-point competitiveness score.
grant_architect: the general agent — pick this for any non-China grant
    request (ERC, NIH, NSF, Horizon, etc.) or when the funder is unspecified.
Routing rule: if BOTH terms ("China" AND "grant"/"proposal"/"funding") appear,
    you MUST select china_grant_architect, not grant_architect.

--- SPECIAL AGENTS (do NOT list these yourself) ---
scientific_verifier, self_evolution_engine, memory_retriever, human_approval_governor

YOU must not add these four to selected_agents or workflow_sequence —
they are orchestration-owned.  Decide WHETHER they run via the policy
fields (self_evolution_policy.run, memory_policy, requires_approval),
NOT by listing the agents.

NOTE (orchestration-owned membership): after your decision is parsed,
the system itself may APPEND ``self_evolution_engine`` and/or
``scientific_verifier`` to selected_agents to reflect what it will run
(driven by your policy fields).  That post-processing is expected and
correct — it is not a contradiction of this rule, which governs only
what YOU emit.

The orchestrator will:
  * always run scientific_verifier after specialists (no need to list it),
  * run self_evolution_engine at the end when self_evolution_policy.run=true,
  * route memory and human approval through its own gates.

--- TASK TYPES ---
research_scan, idea_evaluation, grant_strategy, teaching, communication,
collaboration, data_analysis, admin, deep_research, unknown

--- WHEN TO USE EACH RESEARCH-SCOUT MODE ---
idea_evaluation + research_scout_mode=ideation: user is EXPLORING or EVALUATING an idea/proposal
    without explicitly asking to search for papers. Signals: "explore", "evaluate this idea",
    "what is the opportunity", "research proposal on X", "what should I verify", "hypothesis",
    "proposal concept", "scientific strategy". Do NOT search papers — just ideate.
research_scan + research_scout_mode=literature_scan: user explicitly wants to FIND or SEARCH papers.
    Signals: "find papers", "search papers", "recent papers", "scan arXiv", "weekly brief",
    "literature review", "what papers exist".
deep_research + research_scout_mode=deep_research: user wants a MULTI-ROUND,
    EVIDENCE-FETCHING investigation that goes beyond one literature_scan pass.
    Signals: "deep dive", "deep research", "thorough investigation",
    "exhaustive review", "full landscape", "iterative search", "follow-up searches",
    "expand the evidence", "verify this systematically". The Scout will fetch
    sources, extract claims, and feed them to the verifier round-by-round.
gap_analysis: user wants the unanswered question summarised from prior papers.
grant_opportunity: user wants the funding angle / grant-relevant framing.

--- AUTONOMY LEVELS ---
L0: answer only (no search, no files)
L1: draft text in memory only
L2: search, summarise, rank, retrieve
L3: generate structured files or plans (no external action)
L4: prepare external action (draft email, outline submission) — do NOT send
L5: execute external action — REQUIRES explicit human approval

--- RISK LEVELS ---
low: no external consequence, reversible, on-mission
medium: moderate consequence or uncertainty
high: external visibility, data sharing, off-mission distraction
critical: irreversible, legal, financial, or identity-level change

--- EVIDENCE REQUIREMENT ---
low: casual Q&A, topic overview
medium: research ideation, literature context
high: grant-relevant claims, novelty assessment
ultra: peer-review-level claims, submission-ready outputs

--- MISSION ALIGNMENT SCORING ---
mission_alignment_score (0.0–1.0): how central to OLED/TADF/photophysics/organic-electronics research
strategic_value_score (0.0–1.0): long-term compounding value (grant, paper, collaboration, IP)
urgency_score (0.0–1.0): time pressure
should_this_be_done: "yes" (on-mission), "maybe" (tangential), "no" (off-mission or distracting)

--- SELF-EVOLUTION POLICY ---
run=true: session contains durable feedback, accepted/rejected outputs, recurring patterns, workflow lessons
run=false: trivial task, casual question, no durable learning expected
reason: one sentence explaining the decision

--- MEMORY POLICY ---
retrieve_memory=true for research tasks (profile, prior work, relevant memories)
allow_memory_write=false for low-value or off-mission tasks
memory_write_requires_approval=true for profile-level or identity-level updates

--- BLOCKED ACTIONS ---
Always block: auto-send emails, auto-submit grants, auto-delete files, auto-update research_profile.yaml
Always require approval: any L5 action

--- WORKFLOW SEQUENCE EXAMPLES ---

NOTE: The examples below intentionally OMIT scientific_verifier,
self_evolution_engine, memory_retriever, and human_approval_governor.
They are handled by the orchestrator and must NOT appear in your output.

research_scan:
[
  {"agent": "research_scout", "purpose": "search and rank recent literature", "mode": "literature_scan"}
]

idea_evaluation / grant_strategy:
[
  {"agent": "research_scout", "purpose": "ideate and identify gap", "mode": "ideation"},
  {"agent": "grant_architect", "purpose": "structure the proposal", "mode": "standard"}
]

teaching:
[
  {"agent": "teaching_mentor", "purpose": "generate teaching material", "mode": "standard"}
]

deep_research:
[
  {"agent": "research_scout", "purpose": "multi-round evidence fetch + claim extraction", "mode": "deep_research"}
]

--- AGENT CONFIGS ---
Provide configs only for agents in workflow_sequence.
research_scout config keys: mode, recency_window, max_papers, ranking_criteria
scientific_verifier config keys: strictness (standard|high|ultra), check_citations, check_methodology, check_overclaiming

Return STRICT JSON with EXACTLY this schema — no additional keys:
{
  "task_type": "research_scan | idea_evaluation | grant_strategy | teaching | communication | collaboration | data_analysis | admin | deep_research | unknown",
  "priority": "low | medium | high | urgent",
  "risk_level": "low | medium | high | critical",
  "mission_alignment_score": 0.0,
  "strategic_value_score": 0.0,
  "urgency_score": 0.0,
  "should_this_be_done": "yes | maybe | no",
  "autonomy_level": "L0 | L1 | L2 | L3 | L4 | L5",
  "external_consequence": "none | low | medium | high",
  "evidence_requirement": "low | medium | high | ultra",
  "requires_approval": false,
  "approval_reason": "",
  "blocked_actions": [],
  "selected_agents": [],
  "research_scout_mode": "ideation | literature_scan | gap_analysis | grant_opportunity | deep_research | none",
  "workflow_sequence": [
    {"agent": "...", "purpose": "...", "mode": "..."}
  ],
  "agent_configs": {
    "research_scout": {"mode": "...", "recency_window": "...", "max_papers": 10},
    "scientific_verifier": {"strictness": "standard", "check_citations": true, "check_methodology": true, "check_overclaiming": true}
  },
  "task_decomposition": [],
  "memory_policy": {
    "retrieve_memory": true,
    "allow_memory_write": true,
    "memory_write_requires_approval": false
  },
  "self_evolution_policy": {
    "run": true,
    "reason": "..."
  },
  "rationale": "One sentence executive summary of this decision."
}"""


def _autonomy_int(level: str) -> int:
    """Convert 'L3' → 3."""
    try:
        return int(level[1:])
    except (IndexError, ValueError):
        return 0


def _enforce_safety(decision: GovernorDecision, user_input: str) -> GovernorDecision:
    """Apply Python-level safety overrides regardless of LLM output."""
    lower = user_input.lower()
    current_level = _autonomy_int(decision.autonomy_level)

    for pattern, min_level, force_approval, min_risk in _SAFETY_PATTERNS:
        if pattern in lower:
            if current_level < min_level:
                decision.autonomy_level = f"L{min_level}"
                current_level = min_level
            if force_approval:
                decision.requires_approval = True
                if not decision.approval_reason:
                    decision.approval_reason = f"Input matches high-risk pattern: '{pattern}'"
            # Escalate risk if needed
            _RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            if _RISK_ORDER.get(decision.risk_level, 0) < _RISK_ORDER.get(min_risk, 0):
                decision.risk_level = min_risk

    # External consequence → require approval for L5
    if current_level >= 5 and not decision.requires_approval:
        decision.requires_approval = True
        decision.approval_reason = decision.approval_reason or "L5 action requires explicit human approval."

    return decision


def _enforce_evidence_depth(decision: GovernorDecision, user_input: str) -> GovernorDecision:
    """Raise evidence_requirement for grant/paper submissions."""
    lower = user_input.lower()
    _EV_ORDER = {"low": 0, "medium": 1, "high": 2, "ultra": 3}
    needed = _EV_ORDER.get(decision.evidence_requirement, 1)
    for kw in _HIGH_EVIDENCE_KEYWORDS:
        if kw in lower and needed < 2:
            decision.evidence_requirement = "high"
            break
    return decision


# ---------------------------------------------------------------------------
# Phase 2 keyword-based routing for all implemented specialists.
# The keywords ensure deterministic activation regardless of LLM behaviour.
# ---------------------------------------------------------------------------

_GRANT_ARCHITECT_KEYWORDS: tuple[str, ...] = (
    "grant proposal", "proposal structure", "fundable", "funding angle",
    "work package", "work packages", "central hypothesis", "specific aims",
    "proposal draft", "grant concept",
    "research proposal", "research grant",
    "draft a grant", "draft the grant", "draft me a grant",
    "draft a research grant", "draft me a research grant",
    "draft a proposal", "draft the proposal", "draft me a proposal",
    "build a proposal", "create a proposal", "structure a proposal",
    "build a grant", "create a grant", "structure a grant",
    "grant for", "grant to", "grant on",
    "funding application", "apply for funding",
    "reviewer attack", "reviewer panel", "objectives for the grant",
)

# Triggers that promote a grant_architect routing into the China sub-mode.
# Match is case-insensitive substring; ANY hit promotes the route.
_CHINA_GRANT_KEYWORDS: tuple[str, ...] = (
    "china grant", "china proposal", "china sub-mode", "china sub mode",
    "china-tailored", "china tailored", "china funder",
    "nsfc", "国家自然科学基金", "国自然",
    "national natural science foundation of china",
    "most china", "china most",   # MOST = Ministry of Science & Tech
    "key program",                # nsfc key program
    "excellent young scientist", "distinguished young scholar",
    "major research plan", "中国基金", "中国 申请",
    "invoke the china sub-mode", "invoke china sub-mode",
    "run_china",
)

_TEACHING_MENTOR_KEYWORDS: tuple[str, ...] = (
    "teach this", "teach it", "teach the", "teach my",
    "teaching material", "teaching module", "teaching plan",
    "tutorial", "lecture", "lesson plan", "class activity", "classroom",
    "quiz", "rubric", "assessment rubric",
    "learning outcome", "learning outcomes",
    "socratic", "misconception", "misconceptions",
    "explain to undergraduate", "explain to graduate", "explain to students",
    "for undergraduate students", "for graduate students",
    "to undergraduate students", "to graduate students",
    "undergraduate students", "graduate students",
    "for my students", "to my students", "to my class", "for a class",
    "phd student", "phd students", "course material", "course on",
)

_LAB_DATA_ANALYST_KEYWORDS: tuple[str, ...] = (
    "analyze my data", "analyse my data", "analyze the data", "analyse the data",
    "data analysis", "analysis plan", "j-v-l data", "j-v data", "i-v data",
    "current density", "luminance vs voltage", "photoluminescence data",
    "tcspc", "transient absorption", "fitting the data", "fit the data",
    "plot the data", "plot current density", "plot luminance",
    "reproducibility check", "reproducibility checks", "reproducibility steps",
    "calibration", "raw data", "csv file", "spectroscopy data",
    "fluorescence decay", "absorption spectrum",
)

_INFLUENCE_PUBLIC_COMMUNICATION_KEYWORDS: tuple[str, ...] = (
    "linkedin post", "linkedin draft", "twitter post", "tweet draft",
    "blog post", "blog draft", "outreach post",
    "public-facing", "public facing", "public communication",
    "general audience", "lay audience", "for the public", "to the public",
    "podcast angle", "podcast pitch", "press release",
    "narrative angle", "communication draft", "outreach language",
    "explain to the public", "explanation for the public",
)

_COLLABORATION_OPERATOR_KEYWORDS: tuple[str, ...] = (
    "collaborator", "collaborators", "collaboration", "collaborate",
    "contact author", "contact collaborator", "email collaborator",
    "draft an email to", "draft email to",
    "research partner", "industry partner", "potential partner",
    "partnership",
    "meeting agenda", "follow-up email", "follow up email",
    "invite speaker", "invite a speaker", "webinar speaker", "guest speaker",
    "speaker for", "speaker on",
    "strategic contact", "strategic introduction",
    "co-pi", "co-investigator",
    "outreach to",
)

_FOUNDER_INNOVATION_KEYWORDS: tuple[str, ...] = (
    "startup", "spin-off", "spinout", "spin out",
    "commercialization", "commercialise", "commercialize", "commercialisation",
    "business model", "go-to-market", "go to market",
    "product idea", "product hypothesis", "product-market fit",
    "value proposition", "technical moat",
    "intellectual property", "patentability", "freedom to operate",
    "license this", "license technology",
    "venture", "investor", "investors", "fundraise",
    "founder", "co-founder",
    "market opportunity", "market size",
    "customer discovery", "innovation pathway",
)


def _keyword_specialist_agents(user_input: str) -> list[str]:
    """Return ALL specialist names whose keywords match the user input.

    Covers Wave 1 (grant, teaching), Wave 2 (lab, influence), and
    Wave 3 (collaboration, founder) implemented agents.
    """
    text = (user_input or "").lower()
    found: list[str] = []
    grant_hit = any(k in text for k in _GRANT_ARCHITECT_KEYWORDS)
    china_hit = any(k in text for k in _CHINA_GRANT_KEYWORDS)
    # China-grant override: any China-funder signal promotes the routing
    # into the specialised sub-mode.  Both "grant + China" and "China
    # only" (e.g. "Invoke the China sub-mode") trigger the swap.
    if china_hit:
        found.append("china_grant_architect")
    elif grant_hit:
        found.append("grant_architect")
    if any(k in text for k in _TEACHING_MENTOR_KEYWORDS):
        found.append("teaching_mentor")
    if any(k in text for k in _LAB_DATA_ANALYST_KEYWORDS):
        found.append("lab_data_analyst")
    if any(k in text for k in _INFLUENCE_PUBLIC_COMMUNICATION_KEYWORDS):
        found.append("influence_public_communication")
    if any(k in text for k in _COLLABORATION_OPERATOR_KEYWORDS):
        found.append("collaboration_operator")
    if any(k in text for k in _FOUNDER_INNOVATION_KEYWORDS):
        found.append("founder_innovation")
    return found


# ---------------------------------------------------------------------------
# Canonical agent execution order
# ---------------------------------------------------------------------------

# SINGLE SOURCE OF TRUTH for specialist ordering: import the canonical
# specialist order and bookend it with the orchestration-owned special
# agents.  This keeps the Governor's reported order aligned with the
# order the orchestrator actually executes (review findings 6 + 7).
from core.aura_principles import CANONICAL_AGENT_ORDER as _CANONICAL_AGENT_ORDER
_AGENT_ORDER: tuple[str, ...] = (
    ("memory_retriever",)
    + _CANONICAL_AGENT_ORDER
    + ("scientific_verifier", "self_evolution_engine")
)


def _order_agents(selected: list[str]) -> list[str]:
    """Reorder selected_agents to canonical execution order.

    Unknown agents (shouldn't happen) are placed before the verifier so
    their output is still visible.
    """
    seen: set[str] = set()
    deduped: list[str] = []
    for a in selected:
        if a not in seen:
            deduped.append(a)
            seen.add(a)

    selected_set = set(deduped)
    ordered: list[str] = [a for a in _AGENT_ORDER if a in selected_set]
    unknown: list[str] = [a for a in deduped if a not in _AGENT_ORDER]

    if unknown:
        if "scientific_verifier" in ordered:
            idx = ordered.index("scientific_verifier")
            ordered = ordered[:idx] + unknown + ordered[idx:]
        else:
            ordered.extend(unknown)
    return ordered


# Keyword-based mode correction mirrors research_scout._resolve_mode so the
# governor's research_scout_mode field is always consistent with what the scout
# will actually use.
#
# Defect 13: deep_research now has explicit keyword routing so the governor's
# planning agrees with what the Scout can actually execute.  Order matters —
# deep_research is checked BEFORE literature_scan because "deep dive into
# arxiv papers" should route to deep_research, not the single-pass scan.
_GOVERNOR_MODE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("deep_research", [
        "deep research", "deep dive", "deep investigation",
        "thorough investigation", "exhaustive review",
        "iterative search", "iterative investigation",
        "multi-round search", "multi round search",
        "follow-up searches", "expand the evidence",
        "full landscape investigation",
        "systematic review",
    ]),
    ("gap_analysis", ["gap analysis", "research gap", "identify gap", "what is the gap",
                      "gap in the literature"]),
    ("grant_opportunity", ["grant opportunity", "funding angle", "grant-relevant",
                           "write a grant", "grant call", "grant application"]),
    ("literature_scan", ["find papers", "search papers", "recent papers", "literature scan",
                         "arxiv", "openalex", "weekly brief", "top papers", "score papers",
                         "paper ranking", "latest papers", "literature review"]),
    ("ideation", ["research idea", "proposal concept", "hypothesis", "grant angle",
                  "scientific strategy", "evaluate this idea", "explore"]),
]


def _derive_backward_compat(decision: GovernorDecision, user_input: str = "") -> GovernorDecision:
    """Ensure legacy fields are consistent with the new structured fields."""
    if decision.workflow_sequence and not decision.selected_agents:
        seen: list[str] = []
        for step in decision.workflow_sequence:
            if step.agent and step.agent not in seen and step.agent != "strategic_governor":
                seen.append(step.agent)
        decision.selected_agents = seen

    if (
        decision.self_evolution_policy.run
        and "self_evolution_engine" not in decision.selected_agents
    ):
        decision.selected_agents.append("self_evolution_engine")

    if not decision.self_evolution_policy.run:
        decision.selected_agents = [
            a for a in decision.selected_agents if a != "self_evolution_engine"
        ]

    decision.selected_agents = [a for a in decision.selected_agents if a in ALLOWED_AGENTS]

    if not decision.research_scout_mode or decision.research_scout_mode == "none":
        for step in decision.workflow_sequence:
            if step.agent == "research_scout" and step.mode:
                decision.research_scout_mode = step.mode
                break

    if user_input:
        lower = user_input.lower()
        for mode, keywords in _GOVERNOR_MODE_KEYWORDS:
            if any(kw in lower for kw in keywords):
                decision.research_scout_mode = mode
                if mode == "ideation" and decision.task_type not in ("idea_evaluation", "grant_strategy"):
                    decision.task_type = "idea_evaluation"
                # Defect 13: deep_research keyword routing must also align
                # task_type and ensure the Scout is selected, so the formal
                # plan matches the Scout's actual capability.
                if mode == "deep_research":
                    if decision.task_type not in ("deep_research",):
                        decision.task_type = "deep_research"
                    if "research_scout" not in decision.selected_agents:
                        decision.selected_agents.insert(0, "research_scout")
                    # Deep research is high-evidence by nature.
                    if decision.evidence_requirement in ("low", "medium"):
                        decision.evidence_requirement = "high"
                break

    # Deterministic keyword routing for all implemented specialists
    if user_input:
        keyword_specialists = _keyword_specialist_agents(user_input)
        for agent_name in keyword_specialists:
            if agent_name not in decision.selected_agents:
                decision.selected_agents.append(agent_name)

        # Pairing rules
        # If china_grant_architect is selected, DEMOTE the general
        # grant_architect so we don't run two grant drafts in one
        # session (they would compete for context and confuse the user).
        if "china_grant_architect" in decision.selected_agents:
            decision.selected_agents = [
                a for a in decision.selected_agents if a != "grant_architect"
            ]
            if "research_scout" not in decision.selected_agents:
                decision.selected_agents.insert(0, "research_scout")
            if "scientific_verifier" not in decision.selected_agents:
                decision.selected_agents.append("scientific_verifier")
            if decision.task_type in ("", "unknown", "research_scan", "idea_evaluation"):
                decision.task_type = "grant_strategy"
            # China grants always require strong evidence backing.
            if decision.evidence_requirement in ("low", "medium"):
                decision.evidence_requirement = "high"
            # CRITICAL: grant drafting needs REAL papers backing every
            # quantitative claim.  If the Governor LLM chose ``ideation``
            # (which does NOT search papers — see line 95 of the prompt),
            # the China draft will end up with empty References.  Upgrade
            # the mode to ``literature_scan`` so Scout actually fetches.
            if decision.research_scout_mode in ("", "none", "ideation"):
                decision.research_scout_mode = "literature_scan"

        if "grant_architect" in decision.selected_agents:
            if "research_scout" not in decision.selected_agents:
                decision.selected_agents.insert(0, "research_scout")
            if "scientific_verifier" not in decision.selected_agents:
                decision.selected_agents.append("scientific_verifier")
            if decision.task_type in ("", "unknown", "research_scan", "idea_evaluation"):
                decision.task_type = "grant_strategy"
            if decision.evidence_requirement in ("low", "medium"):
                decision.evidence_requirement = "high"
            # Same fix as above: grants need paper-fetching, not ideation.
            if decision.research_scout_mode in ("", "none", "ideation"):
                decision.research_scout_mode = "literature_scan"

        if "teaching_mentor" in decision.selected_agents:
            if "scientific_verifier" not in decision.selected_agents:
                decision.selected_agents.append("scientific_verifier")
            _REAL_SCOUT_MODES = {
                "literature_scan", "ideation", "gap_analysis", "grant_opportunity",
            }
            if decision.research_scout_mode in _REAL_SCOUT_MODES:
                if "research_scout" not in decision.selected_agents:
                    decision.selected_agents.insert(0, "research_scout")

        if "lab_data_analyst" in decision.selected_agents:
            if "scientific_verifier" not in decision.selected_agents:
                decision.selected_agents.append("scientific_verifier")

        if "influence_public_communication" in decision.selected_agents:
            if "scientific_verifier" not in decision.selected_agents:
                decision.selected_agents.append("scientific_verifier")
            _REAL_SCOUT_MODES_PUB = {
                "literature_scan", "ideation", "gap_analysis", "grant_opportunity",
            }
            if decision.research_scout_mode in _REAL_SCOUT_MODES_PUB:
                if "research_scout" not in decision.selected_agents:
                    decision.selected_agents.insert(0, "research_scout")
            if decision.evidence_requirement in ("low", "medium"):
                decision.evidence_requirement = "high"

        if "collaboration_operator" in decision.selected_agents:
            if "scientific_verifier" not in decision.selected_agents:
                decision.selected_agents.append("scientific_verifier")
            _REAL_SCOUT_MODES_COLLAB = {
                "literature_scan", "ideation", "gap_analysis", "grant_opportunity",
            }
            if decision.research_scout_mode in _REAL_SCOUT_MODES_COLLAB:
                if "research_scout" not in decision.selected_agents:
                    decision.selected_agents.insert(0, "research_scout")

        if "founder_innovation" in decision.selected_agents:
            if "scientific_verifier" not in decision.selected_agents:
                decision.selected_agents.append("scientific_verifier")
            _REAL_SCOUT_MODES_FOUNDER = {
                "literature_scan", "ideation", "gap_analysis", "grant_opportunity",
            }
            if decision.research_scout_mode in _REAL_SCOUT_MODES_FOUNDER:
                if "research_scout" not in decision.selected_agents:
                    decision.selected_agents.insert(0, "research_scout")
            if decision.evidence_requirement in ("low", "medium"):
                decision.evidence_requirement = "high"

        decision.selected_agents = [a for a in decision.selected_agents if a in ALLOWED_AGENTS]
        decision.selected_agents = _order_agents(decision.selected_agents)

    return decision


def run(user_input: str) -> dict:
    user_prompt = (
        f"User request:\n{user_input}\n\n"
        "Return your executive decision as strict JSON."
    )
    try:
        raw = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.1)

        if isinstance(raw.get("memory_policy"), dict):
            raw["memory_policy"] = MemoryPolicy(**raw["memory_policy"])
        if isinstance(raw.get("self_evolution_policy"), dict):
            raw["self_evolution_policy"] = SelfEvolutionPolicy(**raw["self_evolution_policy"])
        if isinstance(raw.get("workflow_sequence"), list):
            raw["workflow_sequence"] = [
                WorkflowStep(**s) if isinstance(s, dict) else s
                for s in raw["workflow_sequence"]
            ]

        decision = GovernorDecision(**raw)
    except Exception as exc:
        return GovernorDecision(
            task_type="unknown",
            priority="medium",
            selected_agents=["scientific_verifier", "self_evolution_engine"],
            research_scout_mode="none",
            requires_approval=True,
            approval_reason=f"Governor failed to parse decision; human review required before consequential action.",
            risk_level="medium",
            autonomy_level="L1",
            external_consequence="none",
            evidence_requirement="high",
            mission_alignment_score=0.0,
            strategic_value_score=0.0,
            urgency_score=0.0,
            should_this_be_done="maybe",
            blocked_actions=["All consequential actions blocked — governor parse failure."],
            self_evolution_policy=SelfEvolutionPolicy(run=True, reason="Parse failure — log for diagnosis."),
            rationale=f"Fallback decision — governor parse error: {exc}",
        ).model_dump()

    decision = _enforce_safety(decision, user_input)
    decision = _enforce_evidence_depth(decision, user_input)
    decision = _derive_backward_compat(decision, user_input)

    return decision.model_dump()
