"""
Patent Intelligence Agent — Stage 1: web-search-based reconnaissance.

Pipeline
--------
1. Scope: LLM extracts a concise patent search topic from the user request.
2. Web reconnaissance: ``integrations.patent_web.run_patent_web_search(topic)``
   discovers publicly indexed patent pages via SearXNG, fetches them, extracts
   metadata, and dedupes by publication / application / URL / title+assignee.
3. LLM analysis: cautious patent-landscape analysis with substantive claims.
4. Output: ``PatentIntelligenceOutput`` validated against ``SpecialistBaseOutput``,
   plus the spec's patent-specific top-level fields.

Constraints
-----------
This is NOT a comprehensive patent search, NOT a freedom-to-operate analysis,
and NOT legal advice. Output language reflects this throughout. Stage-1
honesty flags (``web_extracted=True``, ``not_api_verified=True``) are present
on every evidence record passed to the verifier.

Evidence-quality logic (spec section 10)
----------------------------------------
- ``low``: mock mode used, OR < 2 usable real records, OR mostly low quality.
- ``moderate``: multiple real pages with several medium/high extractions.
- ``strong``: never used at Stage 1.

Confidence is capped by the evidence-quality band and is forced to ``low``
whenever ``mock_mode_used == True``.
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from core.llm import ask_json
from core import normalization as _norm
from core.schemas import SpecialistBaseOutput
from integrations.patent_web import run_patent_web_search


# ---------------------------------------------------------------------------
# Output model — extends SpecialistBaseOutput with the spec's patent fields.
# ---------------------------------------------------------------------------

class PatentIntelligenceOutput(SpecialistBaseOutput):
    agent_name: str = "patent_intelligence"

    # Spec-required patent-specific fields:
    provider_used: str = ""
    search_queries_used: list[str] = []
    retrieved_patent_page_count: int = 0
    deduplicated_patent_record_count: int = 0
    top_patent_records: list[dict] = []
    apparent_landscape_summary: str = ""
    frequent_assignees_or_applicants: list[str] = []
    apparent_theme_clusters: list[dict] = []
    possible_white_space: list[dict] = []
    overlap_risks: list[str] = []
    recommended_follow_up_searches: list[str] = []
    limitations: list[str] = []
    mock_mode_used: bool = False
    # Phase 1 (goal D) — truthful provenance for mixed real+mock runs:
    #   providers_used         : EVERY provider that produced a record
    #                            (not just the last/winning one), so a
    #                            mixed run cannot hide that mock fired.
    #   synthetic_records_present : True if any surviving record is
    #                            synthetic/mock.
    providers_used: list[str] = []
    synthetic_records_present: bool = False

    # Provider-neutral retrieval provenance (primary_provider,
    # provider_used, fallback_used, fallback_from, not_api_verified,
    # non_exhaustive, warnings).  Populated from
    # PatentWebSearchRun.retrieval_provenance.
    retrieval_provenance: dict = {}

    # Rigorous claim-centric analysis output (Algorithms 1-4 from
    # revised_patent_analysis_rigorous.docx) — topic decomposition,
    # per-patent structured profile, per-(patent, topic) relevance
    # scoring, coverage matrix, and ranked technology gaps.  Only
    # populated when at least one real patent source was available
    # (mock records are NEVER passed through the rigorous pipeline).
    rigorous_analysis: dict = {}

    # Full LLM landscape report + raw pipeline output for downstream agents.
    patent_analysis: dict = {}
    patent_evidence_bundle: dict = {}

    # Phase 4: optional local-patent evidence retrieved from a
    # user-supplied folder.  Kept SEPARATE from `top_patent_records` /
    # `patent_evidence_bundle` so the verifier can distinguish
    # web-reconnaissance findings from local-folder evidence.
    local_patent_evidence: list[dict] = []
    local_document_ingestion_summary: dict = {}
    # Human-readable per-file extraction diagnostic (populated by
    # ``_summarise_local_ingestion``) so the draft writer can render a
    # ``### Local Patent Documents`` section the user can act on.
    local_ingestion_diagnostic: dict = {}
    needs_user_input: dict | None = None


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SCOPE_PROMPT = """\
You are a patent intelligence analyst.

Extract the technology topic to search from the user's request. Return strict JSON:
{
  "topic": "concise technical phrase, 3-8 words, suitable for patent search",
  "rationale": "1 sentence"
}

Keep `topic` short and specific. Avoid marketing terms and full sentences.
"""


_ANALYSIS_PROMPT = """\
You are a patent intelligence analyst preparing a CAUTIOUS Stage-1 patent
landscape report based on web-scraped patent landing pages.

CRITICAL CONSTRAINTS:
- This is preliminary reconnaissance from publicly indexed patent pages.
- It is web-retrieved, NOT API-verified.
- It is non-exhaustive — many relevant patents are likely missing.
- It is NOT legal advice and NOT a freedom-to-operate analysis.
- Recommend professional patent counsel for any consequential decision.
- Do NOT claim a direction is unpatented unless supported by an explicit
  negative search, and even then, hedge.
- Distinguish evidence vs inference at every step.

Output strict JSON with these exact keys:
{
  "confidence": "low | medium | high",
  "apparent_landscape_summary": "2-4 sentences",
  "apparent_theme_clusters": [
    {"cluster_name": "...",
     "representative_record_ids": ["..."],
     "supporting_evidence": "what in the data supports this clustering"}
  ],
  "frequent_assignees_or_applicants": ["..."],
  "possible_white_space": [
    {"direction": "...",
     "rationale": "...",
     "confidence": "low|medium",
     "caveat": "what would need to be true for this to hold"}
  ],
  "overlap_risks": ["short description of areas where IP overlap appears likely"],
  "recommended_follow_up_searches": ["query 1", "query 2"],
  "claims_for_verification": [
    "Substantive analytical claim 1 about the retrieved patent set",
    "Substantive analytical claim 2 ...",
    "..."
  ],
  "risks_and_caveats": ["..."],
  "legal_review_required": true
}

`claims_for_verification` MUST be SUBSTANTIVE analytical statements about the
retrieved patent set — NOT recommended actions. Good examples:
- "Several retrieved pages appear to focus on host-emitter combinations for
  OLED systems."
