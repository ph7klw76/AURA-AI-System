from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    """One step in the ordered agent execution sequence."""
    agent: str = ""
    purpose: str = ""
    mode: str = ""


class MemoryPolicy(BaseModel):
    retrieve_memory: bool = True
    allow_memory_write: bool = True
    memory_write_requires_approval: bool = False


class SelfEvolutionPolicy(BaseModel):
    run: bool = True
    reason: str = ""


class GovernorDecision(BaseModel):
    # --- Core routing fields (backward-compat) ---
    task_type: str = ""
    priority: str = "medium"
    selected_agents: list[str] = Field(default_factory=list)
    research_scout_mode: str = "none"
    requires_approval: bool = False
    approval_reason: str = ""
    risk_level: str = "low"
    rationale: str = ""

    # --- Mission-alignment scoring ---
    mission_alignment_score: float = 0.0   # 0.0–1.0
    strategic_value_score: float = 0.0     # 0.0–1.0
    urgency_score: float = 0.0             # 0.0–1.0
    should_this_be_done: str = "yes"       # yes | maybe | no

    # --- Workflow planning ---
    workflow_sequence: list[WorkflowStep] = Field(default_factory=list)
    agent_configs: dict = Field(default_factory=dict)
    task_decomposition: list[str] = Field(default_factory=list)

    # --- Autonomy and safety ---
    autonomy_level: str = "L2"           # L0 | L1 | L2 | L3 | L4 | L5
    external_consequence: str = "none"  # none | low | medium | high
    evidence_requirement: str = "medium" # low | medium | high | ultra
    blocked_actions: list[str] = Field(default_factory=list)

    # --- Policies ---
    memory_policy: MemoryPolicy = Field(default_factory=MemoryPolicy)
    self_evolution_policy: SelfEvolutionPolicy = Field(default_factory=SelfEvolutionPolicy)


class AgentOutput(BaseModel):
    agent_name: str
    summary: str = ""
    findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: str = "medium"


class TopPaper(BaseModel):
    title: str = ""
    source: str = ""
    published_date: str = ""
    total_score: float = 0.0
    recommended_action: str = ""
    url: str = ""
    commentary: str = ""
    evidence_gaps: list[str] = Field(default_factory=list)
    # Provenance
    doi: str = ""
    cited_by_count: int = 0
    publication_type: str = ""  # journal | preprint | conference | review
    abstract_available: bool = False
    retrieved_at: str = ""
    # OLED key metrics (null if not stated in abstract)
    key_metrics: dict = Field(default_factory=dict)


class ClaimEvidenceMap(BaseModel):
    """Structured claim-and-evidence extraction for a single paper."""
    paper_title: str = ""
    main_claims: list[str] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    key_metrics: dict = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    what_it_supports_for_user: list[str] = Field(default_factory=list)
    what_it_does_not_support: list[str] = Field(default_factory=list)


class ResearchGapCandidate(BaseModel):
    """A fully-evidenced research gap with explicit novelty and risk assessment."""
    gap_statement: str = ""
    supporting_papers: list[str] = Field(default_factory=list)
    contradicting_or_overlap_papers: list[str] = Field(default_factory=list)
    why_gap_exists: str = ""
    why_gap_matters: str = ""
    what_is_new: str = ""
    # Critical: what has already been done that limits novelty
    what_is_not_new: str = ""
    minimum_evidence_needed: list[str] = Field(default_factory=list)
    proposal_angle: str = ""
    paper_angle: str = ""
    # low | medium | high
    risk_level: str = "medium"


class OpportunityCluster(BaseModel):
    """A group of related papers forming a research opportunity."""
    cluster_name: str = ""
    core_papers: list[str] = Field(default_factory=list)
    material_systems: list[str] = Field(default_factory=list)
    device_challenges: list[str] = Field(default_factory=list)
    application_challenges: list[str] = Field(default_factory=list)
    possible_grant_angle: str = ""
    strategic_value: float = 0.0
    risk: float = 0.0
    next_action: str = ""


