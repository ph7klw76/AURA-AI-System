from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Phase 2 base schemas — every specialist agent inherits SpecialistBaseOutput.
# Persisted records (memory, reflections) carry a schema_version for migrations.
# ---------------------------------------------------------------------------

class RecommendedAction(BaseModel):
    """A single action a specialist proposes. action_class drives ACTION_POLICY.

    Defect 7: ``action_class`` defaults to an empty string — NOT to
    ``"draft_text"`` — so the orchestrator's policy gate can classify a
    plain-text description on its own merits.  An empty action_class is
    treated by ``core.permissions.gate_recommended_actions`` as
    "needs inference", which keeps risky actions like "send email" or
    "file a patent" from silently inheriting an ``auto`` policy.
    """
    description: str = ""
    action_class: str = ""             # see core.permissions.ACTION_POLICY keys
    rationale: str = ""


class SpecialistBaseOutput(BaseModel):
    """Common contract every Phase 2 specialist agent returns.

    Phase 1 agents (research_scout) keep their existing bespoke schema; Phase 2
    agents inherit this base so the orchestrator, verifier, and formatter can
    treat them uniformly.
    """
    schema_version: int = 1
    agent_name: str
    summary: str = ""
    findings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    claims_for_verification: list[str] = Field(default_factory=list)
    evidence_level: Literal["none", "weak", "moderate", "strong"] = "weak"
    confidence: Literal["low", "medium", "high"] = "medium"
    approval_level: Literal["none", "draft_only", "human_approval_required"] = "draft_only"
    partial_results: bool = False
    failed_stage: str = ""

    @field_validator("recommended_actions", mode="before")
    @classmethod
    def _coerce_actions(cls, v):
        """Accept legacy list[str] and Phase 2 list[dict|RecommendedAction] alike.

        Defect 7: plain strings are NO LONGER coerced into
        ``action_class="draft_text"``.  Their action_class is left empty so
        the orchestrator's policy gate gets to inspect the raw description
        and infer the right action class (or fail closed if it can't).
        """
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        out: list = []
        for item in v:
            if isinstance(item, str):
                # action_class="" → permissions gate will infer or fail closed.
                out.append(RecommendedAction(description=item, action_class=""))
            elif isinstance(item, RecommendedAction):
                out.append(item)
            elif isinstance(item, dict):
                out.append(item)   # let Pydantic coerce dict → RecommendedAction
            # silently drop anything else — keeps fallback robust
        return out


class MemoryRecord(BaseModel):
    """Tagged, versioned memory record. Replaces free-form metadata dicts."""
    schema_version: int = 1
    kind: Literal["lesson", "claim", "preference", "reference"] = "lesson"
    content: str = ""
    agent_of_origin: str = ""
    verified: bool = False
    verifier_route: str = ""
    evidence_level: Literal["none", "weak", "moderate", "strong"] = "weak"
    confidence: float = 0.5
    scope: Literal["session", "topic", "domain", "global"] = "session"
    expires_at: str = ""
    review_after: str = ""
    created_at: str = ""


# ---------------------------------------------------------------------------
# Wave 1 specialist outputs — Grant Architect + Teaching Mentor
# ---------------------------------------------------------------------------