- "The publicly indexed pages reviewed suggest repeated activity around
  emitter stabilisation."
- "This result set is not sufficient to establish patent white space
  conclusively."

`legal_review_required` MUST be true.

WHEN LOCAL PATENT EVIDENCE IS PRESENT (user supplied a folder):
- Treat the [L1], [L2], ... excerpts as the PRIMARY input to the analysis.
- Enumerate `frequent_assignees_or_applicants` by extracting Applicant /
  Assignee / Applicants names that APPEAR LITERALLY in the local
  excerpts (e.g. "JelikaLite LLC", "SHINING BUDDHA CORP.").  Do NOT
  invent names not present in the excerpts.
- Build `apparent_theme_clusters` by grouping local patents by visible
  technology theme (e.g. "wearable PBM devices", "transcranial NIR
  therapy", "OLED-based phototherapy"), citing the [L#] references that
  support each cluster in `representative_record_ids`.
- Populate `apparent_landscape_summary` (2–4 sentences) from the
  themes you actually see in the excerpts — NOT generic boilerplate.
- For `possible_white_space`, look at what the local patents do NOT
  cover (e.g. specific wavelength bands, device form factors,
  indications) and hedge appropriately.
- For `overlap_risks`, name concrete crowded sub-areas observable in
  the local set.
- If local evidence is the ONLY source (web search failed → Records is
  empty), STILL populate every structured field from the local
  evidence — do NOT return empty arrays.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_topic(user_input: str, context: dict) -> str:
    try:
        result = ask_json(
            _SCOPE_PROMPT,
            f"User request: {user_input}\nContext keys: {list(context.keys())}",
            temperature=0.1,
        )
        topic = (result or {}).get("topic", "").strip() if isinstance(result, dict) else ""
        if topic:
            return topic
    except Exception:
        pass
    return user_input.strip()[:120] or "patent search"


def _verifier_feedback_block(context: dict) -> str:
    blocks: list[str] = []
    instructions = context.get("verifier_revision_instructions")
    if isinstance(instructions, list) and instructions:
        blocks.append(
            "\n\nVerifier Revision Instructions (address these):\n"
            + "\n".join(f"  - {v}" for v in instructions[:8])
        )
    corrections = context.get("verifier_corrections")
    if isinstance(corrections, list) and corrections:
        blocks.append(
            "\n\nVerifier Corrections (mandatory fixes):\n"
            + "\n".join(f"  * {c}" for c in corrections[:5])
        )
    risks = context.get("verifier_risks")
    if isinstance(risks, list) and risks:
        blocks.append(
            "\n\nVerifier Risks to Mitigate:\n"
            + "\n".join(f"  ! {r}" for r in risks[:5])
        )
    return "".join(blocks)


def _record_summary(record: dict) -> dict:
    """Trim a PatentEvidenceRecord dict to the fields the analyst needs."""
    return {
        "id": record.get("record_id", ""),
        "title": record.get("title", ""),
        "abstract": (record.get("abstract") or "")[:600],
        "publication_number": record.get("publication_number", ""),
        "application_number": record.get("application_number", ""),
        "jurisdiction": record.get("jurisdiction", ""),
        "assignees": record.get("assignee_or_applicant", [])[:5],
        "inventors": record.get("inventors", [])[:5],
        "filing_date": record.get("filing_date", ""),
        "publication_date": record.get("publication_date", ""),
        "source_domain": record.get("source_domain", ""),
        "url": record.get("url", ""),
        "extraction_quality": record.get("extraction_quality", ""),
        "caution_flags": record.get("caution_flags", []),
        "originating_query": record.get("originating_query", ""),
        # Stage-1 honesty flags surfaced inline for the LLM.
        "web_extracted": record.get("web_extracted", True),
        "not_api_verified": record.get("not_api_verified", True),
    }


def _classify_evidence_level(run: dict) -> str:
    """Spec section 10 conservative bands.  Never returns 'strong' at Stage 1."""
    if run.get("mock_mode_used"):
        return "weak"  # SpecialistBaseOutput uses 'weak' for "low" evidence.
    records = run.get("deduplicated_records", [])
    usable = [r for r in records if r.get("extraction_quality") in ("medium", "high")]
    if len(records) < 2:
        return "weak"
    if len(usable) >= 3 and len(records) >= 3:
        return "moderate"
    return "weak"


def _classify_confidence(run: dict, llm_confidence: str) -> str:
    """Cap confidence by evidence level. Mock mode ⇒ low."""
    if run.get("mock_mode_used"):
        return "low"
    candidate = (llm_confidence or "").strip().lower() or "medium"
    if candidate not in ("low", "medium", "high"):
        candidate = "medium"
    # Stage 1 never claims high confidence.
    if candidate == "high":
        return "medium"
    return candidate


def _frequent_assignees(records: list[dict], top_n: int = 5) -> list[str]:
    counts: dict[str, int] = {}
    for r in records:
        for a in r.get("assignee_or_applicant", []) or []:
            if not a:
                continue
            counts[a.strip()] = counts.get(a.strip(), 0) + 1
    return [a for a, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:top_n]]


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 4: optional local-patent folder ingestion.
# ---------------------------------------------------------------------------
# Opt-in via context["ask_local_folders"]=True or AURA_LOCAL_FOLDERS_ENABLED=1.
# First invocation per session asks the user once; subsequent invocations use
# the recorded preference.  The agent NEVER calls input() — it returns a
# structured ``needs_user_input`` payload for the controller to satisfy.

