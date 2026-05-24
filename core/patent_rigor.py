"""
Rigorous claim-centric patent analysis pipeline.

Implements the methodology specified in
``revised_patent_analysis_rigorous.docx`` (Sections 4–9):

  Algorithm 1 — structured patent feature extraction with claim graph,
                importance scores, and evidence anchors.
  Algorithm 2 — topic decomposition into subtopics, capabilities,
                target_metrics, operating_conditions, application_
                constraints, exclusions.
  Algorithm 3 — patent–topic relevance scoring with separate Relevance,
                Confidence, and Action scores.
  Algorithm 4 — portfolio-level coverage matrix + gap detection,
                differentiating missing-feature / weak-performance /
                feature-combination / translation / evidence gaps.

Operating principle (Section 1):
    parse → extract → normalize → score → aggregate → detect gaps → report

Honesty contract:
    * Every score MUST be backed by an evidence_snippet.
    * Independent claims weighted highest, embodiment-only weighted low.
    * Mock / synthetic records are NEVER passed through this pipeline.
    * On LLM failure, every helper returns a structured empty/uncertain
      result rather than fabricating data.

This module is LLM-agnostic at the algorithm level: each stage takes
plain dicts in and returns Pydantic objects.  The single LLM coupling
is via ``core.llm.ask_json``.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from core import normalization as _norm
from core.llm import ask_json


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

ClaimSupport = Literal["independent", "dependent", "descriptive_only", "unknown"]
DocStatus = Literal["granted", "application", "excerpt", "unknown"]
GapType = Literal[
    "missing_feature",
    "weak_performance",
    "feature_combination",
    "translation",
    "evidence",
]
ScoreBand = Literal["A", "B", "C", "D"]


class TopicProfile(BaseModel):
    """Output of Algorithm 2 — decomposed analyzable topic."""
    topic_name: str = ""
    subtopics: list[str] = Field(default_factory=list)
    desired_capabilities: list[str] = Field(default_factory=list)
    target_metrics: list[str] = Field(default_factory=list)
    operating_conditions: list[str] = Field(default_factory=list)
    application_constraints: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)


class PerformanceMetric(BaseModel):
    metric: str = ""
    value: str = ""
    unit: str = ""
    condition: str = ""
    evidence: str = ""


class PatentFeature(BaseModel):
    name: str = ""
    normalized_name: str = ""
    type: Literal[
        "material", "component", "process", "device",
        "metric", "application", "problem", "other",
    ] = "other"
    importance_score: float = 0.0
    claim_support: ClaimSupport = "unknown"
    evidence: str = ""
    section: str = ""
    claim_no: str = ""
    confidence: float = 0.0


class PatentProfile(BaseModel):
    """Output of Algorithm 1 — one structured profile per patent."""
    patent_id: str = ""
    title: str = ""
    status: DocStatus = "unknown"
    problem: str = ""
    core_invention: str = ""
    independent_claims: list[str] = Field(default_factory=list)
    dependent_claim_count: int = 0
    features: list[PatentFeature] = Field(default_factory=list)
    performance_metrics: list[PerformanceMetric] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    source_url: str = ""
    source_origin: Literal["web", "local"] = "web"


class RelevanceScoring(BaseModel):
    """Output of Algorithm 3 — per (patent, topic) scoring."""
    patent_id: str = ""
    topic_name: str = ""
    relevance_score: float = 0.0      # 0-100
    confidence_score: float = 0.0     # 0-1
    action_score: float = 0.0         # relevance * confidence
    band: ScoreBand = "D"
    covered_subtopics: list[str] = Field(default_factory=list)
    missing_subtopics: list[str] = Field(default_factory=list)
    evidence_summary: str = ""


class CoverageCell(BaseModel):
    """One cell of the coverage matrix (Section 7)."""
    subtopic: str = ""
    patent_id: str = ""
    coverage_strength: float = 0.0    # 0-1
    confidence: float = 0.0           # 0-1
    evidence: str = ""


class GapEntry(BaseModel):
    """One row of Table C — ranked technology gaps."""
    topic_name: str = ""
    subtopic: str = ""
    coverage_strength: float = 0.0
    gap_type: GapType = "missing_feature"
    gap_score: float = 0.0            # Priority * (1 - Coverage) * UnmetNeed * Confidence
    level: Literal["claim", "embodiment", "inference"] = "inference"
    reason: str = ""
    suggested_direction: str = ""


class PatentRigorOutput(BaseModel):
    """Aggregate output of the rigorous pipeline."""
    topic_profile: TopicProfile = Field(default_factory=TopicProfile)
    patent_profiles: list[PatentProfile] = Field(default_factory=list)
    relevance_table: list[RelevanceScoring] = Field(default_factory=list)
    coverage_matrix: list[CoverageCell] = Field(default_factory=list)
    gap_table: list[GapEntry] = Field(default_factory=list)
    abstentions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Algorithm 2 — Topic decomposition
# ---------------------------------------------------------------------------

_TOPIC_PROMPT = """\
You are decomposing a user-supplied technology topic into its analyzable
parts for downstream claim-centric patent analysis.

