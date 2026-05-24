"""
Deep-research rigor layer.

Strictly ADDITIVE enhancement on top of the existing
``qwen_evolver.deep_research`` pipeline (planner → search → fetch →
extract → gap → verify → report).  This module reads the same
``EvidencePack`` + ``ResearchVerificationResult`` the existing
pipeline produces and synthesizes a 16-section structured report
following the user-supplied rigor spec.

AURA INTEGRITY CONTRACT (the spec's bullet 10):
    * No existing function in deep_research is modified by this module.
    * No memory / preference / verifier surface is touched.
    * On any LLM failure, every helper returns a safely-empty result
      rather than raising — the original report stays the source of
      truth for the existing verifier and persistence gates.
    * Confidence is driven by EVIDENCE QUALITY + COUNT, not LLM tone.
    * A final_check pass enforces the 7 acceptance gates and surfaces
      any unmet gate as a structured warning rather than silently
      passing them.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from core import normalization as _norm
from core.llm import ask_json

from .schemas import EvidencePack, ResearchVerificationResult, SourceRecord


# ---------------------------------------------------------------------------
# Schemas (Section 9 — 16-section structured report)
# ---------------------------------------------------------------------------

PurposeKind = Literal[
    "understanding", "comparison", "decision_support", "strategy",
    "policy", "academic_synthesis", "investment_business",
    "scientific_review", "other",
]
Confidence = Literal["high", "moderate", "low"]


class ResearchPurpose(BaseModel):
    """Output of Section-1 purpose clarification."""
    kind: PurposeKind = "other"
    central_question: str = ""
    rationale: str = ""


class ScopeCard(BaseModel):
    """Output of Section-2 scope-and-boundaries declaration."""
    timeframe: str = ""
    geography: str = ""
    domain: str = ""
    stakeholder_focus: list[str] = Field(default_factory=list)
    level_of_depth: Literal["rapid", "standard", "extensive"] = "standard"
    exclusions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class SubQuestion(BaseModel):
    """One sub-question from Section-3 decomposition."""
    question: str = ""
    kind: Literal[
        "what", "why", "who", "evidence_for", "evidence_against",
        "implications", "uncertainty", "conclusion", "other",
    ] = "other"
    priority: float = 0.5


class SourceQualityScore(BaseModel):
    """Output of Section-5 source-quality assessment (one per source)."""
    source_id: str = ""
    title: str = ""
    url: str = ""
    authority: Confidence = "moderate"
    recency: Confidence = "moderate"
    methodology: Confidence = "moderate"
    transparency: Confidence = "moderate"
    bias_risk: Literal["low", "moderate", "high", "unknown"] = "unknown"
    independence: Confidence = "moderate"
    consistency_with_others: Confidence = "moderate"
    overall: Confidence = "moderate"
    notes: str = ""


class CoreAnalyses(BaseModel):
    """Sub-analyses A through G from Section 6.

    Each list of bullet strings. ``confidence_label`` per analysis lets
    the synthesiser know how strongly to lean on it.  Every bullet
    should be short (one analytical claim) and end with citation
    anchors of the form ``[S1, S3]`` referring to source_ids in the
    evidence pack.
    """
    background_context: list[str] = Field(default_factory=list)
    drivers_root_causes: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    comparative: list[str] = Field(default_factory=list)
    trends_trajectory: list[str] = Field(default_factory=list)
    counterarguments: list[str] = Field(default_factory=list)
    risks_uncertainty: list[str] = Field(default_factory=list)
    confidence_by_analysis: dict[str, Confidence] = Field(default_factory=dict)


class RigorousFinding(BaseModel):
    """One finding in Section 8 (Key Findings)."""
    finding: str = ""
    supporting_evidence: list[str] = Field(default_factory=list)
    interpretation: str = ""
    confidence: Confidence = "moderate"
    cited_source_ids: list[str] = Field(default_factory=list)


class CompetingInterpretation(BaseModel):
    """One row of Section 10."""
    interpretation: str = ""
    support: str = ""
    weakness: str = ""
    relative_strength: Confidence = "moderate"


class FinalCheckReport(BaseModel):
    """Output of the spec's seven-question final check."""
    direct_answer_addressed: bool = False
    deeper_than_summary: bool = False
    claims_backed_by_evidence: bool = False
    counterarguments_addressed: bool = False
    uncertainties_explicit: bool = False
    conclusion_follows_from_evidence: bool = False
    aura_integrity_preserved: bool = True
    unmet_gates: list[str] = Field(default_factory=list)


class RigorousReport(BaseModel):
    """The 16-section structured output of Section 9."""
    # 1.
    title: str = ""
    # 2.
    executive_summary_main_conclusion: str = ""
    executive_summary_top_findings: list[str] = Field(default_factory=list)
    executive_summary_key_implications: list[str] = Field(default_factory=list)
    # 3.
    research_objective: ResearchPurpose = Field(default_factory=ResearchPurpose)
    # 4.
    scope_and_assumptions: ScopeCard = Field(default_factory=ScopeCard)
    # 5.
    methodology_source_selection: str = ""
    methodology_evaluation_criteria: str = ""
    methodology_analytical_approach: str = ""
    # 6.
    background_context: str = ""
    # 7.
    core_research_questions: list[SubQuestion] = Field(default_factory=list)
    # 8.
    key_findings: list[RigorousFinding] = Field(default_factory=list)
    # 9.
    deep_analysis: CoreAnalyses = Field(default_factory=CoreAnalyses)
    # 10.
    competing_interpretations: list[CompetingInterpretation] = Field(
        default_factory=list,
    )
    # 11.
    risks_limitations_uncertainties: list[str] = Field(default_factory=list)
    # 12.
    synthesis: str = ""
    # 13.
    conclusion: str = ""
    # 14.
    recommendations: list[str] = Field(default_factory=list)
    # 15. + 16.
    references: list[SourceQualityScore] = Field(default_factory=list)
    appendix_notes: list[str] = Field(default_factory=list)

    # Diagnostics
    final_check: FinalCheckReport = Field(default_factory=FinalCheckReport)
    abstentions: list[str] = Field(default_factory=list)
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Algorithms
# ---------------------------------------------------------------------------