def _maybe_handle_local_patent_folder(
    user_input: str,
    context: dict,
) -> tuple[dict | None, dict]:
    """Return ``(prompt_payload_or_None, extras_for_output)``.

    ``prompt_payload`` is a dict to short-circuit with (the agent returns
    a minimal output carrying ``needs_user_input``).  ``extras`` contains
    ``local_patent_evidence`` + ``local_document_ingestion_summary`` when
    ingestion ran.
    """
    from core import local_documents as ld

    if not isinstance(context, dict):
        context = {}
    session_id = context.get("session_id") or ""
    if not isinstance(session_id, str) or not session_id:
        return None, {}
    if not ld.is_opt_in_enabled(context):
        return None, {}

    agent = "patent_intelligence"
    user_responses = context.get("user_responses") or {}
    if isinstance(user_responses, dict) and agent in user_responses:
        ld.absorb_user_response(session_id, agent, user_responses.get(agent))

    if ld.needs_prompt(session_id, agent):
        return ld.build_prompt_request(session_id, agent).model_dump(), {}

    pref = ld.get_preference(session_id, agent)
    if pref.state != "enabled" or not pref.folder_path:
        return None, {}

    try:
        summary = ld.ingest_folder(session_id, agent, pref.folder_path)
    except Exception as exc:
        return None, {
            "local_patent_evidence": [],
            "local_document_ingestion_summary": {
                "used": False,
                "failure_reason": f"ingest_folder raised: {exc}",
                "partial_results": True,
            },
        }
    # Use the per-document retrieval helper so EVERY ingested patent
    # contributes evidence, not just the 6 globally-highest-overlap
    # chunks (which historically clustered on the same boilerplate
    # "page 2" abstract across many documents and missed 10+ patents).
    refs = ld.retrieve_patent_evidence_per_document(
        session_id, user_input, per_document=5, max_total=60,
    )
    # Loud runtime log so the user can confirm at a glance that the
    # per-document retrieval is active.  If you see "6 chunks across
    # 6 documents" you're running stale code — restart AURA.
    try:
        unique_docs = len({r.document_id for r in refs})
        print(
            f"[patent_intelligence] local-patent retrieval: "
            f"{len(refs)} chunk(s) across {unique_docs} document(s) "
            f"(per_document=5, max_total=60).",
            flush=True,
        )
    except Exception:
        pass
    return None, {
        "local_patent_evidence": [r.model_dump() for r in refs],
        "local_document_ingestion_summary": summary.model_dump(),
        # Defect 6: prompt-injection block.
        "local_evidence_prompt_block": _format_local_patent_block(refs),
    }


def _format_local_patent_block(refs: list) -> str:
    """Render retrieved local-patent excerpts into a prompt-ready block.

    Defect 6: this block is fed into the patent-analysis LLM call so the
    model actually reasons over the user-supplied patent documents.  The
    text is labelled explicitly so the LLM treats it as user-supplied
    (NOT a verified external patent record).
    """
    if not refs:
        return ""
    lines = [
        "User-supplied LOCAL PATENT evidence (extracted from a folder; "
        "treat as user-provided, NOT a verified external patent record):",
    ]
    for i, ref in enumerate(refs, start=1):
        r = ref.model_dump() if hasattr(ref, "model_dump") else (
            ref if isinstance(ref, dict) else {}
        )
        if not r:
            continue
        safe = r.get("safe_reference") or r.get("file_name") or "(unknown)"
        loc = r.get("location_hint") or ""
        quality = r.get("extraction_quality") or "good"
        excerpt = (r.get("excerpt") or "")[:600]
        lines.append(
            f"\n[L{i}] {safe}"
            + (f" ({loc})" if loc else "")
            + f" — extraction_quality={quality}"
        )
        if excerpt:
            lines.append(f"    {excerpt}")
    lines.append(
        "\nThese excerpts are unverified user-supplied material.  Treat "
        "them as supplementary patent context.  Do NOT count them toward "
        "the deduplicated_patent_record_count or treat them as legally "
        "verified prior art."
    )
    return "\n".join(lines)