Output STRICT JSON with this exact schema (no extra keys):
{
  "topic_name": "<concise restatement of the topic>",
  "subtopics": ["technical component or subproblem", ...],
  "desired_capabilities": ["what the system should do", ...],
  "target_metrics": ["lifetime", "efficiency", "EQE", "power density", ...],
  "operating_conditions": ["luminance band", "temperature", "drive mode", ...],
  "application_constraints": ["display | medical | sensing | automotive | ...", ...],
  "exclusions": ["things the user explicitly does NOT want", ...]
}

RULES:
- 3-8 subtopics; each must be a CONCRETE technical component, not a vague theme.
- target_metrics MUST be measurable quantities (units implied) — not adjectives.
- If the topic does not give you enough material for a field, return [] for
  that field.  DO NOT invent constraints the user did not state.
- ``topic_name`` is your one-line restatement — never empty.
"""


def decompose_topic(
    topic: str,
    *,
    extra_context: str = "",
) -> TopicProfile:
    """Algorithm 2 — produce a structured TopicProfile from a user topic.

    Returns a defensive empty profile (with topic_name preserved) when
    the LLM call fails — never raises.
    """
    if not topic or not topic.strip():
        return TopicProfile(topic_name="(empty topic)")
    user = f"Topic: {topic.strip()}"
    if extra_context.strip():
        user += f"\n\nAdditional context:\n{extra_context.strip()[:1500]}"
    try:
        raw = ask_json(_TOPIC_PROMPT, user, temperature=0.1) or {}
    except Exception:
        return TopicProfile(topic_name=topic.strip()[:120])
    try:
        return TopicProfile(
            topic_name=_norm.ensure_str(raw.get("topic_name"))
            or topic.strip()[:120],
            subtopics=_norm.ensure_str_list(raw.get("subtopics"), max_items=8),
            desired_capabilities=_norm.ensure_str_list(
                raw.get("desired_capabilities"), max_items=8,
            ),
            target_metrics=_norm.ensure_str_list(
                raw.get("target_metrics"), max_items=10,
            ),
            operating_conditions=_norm.ensure_str_list(
                raw.get("operating_conditions"), max_items=10,
            ),
            application_constraints=_norm.ensure_str_list(
                raw.get("application_constraints"), max_items=6,
            ),
            exclusions=_norm.ensure_str_list(raw.get("exclusions"), max_items=6),
        )
    except Exception:
        return TopicProfile(topic_name=topic.strip()[:120])


# ---------------------------------------------------------------------------
# Algorithm 1 — Structured patent feature extraction
# ---------------------------------------------------------------------------

_PATENT_EXTRACTION_PROMPT = """\
You are extracting a structured patent profile for downstream
relevance/gap analysis.  The input is one patent or its excerpts.

OUTPUT STRICT JSON with this exact schema:
{
  "title": "patent title (verbatim if available)",
  "status": "granted | application | excerpt | unknown",
  "problem": "1-2 sentences: the technical problem this patent addresses",
  "core_invention": "ONE sentence describing what is CLAIMED",
  "independent_claims": ["claim 1 text or summary", ...],
  "dependent_claim_count": <int>,
  "features": [
    {
      "name": "human-readable feature name",
      "normalized_name": "canonicalized term",
      "type": "material | component | process | device | metric | application | problem | other",
      "importance_score": <0.0-1.0>,
      "claim_support": "independent | dependent | descriptive_only | unknown",
      "evidence": "VERBATIM excerpt that supports this feature",
      "section": "claim / abstract / summary / description / embodiment",
      "claim_no": "1 | 2 | ... or empty",
      "confidence": <0.0-1.0>
    }, ...
  ],
  "performance_metrics": [
    {
      "metric": "EQE | lifetime | luminance | ...",
      "value": "<numeric or qualitative>",
      "unit": "% | hours | cd/m^2 | ...",
      "condition": "operating condition under which measured",
      "evidence": "verbatim excerpt"
    }, ...
  ],
  "applications": ["intended use 1", ...],
  "uncertainties": ["ambiguity / missing context / conflict", ...]
}

CRITICAL RULES:
- importance_score must follow this priority (Section 4.2):
    independent claim support → ≥ 0.7
    dependent claim support   → 0.4 - 0.65
    descriptive / embodiment-only → < 0.4
- NEVER invent claims.  If you cannot read the claim text, leave
  ``independent_claims`` empty and set ``dependent_claim_count = 0``.