class GrantArchitectOutput(SpecialistBaseOutput):
    """Output of the Grant Architect specialist.

    Wave 1 contract: convert verified opportunities into reviewer-aware proposal
    structure. Always reviewed by the Scientific Verifier. Never submits.
    """
    agent_name: Literal["grant_architect"] = "grant_architect"
    approval_level: Literal["none", "draft_only", "human_approval_required"] = "draft_only"

    possible_title: str = ""
    problem_statement: str = ""
    central_hypothesis: str = ""
    objectives: list[str] = Field(default_factory=list)
    work_packages: list[str] = Field(default_factory=list)
    methodology_overview: str = ""
    expected_outcomes: list[str] = Field(default_factory=list)
    reviewer_attack_points: list[str] = Field(default_factory=list)
    evidence_needed_before_submission: list[str] = Field(default_factory=list)
    risk_mitigation: list[str] = Field(default_factory=list)
    collaborator_needs: list[str] = Field(default_factory=list)
    grant_readiness: Literal[
        "idea_only",
        "concept_note_ready",
        "needs_evidence",
        "proposal_draft_ready",
    ] = "idea_only"

    # Phase 5: reviewer-expected structural sections.  All three default to
    # empty lists so existing tests + LLM outputs that omit them still
    # validate; the prompt now asks the LLM to populate them.
    #
    # ``timeline`` is a list of phase strings (e.g.
    #     "Month 0-6: candidate down-selection",
    #     "Month 6-18: device fabrication",
    #     "Year 2-3: stability + commercialization").
    # ``budget`` is a list of free-form line items (e.g.
    #     "Personnel: 1 PDRA × 36 months ≈ €180k",
    #     "Consumables: precursors, hosts ≈ €30k").
    # ``team_roles`` ties FTE intent to WPs (e.g.
    #     "PI (0.2 FTE) — overall direction & WP4",
    #     "PDRA #1 (1.0 FTE) — synthesis WP1+WP2").
    timeline: list[str] = Field(default_factory=list)
    budget: list[str] = Field(default_factory=list)
    team_roles: list[str] = Field(default_factory=list)

    # Phase 5b: numbered references used by the draft body's [N] citations.
    # Populated from Scout's ``top_papers`` at run time so a reader can
    # resolve every cite.  Each entry is a short, single-line citation
    # string in the form "[N] Title — Venue YEAR. DOI: ... URL: ...".
    references_used: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# China Grant Architect — specialised submodule of GrantArchitect.
# Contract enforced by ``core.aura_principles.assert_china_grant_draft_contract``.
# ---------------------------------------------------------------------------

class ChinaReviewerSimulation(BaseModel):
    """One reviewer persona's attack on the proposal (Part 7 §20)."""
    reviewer_kind: Literal[
        "novelty", "methods", "feasibility",
        "china_funder_fit", "budget_compliance",
    ]
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    likely_score: int = 0           # 0..100
    rejection_risk: Literal["low", "moderate", "high", "very_high"] = "moderate"
    required_fixes: list[str] = Field(default_factory=list)


class ChinaCompetitivenessScore(BaseModel):
    """Per-axis scoring (Part 7 §21). Subscore axes are fixed by the rubric."""
    subscores: dict[str, int] = Field(default_factory=dict)
    total: int = 0
    band: str = "not submission-ready"


class ChinaWeaknessRepairItem(BaseModel):
    """One item in the final weakness-repair plan (Part 7 §22)."""
    weakness: str = ""
    why_it_matters: str = ""
    section_to_rewrite: str = ""
    exact_revision: str = ""
    priority: int = 0          # 1 = top priority


class ChinaProposalSection(BaseModel):
    """One drafted section of the 24-section blueprint."""
    name: str
    content: str = ""
    must_include_present: list[str] = Field(default_factory=list)
    must_include_missing: list[str] = Field(default_factory=list)
    reviewer_traps_addressed: list[str] = Field(default_factory=list)
    unsupported_claims_flagged: list[str] = Field(default_factory=list)