def run(user_input: str, context: dict) -> dict:
    """Patent Intelligence specialist handler for the AURA orchestrator.

    Always returns a dict. On any pipeline failure, returns a degraded but
    schema-valid output with partial_results=True and the failure recorded
    in ``risks`` and ``limitations``.
    """
    # Phase 4 — local-patent-folder prompt hook.  If the user has not yet
    # chosen, short-circuit with a structured needs_user_input payload.
    prompt_payload, local_extras = _maybe_handle_local_patent_folder(
        user_input, context or {},
    )
    if prompt_payload is not None:
        return PatentIntelligenceOutput(
            agent_name="patent_intelligence",
            summary=(
                "Patent Intelligence paused to ask the user whether to "
                "attach a local patent folder."
            ),
            partial_results=True,
            failed_stage="awaiting_user_input",
            evidence_level="none",
            confidence="low",
            needs_user_input=prompt_payload,
            limitations=[
                "Awaiting user response to local-folder prompt; web "
                "reconnaissance was not executed.",
            ],
        ).model_dump()

    errors: list[str] = []

    # Phase 3 (MCP): optionally gather SUPPLEMENTARY external search context.
    # OFF by default.  Stage-1 reconnaissance is unchanged; external evidence
    # never upgrades patent confidence or removes the legal disclaimers, and
    # idea-reality competitor signals are deliberately NOT used as prior art.
    _mcp_gathered: dict = {"records": [], "warnings": []}
    try:
        from core.mcp import integration as _mcp_int
        _mcp_gathered = _mcp_int.gather_patent_context(
            user_input, (context or {}).get("session_id"),
        )
    except Exception:  # noqa: BLE001 — MCP must never break the agent
        _mcp_gathered = {"records": [], "warnings": []}

    def _attach_mcp(result_dict: dict) -> dict:
        try:
            from core.mcp import integration as _mi
            _mi.attach_to_output(result_dict, _mcp_gathered)
        except Exception:  # noqa: BLE001
            pass
        return result_dict

    output: dict[str, Any] = {
        "agent_name": "patent_intelligence",
        "summary": "",
        "findings": [],
        "assumptions": [],
        "risks": [],
        "recommended_actions": [],
        "claims_for_verification": [],
        "evidence_level": "weak",
        "confidence": "low",
        "approval_level": "draft_only",
        "partial_results": False,
        "failed_stage": "",
        # Spec-required patent fields:
        "provider_used": "",
        "search_queries_used": [],
        "retrieved_patent_page_count": 0,
        "deduplicated_patent_record_count": 0,
        "top_patent_records": [],
        "apparent_landscape_summary": "",
        "frequent_assignees_or_applicants": [],
        "apparent_theme_clusters": [],
        "possible_white_space": [],
        "overlap_risks": [],
        "recommended_follow_up_searches": [],
        "limitations": [],
        "mock_mode_used": False,
        "patent_analysis": {},
        "patent_evidence_bundle": {},
        # New: provider-neutral retrieval provenance, populated from
        # PatentWebSearchRun.retrieval_provenance.  The draft writer reads
        # this to render the "Retrieval provenance" section so users can
        # tell which backend produced these results and whether fallback
        # fired.
        "retrieval_provenance": {},
    }

    # 1. Topic extraction.
    topic = _extract_topic(user_input, context or {})

    # Kill switch (review finding 5): PATENT_WEB_SEARCH_ENABLED=0 must
    # actually disable Stage-1 web reconnaissance.  Previously this env
    # var was defined in config but never honoured, so a user who set
    # it to 0 still triggered live retrieval.
    import config as _cfg
    if not getattr(_cfg, "PATENT_WEB_SEARCH_ENABLED", True):
        output.update({
            "partial_results": True,
            "failed_stage": "",
            "limitations": [
                "Stage 1 web reconnaissance DISABLED via "
                "PATENT_WEB_SEARCH_ENABLED=0.",
                "No patent retrieval was attempted.",
                "NOT legal advice. NOT freedom-to-operate analysis.",
            ],
            "summary": (
                "Patent web search is disabled (PATENT_WEB_SEARCH_ENABLED=0). "
                "No reconnaissance performed.  Set PATENT_WEB_SEARCH_ENABLED=1 "
                "to enable Stage-1 web reconnaissance."
            ),
        })
        return _attach_mcp(output)

    # 2. Run the patent_web pipeline.
    try:
        run_obj = run_patent_web_search(topic, use_llm_for_queries=True)
    except Exception as exc:
        errors.append(f"patent_web pipeline failed: {exc}")
        output.update({
            "partial_results": True,
            "failed_stage": "patent_web_pipeline",
            "risks": errors + [
                "Patent reconnaissance pipeline failed — no real evidence retrieved."
            ],
            "limitations": [
                "Stage 1 web reconnaissance only.",
                "Pipeline failure prevented any retrieval.",
                "NOT legal advice. NOT freedom-to-operate analysis.",
            ],
            "summary": (
                "Patent intelligence run could not complete. See risks for details. "
                "Stage 1 preliminary reconnaissance; not legal advice."
            ),
        })
        return _attach_mcp(_validate(output))

    run_dict = run_obj.model_dump()
    records = run_dict.get("deduplicated_records", [])
    queries = run_dict.get("queries", [])
    extractions = run_dict.get("extractions", [])
    # Defensive: mock_mode_used must be True if any of these signals fire,
    # otherwise a fallback chain that lands on mock at the end can produce
    # a draft that confidently claims "real SearXNG search" while every
    # record on the page is synthetic.
    provenance = run_dict.get("retrieval_provenance") or {}
    provider_used = (
        provenance.get("provider_used")
        or run_dict.get("provider_used", "")
    )
    # Detect mock from RECORDS, not just from provider_used.  When a
    # fallback chain mixes real + synthetic sources (e.g. SearXNG
    # returned generic non-patent URLs for some queries, mock fired for
    # others), the FallbackProvider's per-query provenance can end up
    # claiming "searxng" as the winner while the surviving records that
    # made it through the patent-host filter are actually mock URLs
    # (``/mock-result/N``).  We scan the records directly and trust the
    # union of every signal.
    def _record_is_mock(r: dict) -> bool:
        if not isinstance(r, dict):
            return False
        url = str(r.get("url", "") or "")
        if "/mock-result/" in url:
            return True
        prov = str(r.get("provider", "") or "").lower()
        return prov == "mock"

    mock_record_count = sum(1 for r in records if _record_is_mock(r))
    real_record_count = len(records) - mock_record_count
    any_mock = mock_record_count > 0
    mock_mode = (
        bool(run_dict.get("mock_mode_used"))
        or str(provider_used).strip().lower() == "mock"
        or any_mock
    )

    # Phase 1 (goal D): track EVERY provider that contributed, not just
    # the last/winning one.  Sources: per-record ``provider`` field,
    # the provenance dict's provider lists, and the singular
    # provider_used.  A synthetic record forces "mock" into the set even
    # if provenance claimed only a real provider won.
    def _collect_providers() -> list[str]:
        seen: list[str] = []
        def _add(p) -> None:
            s = str(p or "").strip().lower()
            if s and s not in seen:
                seen.append(s)
        for r in records:
            if isinstance(r, dict):
                _add(r.get("provider"))
        # Provenance may expose providers_used / providers_attempted /
        # fallback_from in addition to the winning provider_used.
        for key in ("providers_used", "providers_attempted",
                    "providers", "fallback_chain"):
            val = provenance.get(key)
            if isinstance(val, (list, tuple)):
                for p in val:
                    _add(p)
        _add(provenance.get("fallback_from"))
        _add(provenance.get("primary_provider"))
        _add(provider_used)
        # A synthetic record means mock contributed, regardless of what
        # provenance claimed.
        if any_mock:
            _add("mock")
        return seen

    providers_used = _collect_providers()

    # 3. LLM landscape analysis on extracted records.
    # IMPORTANT: when mock_mode=True, the SYNTHETIC mock records
    # (URLs like patents.google.com/mock-result/N) must NOT be fed to
    # the LLM — they pollute the analysis with fake assignees / fake
    # themes.  We drop them but KEEP any real records that the chain
    # also produced (mixed-source case).
    records_for_llm: list[dict] = [r for r in records if not _record_is_mock(r)]
    record_summaries = [_record_summary(r) for r in records_for_llm]
    diagnostics = {
        "provider_used": provider_used,
        "mock_mode_used": mock_mode,
        "queries_executed": [q.get("query") for q in queries],
        "n_search_hits": len(run_dict.get("search_hits", [])),
        "n_extractions": len(extractions),
        # Counts split so the LLM (and the saved report) can see how
        # mixed the result set was.
        "n_records_in_analysis": len(records_for_llm),
        "n_records_after_dedup_total": len(records),
        "n_records_real": real_record_count,
        "n_records_synthetic_dropped": mock_record_count,
        "n_high_quality_extractions": sum(
            1 for r in records_for_llm if r.get("extraction_quality") == "high"
        ),
        "n_medium_quality_extractions": sum(
            1 for r in records_for_llm if r.get("extraction_quality") == "medium"
        ),
        "source_errors": run_dict.get("source_errors", []),
        "limitations": run_dict.get("limitations", []),
    }
    verifier_extra = _verifier_feedback_block(context or {})

    # Include local-patent excerpts in the LLM input BEFORE generation.
    # The block is empty when the user declined / no folder.
    local_patent_block = (local_extras or {}).get("local_evidence_prompt_block", "")

    # If we have NO real records AND NO local evidence, skip the LLM
    # call and emit an honest "no data available" output instead of
    # asking the model to fabricate a landscape from thin air.  This
    # covers pure-mock + no-local; mixed-source runs still proceed with
    # the real records.
    no_real_data = (
        not records_for_llm and not local_patent_block.strip()
    )

    analysis: dict = {}
    if no_real_data:
        analysis = {
            "claims_for_verification": [
                "No real patent records or local documents were available "
                "for this run; no substantive landscape analysis was performed.",
            ],
            "risks_and_caveats": [
                "Every web-search provider failed or fell back to MOCK; "
                "no real patent reconnaissance was performed.",
                "No user-supplied local patent folder was indexed.",
                "This output is intentionally empty of landscape claims to "
                "avoid fabrication from synthetic data.",
            ],
            "apparent_landscape_summary": (
                "Insufficient data to produce a landscape summary. "
                "Configure SearXNG or supply a local patent folder, then re-run."
            ),
        }
    else:
        if mock_mode:
            # Make the mock-mode constraint explicit to the LLM so it
            # cannot accidentally cite the (absent) "Records" section.
            mock_directive = (
                "\n=== ANALYSIS CONSTRAINT — MOCK MODE ===\n"
                "All web-search providers failed; no real patent records were "
                "retrieved.  The Records section above is EMPTY by design.  "
                "Base your analysis EXCLUSIVELY on the LOCAL PATENT EVIDENCE "
                "below.  DO NOT invent records, assignees, or themes that are "
                "not present in the local evidence.\n"
                "=== END ANALYSIS CONSTRAINT ===\n"
            )
        else:
            mock_directive = ""
        try:
            analysis = ask_json(
                _ANALYSIS_PROMPT,
                (
                    f"Topic: {topic}\n"
                    f"Diagnostics: {diagnostics}\n\n"
                    f"Records (Stage 1 web-scraped, best-effort):\n{record_summaries}\n"
                    + mock_directive
                    + (
                        f"\n=== LOCAL PATENT EVIDENCE (user-supplied) ===\n"
                        f"{local_patent_block}\n"
                        f"=== END LOCAL PATENT EVIDENCE ===\n"
                        if local_patent_block else ""
                    )
                    + f"{verifier_extra}\n\n"
                    "Return the cautious patent intelligence report as strict JSON."
                ),
                temperature=0.2,
            ) or {}
        except Exception as exc:
            errors.append(f"LLM analysis failed: {exc}")
            analysis = {}

    # 4. Map to spec fields.
    output["provider_used"] = provider_used
    output["retrieval_provenance"] = run_dict.get("retrieval_provenance") or {}
    output["search_queries_used"] = [q.get("query", "") for q in queries]
    output["retrieved_patent_page_count"] = sum(
        1 for ex in extractions if ex.get("fetch_status") == "ok"
    )
    output["deduplicated_patent_record_count"] = len(records)
    output["top_patent_records"] = [_record_summary(r) for r in records[:10]]
    output["apparent_landscape_summary"] = analysis.get("apparent_landscape_summary", "")
    output["frequent_assignees_or_applicants"] = (
        analysis.get("frequent_assignees_or_applicants")
        or _frequent_assignees(records)
    )
    output["apparent_theme_clusters"] = analysis.get("apparent_theme_clusters", [])
    # Defect 18: nested list-of-dict fields may arrive as strings or
    # malformed shapes.  Normalize defensively and record a structured
    # shape warning so the verifier sees the degradation.
    shape_warnings: list[str] = []
    _shape_warn = shape_warnings.append
    output["possible_white_space"] = _norm.ensure_dict_list(
        analysis.get("possible_white_space"), max_items=10,
        warn=_shape_warn, field_name="possible_white_space",
    )
    output["apparent_theme_clusters"] = _norm.ensure_dict_list(
        analysis.get("apparent_theme_clusters"), max_items=10,
        warn=_shape_warn, field_name="apparent_theme_clusters",
    )
    output["overlap_risks"] = _norm.ensure_str_list(
        analysis.get("overlap_risks"), max_items=10,
    )
    output["recommended_follow_up_searches"] = _norm.ensure_str_list(
        analysis.get("recommended_follow_up_searches"), max_items=10,
    )
    output["mock_mode_used"] = mock_mode
    output["providers_used"] = providers_used
    output["synthetic_records_present"] = any_mock

    # 5. SpecialistBaseOutput fields.
    # Build an honest summary that reflects the ACTUAL evidence basis,
    # not just the count of synthetic records.
    n_local_chunks = 0
    if local_extras and local_extras.get("local_document_ingestion_summary"):
        n_local_chunks = int(
            (local_extras["local_document_ingestion_summary"] or {})
            .get("chunks_indexed", 0) or 0
        )
    local_suffix = (
        f" + {n_local_chunks} chunk(s) from local patent folder"
        if n_local_chunks else ""
    )
    real_web = real_record_count
    synth_web = mock_record_count
    if synth_web > 0 and real_web > 0:
        # Mixed-source: some queries returned real, others fell through
        # to mock.  Real records are analysed; mock are dropped.
        output["summary"] = (
            f"Preliminary patent-landscape reconnaissance for '{topic}'. "
            f"Web search returned a MIXED result set: {real_web} real "
            f"record(s) retained + {synth_web} synthetic mock record(s) "
            "DISCARDED before analysis "
            f"(some queries fell through to mock fallback){local_suffix}. "
            "Stage 1 only — non-exhaustive, NOT a freedom-to-operate "
            "analysis. Professional patent counsel review is required "
            "before any filing, licensing, or commercial decision."
        )
    elif synth_web > 0 and n_local_chunks > 0:
        # All web is mock, but we have real local docs.
        output["summary"] = (
            f"Preliminary patent-landscape reconnaissance for '{topic}'. "
            "Web search FAILED (all providers fell back to MOCK; "
            f"{synth_web} synthetic record(s) DISCARDED before analysis). "
            f"Analysis based EXCLUSIVELY on {n_local_chunks} chunk(s) "
            "from the user-supplied local patent folder. "
            "Stage 1 only — non-exhaustive, NOT a freedom-to-operate "
            "analysis. Professional patent counsel review is required "
            "before any filing, licensing, or commercial decision."
        )
    elif synth_web > 0:
        # All web is mock and no local — nothing to analyse.
        output["summary"] = (
            f"Patent-landscape reconnaissance for '{topic}' FAILED: "
            "every web-search provider fell through to MOCK and no "
            "local patent folder was supplied.  This output contains "
            "no substantive landscape claims to avoid fabrication "
            "from synthetic data.  Configure SearXNG or supply a "
            "local patent folder, then re-run."
        )
    else:
        # Real web search succeeded; local docs (if any) supplement.
        output["summary"] = (
            f"Preliminary patent-landscape reconnaissance for '{topic}'. "
            f"Retrieved {output['retrieved_patent_page_count']} page(s), "
            f"{real_web} deduplicated record(s) via real web search"
            f"{local_suffix}. "
            "Stage 1 only — non-exhaustive, web-retrieved, NOT a "
            "freedom-to-operate analysis. Professional patent counsel "
            "review is required before any filing, licensing, or "
            "commercial decision."
        )

    # Substantive claims_for_verification come from the LLM analysis.
    # Defect 19: a scalar string must become ["string"], NEVER characters.
    claims = _norm.ensure_str_list(
        analysis.get("claims_for_verification"), max_items=20,
    )
    # Belt-and-suspenders: synthesise a hedging claim if the LLM produced none.
    if not claims:
        if records:
            claims.append(
                f"Across {len(records)} publicly indexed patent pages reviewed, "
                "the retrieved set is non-exhaustive and is not sufficient to "
                "establish patent white space conclusively."
            )
        else:
            claims.append(
                "No usable patent pages were retrieved; no substantive "
                "landscape conclusions can be drawn from this run."
            )
    output["claims_for_verification"] = claims

    # Findings — derived from white-space + theme clusters.
    # Defect 18: iterate only confirmed dicts.
    findings: list[str] = []
    for ws in _norm.iter_dicts(output["possible_white_space"]):
        d = _norm.ensure_str(ws.get("direction"))
        c = _norm.ensure_str(ws.get("confidence"))
        cav = _norm.ensure_str(ws.get("caveat"))
        findings.append(
            f"Possible white-space (conf={c}): {d}"
            + (f" — caveat: {cav}" if cav else "")
        )
        if len(findings) >= 6:
            break
    cluster_count = 0
    for cl in _norm.iter_dicts(output["apparent_theme_clusters"]):
        findings.append(
            f"Apparent cluster: {_norm.ensure_str(cl.get('cluster_name'))}"
        )
        cluster_count += 1
        if cluster_count >= 4:
            break
    output["findings"] = findings

    # Risks — analyst caveats + run errors + agent errors + mock warning.
    # Defect 19: risks_and_caveats may be a string; never split into chars.
    risk_list: list[str] = _norm.ensure_str_list(
        analysis.get("risks_and_caveats"), max_items=5,
    )
    risk_list.extend(_norm.ensure_str_list(run_dict.get("limitations"))[:5])
    risk_list.extend(_norm.ensure_str_list(errors))
    # Surface any shape warnings collected above.
    risk_list.extend(shape_warnings)
    if mock_mode:
        risk_list.insert(
            0,
            "Mock fallback used — results are SYNTHETIC and do not represent "
            "real patent reconnaissance. Treat all findings as illustrative only.",
        )
    output["risks"] = risk_list

    # Recommended actions — always include patent-counsel reminder.
    actions = [
        {"description": a, "action_class": "draft_text"}
        for a in (analysis.get("recommended_follow_up_searches") or [])[:5]
    ]
    actions.append({
        "description": (
            "Engage qualified patent counsel for formal prior-art / freedom-to-"
            "operate review before any filing, licensing, or commercial decision."
        ),
        "action_class": "draft_text",
    })
    output["recommended_actions"] = actions

    output["assumptions"] = [
        "Stage 1 reconnaissance over publicly indexed patent pages only.",
        "No patent-family resolution performed.",
        "No legal interpretation performed.",
        f"Search provider used: {provider_used}.",
        f"Mock fallback active: {mock_mode}.",
    ]

    # Limitations — required by spec.
    limitations = list(run_dict.get("limitations", []))
    limitations.extend([
        "Output is preliminary web-based reconnaissance.",
        "Coverage is non-exhaustive; many relevant patents are likely missing.",
        "Output is NOT legal advice and NOT a freedom-to-operate analysis.",
        "Family-level patent resolution was NOT performed.",
    ])
    output["limitations"] = limitations

    # Confidence + evidence band (spec section 10).
    output["evidence_level"] = _classify_evidence_level(run_dict)
    output["confidence"] = _classify_confidence(run_dict, analysis.get("confidence", ""))

    # Partial-results flag.
    # Phase 1 (goal F): a run containing ANY synthetic/mock record (or in
    # mock_mode) is NEVER "complete" — it must report partial_results=True
    # and carry an explicit synthetic-data limitation, even when the LLM
    # analysis succeeded on the surviving real records.
    if (
        errors or not analysis or not records
        or run_dict.get("partial_results")
        or mock_mode
    ):
        output["partial_results"] = True
        if not analysis:
            output["failed_stage"] = "llm_analysis"
        elif not records:
            output["failed_stage"] = "no_records_after_dedup"
        elif mock_mode and not output.get("failed_stage"):
            output["failed_stage"] = "synthetic_records_present"

    if mock_mode:
        # Ensure an explicit synthetic-data limitation is present.
        limitation = (
            "SYNTHETIC/MOCK records were present in this run "
            f"({mock_record_count} synthetic record(s)); results are "
            "partial and must not be treated as complete real "
            "reconnaissance."
        )
        if limitation not in output["limitations"]:
            output["limitations"].append(limitation)

    output["patent_analysis"] = analysis
    output["patent_evidence_bundle"] = run_dict

    # Rigorous claim-centric analysis (Algorithms 1-4 of
    # revised_patent_analysis_rigorous.docx).  Runs on REAL evidence
    # only — mock records are excluded; local PDFs and real web records
    # are concatenated into a corpus.
    output["rigorous_analysis"] = _build_rigorous_analysis(
        topic=topic,
        real_records=records_for_llm,
        local_extras=local_extras,
        verifier_extra=verifier_extra,
    )

    # Phase 4: attach local-patent evidence + summary if ingestion ran.
    if local_extras:
        output["local_patent_evidence"] = list(local_extras.get("local_patent_evidence") or [])
        output["local_document_ingestion_summary"] = dict(
            local_extras.get("local_document_ingestion_summary") or {}
        )
        # Honesty: local docs MUST NOT inflate evidence_level.
        lsummary = output["local_document_ingestion_summary"]
        if lsummary.get("used"):
            # Build a per-file diagnostic so the user can see WHICH files
            # extracted, WHICH failed, and WHY — otherwise they see only
            # "evidence quality is 'none'" with no actionable detail.
            diag = _summarise_local_ingestion(lsummary)
            if diag:
                output["local_ingestion_diagnostic"] = diag

            if lsummary.get("partial_results"):
                output["partial_results"] = True
                output["risks"].append(
                    "Local-folder ingestion partial — "
                    "see ### Local Patent Documents section below."
                )
            hint = lsummary.get("evidence_quality_hint", "none")
            if hint in ("poor", "none"):
                # Detect "looks like scanned PDFs" → suggest OCR.
                scan_hint = ""
                if diag and diag.get("ocr_likely_needed"):
                    scan_hint = (
                        " — most failures look like scanned/image PDFs; "
                        "enable OCR with AURA_LOCAL_PDF_OCR=1 to recover text."
                    )
                output["risks"].append(
                    f"Local-folder evidence quality is '{hint}'; "
                    "do not treat local patents as verified prior art."
                    + scan_hint
                )

    return _attach_mcp(_validate(output))