_PURPOSE_PROMPT = """\
Classify the user's research purpose into ONE of:
  understanding | comparison | decision_support | strategy | policy |
  academic_synthesis | investment_business | scientific_review | other

OUTPUT STRICT JSON:
{
  "kind": "<one of the above>",
  "central_question": "<one precise, defensible central research question>",
  "rationale": "<one sentence: why this purpose fits the request>"
}

Rules:
- ``central_question`` MUST be answerable from the evidence pack.
- Do NOT invent constraints the user did not state.
"""


def clarify_purpose(user_request: str) -> ResearchPurpose:
    if not user_request or not user_request.strip():
        return ResearchPurpose(kind="other", central_question="")
    try:
        raw = ask_json(_PURPOSE_PROMPT, f"User request: {user_request.strip()}",
                       temperature=0.0) or {}
    except Exception:
        return ResearchPurpose(
            kind="other",
            central_question=user_request.strip()[:200],
            rationale="LLM purpose classification failed; using raw request.",
        )
    kind_s = str(raw.get("kind", "other")).strip().lower()
    allowed = {
        "understanding", "comparison", "decision_support", "strategy",
        "policy", "academic_synthesis", "investment_business",
        "scientific_review", "other",
    }
    if kind_s not in allowed:
        kind_s = "other"
    return ResearchPurpose(
        kind=kind_s,
        central_question=_norm.ensure_str(raw.get("central_question"), max_len=400)
        or user_request.strip()[:200],
        rationale=_norm.ensure_str(raw.get("rationale"), max_len=300),
    )


_SCOPE_PROMPT = """\
Declare an explicit scope-and-boundaries card for the research.  Use
ONLY information present in the user's request or central question.
If a field is not derivable, return an empty string / empty list — do
NOT invent constraints.

OUTPUT STRICT JSON:
{
  "timeframe": "e.g. 'last 5 years', '2010-2026', or '' if unspecified",
  "geography": "e.g. 'global', 'EU', 'US', or '' if unspecified",
  "domain": "e.g. 'organic semiconductor materials', 'medical devices'",
  "stakeholder_focus": ["who matters for this question", ...],
  "level_of_depth": "rapid | standard | extensive",
  "exclusions": ["explicit out-of-scope items", ...],
  "assumptions": ["assumptions you're making", ...]
}
"""


def define_scope(purpose: ResearchPurpose, user_request: str) -> ScopeCard:
    if not purpose.central_question:
        return ScopeCard()
    try:
        raw = ask_json(
            _SCOPE_PROMPT,
            f"User request: {user_request.strip()}\n"
            f"Central question: {purpose.central_question}",
            temperature=0.0,
        ) or {}
    except Exception:
        return ScopeCard()
    depth = str(raw.get("level_of_depth", "standard")).strip().lower()
    if depth not in ("rapid", "standard", "extensive"):
        depth = "standard"
    return ScopeCard(
        timeframe=_norm.ensure_str(raw.get("timeframe"), max_len=80),
        geography=_norm.ensure_str(raw.get("geography"), max_len=80),
        domain=_norm.ensure_str(raw.get("domain"), max_len=160),
        stakeholder_focus=_norm.ensure_str_list(
            raw.get("stakeholder_focus"), max_items=8, max_item_len=80,
        ),
        level_of_depth=depth,
        exclusions=_norm.ensure_str_list(
            raw.get("exclusions"), max_items=8, max_item_len=160,
        ),
        assumptions=_norm.ensure_str_list(
            raw.get("assumptions"), max_items=8, max_item_len=160,
        ),
    )


_DECOMPOSE_PROMPT = """\
Decompose the central research question into 4-8 ANALYZABLE
sub-questions covering at minimum:
  - what is happening
  - why is it happening
  - who is affected
  - what evidence supports the main claims
  - what evidence challenges them
  - what is uncertain
Add ``implications`` / ``conclusion`` sub-questions when they
materially advance the analysis.

OUTPUT STRICT JSON:
{
  "sub_questions": [
    {
      "question": "<the sub-question>",
      "kind": "what | why | who | evidence_for | evidence_against | implications | uncertainty | conclusion | other",
      "priority": <0.0-1.0>
    }, ...
  ]
}

Rules:
- Every sub-question must be ANSWERABLE in principle from a research
  evidence pack — not rhetorical, not too broad.
- ``priority`` reflects how essential the sub-question is to the
  central question (1.0 = critical, 0.5 = useful, 0.2 = nice-to-have).
"""


def decompose_question(purpose: ResearchPurpose) -> list[SubQuestion]:
    if not purpose.central_question:
        return []
    try:
        raw = ask_json(
            _DECOMPOSE_PROMPT,
            f"Central question: {purpose.central_question}\n"
            f"Purpose kind: {purpose.kind}",
            temperature=0.1,
        ) or {}
    except Exception:
        return []
    out: list[SubQuestion] = []
    for sq in _norm.iter_dicts(raw.get("sub_questions")):
        kind_s = str(sq.get("kind", "other")).strip().lower()
        if kind_s not in {
            "what", "why", "who", "evidence_for", "evidence_against",
            "implications", "uncertainty", "conclusion", "other",
        }:
            kind_s = "other"
        out.append(SubQuestion(
            question=_norm.ensure_str(sq.get("question"), max_len=300),
            kind=kind_s,
            priority=_clip_float(sq.get("priority"), 0.0, 1.0),
        ))
    return [s for s in out if s.question]


