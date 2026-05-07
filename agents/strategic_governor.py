from __future__ import annotations

from core.llm import ask_json
from core.schemas import GovernorDecision, MemoryPolicy, SelfEvolutionPolicy, WorkflowStep

ALLOWED_AGENTS = [
    "memory_retriever",
    "research_scout",
    "grant_architect",
    "scientific_verifier",
    "lab_data_analyst",
    "teaching_mentor",
    "influence_engine",
    "collaboration_operator",
    "founder_innovation_agent",
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

--- ALLOWED AGENTS ---
memory_retriever, research_scout, grant_architect, scientific_verifier,
lab_data_analyst, teaching_mentor, influence_engine, collaboration_operator,
founder_innovation_agent, human_approval_governor, self_evolution_engine

For the current AURA build, only these are implemented:
research_scout, scientific_verifier, self_evolution_engine

Always include self_evolution_engine last if self_evolution_policy.run is true.

--- TASK TYPES ---
research_scan, idea_evaluation, grant_strategy, teaching, communication,
collaboration, data_analysis, admin, unknown

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

research_scan:
[
  {"agent": "memory_retriever", "purpose": "load profile and prior research memory", "mode": "targeted"},
  {"agent": "research_scout", "purpose": "search and rank recent literature", "mode": "literature_scan"},
  {"agent": "scientific_verifier", "purpose": "verify novelty and evidence quality", "mode": "standard"},
  {"agent": "self_evolution_engine", "purpose": "extract session lessons", "mode": "standard"}
]

idea_evaluation / grant_strategy:
[
  {"agent": "memory_retriever", "purpose": "load profile, prior proposals, relevant lessons", "mode": "targeted"},
  {"agent": "research_scout", "purpose": "ideate and identify gap", "mode": "ideation"},
  {"agent": "scientific_verifier", "purpose": "stress-test claims and methodology", "mode": "strict"},
  {"agent": "self_evolution_engine", "purpose": "extract grant lessons", "mode": "standard"}
]

teaching:
[
  {"agent": "teaching_mentor", "purpose": "generate teaching material", "mode": "standard"},
  {"agent": "self_evolution_engine", "purpose": "extract pedagogy lessons", "mode": "standard"}
]

--- AGENT CONFIGS ---
Provide configs only for agents in workflow_sequence.
research_scout config keys: mode, recency_window, max_papers, ranking_criteria
scientific_verifier config keys: strictness (standard|high|ultra), check_citations, check_methodology, check_overclaiming

Return STRICT JSON with EXACTLY this schema — no additional keys:
{
  "task_type": "research_scan | idea_evaluation | grant_strategy | teaching | communication | collaboration | data_analysis | admin | unknown",
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
  "research_scout_mode": "ideation | literature_scan | gap_analysis | grant_opportunity | none",
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


def _derive_backward_compat(decision: GovernorDecision) -> GovernorDecision:
    """Ensure legacy fields are consistent with the new structured fields."""
    # Derive selected_agents from workflow_sequence when the LLM omitted them
    if decision.workflow_sequence and not decision.selected_agents:
        seen: list[str] = []
        for step in decision.workflow_sequence:
            if step.agent and step.agent not in seen and step.agent != "strategic_governor":
                seen.append(step.agent)
        decision.selected_agents = seen

    # Ensure self_evolution_engine is in selected_agents when policy says run=True
    if (
        decision.self_evolution_policy.run
        and "self_evolution_engine" not in decision.selected_agents
    ):
        decision.selected_agents.append("self_evolution_engine")

    # Remove self_evolution_engine from selected_agents when policy says run=False
    if not decision.self_evolution_policy.run:
        decision.selected_agents = [
            a for a in decision.selected_agents if a != "self_evolution_engine"
        ]

    # Filter unknown agent names
    decision.selected_agents = [a for a in decision.selected_agents if a in ALLOWED_AGENTS]

    # Derive research_scout_mode from workflow_sequence if not set
    if not decision.research_scout_mode or decision.research_scout_mode == "none":
        for step in decision.workflow_sequence:
            if step.agent == "research_scout" and step.mode:
                decision.research_scout_mode = step.mode
                break

    return decision


def run(user_input: str) -> dict:
    user_prompt = (
        f"User request:\n{user_input}\n\n"
        "Return your executive decision as strict JSON."
    )
    try:
        raw = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.1)

        # Coerce nested dicts to Pydantic sub-models
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
        # Failure → safe pause, not "continue as normal"
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
    decision = _derive_backward_compat(decision)

    return decision.model_dump()