def _validate(output: dict) -> dict:
    """Validate against PatentIntelligenceOutput and degrade gracefully.

    Defect 9: when the raw output fails Pydantic validation, we no longer
    return the invalid dict.  Instead, we build a TRUTHFUL, schema-compatible
    degraded output:

      * preserve the original output under ``patent_evidence_bundle.raw_output``
        so post-mortems are possible,
      * set ``partial_results=True`` and ``failed_stage="schema_validation"``,
      * append a risk explaining the schema failure,
      * downgrade ``evidence_level`` to ``"weak"`` and ``confidence`` to
        ``"low"`` so callers cannot mistake a malformed output for verified
        evidence.

    The returned dict is guaranteed to satisfy ``PatentIntelligenceOutput``.
    """
    try:
        return PatentIntelligenceOutput.model_validate(output).model_dump()
    except ValidationError as ve:
        original = output if isinstance(output, dict) else {}
        summary = (
            "Patent intelligence output failed schema validation. "
            "Returning a degraded, schema-compatible record instead. "
            "Stage 1 reconnaissance only — NOT legal advice."
        )
        risks_in = list(original.get("risks", []) or [])
        risks_in.append(f"Schema validation failed: {ve.__class__.__name__}")

        # Coerce the raw error detail to a short string (avoids long traceback
        # contents leaking into report renderers).
        try:
            ve_detail = str(ve)[:240]
        except Exception:
            ve_detail = "unknown validation error"

        safe = PatentIntelligenceOutput(
            agent_name="patent_intelligence",
            summary=summary,
            findings=[],
            assumptions=list(original.get("assumptions", []) or []),
            risks=risks_in,
            recommended_actions=[],
            claims_for_verification=[],
            evidence_level="weak",
            confidence="low",
            approval_level="draft_only",
            partial_results=True,
            failed_stage="schema_validation",
            provider_used=str(original.get("provider_used", "") or ""),
            search_queries_used=[],
            retrieved_patent_page_count=0,
            deduplicated_patent_record_count=0,
            top_patent_records=[],
            apparent_landscape_summary="",
            frequent_assignees_or_applicants=[],
            apparent_theme_clusters=[],
            possible_white_space=[],
            overlap_risks=[],
            recommended_follow_up_searches=[],
            limitations=[
                "Output rejected by Pydantic schema validation.",
                "Reading any structured patent field is unsafe — fields cleared.",
                "NOT legal advice. NOT freedom-to-operate analysis.",
            ],
            mock_mode_used=bool(original.get("mock_mode_used")),
            patent_analysis={"schema_validation_error": ve_detail},
            patent_evidence_bundle={"raw_output": original, "schema_validation_error": ve_detail},
        ).model_dump()
        return safe