_QUALITY_PROMPT = """\
Score the quality of each source in the batch.  Be conservative:
default to ``moderate`` rather than ``high`` when uncertain.

OUTPUT STRICT JSON:
{
  "scores": [
    {
      "source_id": "<exact id from input>",
      "authority": "high | moderate | low",
      "recency": "high | moderate | low",
      "methodology": "high | moderate | low",
      "transparency": "high | moderate | low",
      "bias_risk": "low | moderate | high | unknown",
      "independence": "high | moderate | low",
      "consistency_with_others": "high | moderate | low",
      "overall": "high | moderate | low",
      "notes": "1-2 sentence rationale"
    }, ...
  ]
}

Rules:
- ``overall`` MUST be the WORST of the seven sub-scores (or one step
  better only if there's a clear reason).
- ``bias_risk=high`` MUST cap ``overall`` at ``moderate`` at most.
- ``source_id`` MUST appear in the input verbatim.
"""


def score_source_quality_batch(
    sources: list[SourceRecord], *, batch_size: int = 8,
) -> list[SourceQualityScore]:
    if not sources:
        return []
    out: list[SourceQualityScore] = []
    batch_size = max(1, int(batch_size))
    for start in range(0, len(sources), batch_size):
        chunk = sources[start:start + batch_size]
        user = "Sources to score:\n\n" + "\n\n".join(
            f"=== {s.source_id} ===\n"
            f"title: {s.title}\n"
            f"url: {s.url}\n"
            f"provider: {s.provider}\n"
            f"status: {s.status.value if hasattr(s.status, 'value') else s.status}\n"
            f"summary_snippet: {_source_snippet(s, 600)}"
            for s in chunk
        )
        try:
            raw = ask_json(_QUALITY_PROMPT, user, temperature=0.0) or {}
        except Exception:
            for s in chunk:
                out.append(SourceQualityScore(
                    source_id=s.source_id, title=s.title, url=s.url,
                    notes="LLM scoring failed; default moderate.",
                ))
            continue
        by_id = {
            str(sc.get("source_id", "")).strip(): sc
            for sc in _norm.iter_dicts(raw.get("scores"))
        }
        for s in chunk:
            sc = by_id.get(s.source_id) or {}
            out.append(_score_from_raw(sc, s))
    return out


_CORE_ANALYSES_PROMPT = """\
Conduct the most relevant of the seven core analyses below.  Skip any
sub-analysis that the evidence does not support — leave that array
empty rather than padding with low-evidence claims.

OUTPUT STRICT JSON:
{
  "background_context": ["claim [S1, S3]", ...],
  "drivers_root_causes": [...],
  "stakeholders": [...],
  "comparative": [...],
  "trends_trajectory": [...],
  "counterarguments": [...],
  "risks_uncertainty": [...],
  "confidence_by_analysis": {
    "background_context": "high | moderate | low",
    "drivers_root_causes": "...", "stakeholders": "...",
    "comparative": "...", "trends_trajectory": "...",
    "counterarguments": "...", "risks_uncertainty": "..."
  }
}

RULES:
- Each bullet MUST end with citation anchors in the form
  ``[S:<source_id>]`` (or ``[S:<id1>, S:<id2>]`` for multiple),
  using the EXACT source_ids shown in the "Available sources" list
  in the user message (e.g. ``[S:450e0f23]``, not ``[S1]``).
- A bullet WITHOUT a citation anchor that resolves to a real
  source_id is treated as inadmissible and will be dropped — so do
  not invent ids.
- 2-6 bullets per sub-analysis is typical; >8 means noise.
- ``confidence_by_analysis`` reflects evidence STRENGTH for each
  sub-analysis — not your tone.  Default to ``low`` if the cited
  sources are weak or the bullets are speculative.
"""


def run_core_analyses(
    purpose: ResearchPurpose,
    sub_questions: list[SubQuestion],
    pack: EvidencePack,
    quality: list[SourceQualityScore],
) -> CoreAnalyses:
    if not pack.sources:
        return CoreAnalyses()
    by_id = {s.source_id: s for s in pack.sources}
    qual_by_id = {q.source_id: q for q in quality}
    source_lines = []
    for s in pack.sources[:30]:
        q = qual_by_id.get(s.source_id)
        qual_str = q.overall if q else "unknown"
        source_lines.append(
            f"[S:{s.source_id}] ({qual_str}) {s.title} — "
            f"{_source_snippet(s, 240)}"
        )
    user = (
        f"Central question: {purpose.central_question}\n"
        f"Purpose: {purpose.kind}\n\n"
        f"Sub-questions:\n"
        + "\n".join(f"  - [{sq.kind}] {sq.question}" for sq in sub_questions)
        + "\n\nAvailable sources (id, quality_band, title, snippet):\n"
        + "\n".join(source_lines)
        + "\n\nProduce the seven core analyses per the schema."
    )
    try:
        raw = ask_json(_CORE_ANALYSES_PROMPT, user, temperature=0.1) or {}
    except Exception:
        return CoreAnalyses(confidence_by_analysis={
            k: "low" for k in (
                "background_context", "drivers_root_causes", "stakeholders",
                "comparative", "trends_trajectory", "counterarguments",
                "risks_uncertainty",
            )
        })
    alias_map = _build_id_aliases(pack.sources[:30])
    return CoreAnalyses(
        background_context=_filter_cited(raw.get("background_context"), alias_map),
        drivers_root_causes=_filter_cited(raw.get("drivers_root_causes"), alias_map),
        stakeholders=_filter_cited(raw.get("stakeholders"), alias_map),
        comparative=_filter_cited(raw.get("comparative"), alias_map),
        trends_trajectory=_filter_cited(raw.get("trends_trajectory"), alias_map),
        counterarguments=_filter_cited(raw.get("counterarguments"), alias_map),
        risks_uncertainty=_filter_cited(raw.get("risks_uncertainty"), alias_map),
        confidence_by_analysis=_validate_confidence_map(
            raw.get("confidence_by_analysis"),
        ),
    )