class ChinaGrantArchitectOutput(SpecialistBaseOutput):
    """Output of the China Grant Proposal Architect specialist.

    See ``core.aura_principles.CHINA_GRANT_CONTRACT`` for the immutable
    invariants this schema must satisfy.  approval_level is locked to
    ``draft_only`` because the module can never submit a grant.
    """
    agent_name: Literal["china_grant_architect"] = "china_grant_architect"
    approval_level: Literal["draft_only"] = "draft_only"

    # --- Resolved template metadata (Part 10) ---------------------------
    template_id: str = ""
    template_version: str = ""
    template_override_layers_applied: list[str] = Field(default_factory=list)
    # The effective A-P presentation outline used by the markdown renderer.
    # Stored on the output so downstream tools / tests can introspect how
    # the proposal was arranged.  User-editable via
    # ``agents.grant_architect.apply_china_template_patch``.
    template_presentation_outline: list[dict] = Field(default_factory=list)

    # --- The 24 drafted sections (in blueprint order) -------------------
    sections: list[ChinaProposalSection] = Field(default_factory=list)

    # --- Title / abstract / keywords (called out separately because
    #     they have bilingual + variant requirements; Part 7 §1-3) ------
    titles: dict[str, str] = Field(default_factory=dict)
    abstract: dict[str, str] = Field(default_factory=dict)
    keywords: dict[str, list[str]] = Field(default_factory=dict)

    # --- Five-reviewer simulation (Part 7 §20) --------------------------
    reviewer_simulation: list[ChinaReviewerSimulation] = Field(default_factory=list)

    # --- Submission readiness (Part 7 §21) ------------------------------
    competitiveness_score: ChinaCompetitivenessScore = Field(
        default_factory=ChinaCompetitivenessScore,
    )

    # --- Weakness repair plan (Part 7 §22) ------------------------------
    weakness_repair_plan: list[ChinaWeaknessRepairItem] = Field(
        default_factory=list,
    )

    # --- Information-state separation (Part 8) --------------------------
    confirmed_facts: list[str] = Field(default_factory=list)
    reasonable_assumptions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    # --- Output paths ---------------------------------------------------
    proposal_markdown_path: str = ""

    # --- Numbered references used by the draft's [N] / [S:...] cites ---
    # Populated from Scout's ``top_papers`` at run time so a reader can
    # resolve every citation.  Surfaced in the draft_writer's References
    # section so the same provenance shown by the general agent's
    # markdown is also shown for China drafts.
    references_used: list[str] = Field(default_factory=list)

    # --- Local-document evidence (user-provided PDFs / DOCX / TXT) ----
    # Forwarded from ``scout['local_literature_evidence']`` so the
    # draft_writer can render an auditable "Local-document evidence
    # used" block.  Each entry mirrors ``LocalEvidenceRef.model_dump()``
    # (keys: ``document_id``, ``document_title``, ``excerpt``, etc.)
    # so downstream consumers don't need a separate schema import.
    local_literature_evidence_used: list[dict] = Field(default_factory=list)

    # --- Scout diagnostics (auditable provenance for References) ------
    # Captures: was Scout invoked, in what mode, with which queries,
    # how many raw papers were seen, which provider returned which
    # error.  Lets the user diagnose "References empty" instead of
    # facing a generic placeholder.  Keys:
    #   scout_invoked          : bool
    #   literature_scan_used   : bool
    #   scout_mode             : str  ('literature_scan' | 'ideation' | …)
    #   queries_used           : list[str]
    #   raw_papers_seen        : int   (count BEFORE scoring filters)
    #   provider_counts        : dict[str, int]
    #   source_errors          : list[str]
    #   scout_risks            : list[str]
    scout_diagnostics: dict = Field(default_factory=dict)

    # --- Reflection captured for self-evolution (Part 11) --------------
    reflection_for_memory: dict = Field(default_factory=dict)


class TeachingMentorOutput(SpecialistBaseOutput):
    """Output of the Teaching Mentor specialist.

    Wave 1 contract: convert research into accurate, learner-aware teaching
    material. Reviewed by the Scientific Verifier when technical claims appear.
    """
    agent_name: Literal["teaching_mentor"] = "teaching_mentor"

    target_audience: str = ""
    learner_level: Literal[
        "general_public",
        "undergraduate",
        "graduate",
        "researcher",
        "mixed",
    ] = "undergraduate"
    learning_outcomes: list[str] = Field(default_factory=list)
    conceptual_explanation: str = ""
    socratic_questions: list[str] = Field(default_factory=list)
    common_misconceptions: list[str] = Field(default_factory=list)
    quiz_questions: list[str] = Field(default_factory=list)
    assessment_rubric: list[str] = Field(default_factory=list)
    teaching_activity: str = ""
    technical_cautions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Wave 2 specialist outputs — Lab/Data Analyst + Influence/Public Communication
# ---------------------------------------------------------------------------

class LabDataAnalystOutput(SpecialistBaseOutput):
    """Output of the Lab/Data Analyst specialist.

    Wave 2 contract: plan local data analysis (columns, methods, plots,
    reproducibility checks) without ever touching raw files. Reviewed by the
    Scientific Verifier whenever technical interpretation is involved.

    Default approval_level is "none" — pure read-only computation needs no
    approval. Any recommendation that would *modify* data must use the
    appropriate ACTION_POLICY action_class (e.g. modify_data_file → approval).
    """
    agent_name: Literal["lab_data_analyst"] = "lab_data_analyst"
    approval_level: Literal["none", "draft_only", "human_approval_required"] = "none"

    analysis_type: str = ""
    data_requirements: list[str] = Field(default_factory=list)
    required_columns: list[str] = Field(default_factory=list)
    methods_recommended: list[str] = Field(default_factory=list)
    calculations_recommended: list[str] = Field(default_factory=list)
    plots_recommended: list[str] = Field(default_factory=list)
    data_quality_checks: list[str] = Field(default_factory=list)
    reproducibility_checks: list[str] = Field(default_factory=list)
    interpretation_limits: list[str] = Field(default_factory=list)
    safe_file_handling: list[str] = Field(default_factory=list)
    next_analysis_steps: list[str] = Field(default_factory=list)