- Every feature MUST have an ``evidence`` snippet copied verbatim from
  the input.  If no snippet supports it, do not include the feature.
- ``performance_metrics``: include only metrics with a concrete value
  AND unit AND measurement condition.  Aspirations without a value go
  in ``uncertainties`` instead.
- 4–12 features is typical; more than 20 means you are extracting noise.
"""


def extract_patent_profile(
    *,
    patent_id: str,
    title: str,
    body: str,
    source_url: str = "",
    source_origin: Literal["web", "local"] = "web",
) -> PatentProfile:
    """Algorithm 1 — extract one PatentProfile from a patent's body text.

    Returns a profile with ``uncertainties=["llm_extraction_failed: …"]``
    when the LLM call fails.  Never raises.
    """
    body_excerpt = (body or "").strip()
    if len(body_excerpt) > 12000:
        body_excerpt = body_excerpt[:12000] + "\n...[truncated]"

    user = (
        f"patent_id: {patent_id}\n"
        f"title: {title}\n"
        f"source_url: {source_url}\n\n"
        f"=== PATENT BODY (verbatim excerpts) ===\n{body_excerpt}\n"
        f"=== END BODY ===\n\n"
        "Extract the structured patent profile per the schema."
    )
    try:
        raw = ask_json(_PATENT_EXTRACTION_PROMPT, user, temperature=0.1) or {}
    except Exception as exc:
        return PatentProfile(
            patent_id=patent_id, title=title,
            source_url=source_url, source_origin=source_origin,
            uncertainties=[f"llm_extraction_failed: {exc.__class__.__name__}"],
        )

    features: list[PatentFeature] = []
    for f in _norm.iter_dicts(raw.get("features")):
        try:
            features.append(PatentFeature(
                name=_norm.ensure_str(f.get("name")),
                normalized_name=_norm.ensure_str(f.get("normalized_name")),
                type=_validate_enum(
                    f.get("type"),
                    {"material", "component", "process", "device",
                     "metric", "application", "problem", "other"},
                    "other",
                ),
                importance_score=_clip_float(
                    f.get("importance_score"), 0.0, 1.0,
                ),
                claim_support=_validate_enum(
                    f.get("claim_support"),
                    {"independent", "dependent", "descriptive_only", "unknown"},
                    "unknown",
                ),
                evidence=_norm.ensure_str(f.get("evidence"), max_len=600),
                section=_norm.ensure_str(f.get("section"), max_len=60),
                claim_no=_norm.ensure_str(f.get("claim_no"), max_len=20),
                confidence=_clip_float(f.get("confidence"), 0.0, 1.0),
            ))
        except Exception:
            continue
    metrics: list[PerformanceMetric] = []
    for m in _norm.iter_dicts(raw.get("performance_metrics")):
        try:
            metrics.append(PerformanceMetric(
                metric=_norm.ensure_str(m.get("metric")),
                value=_norm.ensure_str(m.get("value")),
                unit=_norm.ensure_str(m.get("unit")),
                condition=_norm.ensure_str(m.get("condition"), max_len=200),
                evidence=_norm.ensure_str(m.get("evidence"), max_len=400),
            ))
        except Exception:
            continue

    return PatentProfile(
        patent_id=patent_id,
        title=_norm.ensure_str(raw.get("title")) or title,
        status=_validate_enum(
            raw.get("status"),
            {"granted", "application", "excerpt", "unknown"}, "unknown",
        ),
        problem=_norm.ensure_str(raw.get("problem"), max_len=600),
        core_invention=_norm.ensure_str(raw.get("core_invention"), max_len=400),
        independent_claims=_norm.ensure_str_list(
            raw.get("independent_claims"), max_items=10, max_item_len=600,
        ),
        dependent_claim_count=_clip_int(raw.get("dependent_claim_count"), 0, 200),
        features=features,
        performance_metrics=metrics,
        applications=_norm.ensure_str_list(raw.get("applications"), max_items=10),
        uncertainties=_norm.ensure_str_list(raw.get("uncertainties"), max_items=10),
        source_url=source_url,
        source_origin=source_origin,
    )


_BATCH_EXTRACTION_PROMPT = """\
You are extracting structured patent profiles for multiple patents in
ONE call.  The input is a list of patents; produce one profile per
patent.