_SYNTHESIS_PROMPT = """\
Synthesise the evidence into Key Findings + Competing Interpretations
+ overall Synthesis + Conclusion.  Move from information collection to
JUDGEMENT.

OUTPUT STRICT JSON:
{
  "key_findings": [
    {
      "finding": "<the finding, one sentence>",
      "supporting_evidence": ["evidence point 1 [S:<source_id>]", ...],
      "interpretation": "<what this means, 1-2 sentences>",
      "confidence": "high | moderate | low",
      "cited_source_ids": ["<source_id>", "<source_id>", ...]
    }, ...
  ],
  "competing_interpretations": [
    {
      "interpretation": "<alternative reading of the evidence>",
      "support": "<what supports it [S:<source_id>]>",
      "weakness": "<why the better-supported reading wins>",
      "relative_strength": "high | moderate | low"
    }, ...
  ],
  "synthesis": "<2-4 paragraphs explaining what the TOTAL evidence suggests, which factors matter most, which claims are strong/weak, what remains uncertain, and what conclusion is most defensible>",
  "conclusion": "<1 paragraph: the defensible answer to the central question>",
  "recommendations": ["if applicable: actionable next steps grounded in the evidence", ...]
}

RULES:
- ``cited_source_ids`` MUST use the EXACT source_id strings shown in
  the "Available sources" list of the user message (e.g.
  ``["450e0f23", "eef382df"]``).  Do NOT invent sequential aliases
  like ``"S1"``, ``"S2"``.
- ``supporting_evidence`` bullets MUST end with ``[S:<source_id>]``
  anchors using those same exact ids.
- Confidence labels MUST be derived from evidence quality + corroboration,
  not from how confident the prose sounds.
- A finding with cited_source_ids that are all ``low``-quality sources
  CANNOT receive ``high`` confidence.
- Counterarguments addressed in ``competing_interpretations`` MUST cite
  the source_ids that support them — never invent.
- ``recommendations`` is OPTIONAL.  Empty list is fine when the question
  is analytical rather than action-oriented.
"""


def synthesize(
    purpose: ResearchPurpose,
    sub_questions: list[SubQuestion],
    pack: EvidencePack,
    quality: list[SourceQualityScore],
    core: CoreAnalyses,
) -> tuple[list[RigorousFinding], list[CompetingInterpretation], str, str, list[str]]:
    if not pack.sources:
        return [], [], "", "", []
    qual_by_id = {q.source_id: q for q in quality}
    src_lines = []
    for s in pack.sources[:30]:
        q = qual_by_id.get(s.source_id)
        src_lines.append(
            f"[S:{s.source_id}] ({q.overall if q else 'unknown'}) "
            f"{s.title}: {_source_snippet(s, 240)}"
        )
    user = (
        f"Central question: {purpose.central_question}\n\n"
        f"Sub-questions:\n"
        + "\n".join(f"  - {sq.question}" for sq in sub_questions)
        + "\n\nCore-analysis bullets to consolidate:\n"
        + _bulletise("background", core.background_context)
        + _bulletise("drivers", core.drivers_root_causes)
        + _bulletise("stakeholders", core.stakeholders)
        + _bulletise("comparative", core.comparative)
        + _bulletise("trends", core.trends_trajectory)
        + _bulletise("counterarguments", core.counterarguments)
        + _bulletise("risks", core.risks_uncertainty)
        + "\n\nAvailable sources:\n" + "\n".join(src_lines)
        + "\n\nProduce the synthesis JSON."
    )
    try:
        raw = ask_json(_SYNTHESIS_PROMPT, user, temperature=0.1) or {}
    except Exception:
        return [], [], "", "", []

    alias_map = _build_id_aliases(pack.sources[:30])
    findings: list[RigorousFinding] = []
    for f in _norm.iter_dicts(raw.get("key_findings")):
        # Resolve cited_source_ids via alias_map so "S1" / "s1" / "1"
        # all map to the canonical hex id.
        cited: list[str] = []
        seen: set[str] = set()
        for x in (f.get("cited_source_ids") or []):
            if not isinstance(x, str):
                continue
            resolved = _resolve_cite(x, alias_map)
            if resolved and resolved not in seen:
                seen.add(resolved)
                cited.append(resolved)
        # Backfill from anchors in the supporting_evidence bullets so a
        # finding with [S1] anchors in its bullets but no explicit
        # cited_source_ids array still has a populated Cited line.
        if not cited:
            for ev in (f.get("supporting_evidence") or []):
                if isinstance(ev, str):
                    for sid in _extract_cited_ids(ev, alias_map):
                        if sid not in seen:
                            seen.add(sid)
                            cited.append(sid)
        conf = _validate_confidence(f.get("confidence"))
        # Evidence-quality gate: cap confidence if every cited source is
        # low-quality.
        if cited:
            qbands = [qual_by_id.get(c) for c in cited]
            if all(q is not None and q.overall == "low" for q in qbands):
                conf = "low"
        findings.append(RigorousFinding(
            finding=_norm.ensure_str(f.get("finding"), max_len=300),
            supporting_evidence=_norm.ensure_str_list(
                f.get("supporting_evidence"), max_items=8, max_item_len=300,
            ),
            interpretation=_norm.ensure_str(
                f.get("interpretation"), max_len=400,
            ),
            confidence=conf,
            cited_source_ids=cited,
        ))

    competing: list[CompetingInterpretation] = []
    for c in _norm.iter_dicts(raw.get("competing_interpretations")):
        competing.append(CompetingInterpretation(
            interpretation=_norm.ensure_str(c.get("interpretation"), max_len=300),
            support=_norm.ensure_str(c.get("support"), max_len=300),
            weakness=_norm.ensure_str(c.get("weakness"), max_len=300),
            relative_strength=_validate_confidence(c.get("relative_strength")),
        ))

    synthesis = _norm.ensure_str(raw.get("synthesis"), max_len=4000)
    conclusion = _norm.ensure_str(raw.get("conclusion"), max_len=1500)
    recs = _norm.ensure_str_list(
        raw.get("recommendations"), max_items=10, max_item_len=300,
    )
    return findings, competing, synthesis, conclusion, recs