# ---------------------------------------------------------------------------
# Local-folder ingestion diagnostic helper
# ---------------------------------------------------------------------------

def _summarise_local_ingestion(lsummary: dict) -> dict:
    """Build a human-readable per-file ingestion diagnostic.

    Returns a dict with:
      * folder_path
      * files_discovered / supported / skipped
      * extractions: list of {file_name, ext, status, method, quality, reason}
      * unsupported_formats
      * notes
      * counters: failed, succeeded, empty
      * ocr_likely_needed: True if many failures look like scanned PDFs

    All info is already in ``lsummary`` — we just shape it for the
    draft-writer to render as a readable section.  Never raises.
    """
    if not isinstance(lsummary, dict) or not lsummary:
        return {}
    discovery = lsummary.get("discovery") or {}
    extractions = lsummary.get("extractions") or []

    rows: list[dict] = []
    n_failed = 0
    n_ok = 0
    n_empty = 0
    n_pdf_no_text = 0
    n_pdf_total = 0
    for ex in extractions:
        if not isinstance(ex, dict):
            continue
        ext = (ex.get("ext") or "").lower()
        method = ex.get("extraction_method") or ""
        quality = ex.get("extraction_quality") or "none"
        failed = bool(ex.get("failed", False))
        reason = (ex.get("failure_reason") or "").strip()
        status = (
            "failed" if failed
            else "no_text" if quality == "none"
            else "extracted"
        )
        if status == "extracted":
            n_ok += 1
        elif status == "no_text":
            n_empty += 1
        else:
            n_failed += 1
        if ext == ".pdf":
            n_pdf_total += 1
            if status in ("failed", "no_text"):
                n_pdf_no_text += 1
        rows.append({
            "file_name": ex.get("file_name") or "",
            "ext": ext,
            "status": status,
            "method": method,
            "quality": quality,
            "reason": reason[:200],
        })

    return {
        "folder_path": lsummary.get("folder_path", ""),
        "files_discovered": int(discovery.get("files_discovered", 0) or 0),
        "files_supported": int(discovery.get("files_supported", 0) or 0),
        "files_skipped": int(discovery.get("files_skipped", 0) or 0),
        "unsupported_formats": list(discovery.get("unsupported_formats", []) or []),
        "counters": {
            "extracted_ok": n_ok,
            "empty_or_no_text": n_empty,
            "failed": n_failed,
        },
        "extractions": rows,
        "notes": list(lsummary.get("notes", []) or [])[:8],
        # Heuristic: if MOST of the PDF inputs returned no text, the
        # files are likely scanned/image PDFs — OCR is the right fix.
        "ocr_likely_needed": (
            n_pdf_total >= 1 and n_pdf_no_text / max(1, n_pdf_total) >= 0.5
        ),
        "evidence_quality_hint": lsummary.get("evidence_quality_hint", "none"),
        "chunks_indexed": int(lsummary.get("chunks_indexed", 0) or 0),
    }


