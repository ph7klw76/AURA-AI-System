"""
Pydantic models for AURA Deep Research.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ----- Enums ---------------------------------------------------------------
class ResearchDepth(str, Enum):
    rapid = "rapid"
    standard = "standard"
    extensive = "extensive"

class SupportStatus(str, Enum):
    supported = "supported"
    partial = "partial"
    unsupported = "unsupported"
    contradicted = "contradicted"

class EvidenceType(str, Enum):
    quote = "quote"
    paraphrase = "paraphrase"
    table = "table"
    figure = "figure"
    metadata = "metadata"
    inferred = "inferred"

class TrustLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"

class SourceStatus(str, Enum):
    fetched = "fetched"
    failed = "failed"
    skipped = "skipped"

class GapRecommendation(str, Enum):
    continue_research = "continue_research"
    proceed_to_verification = "proceed_to_verification"
    human_review = "human_review"

class Verdict(str, Enum):
    approve = "approve"
    revise = "revise"
    retrieve_more_evidence = "retrieve_more_evidence"
    human_review = "human_review"
    reject = "reject"


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------

class ResearchBranch(BaseModel):
    branch_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    branch_name: str
    branch_goal: str
    branch_queries: list[str] = []
    priority: int = 0
    status: str = "pending"

class ResearchPlan(BaseModel):
    main_question: str
    subquestions: list[str] = []
    initial_queries: list[str] = []
    search_branches: list[ResearchBranch] = []
    inclusion_criteria: list[str] = []
    exclusion_criteria: list[str] = []
    success_criteria: list[str] = []
    stop_conditions: list[str] = []
    expected_outputs: list[str] = []

class ResearchMission(BaseModel):
    mission_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    original_user_request: str
    interpreted_objective: str
    domain: str = ""
    task_type: str = ""
    requested_depth: ResearchDepth = ResearchDepth.standard
    required_outputs: list[str] = []
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class SearchQueryRecord(BaseModel):
    query_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    query_text: str
    branch_id: str = ""
    round_number: int = 0
    rationale: str = ""
    executed_at: str = ""
    result_count: int = 0

class SearchResult(BaseModel):
    result_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str = ""
    url: str = ""
    snippet: str = ""
    provider: str = ""
    rank: int = 0
    fetched: bool = False

class SourceRecord(BaseModel):
    source_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str = ""
    url: str = ""
    source_type: str = ""
    provider: str = ""
    retrieved_at: str = ""
    content_type: str = "text"
    raw_text_path: str = ""
    inline_text: Optional[str] = None
    summary: str = ""
    trust_level: TrustLevel = TrustLevel.unknown
    is_primary_source: bool = False
    status: SourceStatus = SourceStatus.fetched

class EvidenceClaim(BaseModel):
    claim_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    claim_text: str
    source_id: str
    source_location: str = ""
    evidence_excerpt_or_span: str = ""
    evidence_type: EvidenceType = EvidenceType.paraphrase
    support_status: SupportStatus = SupportStatus.unsupported
    confidence_score: float = 0.0
    notes: str = ""

class EvidencePack(BaseModel):
    mission_id: str
    research_question: str
    plan_summary: str = ""
    sources: list[SourceRecord] = []
    evidence_claims: list[EvidenceClaim] = []
    key_findings: list[str] = []
    unresolved_questions: list[str] = []
    contradictions: list[str] = []
    confidence_summary: str = ""
    recommended_next_searches: list[str] = []

class GapAnalysis(BaseModel):
    missing_information: list[str] = []
    weakly_supported_claims: list[str] = []
    contradictory_evidence: list[str] = []
    source_quality_issues: list[str] = []
    followup_queries: list[str] = []
    recommendation: GapRecommendation = GapRecommendation.continue_research

class ResearchVerificationResult(BaseModel):
    decision: Verdict = Verdict.revise
    unsupported_claims: list[str] = []
    # Defect 5: only TRUE contradictions go here.  Generic verifier risks
    # are surfaced separately in `risks` so the report builder and
    # downstream consumers can distinguish them.
    contradictions: list[str] = []
    risks: list[str] = []
    claims_needing_more_evidence: list[str] = []
    report_revision_notes: list[str] = []
    # Defect 6: confidence is grounded in the verifier's route — never the
    # fabricated 0.5 default. -1.0 sentinel means "no confidence available".
    overall_confidence: float = -1.0

class CitationEntry(BaseModel):
    source_id: str
    title: str
    url: str
    retrieved_at: str
    source_type: str
    excerpt: str = ""

class DeepResearchReport(BaseModel):
    title: str = ""
    executive_summary: str = ""
    research_question: str = ""
    methodology: str = ""
    findings: list[str] = []
    opportunity_analysis: str = ""
    strategic_recommendations: list[str] = []
    evidence_caveats: list[str] = []
    unresolved_uncertainties: list[str] = []
    citations: list[CitationEntry] = []
    appendix_sources: list[str] = []

class ResearchReflection(BaseModel):
    mission_id: str
    what_worked: list[str] = []
    what_failed: list[str] = []
    wasted_search_paths: list[str] = []
    high_value_source_patterns: list[str] = []
    common_missing_evidence: list[str] = []
    proposed_workflow_rules: list[str] = []
    requires_human_approval: bool = True