class InfluencePublicCommunicationOutput(SpecialistBaseOutput):
    """Output of the Influence/Public Communication specialist.

    Wave 2 contract: draft public-facing communication (LinkedIn posts, lay
    summaries, podcast angles) WITHOUT publishing. Always reviewed by the
    Scientific Verifier; always carries an explicit publishing-approval flag.
    """
    agent_name: Literal["influence_public_communication"] = "influence_public_communication"
    approval_level: Literal["none", "draft_only", "human_approval_required"] = "draft_only"

    audience: str = ""
    communication_goal: str = ""
    core_message: str = ""
    hook_options: list[str] = Field(default_factory=list)
    linkedin_draft: str = ""
    public_explanation: str = ""
    narrative_angle: str = ""
    evidence_cautions: list[str] = Field(default_factory=list)
    overclaim_risks: list[str] = Field(default_factory=list)
    safer_wording: list[str] = Field(default_factory=list)
    approval_required_before_publishing: bool = True


# ---------------------------------------------------------------------------
# Wave 3 specialist outputs — Collaboration Operator + Founder/Innovation
# ---------------------------------------------------------------------------

class CollaborationOperatorOutput(SpecialistBaseOutput):
    """Output of the Collaboration Operator specialist.

    Wave 3 contract: identify, evaluate, and PREPARE collaboration outreach.
    Drafts emails, agendas, and questions. Never sends, never schedules,
    never implies institutional commitment. Always reviewed by the verifier.
    """
    agent_name: Literal["collaboration_operator"] = "collaboration_operator"
    approval_level: Literal["none", "draft_only", "human_approval_required"] = "draft_only"

    collaboration_goal: str = ""
    suggested_collaboration_type: Literal[
        "research_discussion",
        "grant_collaboration",
        "industry_partnership",
        "student_exchange",
        "technical_consultation",
        "invited_talk",
        "unknown",
    ] = "unknown"

    possible_collaborators: list[str] = Field(default_factory=list)
    collaborator_rationale: list[str] = Field(default_factory=list)
    evidence_for_fit: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    draft_email_subject: str = ""
    draft_email_body: str = ""

    meeting_agenda: list[str] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)

    approval_required_before_contacting: bool = True
    institutional_risk_notes: list[str] = Field(default_factory=list)


class KeyRisk(BaseModel):
    """Structured key-risk entry used by FounderInnovationOutput.

    Defect 2: the prompt asks the LLM for objects with category/description/
    severity/likelihood/mitigation, and the formatter assumes dicts.  The
    canonical schema MUST also be structured so prompt, schema, formatter,
    and consumers stay in sync.
    """
    category: str = ""           # scientific | scale_up | regulatory | ip | market | capital | execution | other
    description: str = ""
    severity: Literal["low", "medium", "high"] = "medium"
    likelihood: Literal["low", "medium", "high"] = "medium"
    mitigation: str = ""