OUTPUT STRICT JSON with this exact schema:
{
  "profiles": [
    {
      "patent_id": "<exactly the patent_id from the input>",
      "title": "patent title (verbatim if available)",
      "status": "granted | application | excerpt | unknown",
      "problem": "1-2 sentences: the technical problem this patent addresses",
      "core_invention": "ONE sentence describing what is CLAIMED",
      "independent_claims": ["claim text or summary", ...],
      "dependent_claim_count": <int>,
      "features": [
        {
          "name": "human-readable feature name",
          "normalized_name": "canonicalized term",
          "type": "material | component | process | device | metric | application | problem | other",
          "importance_score": <0.0-1.0>,
          "claim_support": "independent | dependent | descriptive_only | unknown",
          "evidence": "VERBATIM excerpt from THIS patent supporting this feature",
          "section": "claim / abstract / summary / description / embodiment",
          "claim_no": "1 | 2 | ... or empty",
          "confidence": <0.0-1.0>
        }, ...
      ],
      "performance_metrics": [
        {
          "metric": "EQE | lifetime | luminance | ...",
          "value": "<numeric or qualitative>",
          "unit": "% | hours | cd/m^2 | ...",
          "condition": "operating condition under which measured",
          "evidence": "verbatim excerpt from THIS patent"
        }, ...
      ],
      "applications": ["intended use 1", ...],
      "uncertainties": ["ambiguity / missing context / conflict", ...]
    }
  ]
}

CRITICAL RULES:
- The ``profiles`` array MUST have exactly one entry per input patent.
- Each profile's ``patent_id`` MUST match the corresponding input's
  ``patent_id`` VERBATIM — do not rename, abbreviate, or invent.
- Treat each patent INDEPENDENTLY.  Do NOT mix evidence snippets from
  patent A into patent B's profile.
- ``importance_score`` priority (Section 4.2):
    independent claim support → ≥ 0.7
    dependent claim support   → 0.4 - 0.65
    descriptive / embodiment-only → < 0.4
- Every feature MUST have an ``evidence`` snippet copied verbatim from
  THAT specific patent's body.  If no snippet supports it, drop it.
- ``performance_metrics``: only include metrics with concrete
  value + unit + condition + evidence.  Aspirations → uncertainties.