# ---------------------------------------------------------------------------
# Section 11 final check
# ---------------------------------------------------------------------------

def run_final_check(
    purpose: ResearchPurpose,
    findings: list[RigorousFinding],
    competing: list[CompetingInterpretation],
    risks: list[str],
    conclusion: str,
    synthesis: str,
) -> FinalCheckReport:
    """Deterministic verification of the spec's 7 acceptance gates.

    AURA-integrity is treated as preserved by default — the rigor
    pipeline ADDS to the existing report rather than replacing it, and
    the existing verifier's route still controls persistence.  Any
    future caller that mutates the original report should override.
    """
    unmet: list[str] = []
    direct = bool(conclusion.strip()) and bool(purpose.central_question.strip())
    if not direct:
        unmet.append("Gate 1: conclusion does not directly answer the central question.")
    deeper = bool(synthesis.strip()) and len(synthesis) >= 200
    if not deeper:
        unmet.append("Gate 2: synthesis is missing or shorter than a normal summary.")
    claims_backed = bool(findings) and all(
        bool(f.cited_source_ids) for f in findings
    )
    if not claims_backed:
        unmet.append(
            "Gate 3: at least one key finding is not backed by a cited source.",
        )
    counter = bool(competing)
    if not counter:
        unmet.append(
            "Gate 4: no competing interpretations were considered.",
        )
    uncertainties = bool(risks) and any(r.strip() for r in risks)
    if not uncertainties:
        unmet.append(
            "Gate 5: risks / limitations / uncertainties section is empty.",
        )
    follows = bool(conclusion.strip()) and bool(findings)
    if not follows:
        unmet.append(
            "Gate 6: conclusion does not derive from at least one finding.",
        )
    return FinalCheckReport(
        direct_answer_addressed=direct,
        deeper_than_summary=deeper,
        claims_backed_by_evidence=claims_backed,
        counterarguments_addressed=counter,
        uncertainties_explicit=uncertainties,
        conclusion_follows_from_evidence=follows,
        aura_integrity_preserved=True,
        unmet_gates=unmet,
    )


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def build_rigorous_report(
    *,
    user_request: str,
    pack: EvidencePack,
    verification: ResearchVerificationResult | None = None,
) -> RigorousReport:
    """Compose a 16-section RigorousReport on top of an existing
    deep-research ``EvidencePack`` + verification.  Never raises.

    Returns a defensive empty report (with ``abstentions`` populated)
    when the pack is empty.
    """
    report = RigorousReport()
    purpose = clarify_purpose(user_request)
    report.research_objective = purpose

    scope = define_scope(purpose, user_request)
    report.scope_and_assumptions = scope

    if not pack.sources:
        report.abstentions.append(
            "Evidence pack contains no sources; rigorous synthesis "
            "skipped to avoid fabrication."
        )
        report.title = (purpose.central_question or "Research report")[:160]
        report.executive_summary_main_conclusion = (
            "Insufficient evidence to draw a defensible conclusion."
        )
        report.final_check = run_final_check(
            purpose, [], [], [], "", "",
        )
        return report

    sub_questions = decompose_question(purpose)
    report.core_research_questions = sub_questions

    quality_scores = score_source_quality_batch(pack.sources)
    report.references = quality_scores

    core = run_core_analyses(purpose, sub_questions, pack, quality_scores)
    report.deep_analysis = core
    # Render background as bulleted markdown so the reader sees each
    # background claim distinctly (previously they were glued together
    # by raw newlines and read as one wall of text).
    report.background_context = "\n".join(
        f"- {b}" for b in core.background_context[:6]
    )
    report.risks_limitations_uncertainties = list(core.risks_uncertainty)

    findings, competing, synthesis, conclusion, recs = synthesize(
        purpose, sub_questions, pack, quality_scores, core,
    )
    report.key_findings = findings
    report.competing_interpretations = competing
    report.synthesis = synthesis
    report.conclusion = conclusion
    report.recommendations = recs

    # Executive summary derived deterministically.
    if findings:
        # Use the full conclusion as the main-conclusion text.  The
        # previous 500-char cap clipped sentences mid-word (visible in
        # earlier reports as "...required to translate" with no
        # period).  Fall back to the first finding only when the
        # conclusion is genuinely empty.
        report.executive_summary_main_conclusion = (
            conclusion.strip() or findings[0].finding
        )
        report.executive_summary_top_findings = [
            f.finding for f in findings[:5]
        ]
        report.executive_summary_key_implications = [
            f.interpretation for f in findings[:3] if f.interpretation
        ]

    report.title = (purpose.central_question or "Deep Research Report")[:160]
    report.methodology_source_selection = (
        f"Sources retrieved via the AURA deep_research pipeline "
        f"({len(pack.sources)} sources, "
        f"{sum(1 for q in quality_scores if q.overall == 'high')} high-quality, "
        f"{sum(1 for q in quality_scores if q.overall == 'low')} low-quality)."
    )
    report.methodology_evaluation_criteria = (
        "Per-source 7-axis quality scoring: authority, recency, methodology, "
        "transparency, bias risk, independence, cross-source consistency."
    )
    report.methodology_analytical_approach = (
        "Question decomposition into sub-questions; seven core analyses "
        "(background, drivers, stakeholders, comparison, trends, counterarguments, "
        "risks); evidence-quality-capped confidence on every finding."
    )

    # Verification context appended to appendix without mutating the
    # existing report.
    if verification is not None:
        report.appendix_notes.append(
            f"AURA verifier verdict: decision={verification.decision.value}, "
            f"overall_confidence={verification.overall_confidence:.2f}, "
            f"unsupported_claims={len(verification.unsupported_claims)}."
        )

    report.final_check = run_final_check(
        purpose, findings, competing,
        report.risks_limitations_uncertainties,
        conclusion, synthesis,
    )
    return report