class FounderInnovationOutput(SpecialistBaseOutput):
    """Output of the Founder/Innovation specialist.

    Wave 3 contract: evaluate research as commercialization / startup pathway.
    Strategic analysis ONLY. Never legal, financial, investment, or IP advice.
    Always reviewed by the verifier; always carries an external-commitment flag.
    """
    agent_name: Literal["founder_innovation"] = "founder_innovation"
    approval_level: Literal["none", "draft_only", "human_approval_required"] = "draft_only"

    innovation_thesis: str = ""
    product_hypothesis: str = ""
    target_users_or_customers: list[str] = Field(default_factory=list)
    problem_customer_fit: str = ""

    possible_value_proposition: str = ""
    technical_moat: str = ""
    ip_considerations: list[str] = Field(default_factory=list)

    market_assumptions: list[str] = Field(default_factory=list)
    commercialization_pathways: list[str] = Field(default_factory=list)
    validation_experiments: list[str] = Field(default_factory=list)

    business_model_options: list[str] = Field(default_factory=list)
    # Defect 2: key_risks is the structured contract.  Plain strings are
    # coerced to KeyRisk(description=...) by the validator below.
    key_risks: list[KeyRisk] = Field(default_factory=list)
    regulatory_or_ethical_considerations: list[str] = Field(default_factory=list)

    next_90_day_plan: list[str] = Field(default_factory=list)

    legal_financial_disclaimer: str = (
        "This is strategic analysis, not legal, financial, investment, or IP advice."
    )
    approval_required_before_external_commitment: bool = True

    @field_validator("key_risks", mode="before")
    @classmethod
    def _coerce_key_risks(cls, v):
        """Accept legacy list[str] from older LLM runs and coerce to KeyRisk."""
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        out: list = []
        for item in v:
            if isinstance(item, str):
                if item.strip():
                    out.append(KeyRisk(description=item.strip()))
            elif isinstance(item, KeyRisk):
                out.append(item)
            elif isinstance(item, dict):
                # Map common alternative keys ("risk", "name") onto description.
                d = dict(item)
                if "description" not in d:
                    d["description"] = d.get("risk") or d.get("name") or ""
                out.append(d)   # Pydantic coerces dict → KeyRisk
        return out


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

    # Standard agent fields.
    # Defect 6: recommended_actions is now ``list[RecommendedAction]`` (same
    # contract as every Phase-2 specialist) so the orchestrator's policy gate
    # can read/write structured dicts without schema drift.  Legacy plain-
    # string outputs from older Scout runs are coerced by the validator below.
    findings: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)

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

    # Defect 9: deep_research mode previously injected a raw `deep_research_result`
    # key on a non-validated dict.  The schema now owns the field so every
    # Scout output (including deep_research) flows through Pydantic validation.
    deep_research_result: dict | None = None

    # Phase 4: optional local-literature evidence retrieved from a
    # user-supplied folder.  These fields are populated ONLY when the user
    # opted in and ingestion ran successfully.  They are explicitly kept
    # SEPARATE from external `top_papers` / `claims_for_verification` so the
    # verifier and report can distinguish web-search evidence from
    # local-folder evidence (provenance preserved).
    local_literature_evidence: list[dict] = Field(default_factory=list)
    local_document_ingestion_summary: dict = Field(default_factory=dict)
    needs_user_input: dict | None = None

    @field_validator("recommended_actions", mode="before")
    @classmethod
    def _coerce_scout_actions(cls, v):
        """Defect 6: coerce legacy list[str] from older Scout runs into
        ``list[RecommendedAction]``.  Plain strings get action_class=""
        (matches Phase-2 contract — see RecommendedAction docstring) so
        the orchestrator's policy gate inspects raw descriptions itself.
        """
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        out: list = []
        for item in v:
            if isinstance(item, str):
                out.append(RecommendedAction(description=item, action_class=""))
            elif isinstance(item, RecommendedAction):
                out.append(item)
            elif isinstance(item, dict):
                out.append(item)
        return out


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
    """A structured, triaged lesson extracted from a session.

    Defaults are deliberately conservative — when the LLM omits a field, the
    lesson should NOT auto-save. risk_if_applied defaults to "high" so a
    missing field is treated as risky; save_decision defaults to "needs_review"
    so the user must explicitly approve durable storage.
    """
    lesson: str = ""
    failure_type: str = ""
    confidence: float = 0.5
    # Constrained scope.  An invalid / unknown scope is coerced to the
    # narrowest, safest value ("session"), which the auto-save gate
    # excludes from durable persistence — so a malformed scope can never
    # cause a lesson to be saved beyond the current session.
    scope: Literal["session", "topic", "domain", "global"] = "session"
    evidence_basis: str = ""
    risk_if_applied: str = "high"   # low | medium | high — fail-safe default
    save_decision: str = "needs_review"  # save_now | needs_review | discard
    applies_to_modes: list[str] = Field(default_factory=list)

    @field_validator("scope", mode="before")
    @classmethod
    def _coerce_scope(cls, v):
        """Coerce any invalid scope to 'session' (fail-safe, never raise).

        Persisting a lesson at 'global'/'domain' scope is consequential;
        an LLM that emits a garbage scope ("everywhere", "", 42, None)
        must NOT accidentally land in a broad scope — it falls back to
        the narrowest scope, which the save gate then refuses to persist.
        """
        s = str(v or "").strip().lower()
        return s if s in ("session", "topic", "domain", "global") else "session"


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