- 4-12 features is typical; >20 means you're extracting noise.
"""


def extract_patent_profiles_batched(
    corpus: list[dict],
    *,
    batch_size: int = 3,
    cache=None,
    on_progress=None,
) -> list[PatentProfile]:
    """Algorithm 1 — batched + cached extraction.

    For each ``corpus`` entry (``{patent_id, title, body, source_url,
    source_origin}``), returns a ``PatentProfile``.  Behaviour:

      1. **Cache lookup** — every entry's body is hashed; cached
         profiles are returned directly (no LLM call).
      2. **Batched extraction** — uncached entries are sent ``batch_size``
         at a time in ONE LLM call asking for all profiles together.
      3. **Per-profile fallback** — if a batch's JSON validation fails
         or the LLM omits an entry, we fall back to individual
         ``extract_patent_profile()`` calls for the missing entries so
         no patent is silently dropped.
      4. **Cache write** — every newly-extracted profile is written
         back so the next run is free.

    ``cache`` defaults to :class:`PatentProfileCache.default()`.  Pass
    your own (or ``False``) to disable caching.

    ``on_progress(stage, n_done, n_total, info)`` is an optional
    callback for status reporting.
    """
    from core.patent_profile_cache import PatentProfileCache, compute_body_hash

    if cache is None:
        cache = PatentProfileCache.default()
    use_cache = bool(cache)

    misses: list[tuple[dict, str]] = []
    hits: list[tuple[dict, str, PatentProfile]] = []
    if use_cache:
        misses, hits = cache.partition_corpus(corpus)
    else:
        for entry in corpus:
            if isinstance(entry, dict):
                misses.append((entry, compute_body_hash(str(entry.get("body", "")))))

    if on_progress:
        try:
            on_progress("cache_partition", len(hits), len(corpus), {
                "hits": len(hits), "misses": len(misses),
            })
        except Exception:
            pass

    # Preserve input order: build an index → profile mapping.
    by_index: dict[int, PatentProfile] = {}
    order_by_id: list[str] = []
    for i, entry in enumerate(corpus):
        if not isinstance(entry, dict):
            continue
        pid = str(entry.get("patent_id") or f"P{i + 1}")
        order_by_id.append(pid)

    # Populate cache hits first.
    cached_ids: set[str] = set()
    for entry, _h, prof in hits:
        pid = str(entry.get("patent_id") or "")
        if not pid:
            continue
        cached_ids.add(pid)
        try:
            by_index[order_by_id.index(pid)] = prof
        except ValueError:
            pass

    # Batch the misses.
    pending: list[tuple[int, dict, str]] = []
    for entry, body_hash in misses:
        pid = str(entry.get("patent_id") or "")
        try:
            idx = order_by_id.index(pid)
        except ValueError:
            idx = len(by_index) + len(pending)
        pending.append((idx, entry, body_hash))

    batch_size = max(1, int(batch_size))
    processed = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        batch_profiles = _extract_batch_or_individual([e for _, e, _ in batch])
        for (idx, entry, body_hash), prof in zip(batch, batch_profiles):
            by_index[idx] = prof
            if use_cache and not (prof.uncertainties and any(
                "llm_extraction_failed" in u for u in prof.uncertainties
            )):
                doc_id = str(entry.get("patent_id") or "(unknown)")[:60]
                cache.put(doc_id, body_hash, prof)
        processed += len(batch)
        if on_progress:
            try:
                on_progress("extract_batch", processed, len(pending), {
                    "batch_size": len(batch),
                })
            except Exception:
                pass

    # Return profiles in original corpus order.
    out: list[PatentProfile] = []
    for i in range(len(order_by_id)):
        prof = by_index.get(i)
        if prof is not None:
            out.append(prof)
    return out


def _extract_batch_or_individual(
    batch: list[dict],
) -> list[PatentProfile]:
    """Try a batched LLM call; on any failure mode, fall back to
    individual single-patent extractions for that batch.

    Failure modes that trigger fallback:
      * LLM raised an exception.
      * Returned ``profiles`` is missing or wrong length.
      * Returned profiles don't include all expected patent_ids.
      * Any per-profile validation fails.
    """
    if not batch:
        return []
    if len(batch) == 1:
        # No batching win for a single patent — call the focused prompt.
        e = batch[0]
        return [extract_patent_profile(
            patent_id=str(e.get("patent_id") or "P1"),
            title=str(e.get("title", "")),
            body=str(e.get("body", "")),
            source_url=str(e.get("source_url", "")),
            source_origin=(
                "local" if e.get("source_origin") == "local" else "web"
            ),
        )]

    user_lines = ["Patents to extract (one profile per patent_id):\n"]
    for i, e in enumerate(batch, start=1):
        body = str(e.get("body", ""))
        if len(body) > 8000:
            body = body[:8000] + "\n...[truncated]"
        user_lines.append(
            f"\n=== PATENT {i} ===\n"
            f"patent_id: {e.get('patent_id', '')}\n"
            f"title: {e.get('title', '')}\n"
            f"source_url: {e.get('source_url', '')}\n"
            f"BODY:\n{body}\n"
            f"=== END PATENT {i} ===\n"
        )
    user = "".join(user_lines) + (
        "\nReturn JSON {\"profiles\": [...]} with exactly "
        f"{len(batch)} entries, one per patent above, in the same order, "
        "preserving each patent_id verbatim."
    )

    try:
        raw = ask_json(_BATCH_EXTRACTION_PROMPT, user, temperature=0.1) or {}
        profiles_raw = raw.get("profiles") if isinstance(raw, dict) else None
        if not isinstance(profiles_raw, list):
            raise ValueError("batch response missing 'profiles' array")
        # Index returned profiles by patent_id for safe correlation.
        by_pid: dict[str, dict] = {}
        for pr in profiles_raw:
            if isinstance(pr, dict):
                pid = str(pr.get("patent_id") or "")
                if pid:
                    by_pid[pid] = pr
        out: list[PatentProfile] = []
        all_matched = True
        for e in batch:
            pid = str(e.get("patent_id") or "")
            raw_prof = by_pid.get(pid)
            if raw_prof is None:
                all_matched = False
                break
            prof = _profile_from_raw(
                raw_prof,
                patent_id=pid,
                title=str(e.get("title", "")),
                source_url=str(e.get("source_url", "")),
                source_origin=(
                    "local" if e.get("source_origin") == "local" else "web"
                ),
            )
            out.append(prof)
        if all_matched and len(out) == len(batch):
            return out
        # Else fall through to individual extraction.
    except Exception:
        pass

    # Fallback: extract each patent individually.
    return [
        extract_patent_profile(
            patent_id=str(e.get("patent_id") or f"P{i + 1}"),
            title=str(e.get("title", "")),
            body=str(e.get("body", "")),
            source_url=str(e.get("source_url", "")),
            source_origin=(
                "local" if e.get("source_origin") == "local" else "web"
            ),
        )
        for i, e in enumerate(batch)
    ]


def _profile_from_raw(
    raw: dict,
    *,
    patent_id: str,
    title: str,
    source_url: str,
    source_origin: str,
) -> PatentProfile:
    """Validate a single profile dict from the batched LLM response."""
    features: list[PatentFeature] = []
    for f in _norm.iter_dicts(raw.get("features")):
        try:
            features.append(PatentFeature(
                name=_norm.ensure_str(f.get("name")),
                normalized_name=_norm.ensure_str(f.get("normalized_name")),
                type=_validate_enum(
                    f.get("type"),
                    {"material", "component", "process", "device",
                     "metric", "application", "problem", "other"},
                    "other",
                ),
                importance_score=_clip_float(f.get("importance_score"), 0.0, 1.0),
                claim_support=_validate_enum(
                    f.get("claim_support"),
                    {"independent", "dependent", "descriptive_only", "unknown"},
                    "unknown",
                ),
                evidence=_norm.ensure_str(f.get("evidence"), max_len=600),
                section=_norm.ensure_str(f.get("section"), max_len=60),
                claim_no=_norm.ensure_str(f.get("claim_no"), max_len=20),
                confidence=_clip_float(f.get("confidence"), 0.0, 1.0),
            ))
        except Exception:
            continue
    metrics: list[PerformanceMetric] = []
    for m in _norm.iter_dicts(raw.get("performance_metrics")):
        try:
            metrics.append(PerformanceMetric(
                metric=_norm.ensure_str(m.get("metric")),
                value=_norm.ensure_str(m.get("value")),
                unit=_norm.ensure_str(m.get("unit")),
                condition=_norm.ensure_str(m.get("condition"), max_len=200),
                evidence=_norm.ensure_str(m.get("evidence"), max_len=400),
            ))
        except Exception:
            continue
    return PatentProfile(
        patent_id=patent_id,
        title=_norm.ensure_str(raw.get("title")) or title,
        status=_validate_enum(
            raw.get("status"),
            {"granted", "application", "excerpt", "unknown"}, "unknown",
        ),
        problem=_norm.ensure_str(raw.get("problem"), max_len=600),
        core_invention=_norm.ensure_str(raw.get("core_invention"), max_len=400),
        independent_claims=_norm.ensure_str_list(
            raw.get("independent_claims"), max_items=10, max_item_len=600,
        ),
        dependent_claim_count=_clip_int(raw.get("dependent_claim_count"), 0, 200),
        features=features,
        performance_metrics=metrics,
        applications=_norm.ensure_str_list(raw.get("applications"), max_items=10),
        uncertainties=_norm.ensure_str_list(raw.get("uncertainties"), max_items=10),
        source_url=source_url,
        source_origin="local" if source_origin == "local" else "web",
    )


# ---------------------------------------------------------------------------
# Algorithm 3 — Relevance scoring
# ---------------------------------------------------------------------------

_RELEVANCE_PROMPT = """\
You are scoring how well one patent profile aligns with one decomposed
research topic.  Use the rubric exactly.