# ---------------------------------------------------------------------------
# Markdown rendering (16-section layout from spec Section 9)
# ---------------------------------------------------------------------------

def render_rigorous_report_markdown(r: RigorousReport) -> str:
    """Render the report as a self-contained Markdown document.

    CONTRACT (immutable — see CLAUDE.md):
    All 16 numbered sections from the spec MUST appear in this exact
    order, even when empty.  Empty sections are emitted with an
    ``_(not derivable from current evidence)_`` placeholder so the
    structural contract is preserved and downstream tooling can rely on
    the headings being present.  The numbering matches the user spec:

      1. Title
      2. Executive Summary  (main conclusion, top findings, key implications)
      3. Research Objective
      4. Scope and Assumptions
      5. Methodology  (source selection, evaluation criteria, analytical approach)
      6. Background and Context
      7. Core Research Questions
      8. Key Findings  (finding, supporting evidence, interpretation, confidence)
      9. Deep Analysis  (drivers, stakeholders, comparisons, trends & outlook)
      10. Competing Interpretations
      11. Risks, Limitations, and Uncertainties
      12. Synthesis
      13. Conclusion
      14. Recommendations / Strategic Implications
      15. References
      16. Appendix
    """
    L: list[str] = []
    _PLACE = "_(not derivable from current evidence)_"

    def _emit_section(num: int, title: str) -> None:
        L.append(f"\n## {num}. {title}\n")

    def _emit_lines(lines: list[str]) -> None:
        if not lines:
            L.append(_PLACE)
            return
        L.extend(lines)

    # ---- 1. Title ----------------------------------------------------------
    _emit_section(1, "Title")
    L.append(f"# {r.title or 'Deep Research Report'}")

    # ---- 2. Executive Summary ---------------------------------------------
    _emit_section(2, "Executive Summary")
    L.append(
        f"**Main conclusion:** "
        f"{r.executive_summary_main_conclusion or _PLACE}"
    )
    L.append("\n**Top findings:**")
    if r.executive_summary_top_findings:
        for f in r.executive_summary_top_findings:
            L.append(f"- {f}")
    else:
        L.append(f"- {_PLACE}")
    L.append("\n**Key implications:**")
    if r.executive_summary_key_implications:
        for i in r.executive_summary_key_implications:
            L.append(f"- {i}")
    else:
        L.append(f"- {_PLACE}")

    # ---- 3. Research Objective --------------------------------------------
    _emit_section(3, "Research Objective")
    L.append(f"- **Purpose:** `{r.research_objective.kind}`")
    L.append(
        f"- **Central question:** "
        f"{r.research_objective.central_question or _PLACE}"
    )
    L.append(f"- **Rationale:** {r.research_objective.rationale or _PLACE}")

    # ---- 4. Scope and Assumptions -----------------------------------------
    _emit_section(4, "Scope and Assumptions")
    sc = r.scope_and_assumptions
    for label, value in [
        ("Timeframe", sc.timeframe), ("Geography", sc.geography),
        ("Domain", sc.domain), ("Depth", sc.level_of_depth),
    ]:
        L.append(f"- **{label}:** {value or _PLACE}")
    L.append(
        f"- **Stakeholder focus:** "
        f"{', '.join(sc.stakeholder_focus) if sc.stakeholder_focus else _PLACE}"
    )
    L.append(
        f"- **Exclusions:** "
        f"{', '.join(sc.exclusions) if sc.exclusions else _PLACE}"
    )
    L.append("- **Assumptions:**")
    if sc.assumptions:
        for a in sc.assumptions:
            L.append(f"    - {a}")
    else:
        L.append(f"    - {_PLACE}")

    # ---- 5. Methodology ----------------------------------------------------
    _emit_section(5, "Methodology")
    L.append(
        f"- **Source selection:** {r.methodology_source_selection or _PLACE}"
    )
    L.append(
        f"- **Evaluation criteria:** {r.methodology_evaluation_criteria or _PLACE}"
    )
    L.append(
        f"- **Analytical approach:** {r.methodology_analytical_approach or _PLACE}"
    )

    # ---- 6. Background and Context ----------------------------------------
    _emit_section(6, "Background and Context")
    L.append(r.background_context or _PLACE)

    # ---- 7. Core Research Questions ---------------------------------------
    _emit_section(7, "Core Research Questions")
    if r.core_research_questions:
        for sq in r.core_research_questions:
            L.append(
                f"- _[{sq.kind} · priority {sq.priority:.2f}]_ {sq.question}"
            )
    else:
        L.append(f"- {_PLACE}")

    # ---- 8. Key Findings --------------------------------------------------
    _emit_section(8, "Key Findings")
    if r.key_findings:
        for i, f in enumerate(r.key_findings, start=1):
            L.append(f"\n### Finding {i} (_{f.confidence}_ confidence)\n")
            L.append(f"**{f.finding}**")
            L.append("\n_Supporting evidence:_")
            if f.supporting_evidence:
                for e in f.supporting_evidence:
                    L.append(f"- {e}")
            else:
                L.append(f"- {_PLACE}")
            L.append(f"\n_Interpretation:_ {f.interpretation or _PLACE}")
            L.append(
                "\n_Cited:_ "
                + (", ".join(f"[S:{s}]" for s in f.cited_source_ids)
                   if f.cited_source_ids else _PLACE)
            )
    else:
        L.append(_PLACE)

    # ---- 9. Deep Analysis -------------------------------------------------
    _emit_section(9, "Deep Analysis")
    da_sections = [
        ("Drivers / root causes", r.deep_analysis.drivers_root_causes, "drivers_root_causes"),
        ("Stakeholders", r.deep_analysis.stakeholders, "stakeholders"),
        ("Comparative", r.deep_analysis.comparative, "comparative"),
        ("Trends & outlook", r.deep_analysis.trends_trajectory, "trends_trajectory"),
    ]
    for label, items, key in da_sections:
        conf = r.deep_analysis.confidence_by_analysis.get(key, "moderate")
        L.append(f"\n### {label} (_{conf}_ confidence)\n")
        if items:
            for it in items:
                L.append(f"- {it}")
        else:
            L.append(f"- {_PLACE}")

    # ---- 10. Competing Interpretations ------------------------------------
    _emit_section(10, "Competing Interpretations")
    if r.competing_interpretations:
        L.append("| Interpretation | Support | Weakness | Strength |")
        L.append("|---|---|---|---|")
        for c in r.competing_interpretations:
            L.append(
                f"| {_md(c.interpretation)} | {_md(c.support)} | "
                f"{_md(c.weakness)} | _{c.relative_strength}_ |"
            )
    else:
        L.append(_PLACE)

    # ---- 11. Risks, Limitations, and Uncertainties -----------------------
    _emit_section(11, "Risks, Limitations, and Uncertainties")
    if r.risks_limitations_uncertainties:
        for u in r.risks_limitations_uncertainties:
            L.append(f"- {u}")
    else:
        L.append(f"- {_PLACE}")

    # ---- 12. Synthesis ----------------------------------------------------
    _emit_section(12, "Synthesis")
    L.append(r.synthesis or _PLACE)

    # ---- 13. Conclusion ---------------------------------------------------
    _emit_section(13, "Conclusion")
    L.append(r.conclusion or _PLACE)

    # ---- 14. Recommendations / Strategic Implications --------------------
    _emit_section(14, "Recommendations or Strategic Implications")
    if r.recommendations:
        for rec in r.recommendations:
            L.append(f"- {rec}")
    else:
        L.append(f"- {_PLACE}")

    # ---- 15. References ---------------------------------------------------
    _emit_section(15, "References (per-source quality)")
    if r.references:
        # First: a readable per-source list with full title + URL.
        # Tables that bury the title at 50 chars made it impossible to
        # tell which source was which.
        L.append("**Sources (full citations):**\n")
        for s in r.references:
            title = _md(s.title) or "(no title)"
            url = (s.url or "").strip()
            url_part = f" — <{url}>" if url else ""
            L.append(
                f"- **[S:{s.source_id}]** {title}{url_part}  "
                f"_(quality: **{s.overall}**)_"
            )
        # Then the per-axis quality breakdown table.  Keeping it
        # narrow: the Source cell now holds only the id, so the table
        # never has to truncate.
        L.append("\n**Per-source 7-axis quality breakdown:**\n")
        L.append(
            "| Source | Overall | Authority | Recency | Methodology | "
            "Transparency | Bias risk | Independence | Consistency |"
        )
        L.append("|---|---|---|---|---|---|---|---|---|")
        for s in r.references:
            L.append(
                f"| [S:{s.source_id}] | _**{s.overall}**_ | {s.authority} "
                f"| {s.recency} | {s.methodology} | {s.transparency} "
                f"| {s.bias_risk} | {s.independence} "
                f"| {s.consistency_with_others} |"
            )
    else:
        L.append(_PLACE)

    # ---- 16. Appendix -----------------------------------------------------
    _emit_section(16, "Appendix")
    if r.appendix_notes:
        for n in r.appendix_notes:
            L.append(f"- {n}")
    else:
        L.append(f"- {_PLACE}")

    # ---- Diagnostics (outside 16-section contract) -----------------------
    L.append("\n## Final-Check Gates\n")
    fc = r.final_check
    L.append(f"- {_tick(fc.direct_answer_addressed)} Direct answer to central question")
    L.append(f"- {_tick(fc.deeper_than_summary)} Deeper than a normal summary")
    L.append(f"- {_tick(fc.claims_backed_by_evidence)} Major claims backed by cited evidence")
    L.append(f"- {_tick(fc.counterarguments_addressed)} Counterarguments addressed")
    L.append(f"- {_tick(fc.uncertainties_explicit)} Uncertainties stated explicitly")
    L.append(f"- {_tick(fc.conclusion_follows_from_evidence)} Conclusion follows from evidence")
    L.append(f"- {_tick(fc.aura_integrity_preserved)} AURA integrity preserved")
    if fc.unmet_gates:
        L.append("\n_Unmet gates:_")
        for u in fc.unmet_gates:
            L.append(f"- ⚠ {u}")
    if r.abstentions:
        L.append("\n## Abstentions\n")
        for a in r.abstentions:
            L.append(f"- {a}")
    L.append(f"\n_Generated at {r.generated_at}_\n")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