class ResearchScoutOutput(BaseModel):
    agent_name: str = "research_scout"
    # ideation | literature_scan | gap_analysis | grant_opportunity
    mode: str = "ideation"
    summary: str = ""

    # Core intelligence outputs
    opportunity_map: list[OpportunityCluster] = Field(default_factory=list)
    top_papers: list[TopPaper] = Field(default_factory=list)
    claim_evidence_map: list[ClaimEvidenceMap] = Field(default_factory=list)
    research_gap_candidates: list[ResearchGapCandidate] = Field(default_factory=list)
    # Backward-compat single string (set from first candidate)
    research_gap_candidate: str = ""

    # Risk and strategy
    novelty_risks: list[str] = Field(default_factory=list)
    methodology_risks: list[str] = Field(default_factory=list)
    grant_angles: list[str] = Field(default_factory=list)
    collaboration_targets: list[str] = Field(default_factory=list)
    kill_criteria: list[str] = Field(default_factory=list)

    # Standard agent fields
    findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)

    # Query transparency
    queries_used: list[str] = Field(default_factory=list)
    queries_recommended_next: list[str] = Field(default_factory=list)
    # Backward-compat alias
    search_queries: list[str] = Field(default_factory=list)

    # Quality and verification
    confidence: str = "medium"
    evidence_quality: str = "moderate"   # weak | moderate | strong
    requires_scientific_verification: bool = True
    literature_scan_used: bool = False

    # Verifier-ready claims package
    claims_for_verification: list[str] = Field(default_factory=list)

    # Safe-failure metadata
    partial_results: bool = False
    failed_stage: str = ""
    recovery_action: str = ""

    report_paths: list[str] = Field(default_factory=list)


class ClaimCheck(BaseModel):
    """Verification result for a single extracted claim."""
    claim: str = ""
    claim_type: str = "mechanism"
    support_status: str = "unverifiable"
    severity: str = "low"
    confidence: float = 0.5
    evidence_needed: list[str] = Field(default_factory=list)
    correction: str = ""


class VerificationReport(BaseModel):
    overall_assessment: str = "incomplete"
    claim_checks: list[ClaimCheck] = Field(default_factory=list)
    methodology_risks: list[str] = Field(default_factory=list)
    novelty_risks: list[str] = Field(default_factory=list)
    citation_risks: list[str] = Field(default_factory=list)
    grant_risks: list[str] = Field(default_factory=list)
    action_governance_risks: list[str] = Field(default_factory=list)
    required_human_approvals: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    final_recommendation: str = "needs_more_evidence"
    route: str = "revise"
    verified_at: str = ""
    model_used: str = ""
    truncated: bool = False
    evidence_sources_checked: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)


class LessonDetail(BaseModel):
    """A structured, triaged lesson extracted from a session."""
    lesson: str = ""
    failure_type: str = ""
    confidence: float = 0.5
    scope: str = "session"          # session | topic | domain | global
    evidence_basis: str = ""
    risk_if_applied: str = "low"    # low | medium | high
    save_decision: str = "needs_review"  # save_now | needs_review | discard
    applies_to_modes: list[str] = Field(default_factory=list)


class ProfileUpdateProposal(BaseModel):
    """Patch-style profile update proposal (draft only — never auto-applied)."""
    field_path: str = ""
    current_value: str = ""
    proposed_value: str = ""
    rationale: str = ""
    requires_human_approval: bool = True


class NextExperiment(BaseModel):
    """A concrete next-step experiment proposed by the evolution engine."""
    description: str = ""
    motivation: str = ""
    expected_outcome: str = ""
    agent_mode: str = ""    # which scout mode to use
    priority: str = "medium"  # low | medium | high


class ReflectionRecord(BaseModel):
    # --- Structured new fields ---
    session_assessment: str = ""
    failure_modes: list[str] = Field(default_factory=list)
    lesson_details: list[LessonDetail] = Field(default_factory=list)
    memory_update_proposals: list[str] = Field(default_factory=list)
    workflow_update_proposals: list[str] = Field(default_factory=list)
    rubric_update_proposals: list[str] = Field(default_factory=list)
    profile_update_proposals: list[ProfileUpdateProposal] = Field(default_factory=list)
    next_experiments: list[NextExperiment] = Field(default_factory=list)
    human_approval_required: bool = False
    do_not_learn: list[str] = Field(default_factory=list)

    # --- Backward-compat flat fields ---
    what_worked: list[str] = Field(default_factory=list)
    what_failed_or_was_weak: list[str] = Field(default_factory=list)
    reusable_lessons: list[str] = Field(default_factory=list)
    memory_updates: list[str] = Field(default_factory=list)
    workflow_improvements: list[str] = Field(default_factory=list)
    suggested_profile_updates: list[str] = Field(default_factory=list)