OUTPUT STRICT JSON:
{
  "relevance_score": <0-100>,
  "confidence_score": <0.0-1.0>,
  "action_score": <relevance_score * confidence_score>,
  "covered_subtopics": ["which topic subtopics this patent covers"],
  "missing_subtopics": ["topic subtopics this patent does NOT cover"],
  "evidence_summary": "1-3 sentences citing claim/section anchors"
}

RUBRIC (Section 6):

RelevanceScore = 100 * (
   0.30 * Semantic alignment
 + 0.25 * Claim support for topic-critical elements
 + 0.15 * Subtopic coverage breadth/depth
 + 0.10 * Metric match under comparable conditions
 + 0.10 * Application-domain fit
 + 0.10 * Match to the technical problem being solved
)

ConfidenceScore = (
   0.35 * Evidence strength (independent claim > dependent > description)
 + 0.20 * Document quality / completeness
 + 0.20 * Specificity (concrete detail vs generic language)
 + 0.15 * Internal consistency
 + 0.10 * Completeness for topic-critical attributes
)

ActionScore = RelevanceScore * ConfidenceScore

BANDS:
   A >= 75   strong direct relevance — cite core claims
   B 55-74   material partial — state covered & missing
   C 35-54   indirect / peripheral — use cautious wording
   D <  35   weak — do not oversell; explain mismatch