# ---------------------------------------------------------------------------
# Rigorous claim-centric analysis (Algorithms 1-4)
# ---------------------------------------------------------------------------

def _build_rigorous_analysis(
    *,
    topic: str,
    real_records: list[dict],
    local_extras: dict | None,
    verifier_extra: str = "",
) -> dict:
    """Assemble the patent corpus and run the rigorous pipeline.

    Returns a dict suitable for ``output["rigorous_analysis"]``.
    Skips the pipeline entirely when no real evidence is available.
    """
    from core.patent_rigor import run_rigorous_pipeline

    corpus: list[dict] = []

    # Web records (already mock-filtered upstream).
    for r in real_records or []:
        if not isinstance(r, dict):
            continue
        body_parts = [
            r.get("title", ""),
            r.get("abstract", ""),
            r.get("claims_excerpt", ""),
            r.get("description_excerpt", ""),
            r.get("raw_text_excerpt", ""),
        ]
        body = "\n\n".join(str(p) for p in body_parts if p)
        if not body.strip():
            continue
        corpus.append({
            "patent_id": (
                r.get("publication_number")
                or r.get("application_number")
                or r.get("record_id")
                or r.get("normalised_key")
                or f"W{len(corpus) + 1}"
            ),
            "title": r.get("title", ""),
            "body": body,
            "source_url": r.get("url", ""),
            "source_origin": "web",
        })

    # Local-patent retrieved chunks — group by document so each local
    # patent contributes ONE corpus entry (Algorithm 1 expects per-patent
    # bodies, not per-chunk fragments).
    if local_extras:
        chunks = local_extras.get("local_patent_evidence") or []
        by_doc: dict[str, dict] = {}
        for ch in chunks:
            if not isinstance(ch, dict):
                continue
            doc_id = ch.get("document_id") or ch.get("file_name") or ""
            if not doc_id:
                continue
            file_name = ch.get("file_name", "") or doc_id
            excerpt = (ch.get("excerpt") or "").strip()
            if not excerpt:
                continue
            entry = by_doc.setdefault(doc_id, {
                "patent_id": (
                    file_name.split()[0]   # e.g. "US10478635 …" → "US10478635"
                    if file_name else f"L{len(by_doc) + 1}"
                )[:30],
                "title": file_name,
                "body_parts": [],
                "source_url": "",
                "source_origin": "local",
            })
            entry["body_parts"].append(
                f"[{ch.get('safe_reference') or ch.get('location_hint') or ''}]\n"
                f"{excerpt}"
            )
        for entry in by_doc.values():
            entry["body"] = "\n\n".join(entry.pop("body_parts"))
            if entry["body"].strip():
                corpus.append(entry)

    if not corpus:
        return {
            "topic_profile": {"topic_name": topic},
            "patent_profiles": [],
            "relevance_table": [],
            "coverage_matrix": [],
            "gap_table": [],
            "abstentions": [
                "No real patent evidence available; rigorous claim-centric "
                "analysis skipped to avoid fabrication."
            ],
        }

    # Progress callback prints batch / cache stats so a long cold run
    # doesn't look like a hang.
    def _on_progress(stage: str, n_done: int, n_total: int, info: dict) -> None:
        try:
            if stage == "cache_partition":
                print(
                    f"[patent_intelligence] rigor cache: "
                    f"{info.get('hits', 0)} hit(s), "
                    f"{info.get('misses', 0)} miss(es).",
                    flush=True,
                )
            elif stage == "extract_batch":
                print(
                    f"[patent_intelligence] rigor extraction: "
                    f"{n_done}/{n_total} (batch_size={info.get('batch_size', 0)}).",
                    flush=True,
                )
        except Exception:
            pass

    try:
        result = run_rigorous_pipeline(
            topic=topic,
            patents=corpus,
            topic_extra_context=verifier_extra,
            batch_size=3,
            on_progress=_on_progress,
        )
        return result.model_dump()
    except Exception as exc:
        return {
            "topic_profile": {"topic_name": topic},
            "patent_profiles": [],
            "relevance_table": [],
            "coverage_matrix": [],
            "gap_table": [],
            "abstentions": [
                f"Rigorous pipeline failed: {exc.__class__.__name__}: {exc}",
            ],
        }
