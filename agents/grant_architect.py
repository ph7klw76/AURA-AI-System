"""
AURA Grant Architect — Wave 1 specialist + China specialisation sub-mode.

Converts validated research opportunities and literature findings into a
reviewer-aware grant proposal STRUCTURE. Never submits, never represents the
user institutionally. The Scientific Verifier always reviews this output.

Public surface:
    run(user_input, context) -> dict           — general grant draft
    run_china(user_input, context) -> dict     — China-tailored sub-mode
        (24-section blueprint, 5-reviewer simulation, deterministic 0-100
         competitiveness score, weakness-repair plan, layered overrides).
        Contract enforced by core.aura_principles.CHINA_GRANT_CONTRACT.

The China sub-mode is implemented BELOW the general code in a clearly
delimited section.  It reuses the same imports (ask_json, memory) and
follows the same Pydantic / fallback / forbidden-action conventions
as the general agent — so the two share one auditable codepath rather
than living in parallel module trees.
"""
from __future__ import annotations

import json
import re as _re
from typing import Any

from pydantic import ValidationError

from core.llm import ask_json
from core.memory import retrieve_relevant_memory
from core.schemas import GrantArchitectOutput


SYSTEM_PROMPT = """\
You are the AURA Grant Architect.

Your job is to convert research opportunities into a fundable, reviewer-aware
proposal structure. You are NOT writing the final official submission.

Hard rules — never break:
- Use ONLY evidence from the user input and previous agent outputs.
- Do NOT invent citations, authors, datasets, preliminary results, or collaborators.
- Do NOT claim "ready to submit" unless evidence is strong.
- Separate verified findings from assumptions explicitly.
- Identify what evidence is still needed BEFORE submission.
- Think like a strict reviewer panel, not an enthusiastic applicant.
- Never submit grants, never represent the user institutionally.
- Return strict JSON only — no prose, no markdown fences.

Citation requirement (CRITICAL):
- When the user message includes a "References" block, every quantitative
  performance claim or competitor mention in problem_statement,
  central_hypothesis, methodology_overview, expected_outcomes, and
  reviewer_attack_points MUST be backed by a numeric citation in the form
  ``[N]`` referring to that References block.
- If no References block is supplied, explicitly say "no literature support
  available" in the relevant section and mark grant_readiness as at most
  "needs_evidence".
- NEVER fabricate citation numbers. If you cannot find a matching reference,
  do not cite — add the claim to evidence_needed_before_submission instead.
- Preserve a placeholder line ``[INSERT PILOT DATA HERE]`` inside
  methodology_overview where the team's own preliminary data should appear.

Reviewer-attack-point checklist (include explicitly):
- novelty over-claim risk
- feasibility under available equipment / budget
- statistical or sample-size weakness
- IP/regulatory blockers (especially for biomedical translation)
- competition from established groups
- timeline realism

Grant readiness scale:
- idea_only:           single sentence concept, no evidence
- concept_note_ready:  problem + hypothesis defendable; evidence still light
- needs_evidence:      structure is sound, but specific gaps must close before draft
- proposal_draft_ready: sufficient evidence to draft a competitive proposal

Default to a CONSERVATIVE reading. When evidence is missing, choose the lower tier.

Three reviewer-expected structural sections (populate when grant_readiness is
``concept_note_ready`` or higher; emit empty lists for ``idea_only``):
- ``timeline``: ordered phase strings like
  "Month 0-6: computational screening + first synthesis cycle".
- ``budget``: free-form line items like
  "Personnel: 1 PDRA × 36 months ≈ €180k", "Consumables: ≈ €40k".
  Currency / amount may be approximate; mark uncertainty explicitly.
- ``team_roles``: FTE-to-WP mappings like
  "PI (0.2 FTE) — direction & WP4", "PDRA (1.0 FTE) — synthesis WP1+WP2".

Risks vs reviewer_attack_points vs risk_mitigation — DO NOT REPEAT CONTENT:
- ``reviewer_attack_points`` = what a strict reviewer panel would attack.
- ``risk_mitigation`` = how YOU will address each attack point and risk.
- ``risks`` = project-internal risks that are NOT already covered by an
  attack point (e.g. supply chain, IRB delay, hiring).
- Each concrete concern must appear in AT MOST ONE of these three lists.
  Repeating the same concern in two or three forms is a structural defect
  that will be filtered before persistence.

Return JSON with EXACTLY this schema (no extra keys):
{
  "agent_name": "grant_architect",
  "summary": "...",
  "findings": ["..."],
  "assumptions": ["..."],
  "risks": ["..."],
  "recommended_actions": ["..."],
  "claims_for_verification": ["..."],
  "evidence_level": "none|weak|moderate|strong",
  "confidence": "low|medium|high",
  "approval_level": "draft_only",
  "possible_title": "...",
  "problem_statement": "...",
  "central_hypothesis": "...",
  "objectives": ["...", "...", "..."],
  "work_packages": ["WP1: ...", "WP2: ..."],
  "methodology_overview": "...",
  "expected_outcomes": ["..."],
  "reviewer_attack_points": ["..."],
  "evidence_needed_before_submission": ["..."],
  "risk_mitigation": ["..."],
  "collaborator_needs": ["..."],
  "timeline": ["Month 0-6: ...", "..."],
  "budget": ["Personnel: ...", "..."],
  "team_roles": ["PI (0.2 FTE) — ...", "..."],
  "grant_readiness": "idea_only | concept_note_ready | needs_evidence | proposal_draft_ready"
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_context(value: Any, max_chars: int = 4000) -> str:
    """Serialise context for the local LLM with a hard size cap."""
    try:
        text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]"
    return text


def _references_list_from_scout(scout_output: dict, max_refs: int = 12) -> list[str]:
    """Return references as a list of short citation strings.

    Used to populate ``GrantArchitectOutput.references_used`` so the saved
    draft can render a resolvable ``## References`` section AND so cite
    validation can count how many references exist.
    """
    from core import normalization as _norm
    papers = _norm.ensure_dict_list(scout_output.get("top_papers"))
    if not papers:
        return []
    refs: list[str] = []
    for i, p in enumerate(papers[:max_refs], start=1):
        title = _norm.ensure_str(p.get("title")) or "(untitled)"
        if len(title) > 200:
            title = title[:200].rstrip() + "…"
        source = _norm.ensure_str(p.get("source"))
        year_raw = _norm.ensure_str(p.get("published_date"))
        year = year_raw[:4] if year_raw else ""
        doi = _norm.ensure_str(p.get("doi"))
        url = _norm.ensure_str(p.get("url"))
        suffix_parts: list[str] = []
        venue_year = " ".join(part for part in (source, year) if part).strip()
        if venue_year:
            suffix_parts.append(venue_year)
        if doi:
            suffix_parts.append(f"DOI: {doi}")
        if url and not doi:
            suffix_parts.append(f"URL: {url}")
        suffix = " — " + " · ".join(suffix_parts) if suffix_parts else ""
        refs.append(f"[{i}] {title}{suffix}")
    return refs


def _format_references_block(scout_output: dict, max_refs: int = 12) -> str:
    """Render Scout's top_papers as a numbered ``References`` list.

    Each line follows the pattern:
        [N] Title — venue/source year. DOI: <doi> URL: <url>

    Architect MUST cite these by ``[N]`` for any quantitative claim that
    relies on prior literature.  Returns an empty string when there are
    no papers (Architect's prompt then knows to declare "no literature
    support available").
    """
    from core import normalization as _norm
    papers = _norm.ensure_dict_list(scout_output.get("top_papers"))
    if not papers:
        return ""
    lines: list[str] = ["References (cite by [N] in the draft):"]
    for i, p in enumerate(papers[:max_refs], start=1):
        title = _norm.ensure_str(p.get("title")) or "(untitled)"
        source = _norm.ensure_str(p.get("source"))
        year_raw = _norm.ensure_str(p.get("published_date"))
        year = year_raw[:4] if year_raw else ""
        doi = _norm.ensure_str(p.get("doi"))
        url = _norm.ensure_str(p.get("url"))
        # Truncate long titles so the prompt budget stays bounded.
        if len(title) > 180:
            title = title[:180].rstrip() + "…"
        suffix_parts: list[str] = []
        venue_year = " ".join(p for p in (source, year) if p).strip()
        if venue_year:
            suffix_parts.append(venue_year)
        if doi:
            suffix_parts.append(f"DOI: {doi}")
        if url and not doi:
            suffix_parts.append(f"URL: {url}")
        suffix = " — " + " · ".join(suffix_parts) if suffix_parts else ""
        lines.append(f"[{i}] {title}{suffix}")
    return "\n".join(lines)


def _scout_excerpt(scout_output: dict) -> str:
    """Pull only the verifier-relevant fields from scout output to keep prompt tight.

    Defect 24: defensively normalize Scout fields.  ``top_papers`` /
    ``findings`` / ``claims_for_verification`` may arrive as malformed
    types (string, dict, None) from a misbehaving Scout — iterating
    naively would crash before the fallback path runs.
    """
    from core import normalization as _norm
    if not isinstance(scout_output, dict):
        return "{}"
    top_papers_raw = _norm.ensure_dict_list(
        scout_output.get("top_papers"), max_items=5,
    )
    top_papers = []
    for p in top_papers_raw:
        try:
            score = round(float(p.get("total_score", 0.0) or 0.0), 2)
        except (TypeError, ValueError):
            score = 0.0
        km = p.get("key_metrics")
        if not isinstance(km, dict):
            km = {}
        top_papers.append({
            "title": _norm.ensure_str(p.get("title")),
            "source": _norm.ensure_str(p.get("source")),
            "score": score,
            "key_metrics": km,
        })
    excerpt = {
        "mode": _norm.ensure_str(scout_output.get("mode")),
        "summary": _norm.ensure_str(scout_output.get("summary"), max_len=600),
        "research_gap_candidate": _norm.ensure_str(
            scout_output.get("research_gap_candidate"), max_len=400,
        ),
        "findings": _norm.ensure_str_list(
            scout_output.get("findings"), max_items=6,
        ),
        "claims_for_verification": _norm.ensure_str_list(
            scout_output.get("claims_for_verification"), max_items=6,
        ),
        "top_papers": top_papers,
        "literature_scan_used": bool(scout_output.get("literature_scan_used", False)),
        "evidence_quality": _norm.ensure_str(scout_output.get("evidence_quality")),
        "confidence": _norm.ensure_str(scout_output.get("confidence")),
    }
    return _safe_context(excerpt, max_chars=2500)


def _fallback_output(error: Exception | str) -> dict:
    """Safe, conservative fallback when validation or the LLM call fails.

    Returns a fully-formed dict that the orchestrator and verifier can consume.
    """
    message = str(error)
    return GrantArchitectOutput(
        summary="Grant Architect could not produce a fully validated proposal structure.",
        findings=["Manual review is needed before using this grant architecture."],
        assumptions=["The available evidence may be incomplete."],
        risks=[
            "Grant framing may be weak without stronger literature or preliminary evidence.",
            f"Internal error or validation issue: {message[:300]}",
        ],
        recommended_actions=[
            "Review Research Scout output and gap candidate before drafting.",
            "Collect stronger evidence before developing a full proposal.",
            "Run Scientific Verifier on any grant claims before circulation.",
        ],
        claims_for_verification=[],
        evidence_level="weak",
        confidence="low",
        approval_level="draft_only",
        partial_results=True,
        failed_stage="llm_grant_architecture",
        possible_title="Draft grant concept requires manual refinement",
        problem_statement="Insufficient validated information to generate a strong problem statement.",
        central_hypothesis="Hypothesis requires additional evidence before use.",
        objectives=[],
        work_packages=[],
        methodology_overview="Methodology requires expert review.",
        expected_outcomes=[],
        reviewer_attack_points=[
            "Insufficient evidence to defend novelty.",
            "Unclear feasibility under available infrastructure.",
            "Risk of over-claiming biomedical/translational impact.",
        ],
        evidence_needed_before_submission=[
            "Targeted literature support for the central hypothesis.",
            "Preliminary data or simulation evidence.",
            "Clear feasibility argument tied to specific equipment / time.",
        ],
        risk_mitigation=["Do not submit until evidence gaps are addressed."],
        collaborator_needs=[],
        grant_readiness="idea_only",
    ).model_dump()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(user_input: str, context: dict | None = None) -> dict:
    """Generate a reviewer-aware grant proposal structure.

    Args:
        user_input: original user prompt
        context: prior orchestrator outputs (research_scout, strategic_governor, ...)

    Returns:
        dict matching GrantArchitectOutput.model_dump()
    """
    ctx = context or {}

    try:
        memory_records = retrieve_relevant_memory(user_input, limit=8) or []
    except Exception:
        memory_records = []

    scout_output = ctx.get("research_scout") or {}
    if not scout_output and isinstance(ctx.get("specialists"), dict):
        scout_output = ctx["specialists"].get("research_scout", {}) or {}

    governor = ctx.get("strategic_governor") or {}

    references_block = _format_references_block(scout_output, max_refs=12)
    references_list = _references_list_from_scout(scout_output, max_refs=12)

    user_prompt = (
        "User request:\n"
        f"{user_input}\n\n"
        "Strategic governor signals (task_type, evidence_requirement, autonomy_level):\n"
        f"{_safe_context({k: governor.get(k) for k in ('task_type','evidence_requirement','autonomy_level','rationale')}, max_chars=600)}\n\n"
        "Research Scout excerpt (gap, claims, top papers):\n"
        f"{_scout_excerpt(scout_output)}\n\n"
        "Relevant AURA memory (top 8):\n"
        f"{_safe_context(memory_records[:8], max_chars=1500)}\n\n"
    )

    # Defect: Scout's 49-paper scan was thrown away before reaching the
    # Architect — every claim was therefore uncited and the verifier
    # routed to human_review.  We now expose the top 12 papers as a
    # numbered References block and require [N] citations in the draft.
    if references_block:
        user_prompt += references_block + "\n\n"
    else:
        user_prompt += (
            "References: (none — Research Scout did not return any papers; "
            "explicitly say 'no literature support available' in the draft "
            "and cap grant_readiness at 'needs_evidence').\n\n"
        )

    # --- Inject verifier revision instructions if present (retry context) ---
    # This is the second-pass "revise" loop: the previous draft was rejected
    # by the Scientific Verifier; address every item before re-emitting.
    on_retry = bool(
        ctx.get("verifier_revision_instructions")
        or ctx.get("verifier_corrections")
        or ctx.get("verifier_risks")
    )
    if on_retry:
        user_prompt += (
            "\n=== RETRY CONTEXT — PRIOR DRAFT WAS REJECTED ===\n"
            "Address every numbered item below.  A claim that triggered a "
            "verifier correction must be rewritten with a numeric [N] "
            "citation from the References block OR demoted to "
            "evidence_needed_before_submission.  Do NOT repeat the exact "
            "wording that was flagged.\n\n"
        )

    verifier_instructions = ctx.get("verifier_revision_instructions")
    if verifier_instructions and isinstance(verifier_instructions, list):
        user_prompt += (
            "Verifier Revision Instructions (address each before finalising):\n"
            + "\n".join(f"  - {v}" for v in verifier_instructions[:8])
            + "\n\n"
        )
    verifier_corrections = ctx.get("verifier_corrections")
    if verifier_corrections and isinstance(verifier_corrections, list):
        user_prompt += (
            "Verifier Corrections (mandatory fixes — each must be applied "
            "verbatim or the claim removed):\n"
            + "\n".join(f"  * {c}" for c in verifier_corrections[:5])
            + "\n\n"
        )
    verifier_risks = ctx.get("verifier_risks")
    if verifier_risks and isinstance(verifier_risks, list):
        user_prompt += (
            "Verifier Risks to Mitigate (acknowledge each in the risks list):\n"
            + "\n".join(f"  ! {r}" for r in verifier_risks[:5])
            + "\n\n"
        )

    # Surface the previous Architect draft so the LLM can revise rather
    # than regenerate from scratch and re-introduce the same overclaims.
    if on_retry:
        prior_specialists = ctx.get("specialists") or {}
        prior_architect = prior_specialists.get("grant_architect") if isinstance(
            prior_specialists, dict
        ) else None
        if isinstance(prior_architect, dict) and prior_architect:
            prior_excerpt = {
                k: prior_architect.get(k)
                for k in (
                    "possible_title", "summary", "problem_statement",
                    "central_hypothesis", "objectives",
                    "expected_outcomes", "risks",
                )
            }
            user_prompt += (
                "Prior Architect draft (revise, do not regenerate verbatim):\n"
                f"{_safe_context(prior_excerpt, max_chars=2000)}\n\n"
            )

    user_prompt += (
        "Task: produce a reviewer-aware grant proposal STRUCTURE matching the JSON schema. "
        "Be conservative. Mark missing evidence explicitly. Do not invent citations or results. "
        "Default approval_level to 'draft_only'. Return strict JSON only."
    )

    try:
        raw = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.15)
    except Exception as exc:
        return _fallback_output(exc)

    if not isinstance(raw, dict):
        return _fallback_output("LLM returned non-dict output.")

    # Sanity check: the LLM must produce at least one substantive Grant Architect
    # field. If it returns e.g. {"bad": "schema"}, every field would silently
    # fall back to its default and we would wrongly publish a confident-looking
    # proposal full of empty strings. Treat that as a failure.
    _SUBSTANTIVE = (
        "summary", "possible_title", "problem_statement", "central_hypothesis",
        "objectives", "work_packages", "methodology_overview", "expected_outcomes",
    )
    if not any(raw.get(f) for f in _SUBSTANTIVE):
        return _fallback_output("LLM response contained no substantive grant fields.")

    # Force agent_name regardless of what the LLM emitted (Literal-locked anyway)
    raw["agent_name"] = "grant_architect"

    # Force draft_only approval — Grant Architect must NEVER promote itself to
    # human_approval_required since that would imply readiness to submit.
    raw["approval_level"] = "draft_only"

    # Phase 5: cross-section dedup.  LLMs routinely emit the same concern
    # in ``reviewer_attack_points``, ``risk_mitigation``, AND ``risks``
    # (in slightly different wording), producing a draft where the same
    # risk appears three times.  We dedup post-hoc: anything close enough
    # to an attack point or mitigation is removed from ``risks``.
    raw["risks"] = _dedup_risks_against(
        raw.get("risks") or [],
        raw.get("reviewer_attack_points") or [],
        raw.get("risk_mitigation") or [],
    )

    # Fix B: store references so the saved Markdown can render a resolvable
    # ``## References`` section to back the in-text [N] citations.
    raw["references_used"] = references_list

    # Fix E: LLMs sometimes double-bracket the placeholder ([[INSERT...]]).
    # Normalize to a single set of brackets in every string field.
    _normalize_placeholders(raw)

    # Fix C: detect [N] citations that point past the end of the references
    # list and surface them as risks so the user / verifier sees them.
    dangling = _find_dangling_citations(raw, len(references_list))
    if dangling:
        warning = (
            "Cite validation: in-text citation(s) "
            + ", ".join(f"[{n}]" for n in sorted(dangling))
            + f" exceed the {len(references_list)} reference(s) supplied. "
            "Either remove them or extend the literature scan."
        )
        raw.setdefault("risks", []).append(warning)

    try:
        validated = GrantArchitectOutput.model_validate(raw)
    except ValidationError as exc:
        return _fallback_output(exc)

    return validated.model_dump()


# ---------------------------------------------------------------------------
# Placeholder normalization (Fix E)
# ---------------------------------------------------------------------------

_TEXT_FIELDS_FOR_PLACEHOLDER_FIX: tuple[str, ...] = (
    "summary", "problem_statement", "central_hypothesis",
    "methodology_overview",
)
_LIST_FIELDS_FOR_PLACEHOLDER_FIX: tuple[str, ...] = (
    "objectives", "work_packages", "expected_outcomes", "timeline",
    "budget", "team_roles", "reviewer_attack_points",
    "evidence_needed_before_submission", "risk_mitigation",
    "collaborator_needs",
)


def _normalize_placeholders(raw: dict) -> None:
    """In-place: ``[[INSERT PILOT DATA HERE]]`` → ``[INSERT PILOT DATA HERE]``."""
    pattern = _re.compile(r"\[\[\s*(INSERT [^\]]+?)\s*\]\]")
    repl = r"[\1]"
    for key in _TEXT_FIELDS_FOR_PLACEHOLDER_FIX:
        v = raw.get(key)
        if isinstance(v, str):
            raw[key] = pattern.sub(repl, v)
    for key in _LIST_FIELDS_FOR_PLACEHOLDER_FIX:
        v = raw.get(key)
        if isinstance(v, list):
            raw[key] = [
                pattern.sub(repl, item) if isinstance(item, str) else item
                for item in v
            ]


# ---------------------------------------------------------------------------
# Citation validation (Fix C)
# ---------------------------------------------------------------------------

_CITE_RE = _re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def _find_dangling_citations(raw: dict, n_refs: int) -> set[int]:
    """Return the set of [N] cite numbers > n_refs across all text fields."""
    text_chunks: list[str] = []
    for key in _TEXT_FIELDS_FOR_PLACEHOLDER_FIX:
        v = raw.get(key)
        if isinstance(v, str):
            text_chunks.append(v)
    for key in _LIST_FIELDS_FOR_PLACEHOLDER_FIX:
        v = raw.get(key)
        if isinstance(v, list):
            text_chunks.extend(s for s in v if isinstance(s, str))
    blob = "\n".join(text_chunks)
    dangling: set[int] = set()
    for match in _CITE_RE.finditer(blob):
        for num_str in match.group(1).split(","):
            try:
                num = int(num_str.strip())
            except ValueError:
                continue
            if num < 1 or num > n_refs:
                dangling.add(num)
    return dangling


# ---------------------------------------------------------------------------
# Risk dedup (defect: same concern echoed across three sections)
# ---------------------------------------------------------------------------

_STOPWORDS_FOR_DEDUP: frozenset[str] = frozenset({
    "the", "and", "for", "with", "from", "into", "that", "this", "may",
    "must", "without", "before", "after", "than", "such", "also",
    "however", "any", "all", "some", "more", "less", "very", "is",
    "are", "be", "been", "being", "to", "of", "in", "on", "as",
    "a", "an", "by", "or", "if", "it", "its", "their", "there",
    "risk", "issue", "concern", "may", "could", "should", "would",
})


def _significant_tokens(text: str) -> set[str]:
    tokens = _re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text or "")
    return {
        t.lower() for t in tokens
        if t.lower() not in _STOPWORDS_FOR_DEDUP
    }


def _dedup_risks_against(
    risks: list,
    attack_points: list,
    mitigations: list,
    *,
    overlap_threshold: float = 0.5,
) -> list[str]:
    """Remove ``risks`` entries that significantly overlap with any item in
    ``attack_points`` or ``mitigations`` (token overlap coefficient).

    The intent is to keep ``risks`` lean and project-internal — anything
    already covered by an attack point or a mitigation is duplication.

    Scoring uses the **overlap coefficient** ``|A ∩ B| / min(|A|, |B|)``
    rather than Jaccard, so that a short risk that is a near-subset of a
    longer attack point still collapses ("Novelty over-claim: …" vs
    "Novelty over-claim risk — MR-TADF for red is published by Hatakeyama
    group.").  Comparison ignores stopwords + generic words like ``risk``
    / ``issue`` so phrasing variants collapse together.

    Empty / non-string entries are dropped (defensive).
    """
    if not risks:
        return []
    reference = [str(x) for x in (attack_points or []) if isinstance(x, (str, int, float))]
    reference += [str(x) for x in (mitigations or []) if isinstance(x, (str, int, float))]
    ref_token_sets = [
        _significant_tokens(r) for r in reference if _significant_tokens(r)
    ]

    def _overlap(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / min(len(a), len(b))

    kept: list[str] = []
    seen_self: list[set[str]] = []
    for item in risks:
        if not isinstance(item, (str, int, float)):
            continue
        text = str(item).strip()
        if not text:
            continue
        toks = _significant_tokens(text)
        if not toks:
            kept.append(text)
            continue
        is_dup = any(
            _overlap(toks, ref_toks) >= overlap_threshold
            for ref_toks in ref_token_sets
        )
        if is_dup:
            continue
        if any(_overlap(toks, prior) >= overlap_threshold for prior in seen_self):
            continue
        kept.append(text)
        seen_self.append(toks)
    return kept


# ===========================================================================
# CHINA GRANT ARCHITECT SUB-MODE
# ===========================================================================
#
# Specialised China-tailored sub-mode of this Grant Architect.  It does
# NOT replace the general ``run()`` above — it consumes the general
# Architect's output as a backbone and adds:
#   * 24-section China Grant Blueprint draft
#   * 5-reviewer simulation (canonical order)
#   * Deterministic 0-100 competitiveness score (fixed rubric)
#   * Top-5 weakness-repair plan
#   * Layered template override resolution
#   * Reflection capture for self-evolution
#
# Public entry: ``run_china(user_input, context) -> dict``
# Contract:     ``core.aura_principles.assert_china_grant_draft_contract``
# ===========================================================================

from datetime import datetime, timezone

import config
from core.aura_principles import (
    CHINA_GRANT_FORBIDDEN_ACTIONS,
    CHINA_GRANT_FORBIDDEN_INTENT_PATTERNS,
    CHINA_GRANT_PROPOSAL_SECTIONS,
    CHINA_GRANT_REVIEWER_ROSTER,
    CHINA_GRANT_SCORE_RUBRIC,
    assert_china_grant_draft_contract,
    classify_competitiveness,
)
from core.grant_templates.china_blueprint import (
    TEMPLATE_ID, resolve_template,
)
from core.memory import save_reflection
from core.schemas import (
    ChinaCompetitivenessScore,
    ChinaGrantArchitectOutput,
    ChinaProposalSection,
    ChinaReviewerSimulation,
    ChinaWeaknessRepairItem,
)

_CHINA_REPORTS_DIR = config.BASE_DIR / "reports" / "china_grants"
_CHINA_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

CHINA_DRAFTING_SYSTEM_PROMPT = """\
You are the AURA China Grant Proposal Architect — a specialised
submodule of the general Grant Architect, focused on China-tailored
proposals (NSFC, MOST, provincial, key R&D, etc.).

Your job: turn a research opportunity + Research Scout literature +
Grant Architect skeleton + China funder context into a high-rigor,
reviewer-defensible draft using the 24-section China Grant Blueprint.

HARD RULES — never break:
- Use ONLY evidence supplied in the user message (Scout papers,
  local-document evidence, prior Architect output, user-provided
  preliminary data, the call metadata).  Do NOT invent citations,
  datasets, results, or institutional commitments.
- For every quantitative or comparative claim, cite from the
  numbered References block as ``[N]`` (e.g. ``[3]`` or ``[1, 5]``).
  When the supporting evidence comes from a user-provided local file,
  cite with ``[LOCAL:<doc_id>]`` using the exact doc_id shown in the
  Local-document evidence block.  If neither source supports a claim,
  add it to ``missing_information`` instead of citing or asserting it.
- Sections must NOT flag "specific literature citations" in
  ``must_include_missing`` when a References block (web OR local) WAS
  provided — flag it only when the relevant numbered/local citation
  truly does not exist in the supplied evidence.
- Distinguish ``confirmed_facts`` vs ``reasonable_assumptions`` vs
  ``missing_information``.  Be conservative.
- Any sentence claiming "first", "novel", "unprecedented",
  "breakthrough", "transformative" MUST be paired with a specific
  contrast to the state of the art.  Otherwise demote to a hedged
  formulation.
- Never imply a grant rule unless it appears in the call metadata.
- ``recommended_actions`` may suggest drafting, reviewing, gathering
  evidence — NEVER submitting, NEVER altering official files, NEVER
  representing the user.

OUTPUT STRICT JSON matching this shape (no markdown fences, no prose):
{
  "titles": {"formal_en": "", "reviewer_friendly_en": "",
             "ambitious_en": "", "formal_zh": "(optional)"},
  "abstract": {"full_en": "", "concise_en": "",
               "full_zh": "(optional)", "logic_audit": ""},
  "keywords": {"scientific": [], "funder_alignment": [],
               "scientific_zh": [], "warnings": []},
  "sections": [
    {"name": "<exact blueprint section name>",
     "content": "<the drafted section in markdown>",
     "must_include_present": [...],
     "must_include_missing": [...],
     "reviewer_traps_addressed": [...],
     "unsupported_claims_flagged": [...]
    }, ...
  ],
  "confirmed_facts": [...],
  "reasonable_assumptions": [...],
  "missing_information": [...]
}

The ``sections`` array must contain ONE entry per section name from
the 24-section blueprint supplied in the user message — in that exact
order.  Sections that the available evidence does not support MUST
still be present with content explaining what is missing (do not silently
skip a section).

When the topic involves molecular emitters / OLEDs / photobiomodulation,
include an explicit conceptual-framework chain inside the section
``"Central Hypothesis"`` of the form:
    molecular design -> excited-state behavior -> device architecture
    -> optical output -> photobiomodulation relevance
so the A-P presentation outline's item 14 has substance to render.

The ``Research Content / Work Packages`` section should design 4-5 WPs,
each with: objective, rationale, methods, measurable outputs, risks,
fallback plan, deliverables.  Use ``WP1: ...`` style headings.
"""


CHINA_REVIEWER_SYSTEM_PROMPT = """\
You are simulating a strict review panel for a China grant proposal.
There are exactly FIVE reviewers, in this canonical order:

  1. novelty            — challenges every novelty claim against the SOTA.
  2. methods            — challenges controls, variables, validation, failure modes.
  3. feasibility        — challenges timeline, equipment, personnel, dependencies.
  4. china_funder_fit   — reads against the specific China call: theme alignment,
                          discipline code, language, compliance, strategic priorities.
  5. budget_compliance  — attacks budget reasonableness, task-to-budget mapping,
                          attachments completeness, ethics/security compliance.

For each reviewer produce:
{
  "reviewer_kind": "novelty | methods | feasibility | china_funder_fit | budget_compliance",
  "strengths": [...],
  "weaknesses": [...],
  "likely_score": <0-100>,
  "rejection_risk": "low | moderate | high | very_high",
  "required_fixes": [...]
}

OUTPUT STRICT JSON:
{ "reviews": [ <five reviewer objects in canonical order> ] }

RULES:
- Be brutal but constructive.  A reviewer that finds no weaknesses is
  not doing their job.
- ``likely_score`` is the reviewer's own band (0-100) — not the final
  competitiveness score.
- ``required_fixes`` MUST be actionable (e.g. "add controls X, Y to
  WP2 methods"), not vague ("strengthen methods").
- Never recommend submission.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CHINA_FORBIDDEN_PATTERNS = tuple(
    p.lower() for p in
    (CHINA_GRANT_FORBIDDEN_INTENT_PATTERNS + CHINA_GRANT_FORBIDDEN_ACTIONS)
)


def _china_safe(text: Any, n: int = 1500) -> str:
    if text is None:
        return ""
    s = json.dumps(text) if not isinstance(text, str) else text
    return s[:n]


def _china_filter_forbidden_actions(actions: list) -> tuple[list, list[str]]:
    """Strip any recommended_actions that match a forbidden behaviour.

    Returns (clean_actions, blocked_descriptions).
    """
    clean: list = []
    blocked: list[str] = []
    for a in actions or []:
        desc = ""
        if isinstance(a, dict):
            desc = (a.get("description") or "").lower()
        elif isinstance(a, str):
            desc = a.lower()
        if any(p in desc for p in _CHINA_FORBIDDEN_PATTERNS):
            blocked.append(desc[:200])
            continue
        clean.append(a)
    return clean, blocked


def _china_scout_excerpt(scout: dict) -> str:
    if not isinstance(scout, dict):
        return ""
    keep = {
        "gap_analysis": scout.get("gap_analysis"),
        "top_papers": (scout.get("top_papers") or [])[:8],
        "supporting_claims": (scout.get("supporting_claims") or [])[:6],
    }
    return _china_safe(keep, 2000)


def _china_general_architect_excerpt(general: dict) -> str:
    if not isinstance(general, dict):
        return ""
    keep = {
        k: general.get(k) for k in (
            "possible_title", "problem_statement", "central_hypothesis",
            "objectives", "work_packages", "methodology_overview",
            "expected_outcomes", "reviewer_attack_points",
            "evidence_needed_before_submission",
            "risk_mitigation", "timeline", "budget", "team_roles",
            "references_used",
        )
    }
    return _china_safe(keep, 3500)


def _china_normalise_sections(
    raw_sections: list, blueprint_order: list[str],
) -> list[ChinaProposalSection]:
    """Reorder LLM sections to match the blueprint; insert missing ones
    as empty placeholders so the contract holds."""
    by_name: dict[str, dict] = {}
    for s in raw_sections or []:
        if isinstance(s, dict):
            name = str(s.get("name", "")).strip()
            if name:
                by_name[name] = s
    out: list[ChinaProposalSection] = []
    for name in blueprint_order:
        s = by_name.get(name) or {}
        out.append(ChinaProposalSection(
            name=name,
            content=str(s.get("content") or ""),
            must_include_present=[
                str(x) for x in (s.get("must_include_present") or [])
                if isinstance(x, str)
            ][:12],
            must_include_missing=[
                str(x) for x in (s.get("must_include_missing") or [])
                if isinstance(x, str)
            ][:12],
            reviewer_traps_addressed=[
                str(x) for x in (s.get("reviewer_traps_addressed") or [])
                if isinstance(x, str)
            ][:8],
            unsupported_claims_flagged=[
                str(x) for x in (s.get("unsupported_claims_flagged") or [])
                if isinstance(x, str)
            ][:8],
        ))
    return out


def _china_normalise_reviewers(
    raw_reviews: list,
) -> list[ChinaReviewerSimulation]:
    """Force reviewers into canonical roster order; backfill missing ones."""
    by_kind: dict[str, dict] = {}
    for r in raw_reviews or []:
        if isinstance(r, dict):
            kind = str(r.get("reviewer_kind", "")).strip().lower()
            if kind in CHINA_GRANT_REVIEWER_ROSTER:
                by_kind[kind] = r
    out: list[ChinaReviewerSimulation] = []
    for kind in CHINA_GRANT_REVIEWER_ROSTER:
        r = by_kind.get(kind) or {}
        try:
            likely = int(r.get("likely_score", 0))
        except (TypeError, ValueError):
            likely = 0
        risk = str(r.get("rejection_risk", "moderate")).strip().lower()
        if risk not in ("low", "moderate", "high", "very_high"):
            risk = "moderate"
        out.append(ChinaReviewerSimulation(
            reviewer_kind=kind,
            strengths=[s for s in (r.get("strengths") or []) if isinstance(s, str)][:6],
            weaknesses=[s for s in (r.get("weaknesses") or []) if isinstance(s, str)][:8],
            likely_score=max(0, min(100, likely)),
            rejection_risk=risk,
            required_fixes=[s for s in (r.get("required_fixes") or []) if isinstance(s, str)][:8],
        ))
    return out


def _china_score(
    sections: list[ChinaProposalSection],
    reviewers: list[ChinaReviewerSimulation],
    has_call_metadata: bool,
) -> ChinaCompetitivenessScore:
    """Deterministic scoring from reviewer signal + section completeness.

    Per-axis ceiling = rubric weight (Part 7 §21).  Each axis is
    derived from a reviewer's likely_score *normalised to its weight*
    plus penalties for sections that flagged missing must_include
    items or unsupported claims.  This keeps the score reproducible
    rather than an LLM "vibe number".
    """
    by_kind = {r.reviewer_kind: r for r in reviewers}

    def axis(kind: str, weight: int) -> int:
        r = by_kind.get(kind)
        if r is None:
            return weight // 2
        return int(round(weight * r.likely_score / 100.0))

    missing_must = sum(len(s.must_include_missing) for s in sections)
    unsupported = sum(len(s.unsupported_claims_flagged) for s in sections)
    penalty = min(10, missing_must) + min(10, unsupported)

    subs = {
        "call_alignment":         axis("china_funder_fit",  CHINA_GRANT_SCORE_RUBRIC["call_alignment"]),
        "scientific_significance": axis("novelty",          CHINA_GRANT_SCORE_RUBRIC["scientific_significance"]),
        "originality_innovation": axis("novelty",           CHINA_GRANT_SCORE_RUBRIC["originality_innovation"]),
        "hypothesis_clarity":     axis("methods",           CHINA_GRANT_SCORE_RUBRIC["hypothesis_clarity"]),
        "methodological_rigor":   axis("methods",           CHINA_GRANT_SCORE_RUBRIC["methodological_rigor"]),
        "feasibility":            axis("feasibility",       CHINA_GRANT_SCORE_RUBRIC["feasibility"]),
        "research_foundation":    axis("feasibility",       CHINA_GRANT_SCORE_RUBRIC["research_foundation"]),
        "budget_logic":           axis("budget_compliance", CHINA_GRANT_SCORE_RUBRIC["budget_logic"]),
        "risk_mitigation":        axis("methods",           CHINA_GRANT_SCORE_RUBRIC["risk_mitigation"]),
        "compliance_completeness": axis("budget_compliance", CHINA_GRANT_SCORE_RUBRIC["compliance_completeness"]),
    }
    # If we have no call metadata, cap call_alignment at half-weight —
    # the proposal cannot legitimately claim strong alignment with an
    # unknown call.
    if not has_call_metadata:
        subs["call_alignment"] = min(
            subs["call_alignment"], CHINA_GRANT_SCORE_RUBRIC["call_alignment"] // 2,
        )

    total = max(0, sum(subs.values()) - penalty)
    return ChinaCompetitivenessScore(
        subscores=subs,
        total=total,
        band=classify_competitiveness(total),
    )


def _china_repair_plan(
    sections: list[ChinaProposalSection],
    reviewers: list[ChinaReviewerSimulation],
    score: ChinaCompetitivenessScore,
) -> list[ChinaWeaknessRepairItem]:
    """Compose the top-5 weakness repair plan (Part 7 §22).

    Priority = reviewer rejection_risk weighted by axis weight.
    """
    risk_w = {"very_high": 4, "high": 3, "moderate": 2, "low": 1}
    items: list[tuple[int, ChinaWeaknessRepairItem]] = []
    for r in reviewers:
        for w in r.weaknesses[:3]:
            # Try to match a section by keyword overlap.
            section_name = ""
            best = 0
            for s in sections:
                overlap = sum(
                    1 for tok in w.lower().split()
                    if len(tok) > 3 and tok in s.name.lower()
                )
                if overlap > best:
                    best = overlap
                    section_name = s.name
            prio = risk_w.get(r.rejection_risk, 2)
            items.append((prio, ChinaWeaknessRepairItem(
                weakness=w,
                why_it_matters=f"Flagged by '{r.reviewer_kind}' reviewer "
                               f"(rejection risk={r.rejection_risk}).",
                section_to_rewrite=section_name or "Risk Register and Mitigation",
                exact_revision=(r.required_fixes[0]
                                if r.required_fixes else
                                "Tighten claim and add supporting citation."),
                priority=0,  # filled below
            )))
    # Section-level signals (missing must_includes).
    for s in sections:
        for miss in s.must_include_missing[:2]:
            items.append((1, ChinaWeaknessRepairItem(
                weakness=f"Section '{s.name}' missing required item: {miss}",
                why_it_matters="Listed in the blueprint as must-include — "
                               "reviewers expect it.",
                section_to_rewrite=s.name,
                exact_revision=f"Add: {miss}",
                priority=0,
            )))
    # Rank by priority weight descending; pick top 10 (Part 7 §35 of the
    # user spec).  ``priority`` 1..10 from strongest to weakest.
    items.sort(key=lambda x: x[0], reverse=True)
    top: list[ChinaWeaknessRepairItem] = []
    for i, (_, item) in enumerate(items[:10], start=1):
        item.priority = i
        top.append(item)
    return top


# ---------------------------------------------------------------------------
# A-P outline renderer (default presentation style — user-editable via
# ``apply_china_template_patch``)
# ---------------------------------------------------------------------------

def _china_render_reviewer_block(reviewers: list[ChinaReviewerSimulation]) -> list[str]:
    L: list[str] = []
    for r in reviewers:
        L.append(f"#### {r.reviewer_kind} "
                 f"(likely_score={r.likely_score}, "
                 f"rejection_risk={r.rejection_risk})\n")
        if r.strengths:
            L.append("**Strengths:**")
            for s in r.strengths:
                L.append(f"- {s}")
        if r.weaknesses:
            L.append("\n**Weaknesses:**")
            for w in r.weaknesses:
                L.append(f"- {w}")
        if r.required_fixes:
            L.append("\n**Required fixes (mandatory revisions):**")
            for f in r.required_fixes:
                L.append(f"- {f}")
        L.append("")
    return L


def _china_render_competitiveness_block(
    score: ChinaCompetitivenessScore,
) -> list[str]:
    L: list[str] = []
    L.append("| Axis | Weight | Score |")
    L.append("|---|---|---|")
    for axis, weight in CHINA_GRANT_SCORE_RUBRIC.items():
        got = score.subscores.get(axis, 0)
        L.append(f"| {axis} | {weight} | {got} |")
    L.append(f"| **Total** | **100** | **{score.total}** |")
    L.append("")
    L.append(f"**Decision band:** _{score.band}_  ")
    L.append(f"(>=90 competitive · >=80 promising · >=70 vulnerable · <70 not submission-ready)")
    return L


def _china_render_weakness_block(
    plan: list[ChinaWeaknessRepairItem],
) -> list[str]:
    L: list[str] = []
    if not plan:
        L.append("_(no weaknesses identified — re-run the reviewer simulation)_")
        return L
    for w in plan:
        L.append(f"##### Priority {w.priority}: {w.weakness}")
        L.append(f"- **Why it matters:** {w.why_it_matters}")
        L.append(f"- **What to revise / section to rewrite:** {w.section_to_rewrite}")
        L.append(f"- **Evidence needed / exact revision:** {w.exact_revision}\n")
    return L


def _china_render_section(
    out: ChinaGrantArchitectOutput, section_name: str,
) -> list[str]:
    L: list[str] = []
    sec = next(
        (s for s in out.sections if s.name == section_name), None,
    )
    if sec is None or not sec.content:
        L.append(f"_(blueprint section '{section_name}' not yet drafted)_")
        return L
    L.append(sec.content)
    if sec.must_include_missing:
        L.append("\n> ⚠ Missing must-include items:")
        for m in sec.must_include_missing:
            L.append(f"> - {m}")
    if sec.unsupported_claims_flagged:
        L.append("\n> ⚠ Unsupported claims flagged for evidence:")
        for c in sec.unsupported_claims_flagged:
            L.append(f"> - {c}")
    return L


def _china_render_item_source(
    out: ChinaGrantArchitectOutput, source: dict,
) -> list[str]:
    kind = (source or {}).get("kind", "")
    if kind == "titles_triplet":
        L: list[str] = []
        for key, label in (
            ("formal_en", "Formal scientific title"),
            ("reviewer_friendly_en", "Reviewer-friendly title"),
            ("ambitious_en", "Ambitious but credible title"),
        ):
            L.append(f"- **{label}:** {out.titles.get(key) or '_(not generated)_'}")
        return L
    if kind == "titles_bilingual":
        en = out.titles.get("formal_en") or "_(English title not generated)_"
        zh = out.titles.get("formal_zh") or "_(Chinese title placeholder — fill if required by the call)_"
        return [f"- **English:** {en}", f"- **中文 / Chinese:** {zh}"]
    if kind == "abstract":
        key = source.get("key", "")
        txt = (out.abstract or {}).get(key, "")
        return [txt or "_(not generated)_"]
    if kind == "keywords":
        L = []
        kw = out.keywords or {}
        if not kw:
            return ["_(no keywords generated)_"]
        for cat in ("scientific", "scientific_zh", "funder_alignment", "warnings"):
            vals = kw.get(cat) or []
            if vals:
                label = {"scientific":"Scientific",
                         "scientific_zh":"Scientific (中文)",
                         "funder_alignment":"Funder-alignment",
                         "warnings":"Warnings"}[cat]
                L.append(f"- **{label}:** " + ", ".join(vals))
        return L or ["_(no keywords generated)_"]
    if kind == "section":
        return _china_render_section(out, source.get("name", ""))
    if kind == "section_pair":
        L = []
        for name in source.get("names", []) or []:
            L.append(f"**{name}:**\n")
            L.extend(_china_render_section(out, name))
            L.append("")
        return L
    if kind == "reviewer_simulation":
        return _china_render_reviewer_block(out.reviewer_simulation)
    if kind == "competitiveness":
        return _china_render_competitiveness_block(out.competitiveness_score)
    if kind == "weakness_repair":
        return _china_render_weakness_block(out.weakness_repair_plan)
    if kind == "narrative":
        return [source.get("text", "") or ""]
    return [f"_(unknown outline source kind '{kind}')_"]


def _china_render_markdown(out: ChinaGrantArchitectOutput) -> str:
    """Render the proposal using the resolved template's A-P outline.

    Default style: 16 parts (A-P) carrying 36 numbered items per the
    user spec.  If a user override removes ``presentation_outline``,
    we fall back to the legacy 24-section numeric layout so a malformed
    patch never breaks rendering.
    """
    # Pull the active outline.  Stashed on the output object by run_china().
    outline: list[dict] = list(out.template_presentation_outline or [])

    L: list[str] = []
    L.append("# " + (out.titles.get("formal_en") or "China Grant Proposal Draft"))
    L.append("")
    L.append(f"_Template: `{out.template_id}` v{out.template_version} — "
             f"layers applied: "
             f"{', '.join(out.template_override_layers_applied) or '(master only)'}_")
    L.append("")
    L.append(f"_Competitiveness: **{out.competitiveness_score.total}/100** "
             f"— {out.competitiveness_score.band}_")
    L.append("")

    if outline:
        for part in outline:
            letter = part.get("letter", "?")
            title = part.get("title", "(untitled)")
            L.append(f"## {letter}. {title}\n")
            for it in part.get("items", []) or []:
                number = it.get("number", "?")
                label = it.get("label", "")
                src = it.get("source") or {}
                L.append(f"### {number}. {label}\n")
                L.extend(_china_render_item_source(out, src))
                L.append("")
            L.append("")
    else:
        # Legacy fallback: 24-section numeric layout.
        for i, sec in enumerate(out.sections, start=1):
            L.append(f"## {i}. {sec.name}\n")
            L.append(sec.content or "_(not yet drafted)_")
            if sec.must_include_missing:
                L.append("\n> ⚠ Missing must-include items:")
                for m in sec.must_include_missing:
                    L.append(f"> - {m}")
            if sec.unsupported_claims_flagged:
                L.append("\n> ⚠ Unsupported claims flagged for evidence:")
                for c in sec.unsupported_claims_flagged:
                    L.append(f"> - {c}")
            L.append("")
        L.append("## Reviewer Simulation\n")
        L.extend(_china_render_reviewer_block(out.reviewer_simulation))
        L.append("## Competitiveness Scorecard\n")
        L.extend(_china_render_competitiveness_block(out.competitiveness_score))
        L.append("")
        L.append("## Weakness Repair Plan (top 10)\n")
        L.extend(_china_render_weakness_block(out.weakness_repair_plan))

    # ---- Tail: information-state separation (always emitted) ---------
    L.append("\n## Information State\n")
    L.append("**Confirmed facts:**")
    for x in out.confirmed_facts or ["_(none)_"]:
        L.append(f"- {x}")
    L.append("\n**Reasonable assumptions:**")
    for x in out.reasonable_assumptions or ["_(none)_"]:
        L.append(f"- {x}")
    L.append("\n**Missing information:**")
    for x in out.missing_information or ["_(none)_"]:
        L.append(f"- {x}")

    # ---- Local-document evidence used (user-provided files) ----------
    L.append("\n## Local-document evidence used\n")
    if out.local_literature_evidence_used:
        for r in out.local_literature_evidence_used[:12]:
            if not isinstance(r, dict):
                continue
            doc = r.get("document_title") or r.get("document_id") or "(local doc)"
            excerpt = (r.get("excerpt") or "")[:240].replace("\n", " ")
            L.append(
                f"- **[LOCAL:{r.get('document_id','?')}]** {doc} — "
                f"_{excerpt}_"
            )
    else:
        L.append(
            "_No user-provided local files were ingested for this run. "
            "Enable the local_documents subsystem and point it at a "
            "folder to add PDF / DOCX / TXT evidence to the proposal._"
        )

    # ---- References (always emitted — was missing in earlier builds) -
    L.append("\n## References\n")
    if out.references_used:
        if (out.scout_diagnostics or {}).get("self_heal_used"):
            L.append(
                "_⚠ **Self-heal triggered.** Research Scout returned "
                "zero papers (likely routed in `ideation` mode), so the "
                "architect ran an EMERGENCY direct fetch against the "
                "5-provider abstraction (OpenAlex · arXiv · Crossref · "
                "Semantic Scholar · Europe PMC).  These references "
                "BYPASSED Scout's scoring + dedup + gap-analysis "
                "pipeline — treat their relevance as provisional and "
                "re-run with the routing fix in place for full quality._\n"
            )
        else:
            L.append(
                "_Retrieved by Research Scout via the multi-provider "
                "literature scan (OpenAlex · arXiv · Crossref · Semantic "
                "Scholar · Europe PMC).  Each item is cited with [N] in "
                "the section bodies above._\n"
            )
        for ref in out.references_used:
            L.append(ref)
    else:
        # Render the ACTUAL Scout diagnostic state so the user can
        # immediately diagnose WHICH failure mode hit, instead of
        # facing a generic 4-cause list.
        d = out.scout_diagnostics or {}
        L.append(
            "_No references reached the architect for this run.  "
            "Below is the actual Scout diagnostic state — use it to "
            "pinpoint the failure._\n"
        )
        L.append("**Research Scout diagnostic snapshot:**")
        L.append(f"- `scout_invoked`        : `{d.get('scout_invoked', False)}`")
        L.append(f"- `literature_scan_used` : `{d.get('literature_scan_used', False)}`")
        L.append(f"- `scout_mode`           : `{d.get('scout_mode', 'unknown')}`")
        L.append(f"- `raw_papers_seen`      : `{d.get('raw_papers_seen', 0)}`")
        provider_counts = d.get("provider_counts") or {}
        if provider_counts:
            L.append("- `provider_counts`      : `"
                     + ", ".join(f"{k}={v}" for k, v in provider_counts.items())
                     + "`")
        else:
            L.append("- `provider_counts`      : `(none — no papers from any of OpenAlex / arXiv / Crossref / Semantic Scholar / Europe PMC)`")
        queries = d.get("queries_used") or []
        if queries:
            L.append("- `queries_used`         :")
            for q in queries[:5]:
                L.append(f"    - `{q}`")
        else:
            L.append("- `queries_used`         : `(none recorded)`")
        errors = d.get("source_errors") or []
        if errors:
            L.append("- **Provider errors caught upstream:**")
            for e in errors[:5]:
                L.append(f"    - {e}")
        risks = d.get("scout_risks") or []
        if risks:
            L.append("- **Scout-level risks:**")
            for r in risks:
                L.append(f"    - {r}")
        # Actionable diagnosis based on the diagnostic state.
        L.append("")
        L.append("**Most likely cause + fix:**")
        if not d.get("scout_invoked"):
            L.append(
                "- ❌ Scout was not invoked.  The Strategic Governor "
                "either omitted `research_scout` or the orchestrator "
                "dropped it.  Re-run; the registry's evidence-heavy "
                "whitelist now includes `china_grant_architect` so "
                "Scout is auto-prepended."
            )
        elif d.get("scout_mode") != "literature_scan" and not d.get("literature_scan_used"):
            L.append(
                f"- ❌ Scout ran in `{d.get('scout_mode', 'unknown')}` "
                "mode — does NOT fetch papers.  The Governor's mode-"
                "upgrade rule should force `literature_scan`; re-run "
                "with verbose Governor logging to see why it didn't."
            )
        elif errors and len(errors) >= 3:
            L.append(
                f"- ❌ All 5 providers returned errors "
                f"({len(errors)} caught).  Likely network outage or "
                "egress firewall.  Verify connectivity to "
                "api.openalex.org · export.arxiv.org · api.crossref.org "
                "· api.semanticscholar.org · www.ebi.ac.uk/europepmc."
            )
        elif int(d.get("raw_papers_seen", 0)) == 0:
            L.append(
                "- ❌ Scout's literature scan ran but returned 0 raw "
                "papers from any provider.  Query likely too narrow "
                "or off-topic.  Either re-run with broader terms "
                "(e.g. \"MR-TADF NIR OLEDs\" instead of a long "
                "compound query) or paste a References block in the "
                "user prompt — the architect preserves it."
            )
        else:
            L.append(
                f"- ⚠ Scout fetched {d.get('raw_papers_seen', 0)} raw "
                "papers but they were filtered out by the scoring "
                "stage before reaching the architect.  Either the "
                "papers were off-topic (scoring threshold too strict) "
                "or the scoring LLM failed.  Check "
                "`reports/weekly_brief_*` for the latest scoring log."
            )
    return "\n".join(L)


_CHINA_QUERY_PLAN_PROMPT = """\
You are planning a focused literature search to back a China grant
proposal.  Given the user request and any call metadata, produce 3-5
PRECISE search queries that a scientific database (OpenAlex, Crossref,
arXiv, Semantic Scholar, Europe PMC) would resolve to the MOST relevant
papers.

Rules:
- Queries must be specific to the actual topic (materials, device,
  wavelength, mechanism), NOT generic.
- Prefer the exact technical terms a domain expert would use.
- Do NOT pad with filler words; each query is 3-8 keywords.

OUTPUT STRICT JSON:
{ "queries": ["...", "...", "..."] }
"""


_CHINA_SCORE_PAPERS_PROMPT = """\
Score each candidate paper's RELEVANCE to the research topic on a
0.0-1.0 scale, where:
  1.0 = directly on-topic (same materials/device/mechanism/application)
  0.5 = adjacent / partially relevant
  0.0 = off-topic (different field, a software package, unrelated)

Be strict.  A green-OLED paper is NOT highly relevant to a red/NIR
proposal.  A statistics package is 0.0.

OUTPUT STRICT JSON:
{ "scores": [ {"index": <int>, "relevance": <0.0-1.0>,
               "reason": "<one short clause>"}, ... ] }
The ``index`` MUST match the paper's [index] in the input list.
"""


def _china_self_heal_literature(
    *, user_input: str, call_meta: dict, max_refs: int = 12,
    min_refs: int = 5, relevance_threshold: float = 0.5,
    soft_floor: float = 0.3,
) -> tuple[list[dict], list[str]]:
    """Emergency, RELEVANCE-SCORED literature fetch.

    Used only when Research Scout returned zero papers.  Steps:
      1. LLM plans 4-6 focused search queries,
      2. fetch candidates from the 5-provider abstraction at a HIGHER
         per-query depth than Scout's default (so the pool isn't
         starved when some providers rate-limit),
      3. LLM scores each candidate's relevance 0-1,
      4. keep all papers >= ``relevance_threshold``; if fewer than
         ``min_refs`` pass, BACKFILL with the next-most-relevant
         papers down to ``soft_floor`` so the proposal always has a
         usable evidence base (the user wants >= 5),
      5. cap at ``max_refs``.

    Returns ``(scored_papers, references_list)``.  Empty lists only
    when literally nothing relevant exists.
    """
    from integrations.research_evolution.paper_sources import (
        search_all_sources, deduplicate_papers,
    )

    topic = (user_input or "").strip()
    theme = str(call_meta.get("specific_theme") or "").strip()
    seed = (topic + (" " + theme if theme else "")).strip() or "MR-TADF red NIR OLED"

    # 1. LLM query planning (4-6 focused queries) -------------------------
    queries: list[str] = []
    try:
        plan = ask_json(
            _CHINA_QUERY_PLAN_PROMPT,
            f"User request:\n{topic}\n\nCall metadata:\n{_china_safe(call_meta, 600)}",
            temperature=0.1,
        ) or {}
        queries = [
            str(q).strip() for q in (plan.get("queries") or [])
            if isinstance(q, str) and q.strip()
        ][:6]
    except Exception:
        queries = []
    if not queries:
        queries = [seed[:160]]

    # 2. Fetch candidates — call search_all_sources DIRECTLY with a
    #    higher per-query depth (8 vs discover_papers' hardcoded 3) so
    #    a few provider rate-limits don't starve the pool.
    try:
        raw = search_all_sources(queries[:6], max_per_topic=8)
        candidates = [
            p for p in raw
            if isinstance(p, dict)
            and "source_error" not in p and "source_errors" not in p
            and p.get("title")
        ]
        candidates = deduplicate_papers(candidates)
    except Exception:
        candidates = []
    if not candidates:
        return [], []

    # De-dup by title (belt-and-braces) before scoring.
    seen_titles: set[str] = set()
    deduped: list[dict] = []
    for p in candidates:
        key = (p.get("title") or "").strip().lower()[:120]
        if key and key not in seen_titles:
            seen_titles.add(key)
            deduped.append(p)
    deduped = deduped[:40]   # cap LLM scoring input

    # 3. LLM relevance scoring --------------------------------------------
    paper_lines = []
    for i, p in enumerate(deduped):
        title = (p.get("title") or "")[:200]
        abstract = (p.get("abstract") or "")[:300]
        paper_lines.append(f"[{i}] {title}\n    {abstract}")
    scores_by_index: dict[int, float] = {}
    try:
        scored = ask_json(
            _CHINA_SCORE_PAPERS_PROMPT,
            f"Research topic:\n{topic}\n\nCandidate papers:\n"
            + "\n".join(paper_lines),
            temperature=0.0,
        ) or {}
        for s in (scored.get("scores") or []):
            if not isinstance(s, dict):
                continue
            try:
                idx = int(s.get("index"))
                rel = float(s.get("relevance"))
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(deduped):
                scores_by_index[idx] = max(0.0, min(1.0, rel))
    except Exception:
        scores_by_index = {}

    # 4. Filter + relevance-ranked BACKFILL -------------------------------
    if scores_by_index:
        ranked = sorted(
            ((scores_by_index.get(i, 0.0), p) for i, p in enumerate(deduped)),
            key=lambda x: x[0], reverse=True,
        )
        # First pass: strict threshold.
        kept_pairs = [(rel, p) for rel, p in ranked if rel >= relevance_threshold]
        # Backfill: if we have fewer than min_refs, add the next-best
        # papers down to the soft floor (still on-topic, just less
        # central) until we reach min_refs or run out.
        if len(kept_pairs) < min_refs:
            for rel, p in ranked:
                if rel >= relevance_threshold:
                    continue          # already kept
                if rel < soft_floor:
                    break             # ranked desc — nothing else qualifies
                kept_pairs.append((rel, p))
                if len(kept_pairs) >= min_refs:
                    break
        for rel, p in kept_pairs:
            p["relevance_score"] = round(rel, 2)
        kept = [p for _, p in kept_pairs]
    else:
        # Scoring LLM failed — fall back to recency+DOI ranking.
        def _k(p):
            yr = (p.get("published_date") or "")[:4]
            try:
                return (1 if p.get("doi") else 0, int(yr))
            except Exception:
                return (1 if p.get("doi") else 0, 0)
        kept = sorted(deduped, key=_k, reverse=True)[:max_refs]

    kept = kept[:max_refs]
    if not kept:
        return [], []
    references_list = _references_list_from_scout(
        {"top_papers": kept}, max_refs=max_refs,
    )
    return kept, references_list


def _china_capture_reflection(
    *, user_input: str, call_meta: dict, score: ChinaCompetitivenessScore,
    reviewers: list[ChinaReviewerSimulation], blocked: list[str],
) -> dict:
    """Build the Part-11 reflection record and persist it.

    Stores reusable strategic lessons only — not every raw sentence.
    """
    reviewer_risks = [
        f"{r.reviewer_kind}: {r.rejection_risk}"
        for r in reviewers if r.rejection_risk in ("high", "very_high")
    ]
    weak_patterns: list[str] = []
    for r in reviewers:
        weak_patterns.extend(r.weaknesses[:1])
    reflection = {
        "reflection_type": "grant_proposal_learning",
        "grant_region": "China",
        "call_type": call_meta.get("program_type", "") or "unknown",
        "proposal_topic": (user_input or "")[:200],
        "useful_patterns": [],
        "weak_patterns": weak_patterns[:8],
        "user_preferences": [],
        "reviewer_risks": reviewer_risks,
        "budget_lessons": [],
        "compliance_lessons": [],
        "template_updates_suggested": [],
        "approved_for_memory": score.total >= 70,
        "score_total": score.total,
        "score_band": score.band,
        "blocked_forbidden_actions": blocked,
    }
    try:
        save_reflection(reflection)
    except Exception:
        pass
    return reflection


def _china_fallback(reason: Any) -> dict:
    """Return a defensive empty output that still passes the contract.

    Emits a SINGLE clean failure-cause line via ``missing_information``
    rather than copying the raw exception text into every reviewer's
    weaknesses + every weakness-repair item (which produced a flood of
    duplicated truncated-JSON snippets in earlier builds).  Reviewers
    are returned with a single neutral note that the drafting step
    failed — the noisy details live in one place only.
    """
    cause = str(reason)[:300]
    # Strip raw JSON fragments from the reason line so the placeholder
    # markdown is readable.  If the reason contains a "{" we only keep
    # the prefix before it.
    if "{" in cause:
        cause = cause.split("{", 1)[0].rstrip(":; ") or cause[:200]
    out = ChinaGrantArchitectOutput(
        template_id=TEMPLATE_ID,
        template_version="1.0",
        template_override_layers_applied=[],
        sections=[
            ChinaProposalSection(
                name=name,
                content=f"_(drafting failed — see Missing Information)_",
            )
            for name in CHINA_GRANT_PROPOSAL_SECTIONS
        ],
        reviewer_simulation=[
            ChinaReviewerSimulation(
                reviewer_kind=kind,
                weaknesses=[
                    "Cannot review — drafting step did not complete.",
                ],
                rejection_risk="very_high",
                required_fixes=[
                    "Re-run after fixing the drafting failure (see Missing "
                    "Information for the cause).",
                ],
            )
            for kind in CHINA_GRANT_REVIEWER_ROSTER
        ],
        missing_information=[f"Drafting failed: {cause}"],
        summary="China Grant Architect failed to produce a draft.",
        risks=[
            "Drafting step did not complete; the report is a structural "
            "placeholder only. Do NOT treat any field as evidence-backed.",
        ],
        confidence="low",
        evidence_level="none",
    )
    out.competitiveness_score = _china_score(
        out.sections, out.reviewer_simulation, has_call_metadata=False,
    )
    # Synthesise a single repair-plan item rather than 5 copies of the
    # same failure noise.
    out.weakness_repair_plan = [
        ChinaWeaknessRepairItem(
            weakness="Drafting step failed — no content available to "
                     "evaluate.",
            why_it_matters="No section content was produced, so no "
                           "reviewer assessment is possible.",
            section_to_rewrite="(re-run the architect)",
            exact_revision=(
                "Re-run with a smaller scope (fewer sections in one go), "
                "a broader query, or after verifying the LLM endpoint is "
                "reachable.  See Missing Information for the underlying "
                "cause."
            ),
            priority=1,
        )
    ]
    return out.model_dump()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_china(user_input: str, context: dict | None = None) -> dict:
    """Generate a China-tailored grant proposal draft.

    Expected context keys (all optional — module degrades gracefully):
        ``research_scout``           — Scout output (gap, top_papers)
        ``grant_architect``          — general Grant Architect output, used
                                       as a backbone IF supplied.  NOTE:
                                       in default routing the Strategic
                                       Governor demotes the general
                                       grant_architect when this agent is
                                       selected (to avoid duplicate proposal
                                       drafting), so this key is usually
                                       ABSENT and the architect drafts from
                                       Scout + the China blueprint directly.
        ``strategic_governor``       — Governor signals
        ``china_call_metadata``      — dict of Part-3 §A call inputs
        ``china_call_scope``         — string key for per-call overrides
        ``china_user_scope``         — string key for per-user overrides
    """
    ctx = context or {}
    call_meta: dict = ctx.get("china_call_metadata") or {}
    call_scope: str = str(ctx.get("china_call_scope") or "").strip()
    user_scope: str = str(ctx.get("china_user_scope") or "user").strip() or "user"

    # ---- 1. Resolve effective template (layered overrides) -------------
    try:
        template = resolve_template(call_scope=call_scope, user_scope=user_scope)
    except Exception:
        from core.grant_templates.china_blueprint import (
            CHINA_GRANT_MASTER_TEMPLATE,
        )
        template = dict(CHINA_GRANT_MASTER_TEMPLATE)
    blueprint_order: list[str] = template.get(
        "sections", list(CHINA_GRANT_PROPOSAL_SECTIONS),
    )
    layers_applied: list[str] = ["china_grant_master_template"]
    if user_scope:
        layers_applied.append(f"user_override_preferences:{user_scope}")
    if call_scope:
        layers_applied.append(f"specific_call_requirements:{call_scope}")

    # ---- 2. Pull memory + upstream context -----------------------------
    try:
        memory_records = retrieve_relevant_memory(
            f"china grant {user_input}", limit=8,
        ) or []
    except Exception:
        memory_records = []

    # The orchestrator can pass upstream specialist outputs either at
    # the top level (``ctx["research_scout"]``) or nested under a
    # ``ctx["specialists"]`` dict.  Check both so References are
    # populated regardless of wrapping convention.
    specialists = ctx.get("specialists") if isinstance(ctx.get("specialists"), dict) else {}
    scout = (
        ctx.get("research_scout")
        or (specialists.get("research_scout") if specialists else None)
        or {}
    )
    general_architect = (
        ctx.get("grant_architect")
        or (specialists.get("grant_architect") if specialists else None)
        or {}
    )
    governor = (
        ctx.get("strategic_governor")
        or (specialists.get("strategic_governor") if specialists else None)
        or {}
    )

    # ---- 3. Build the drafting prompt ---------------------------------
    # ---- Build numbered References block + local-document evidence ---
    # Two evidence sources reach the China architect via the orchestrator:
    #   (a) Scout's web/database literature (``scout['top_papers']``)
    #   (b) Scout's local-document chunks (``scout['local_literature_evidence']``
    #       and the pre-formatted ``scout['local_evidence_prompt_block']``)
    # We surface BOTH to the drafting LLM so it can back claims with [N]
    # citations.  Without this, the LLM has no anchored evidence and
    # ends up flagging "specific literature citations" as missing in
    # every section's must_include_missing — the symptom you reported.
    references_list = _references_list_from_scout(scout, max_refs=12)

    # ---- SELF-HEAL: emergency RELEVANCE-SCORED literature fetch ------
    # If Scout came back with ZERO papers (because routing landed it in
    # ``ideation`` mode, the workflow upstream broke, or Scout was never
    # called), the architect would otherwise have no evidence to cite.
    # ``_china_self_heal_literature`` runs a focused mini-scan:
    #   1. LLM plans 3-5 precise search queries from the request,
    #   2. fetches candidates from the 5-provider abstraction,
    #   3. LLM scores each candidate's relevance 0-1,
    #   4. keeps only papers >= 0.5 (sorted by relevance).
    # This stops the previous failure where the naive fetch returned
    # off-topic junk (a statistics R-package, green-OLED papers for a
    # red/NIR proposal).
    self_heal_used = False
    if not references_list:
        try:
            healed_papers, healed_refs = _china_self_heal_literature(
                user_input=user_input, call_meta=call_meta, max_refs=10,
            )
            if healed_refs:
                references_list = healed_refs
                scout = dict(scout or {})
                scout["top_papers"] = healed_papers
                self_heal_used = True
                print(
                    f"[china_grant_architect] self-heal: Scout returned "
                    f"0 papers; relevance-scored mini-scan kept "
                    f"{len(healed_refs)} on-topic references.",
                    flush=True,
                )
            else:
                print(
                    "[china_grant_architect] self-heal: mini-scan found "
                    "no sufficiently relevant papers (threshold 0.5); "
                    "leaving References empty rather than citing junk.",
                    flush=True,
                )
        except Exception as exc:
            # Self-heal is best-effort.  If it fails, fall through to
            # the existing empty-References diagnostic placeholder.
            print(
                f"[china_grant_architect] self-heal failed: "
                f"{exc.__class__.__name__}: {str(exc)[:160]}",
                flush=True,
            )
    # Count provider coverage so the LLM (and the user) can see which
    # of the five databases (OpenAlex / arXiv / Crossref / Semantic
    # Scholar / Europe PMC) actually contributed papers.  The scoring
    # downstream of Scout writes ``source`` on every paper.
    provider_counts: dict[str, int] = {}
    for p in (scout or {}).get("top_papers") or []:
        if isinstance(p, dict):
            src = (p.get("source") or "unknown").lower()
            provider_counts[src] = provider_counts.get(src, 0) + 1

    # Build a structured scout-diagnostic block so the empty-References
    # placeholder can show EXACTLY what happened — was Scout invoked,
    # in which mode, with which queries, and which providers errored?
    # (Re-count provider coverage AFTER the self-heal step so the
    # diagnostic reflects the actual final state.)
    provider_counts = {}
    for p in (scout or {}).get("top_papers") or []:
        if isinstance(p, dict):
            src = (p.get("source") or "unknown").lower()
            provider_counts[src] = provider_counts.get(src, 0) + 1
    scout_diagnostics = {
        "scout_invoked": bool(scout),
        "literature_scan_used": bool(
            (scout or {}).get("literature_scan_used")
        ),
        "scout_mode": (scout or {}).get("mode", "unknown"),
        "queries_used": [
            str(q) for q in ((scout or {}).get("queries_used") or [])
            if isinstance(q, str)
        ][:10],
        "raw_papers_seen": len((scout or {}).get("top_papers") or []),
        "provider_counts": dict(provider_counts),
        "source_errors": [
            str(f) for f in ((scout or {}).get("findings") or [])
            if isinstance(f, str) and f.lower().startswith("source error")
        ][:5],
        "scout_risks": [
            str(r) for r in ((scout or {}).get("risks") or [])
            if isinstance(r, str)
        ][:3],
        # New: was the architect's emergency self-heal fetch used?
        "self_heal_used": self_heal_used,
    }
    if references_list:
        cover_line = (
            "Provider coverage (Research Scout retrieved papers from): "
            + ", ".join(f"{k}={v}" for k, v in sorted(provider_counts.items()))
            + ". "
            "These five databases — OpenAlex, arXiv, Crossref, Semantic "
            "Scholar, Europe PMC — are the AURA literature scan's "
            "full provider set."
        )
        references_block_for_prompt = (
            cover_line + "\n\n"
            "References (cite these with [N] in every section's content):\n"
            + "\n".join(references_list)
        )
    else:
        references_block_for_prompt = (
            "References: (none — Research Scout's multi-provider scan "
            "(OpenAlex · arXiv · Crossref · Semantic Scholar · Europe "
            "PMC) returned zero usable papers for this query.  Every "
            "quantitative or comparative claim MUST be added to "
            "missing_information instead of cited.)"
        )

    local_evidence_block = ""
    local_lit = (scout or {}).get("local_literature_evidence") or []
    if isinstance(local_lit, list) and local_lit:
        # Prefer the pre-formatted block Scout already produced.
        pre = (scout or {}).get("local_evidence_prompt_block") or ""
        if isinstance(pre, str) and pre.strip():
            local_evidence_block = (
                "\n\nLocal-document evidence (user-provided PDFs / DOCX / "
                "TXT — cite with the [LOCAL:<doc_id>] anchors shown below "
                "in any section where they support the claim):\n" + pre[:3500]
            )
        else:
            # Fall back to a compact summary.
            keep = [
                {"doc": (r.get("document_title") or r.get("document_id") or ""),
                 "excerpt": (r.get("excerpt") or "")[:300]}
                for r in local_lit[:6] if isinstance(r, dict)
            ]
            local_evidence_block = (
                "\n\nLocal-document evidence (from user-provided files; "
                "cite as [LOCAL:<doc>] in the relevant section):\n"
                + _china_safe(keep, 3000)
            )

    # Shared context block used by EVERY drafting sub-call.  Kept tight
    # so the per-chunk payload stays well under the 8192-token output
    # budget (room for the LLM's actual JSON response).
    _shared_ctx = (
        f"User request:\n{user_input}\n\n"
        f"China call metadata (may be partial — flag what is missing):\n"
        f"{_china_safe(call_meta, 1000)}\n\n"
        f"Strategic Governor signals:\n"
        f"{_china_safe({k: governor.get(k) for k in ('task_type','evidence_requirement','autonomy_level','rationale')}, 400)}\n\n"
        f"Research Scout excerpt:\n{_china_scout_excerpt(scout)}\n\n"
        f"General Grant Architect skeleton (use as starting backbone):\n"
        f"{_china_general_architect_excerpt(general_architect)}\n\n"
        f"Relevant AURA memory (top 8):\n{_china_safe(memory_records[:8], 1000)}\n\n"
        f"{references_block_for_prompt}\n"
        f"{local_evidence_block}\n\n"
    )

    # ---- 4. CHUNKED DRAFTING ------------------------------------------
    # The earlier single-call design blew the LLM output budget (~12K
    # tokens of JSON for 24 bilingual sections + state + headers) and
    # the truncated JSON couldn't be repaired.  We now split the work:
    #
    #   Sub-call 1 (framing) : titles, abstract, keywords, confirmed_facts,
    #                           reasonable_assumptions, missing_information
    #   Sub-call 2..N        : sections, in chunks of CHUNK_SIZE
    #
    # If any sub-call fails, the others still succeed → partial output
    # is preserved instead of the entire run collapsing to placeholders.
    CHUNK_SIZE = 8
    section_hints = template.get("section_hints", {}) or {}

    drafted: dict = {
        "titles": {}, "abstract": {}, "keywords": {},
        "sections": [],
        "confirmed_facts": [], "reasonable_assumptions": [],
        "missing_information": [],
    }
    sub_call_errors: list[str] = []

    # --- Sub-call 1: framing (no sections in this call) ---------------
    framing_prompt = (
        _shared_ctx
        + "Task A: produce ONLY the framing fields (no `sections` "
        "array in this call).  Return strict JSON with this shape:\n"
        "{\n"
        '  "titles": {"formal_en": "", "reviewer_friendly_en": "", '
        '"ambitious_en": "", "formal_zh": "(optional)"},\n'
        '  "abstract": {"full_en": "", "concise_en": "", '
        '"full_zh": "(optional)", "logic_audit": ""},\n'
        '  "keywords": {"scientific": [], "funder_alignment": [], '
        '"scientific_zh": [], "warnings": []},\n'
        '  "confirmed_facts": [...],\n'
        '  "reasonable_assumptions": [...],\n'
        '  "missing_information": [...]\n'
        "}\n"
        "Be honest about missing evidence.  No prose, no markdown."
    )
    try:
        framing = ask_json(
            CHINA_DRAFTING_SYSTEM_PROMPT, framing_prompt, temperature=0.15,
        )
        if isinstance(framing, dict):
            for k in ("titles", "abstract", "keywords",
                      "confirmed_facts", "reasonable_assumptions",
                      "missing_information"):
                if framing.get(k) is not None:
                    drafted[k] = framing[k]
    except Exception as exc:
        sub_call_errors.append(
            f"framing sub-call failed: "
            f"{exc.__class__.__name__}: {str(exc)[:160]}"
        )

    # --- Sub-calls 2..N: sections, chunked ----------------------------
    drafted_sections: list[dict] = []
    chunks = [
        blueprint_order[i:i + CHUNK_SIZE]
        for i in range(0, len(blueprint_order), CHUNK_SIZE)
    ]
    for chunk_idx, chunk in enumerate(chunks, start=1):
        # Only ship the hints for THIS chunk's sections to keep input lean.
        hints_for_chunk = {n: section_hints.get(n, {}) for n in chunk}
        sections_prompt = (
            _shared_ctx
            + f"Task B (chunk {chunk_idx}/{len(chunks)}): draft "
            f"ONLY these {len(chunk)} sections, in this exact order:\n"
            + "\n".join(f"  - {n}" for n in chunk)
            + "\n\nPer-section drafting hints (for THIS chunk only):\n"
            + _china_safe(hints_for_chunk, 3000)
            + "\n\nReturn STRICT JSON of shape:\n"
            "{\n"
            '  "sections": [\n'
            '    {"name": "<exact section name>", "content": "<markdown>", '
            '"must_include_present": [...], "must_include_missing": [...], '
            '"reviewer_traps_addressed": [...], '
            '"unsupported_claims_flagged": [...]\n'
            "    }, ...\n"
            "  ]\n"
            "}\n"
            "Use the EXACT section names listed above.  Do NOT include "
            "sections from other chunks.  Be honest about missing evidence."
        )
        try:
            chunk_out = ask_json(
                CHINA_DRAFTING_SYSTEM_PROMPT, sections_prompt,
                temperature=0.15,
            )
            if isinstance(chunk_out, dict):
                for s in chunk_out.get("sections") or []:
                    if isinstance(s, dict) and s.get("name") in chunk:
                        drafted_sections.append(s)
        except Exception as exc:
            sub_call_errors.append(
                f"sections chunk {chunk_idx} sub-call failed: "
                f"{exc.__class__.__name__}: {str(exc)[:160]}"
            )

    drafted["sections"] = drafted_sections

    # If BOTH framing and ALL section chunks failed, fall back.
    # Otherwise keep whatever we recovered (partial > empty).
    all_failed = (
        not drafted.get("titles")
        and not drafted.get("abstract")
        and not drafted_sections
    )
    if all_failed and sub_call_errors:
        return _china_fallback("; ".join(sub_call_errors[:3]))

    # Surface per-chunk errors as missing-information entries so the
    # reader knows which parts of the draft were skipped.
    if sub_call_errors:
        drafted["missing_information"] = (
            list(drafted.get("missing_information") or [])
            + [f"Drafting note: {e}" for e in sub_call_errors]
        )

    sections = _china_normalise_sections(
        drafted.get("sections") or [], blueprint_order,
    )

    # ---- 5. Reviewer-simulation LLM call ------------------------------
    # Reviewers don't need the full section content — a compact summary
    # (name + first 600 chars + the flagged claims) is enough to attack
    # the proposal, and it keeps the input well under the 8192-token
    # output budget so the reviewer JSON itself doesn't get truncated.
    def _compact_section_for_review(s) -> dict:
        return {
            "name": s.name,
            "content_excerpt": (s.content or "")[:600],
            "must_include_missing": s.must_include_missing[:4],
            "unsupported_claims_flagged": s.unsupported_claims_flagged[:4],
        }
    reviewer_prompt = (
        "Proposal draft to attack (24 sections, compact JSON):\n"
        + _china_safe([_compact_section_for_review(s) for s in sections], 6000)
        + "\n\nCall metadata:\n" + _china_safe(call_meta, 800)
        + "\n\nReturn the strict JSON described in the system prompt."
    )
    try:
        sim_raw = ask_json(
            CHINA_REVIEWER_SYSTEM_PROMPT, reviewer_prompt, temperature=0.15,
        ) or {}
    except Exception:
        sim_raw = {}
    reviewers = _china_normalise_reviewers(
        (sim_raw or {}).get("reviews") or [],
    )

    # ---- 6. Deterministic scoring + weakness repair plan -------------
    score = _china_score(
        sections, reviewers, has_call_metadata=bool(call_meta),
    )
    repair_plan = _china_repair_plan(sections, reviewers, score)

    # ---- 7. Information-state separation ------------------------------
    confirmed = [s for s in (drafted.get("confirmed_facts") or [])
                 if isinstance(s, str)][:20]
    assumptions = [s for s in (drafted.get("reasonable_assumptions") or [])
                   if isinstance(s, str)][:20]
    missing = [s for s in (drafted.get("missing_information") or [])
               if isinstance(s, str)][:20]

    # ---- 8. Compose output object -------------------------------------
    titles = drafted.get("titles") or {}
    abstract = drafted.get("abstract") or {}
    keywords = drafted.get("keywords") or {}
    if not isinstance(titles, dict):    titles = {}
    if not isinstance(abstract, dict):  abstract = {}
    if not isinstance(keywords, dict):  keywords = {}

    out = ChinaGrantArchitectOutput(
        agent_name="china_grant_architect",
        approval_level="draft_only",
        summary=(abstract.get("concise_en") or "")[:600],
        findings=[s.name for s in sections if s.content][:10],
        assumptions=assumptions,
        risks=[w for r in reviewers for w in r.weaknesses[:1]][:10],
        recommended_actions=[],
        claims_for_verification=[s.name + ": " + s.content[:200]
                                 for s in sections if s.unsupported_claims_flagged][:8],
        evidence_level="moderate" if scout else "weak",
        confidence=("low" if score.total < 70
                    else "medium" if score.total < 85 else "high"),
        partial_results=False,
        failed_stage="",
        template_id=TEMPLATE_ID,
        template_version=str(template.get("version", "1.0")),
        template_override_layers_applied=layers_applied,
        template_presentation_outline=(
            template.get("presentation_outline") or []
        ),
        # Carry Scout's top_papers through so the draft_writer
        # References section is populated; mirrors the general
        # grant_architect's references_used wiring.
        references_used=references_list,
        # Carry local-document evidence through so the draft_writer
        # renders an auditable "Local-document evidence used" block.
        local_literature_evidence_used=[
            r for r in ((scout or {}).get("local_literature_evidence") or [])
            if isinstance(r, dict)
        ][:12],
        # Surface Scout's diagnostic state so the empty-References
        # placeholder can show exactly what happened upstream.
        scout_diagnostics=scout_diagnostics,
        sections=sections,
        titles={k: str(v) for k, v in titles.items() if isinstance(v, str)},
        abstract={k: str(v) for k, v in abstract.items() if isinstance(v, str)},
        keywords={k: [str(x) for x in (v or []) if isinstance(x, str)]
                  for k, v in keywords.items()},
        reviewer_simulation=reviewers,
        competitiveness_score=score,
        weakness_repair_plan=repair_plan,
        confirmed_facts=confirmed,
        reasonable_assumptions=assumptions,
        missing_information=missing,
    )

    # ---- 9. Filter forbidden actions before contract check ------------
    out.recommended_actions, blocked = _china_filter_forbidden_actions(
        out.recommended_actions or [],
    )

    # ---- 10. Render the proposal markdown -----------------------------
    md = _china_render_markdown(out)
    from core.path_safety import unique_filename_stamp
    # Phase 2 (goal F): microsecond + UUID suffix so two China drafts in
    # the same second do not overwrite each other.
    ts = unique_filename_stamp(utc=True)
    md_path = _CHINA_REPORTS_DIR / f"china_grant_{ts}.md"
    try:
        md_path.write_text(md, encoding="utf-8")
        out.proposal_markdown_path = str(
            md_path.relative_to(config.BASE_DIR)
        )
    except Exception:
        out.proposal_markdown_path = ""

    # ---- 11. Reflection capture (Part 11) -----------------------------
    out.reflection_for_memory = _china_capture_reflection(
        user_input=user_input, call_meta=call_meta, score=score,
        reviewers=reviewers, blocked=blocked,
    )

    # ---- 12. Validate via Pydantic + assert the immutable contract ----
    payload = out.model_dump()
    try:
        ChinaGrantArchitectOutput.model_validate(payload)
    except ValidationError as exc:
        return _china_fallback(exc)
    try:
        assert_china_grant_draft_contract(payload)
    except Exception as exc:
        # Last-ditch: contract violated.  Down-grade to fallback rather
        # than ship a non-compliant draft.
        return _china_fallback(f"Contract violation: {exc}")

    return payload

# ---------------------------------------------------------------------------
# User-editable template hooks
# ---------------------------------------------------------------------------
# These wrappers let the user (or main.py / a slash command) modify the
# China grant blueprint from inside AURA itself without editing source code.
# Edits land as JSONL records in core.memory so every change is auditable
# and reversible.  They DO NOT mutate CHINA_GRANT_MASTER_TEMPLATE.

def apply_china_template_patch(
    patch: dict,
    *,
    scope: str = "user",
    layer: str = "user",
) -> dict:
    """Persist a China-template override and return the effective template.

    Args:
        patch:  partial dict that will be deep-merged on top of the master
                template (e.g. ``{"fields": {"application_language": "en"},
                "presentation_outline": [...]}``).
        scope:  identifier for this override (e.g. ``"user"`` for the
                user-default, or ``"NSFC_2026_general"`` for a specific
                call).  Lets the user maintain several named templates.
        layer:  ``"user"`` (default) or ``"call"``.  Call-level patches
                override user-level patches at resolution time.

    Returns:
        The newly-resolved effective template.  Callers can diff against
        the master to confirm the patch took effect.

    The 24-section content contract is unaffected — see
    ``core.aura_principles.CHINA_GRANT_CONTRACT`` — so a malformed
    ``presentation_outline`` patch can never strip evidence; rendering
    falls back to the legacy 24-section numeric layout if the outline
    becomes invalid.
    """
    from core.grant_templates.china_blueprint import (
        save_user_override as _save_user_override,
        save_call_override as _save_call_override,
        resolve_template as _resolve_template,
    )
    if layer == "call":
        _save_call_override(patch, scope=scope)
        return _resolve_template(call_scope=scope, user_scope="user")
    _save_user_override(patch, scope=scope)
    return _resolve_template(user_scope=scope)


def get_china_template(*, call_scope: str = "", user_scope: str = "user") -> dict:
    """Return the effective China-grant template the next ``run_china``
    call would use.  Pure inspection — no side effects."""
    from core.grant_templates.china_blueprint import resolve_template
    return resolve_template(call_scope=call_scope, user_scope=user_scope)


def list_china_template_overrides() -> dict:
    """Return a summary of which override layers are currently in
    effect, plus every per-call override scope ever saved."""
    from core.grant_templates.china_blueprint import list_active_overrides
    return list_active_overrides()


def reset_china_template_to_master(*, scope: str = "user") -> dict:
    """Overwrite the named override with an empty patch — effectively
    resetting the template back to the in-code master defaults.

    The original override records remain in the JSONL audit trail; the
    new empty patch simply takes priority because resolution uses the
    most-recent record.
    """
    return apply_china_template_patch({}, scope=scope, layer="user")