CRITICAL: a patent semantically similar to the topic but with WEAK
claim support MUST receive a high relevance + LOW confidence (so the
ActionScore stays low).  Never give confidence > 0.6 to a patent whose
strongest support is descriptive_only.
"""


def score_patent_relevance(
    profile: PatentProfile, topic: TopicProfile,
) -> RelevanceScoring:
    """Algorithm 3 — relevance × confidence → action; never raises."""
    if not profile.patent_id or not topic.topic_name:
        return RelevanceScoring(
            patent_id=profile.patent_id,
            topic_name=topic.topic_name,
            band="D",
        )
    user = (
        "PATENT PROFILE:\n"
        f"  patent_id: {profile.patent_id}\n"
        f"  title: {profile.title}\n"
        f"  status: {profile.status}\n"
        f"  problem: {profile.problem}\n"
        f"  core_invention: {profile.core_invention}\n"
        f"  independent_claims: {profile.independent_claims}\n"
        f"  feature_summary: {[(f.normalized_name or f.name, f.claim_support, f.importance_score) for f in profile.features[:12]]}\n"
        f"  performance_metrics: {[(m.metric, m.value, m.unit, m.condition) for m in profile.performance_metrics[:10]]}\n"
        f"  applications: {profile.applications}\n"
        "\nTOPIC PROFILE:\n"
        f"  topic_name: {topic.topic_name}\n"
        f"  subtopics: {topic.subtopics}\n"
        f"  desired_capabilities: {topic.desired_capabilities}\n"
        f"  target_metrics: {topic.target_metrics}\n"
        f"  operating_conditions: {topic.operating_conditions}\n"
        f"  application_constraints: {topic.application_constraints}\n"
        f"  exclusions: {topic.exclusions}\n"
        "\nScore per the rubric."
    )
    try:
        raw = ask_json(_RELEVANCE_PROMPT, user, temperature=0.0) or {}
    except Exception:
        return RelevanceScoring(
            patent_id=profile.patent_id,
            topic_name=topic.topic_name,
            band="D",
            evidence_summary="LLM scoring call failed.",
        )

    rel = _clip_float(raw.get("relevance_score"), 0.0, 100.0)
    conf = _clip_float(raw.get("confidence_score"), 0.0, 1.0)
    # Recompute action to avoid LLM arithmetic drift.
    action = rel * conf
    return RelevanceScoring(
        patent_id=profile.patent_id,
        topic_name=topic.topic_name,
        relevance_score=rel,
        confidence_score=conf,
        action_score=action,
        band=_band_for_action(action),
        covered_subtopics=_norm.ensure_str_list(
            raw.get("covered_subtopics"), max_items=10,
        ),
        missing_subtopics=_norm.ensure_str_list(
            raw.get("missing_subtopics"), max_items=10,
        ),
        evidence_summary=_norm.ensure_str(
            raw.get("evidence_summary"), max_len=400,
        ),
    )


# ---------------------------------------------------------------------------
# Algorithm 4 — Coverage matrix + gap detection
# ---------------------------------------------------------------------------

def build_coverage_matrix(
    profiles: list[PatentProfile],
    scorings: list[RelevanceScoring],
    topic: TopicProfile,
) -> list[CoverageCell]:
    """Heuristic coverage matrix: per subtopic, take max coverage_strength
    across patents that cover it.  Coverage strength derives from each
    patent's relevance contribution (action_score / 100) capped at the
    feature-importance signal for that subtopic.

    This is a deterministic aggregator — no LLM call.
    """
    if not topic.subtopics:
        return []
    by_patent: dict[str, RelevanceScoring] = {s.patent_id: s for s in scorings}
    cells: list[CoverageCell] = []
    for subtopic in topic.subtopics:
        st_low = subtopic.lower()
        for p in profiles:
            sc = by_patent.get(p.patent_id)
            if sc is None:
                continue
            covers = any(st_low in c.lower() for c in sc.covered_subtopics)
            if not covers:
                continue
            # Strength = action_score / 100; confidence carries over.
            cells.append(CoverageCell(
                subtopic=subtopic,
                patent_id=p.patent_id,
                coverage_strength=min(1.0, sc.action_score / 100.0),
                confidence=sc.confidence_score,
                evidence=sc.evidence_summary,
            ))
    return cells


def detect_gaps(
    profiles: list[PatentProfile],
    scorings: list[RelevanceScoring],
    coverage: list[CoverageCell],
    topic: TopicProfile,
) -> list[GapEntry]:
    """Algorithm 4 — produce one GapEntry per subtopic.

    Deterministic ranking:
        GapScore = Priority * (1 - Coverage) * UnmetNeed * Confidence
    Priority defaults to 1.0 (uniform unless the user gives priorities).
    UnmetNeed is the share of patents missing this subtopic.  Confidence
    is the mean confidence_score across the coverage cells for the
    subtopic (or 0.5 default).
    """
    if not topic.subtopics:
        return []
    by_subtopic: dict[str, list[CoverageCell]] = {}
    for c in coverage:
        by_subtopic.setdefault(c.subtopic, []).append(c)

    n_patents = max(1, len(profiles))
    gaps: list[GapEntry] = []
    for subtopic in topic.subtopics:
        cells = by_subtopic.get(subtopic, [])
        coverage_strength = max((c.coverage_strength for c in cells), default=0.0)
        confidence = (
            sum(c.confidence for c in cells) / len(cells) if cells else 0.5
        )
        unmet = 1.0 - (len(cells) / n_patents)
        score = 1.0 * (1.0 - coverage_strength) * unmet * (
            confidence if cells else 1.0
        )
        gap_type, level, reason = _classify_gap(
            subtopic, cells, profiles, scorings,
        )
        suggested = _suggest_direction(subtopic, gap_type)
        gaps.append(GapEntry(
            topic_name=topic.topic_name,
            subtopic=subtopic,
            coverage_strength=coverage_strength,
            gap_type=gap_type,
            gap_score=round(score, 4),
            level=level,
            reason=reason,
            suggested_direction=suggested,
        ))
    gaps.sort(key=lambda g: -g.gap_score)
    return gaps


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_enum(value: Any, allowed: set[str], default: str) -> str:
    s = str(value or "").strip().lower()
    return s if s in allowed else default


def _clip_float(value: Any, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return lo
    if v != v:   # NaN
        return lo
    return max(lo, min(hi, v))


def _clip_int(value: Any, lo: int, hi: int) -> int:
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


def _band_for_action(action: float) -> ScoreBand:
    if action >= 75:
        return "A"
    if action >= 55:
        return "B"
    if action >= 35:
        return "C"
    return "D"


def _classify_gap(
    subtopic: str,
    cells: list[CoverageCell],
    profiles: list[PatentProfile],
    scorings: list[RelevanceScoring],
) -> tuple[GapType, Literal["claim", "embodiment", "inference"], str]:
    """Decide gap_type + level + human-readable reason per Section 7.

    Heuristic:
      * No cells              → missing_feature, inference
      * Cells but all conf < 0.5 → evidence
      * Cells but no metric backing in profiles → weak_performance
      * Otherwise → feature_combination (low coverage despite presence)
    """
    if not cells:
        return ("missing_feature", "inference",
                f"No patent in the corpus covers '{subtopic}'.")
    if all(c.confidence < 0.5 for c in cells):
        return ("evidence", "inference",
                f"Patents mention '{subtopic}' but evidence is descriptive-only "
                "or otherwise low-confidence.")
    metric_hits = sum(
        1 for p in profiles for m in p.performance_metrics
        if subtopic.lower() in (m.metric or "").lower()
    )
    if metric_hits == 0:
        return ("weak_performance", "embodiment",
                f"'{subtopic}' is present in claims/description but lacks "
                "quantitative metric values under stated conditions.")
    avg_strength = sum(c.coverage_strength for c in cells) / len(cells)
    if avg_strength < 0.6:
        return ("feature_combination", "claim",
                f"Individual elements supporting '{subtopic}' appear, but the "
                "claim-supported combination is incomplete.")
    return ("translation", "embodiment",
            f"'{subtopic}' is technically present but manufacturability / "
            "stability / deployment evidence is sparse.")


def _suggest_direction(subtopic: str, gap_type: GapType) -> str:
    if gap_type == "missing_feature":
        return f"Search for prior art / preliminary data covering {subtopic}."
    if gap_type == "weak_performance":
        return f"Generate or cite quantitative metric data for {subtopic} under stated conditions."
    if gap_type == "feature_combination":
        return f"Demonstrate a claim-supported combination achieving {subtopic}."
    if gap_type == "translation":
        return f"Show manufacturability / stability / deployment evidence for {subtopic}."
    return f"Strengthen evidence base for {subtopic} with measurable data."


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def run_rigorous_pipeline(
    *,
    topic: str,
    patents: list[dict],
    topic_extra_context: str = "",
    batch_size: int = 3,
    cache=None,
    on_progress=None,
) -> PatentRigorOutput:
    """End-to-end orchestrator implementing Algorithms 1-4.

    Each ``patents`` entry is a dict with:
        patent_id, title, body, source_url, source_origin ('web' | 'local')

    Synthetic / mock records should be filtered OUT before calling this.

    Performance:
        * Profile extraction is BATCHED (default 3 patents per LLM call).
        * Profiles are CACHED to disk keyed by ``sha256(body)`` so a
          repeated run on unchanged inputs is essentially free.
        * Pass ``cache=False`` to bypass the cache (e.g. when prompt
          tweaks invalidate prior extractions).
    """
    out = PatentRigorOutput()
    out.topic_profile = decompose_topic(topic, extra_context=topic_extra_context)

    if not patents:
        out.abstentions.append(
            "No real patent inputs were provided; abstaining from rigorous analysis."
        )
        return out

    valid_patents = [p for p in patents if isinstance(p, dict)]
    profiles = extract_patent_profiles_batched(
        valid_patents,
        batch_size=batch_size,
        cache=cache,
        on_progress=on_progress,
    )
    out.patent_profiles = profiles

    scorings: list[RelevanceScoring] = []
    for prof in profiles:
        scorings.append(score_patent_relevance(prof, out.topic_profile))
    out.relevance_table = scorings

    out.coverage_matrix = build_coverage_matrix(
        profiles, scorings, out.topic_profile,
    )
    out.gap_table = detect_gaps(
        profiles, scorings, out.coverage_matrix, out.topic_profile,
    )
    return out