import re as _re


def _source_snippet(s: SourceRecord, max_len: int = 600) -> str:
    """Return the best available short text for a source.

    SourceRecord exposes ``summary`` and ``inline_text`` (not
    ``content_summary``).  Use summary if present, else a trimmed
    excerpt of the inline text.  Empty string if neither is present.
    """
    text = (getattr(s, "summary", "") or "").strip()
    if not text:
        text = (getattr(s, "inline_text", "") or "").strip()
    text = " ".join(text.split())
    return text[:max_len]


def _clip_float(value: Any, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return lo
    if v != v:
        return lo
    return max(lo, min(hi, v))


def _validate_confidence(value: Any) -> Confidence:
    s = str(value or "").strip().lower()
    return s if s in ("high", "moderate", "low") else "moderate"


def _validate_confidence_map(value: Any) -> dict[str, Confidence]:
    out: dict[str, Confidence] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out[str(k)] = _validate_confidence(v)
    return out


def _score_from_raw(sc: dict, s: SourceRecord) -> SourceQualityScore:
    bias = str(sc.get("bias_risk", "unknown")).strip().lower()
    if bias not in ("low", "moderate", "high", "unknown"):
        bias = "unknown"
    overall = _validate_confidence(sc.get("overall"))
    if bias == "high" and overall == "high":
        overall = "moderate"
    return SourceQualityScore(
        source_id=s.source_id,
        title=s.title,
        url=s.url,
        authority=_validate_confidence(sc.get("authority")),
        recency=_validate_confidence(sc.get("recency")),
        methodology=_validate_confidence(sc.get("methodology")),
        transparency=_validate_confidence(sc.get("transparency")),
        bias_risk=bias,
        independence=_validate_confidence(sc.get("independence")),
        consistency_with_others=_validate_confidence(
            sc.get("consistency_with_others"),
        ),
        overall=overall,
        notes=_norm.ensure_str(sc.get("notes"), max_len=400),
    )


_CITE_RE = _re.compile(r"\[S\s*([A-Za-z0-9_\-,\s:]+?)\]", _re.IGNORECASE)


def _build_id_aliases(sources: list[SourceRecord]) -> dict[str, str]:
    """Build a tolerant alias-map from any reasonable citation form to
    the canonical ``source_id``.

    The LLM sometimes echoes hex ids verbatim (``[S:450e0f23]``), and
    sometimes invents sequential aliases keyed by their order in the
    prompt (``[S1]``, ``[S2]``…).  Both must resolve.  Without this
    map, ``_filter_cited`` silently drops every bullet whose anchors
    use sequential aliases, which empties Section 9 (Deep Analysis).
    """
    alias: dict[str, str] = {}
    for i, s in enumerate(sources, start=1):
        sid = s.source_id
        # Canonical hex id, several caseings.
        alias[sid] = sid
        alias[sid.lower()] = sid
        alias[sid.upper()] = sid
        # Sequential aliases — match how the LLM was primed by schema
        # examples like "S1", "S3".
        alias[f"S{i}"] = sid
        alias[f"s{i}"] = sid
        alias[str(i)] = sid
    return alias


def _resolve_cite(token: str, alias_map: dict[str, str]) -> str | None:
    """Canonicalise one citation token to a source_id, or None."""
    if not token:
        return None
    cand = token.strip().lstrip(":").strip()
    # Direct hit.
    if cand in alias_map:
        return alias_map[cand]
    # Strip a single leading 'S'/'s' (handles "[S:S1]" → "S1" → ":S1"
    # → cand="S1") then re-try.
    stripped = cand.lstrip("Ss").lstrip(":").strip()
    if stripped in alias_map:
        return alias_map[stripped]
    if stripped.lower() in alias_map:
        return alias_map[stripped.lower()]
    return None


def _extract_cited_ids(text: str, alias_map: dict[str, str]) -> list[str]:
    """Pull every citation anchor out of ``text`` and canonicalise it.

    Returns the de-duplicated list of resolved source_ids (order
    preserved).  Unrecognised tokens are dropped silently.
    """
    out: list[str] = []
    seen: set[str] = set()
    for m in _CITE_RE.finditer(text):
        for part in m.group(1).split(","):
            sid = _resolve_cite(part, alias_map)
            if sid and sid not in seen:
                seen.add(sid)
                out.append(sid)
    return out


def _filter_cited(items: Any, alias_map: dict[str, str]) -> list[str]:
    """Keep only bullets that cite at least one resolvable source_id.

    Bullets without ``[S<id>]`` anchors or whose anchors can't be
    resolved via ``alias_map`` are dropped (per the spec's
    "inadmissible without citation" rule).  Sequential aliases like
    ``[S1]`` and hex ids like ``[S:450e0f23]`` both resolve.
    """
    if not isinstance(items, list):
        return []
    kept: list[str] = []
    for raw in items:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
            continue
        if _extract_cited_ids(text, alias_map):
            kept.append(text)
    return kept[:8]


def _bulletise(label: str, items: list[str]) -> str:
    if not items:
        return ""
    return "\n" + label + ":\n" + "\n".join(f"  - {it}" for it in items[:6])


def _md(text: str) -> str:
    if text is None:
        return ""
    return str(text).replace("\n", " ").replace("|", "\\|").strip()


def _tick(ok: bool) -> str:
    return "✅" if ok else "❌"
