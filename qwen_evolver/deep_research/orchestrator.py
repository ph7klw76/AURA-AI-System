"""
Deep Research Orchestrator — main loop that runs a mission.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import config
from .schemas import (
    ResearchMission, EvidencePack, EvidenceClaim,
    GapAnalysis, DeepResearchReport, ResearchReflection,
    ResearchVerificationResult, Verdict, SourceRecord,
)
from .planner import plan_from_mission
from .search_providers import (
    SearchProvider, MockSearchProvider, SearXNGSearchProvider,
)
from .source_reader import fetch_source
from .evidence_extractor import extract_claims
from .evidence_store import save_evidence_pack
from .gap_analyzer import analyse_gaps
from .verifier_bridge import verify_evidence
from .report_builder import build_report
from .research_logger import save_reflection

REPORTS_DIR = config.BASE_DIR / "reports" / "deep_research"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_provider(on_status=None) -> tuple[SearchProvider, list[str]]:
    """Return (provider, provider_warnings).

    Precedence (SearXNG is the only real provider; mock is the only fallback)
    ------------------------------------------------------------------------
    1. SEARXNG_ENABLED=1  → try SearXNG; fall back to Mock on failure.
    2. SEARXNG_ENABLED=0  → Mock (clearly labelled in warnings).

    *provider_warnings* is a list of human-readable strings that callers should
    add to the research report / reflection so the user knows which provider
    was used and why.
    """
    say = on_status or (lambda _: None)
    warnings: list[str] = []

    if config.SEARXNG_ENABLED:
        from core.searxng_runtime import ensure_searxng_ready
        status = ensure_searxng_ready(
            timeout_s=float(config.SEARXNG_TIMEOUT_SECONDS),
            on_status=say,
        )
        if status["ok"]:
            return SearXNGSearchProvider(
                base_url=config.SEARXNG_URL,
                timeout=config.SEARXNG_TIMEOUT_SECONDS,
            ), warnings

        warn = f"SearXNG unavailable: {status['message']}"
        warnings.append(warn)
        say(warn)
        warnings.append(
            "Falling back to mock search provider. "
            "Results are SYNTHETIC and do NOT represent real web search."
        )
        say("Using mock provider (synthetic results).")
        return MockSearchProvider(), warnings

    warnings.append(
        "SEARXNG_ENABLED=0. Using mock search provider — results are SYNTHETIC. "
        "Enable SearXNG (see deployment/searxng/) for real web search."
    )
    return MockSearchProvider(), warnings


def _budget(depth: str, key: str) -> int:
    """Return budget based on depth and env overrides."""
    env_map = {
        "max_rounds": ("AURA_RESEARCH_MAX_ROUNDS", {"rapid": 1, "standard": 2, "extensive": 4}),
        "max_queries": ("AURA_RESEARCH_MAX_QUERIES", {"rapid": 5, "standard": 15, "extensive": 30}),
        "max_sources": ("AURA_RESEARCH_MAX_SOURCES", {"rapid": 5, "standard": 15, "extensive": 30}),
    }
    env_var, defaults = env_map[key]
    try:
        return int(os.getenv(env_var, str(defaults.get(depth, 5))))
    except Exception:
        return defaults.get(depth, 5)


def run_research(mission: ResearchMission) -> dict:
    # Fail closed on traversal-style mission_id BEFORE any read/write path
    # is derived from it (evidence, sources, reports, reflections all key
    # off mission.mission_id).
    from core.path_safety import validate_mission_id
    validate_mission_id(mission.mission_id)
    provider, provider_warnings = _resolve_provider()
    # Defect 4: track whether the active provider is the mock fallback so
    # downstream consumers cannot claim strong/high confidence on synthetic
    # data.  The label survives even if no sources are fetched.
    used_mock_provider = isinstance(provider, MockSearchProvider)
    plan = plan_from_mission(mission)

    evidence_pack = EvidencePack(
        mission_id=mission.mission_id,
        research_question=plan.main_question,
        plan_summary=f"{len(plan.initial_queries)} initial queries, {len(plan.search_branches)} branches",
    )

    max_rounds = _budget(mission.requested_depth.value, "max_rounds")
    max_queries = _budget(mission.requested_depth.value, "max_queries")
    max_sources = _budget(mission.requested_depth.value, "max_sources")

    current_queries = list(plan.initial_queries[:10])
    sources_fetched: list[SourceRecord] = []
    all_claims: list[EvidenceClaim] = []
    round_num = 0
    reflection_notes: list[str] = list(provider_warnings)
    wasted_paths: list[str] = []

    while round_num < max_rounds and current_queries and len(sources_fetched) < max_sources:
        round_num += 1
        for q in current_queries[:max_queries]:
            results = provider.search(q, max_results=5)
            for sr in results:
                if len(sources_fetched) >= max_sources:
                    break
                # ---- handle mock provider without network fetch (issue 14) ----
                if isinstance(provider, MockSearchProvider):
                    now = datetime.now(timezone.utc).isoformat()
                    record = SourceRecord(
                        source_id=sr.result_id,
                        title=sr.title,
                        url=sr.url,
                        provider=sr.provider,
                        retrieved_at=now,
                        status="fetched",
                        inline_text=f"Mock content for {sr.title}. This is synthetic text for testing.",
                    )
                    sources_fetched.append(record)
                    claims = extract_claims(record)
                    all_claims.extend(claims)
                    continue

                record = fetch_source(sr, mission.mission_id)
                if record.status == "fetched":
                    sources_fetched.append(record)
                    claims = extract_claims(record)
                    all_claims.extend(claims)

        # Update pack
        evidence_pack.sources = sources_fetched.copy()
        evidence_pack.evidence_claims = all_claims.copy()
        evidence_pack.key_findings = [c.claim_text for c in all_claims if c.support_status.value == "supported"][:5]
        save_evidence_pack(evidence_pack)

        # Gap analysis
        gap = analyse_gaps(evidence_pack)
        if gap.followup_queries:
            current_queries = gap.followup_queries[:max_queries]
        else:
            current_queries = []
        if gap.recommendation.value == "proceed_to_verification":
            break
        if gap.recommendation.value == "human_review":
            reflection_notes.append("Gap analyser recommended human_review")
            wasted_paths.append("gap_analysis_human_review")
            break

    # Verification
    verif = verify_evidence(evidence_pack, mission.original_user_request)

    # Defect 10 + 11: pass the verifier result to the report builder so the
    # synthesiser SEES the verdict and reflects rejected/unsupported state.
    # build_report now returns (report, status) so the orchestrator can
    # detect a report-generation failure.
    report, report_status = build_report(evidence_pack, verification=verif)
    report_generation_failed = not report_status.startswith("ok")

    # NOTE: Legacy 6-section markdown writer removed.  Per AURA contract
    # (see core/aura_principles.py + CLAUDE.md), there is exactly ONE
    # report file per mission and it is the 16-section rigorous report
    # written further below at the same path
    # (reports/deep_research/<mission_id>_report.md).  The legacy
    # ``report`` object is folded into the rigorous report's Appendix
    # so nothing is lost.

    # Reflection
    reflection = ResearchReflection(
        mission_id=mission.mission_id,
        what_worked=[f"Seeded with {len(plan.initial_queries)} queries", f"Used {len(sources_fetched)} sources"],
        what_failed=reflection_notes,
        wasted_search_paths=wasted_paths,
        high_value_source_patterns=[provider.__class__.__name__.lower().replace("searchprovider", "")],
        common_missing_evidence=["verdict: " + verif.decision.value],
        proposed_workflow_rules=[],
    )
    save_reflection(reflection)

    # ----------------------------------------------------------------
    # 16-section structured report (MANDATORY — enforced by
    # core/aura_principles.py + CLAUDE.md).
    #
    # AURA INTEGRITY CONTRACT (do not change without explicit user
    # approval — see core/aura_principles.DEEP_RESEARCH_CONTRACT):
    #   * Exactly ONE markdown report per mission, at
    #     reports/deep_research/<mission_id>_report.md.  No separate
    #     _rigorous_report.md companion (two files confused users).
    #   * All 16 sections from DEEP_RESEARCH_REPORT_SECTIONS are
    #     emitted in order, empty sections use the placeholder.
    #   * AURA_DEEP_RESEARCH_RIGOR=0 is a degraded test-mode toggle,
    #     not an opt-out — the file is still written.
    #   * Pipeline failures degrade to a defensive empty report whose
    #     renderer still emits every section.  No silent skips.
    #   * Additive only — never mutates verifier, memory, or any
    #     legacy persistence path.
    # ----------------------------------------------------------------
    from .rigor import (
        RigorousReport, build_rigorous_report, render_rigorous_report_markdown,
    )
    from core.aura_principles import (
        DEEP_RESEARCH_REPORT_FILENAME_TEMPLATE,
        DEEP_RESEARCH_REPORT_SECTIONS,
        assert_deep_research_report_layout,
        assert_single_report_file,
    )
    rigorous_payload: dict = {}
    _rigor_disabled = os.getenv("AURA_DEEP_RESEARCH_RIGOR", "1").strip() == "0"

    if _rigor_disabled:
        # Degraded mode for hermetic offline tests with no LLM.  Still
        # produce a structurally-complete 16-section markdown so the
        # contract holds.
        rr = RigorousReport(
            title=report.title or mission.original_user_request[:160],
            abstentions=[
                "AURA_DEEP_RESEARCH_RIGOR=0 — rigorous synthesis skipped; "
                "this is a structural placeholder.",
            ],
        )
    else:
        try:
            rr = build_rigorous_report(
                user_request=mission.original_user_request,
                pack=evidence_pack,
                verification=verif,
            )
        except Exception as exc:
            # Build-time failure: degrade to an empty-but-valid report
            # so the 16-section markdown is still emitted.
            rr = RigorousReport(
                title=report.title or mission.original_user_request[:160],
                abstentions=[
                    f"Rigorous synthesis failed: "
                    f"{exc.__class__.__name__}: {str(exc)[:200]}. "
                    "Report falls back to structural placeholders.",
                ],
            )

    # Fold legacy ``report`` artefacts into the Appendix so nothing is
    # lost when the legacy 6-section writer was removed.
    if report.executive_summary and not rr.executive_summary_main_conclusion:
        rr.executive_summary_main_conclusion = report.executive_summary[:500]
    if report.findings:
        # Normalise the legacy `[SRC_<id>]` anchors to the rigorous
        # `[S:<id>]` form so anchor style is uniform across the whole
        # report.
        import re as _re_local
        _legacy_anchor = _re_local.compile(r"\[SRC_([A-Za-z0-9_-]+)\]")
        normalised = [
            _legacy_anchor.sub(r"[S:\1]", f) for f in report.findings
        ]
        rr.appendix_notes.append(
            "Legacy synthesiser findings (pre-rigor):\n"
            + "\n".join(f"  - {f}" for f in normalised)
        )
    if report.strategic_recommendations and not rr.recommendations:
        rr.recommendations = list(report.strategic_recommendations)
    if report.evidence_caveats:
        rr.risks_limitations_uncertainties = (
            list(rr.risks_limitations_uncertainties)
            + [c for c in report.evidence_caveats
               if c not in rr.risks_limitations_uncertainties]
        )
    for pw in provider_warnings:
        rr.appendix_notes.append(f"Provider notice: {pw}")
    if len(sources_fetched) == 0:
        rr.abstentions.append(
            "No sources were successfully fetched. Findings are based on "
            "synthetic mock data or empty evidence and must not be treated "
            "as verified research."
        )

    rigorous_payload = rr.model_dump()

    # Unified path — there is exactly ONE report file per mission.
    report_md_path = REPORTS_DIR / (
        DEEP_RESEARCH_REPORT_FILENAME_TEMPLATE.format(
            mission_id=mission.mission_id,
        )
    )

    # Always write the 16-section markdown — even if rendering raises,
    # write a minimal contract-preserving fallback rather than skipping.
    try:
        md = render_rigorous_report_markdown(rr)
    except Exception as exc:
        md = (
            f"# {rr.title or 'Deep Research Report'}\n\n"
            f"> ⚠ Rigorous markdown rendering failed: "
            f"{exc.__class__.__name__}: {str(exc)[:200]}\n\n"
            + "\n".join(
                f"## {i}. {name}\n\n_(not derivable from current evidence)_\n"
                for i, name in enumerate(DEEP_RESEARCH_REPORT_SECTIONS, start=1)
            )
        )

    report_write_ok = True
    try:
        report_md_path.write_text(md, encoding="utf-8")
    except Exception:
        # Truly catastrophic (disk full / permissions) — record and
        # continue; do not abort the deep_research run.
        report_write_ok = False

    # Defensive cleanup: if a legacy _rigorous_report.md companion file
    # exists from a previous build of AURA, delete it so the contract
    # ("exactly ONE report file per mission") holds.
    _legacy_companion = REPORTS_DIR / f"{mission.mission_id}_rigorous_report.md"
    if _legacy_companion.exists():
        try:
            _legacy_companion.unlink()
        except Exception:
            pass

    # Runtime contract assertions (cheap — only run on the file we just
    # wrote).  Violations are surfaced as reflection notes rather than
    # raising, because failing the run after the report is on disk
    # would lose the user's work.
    if report_write_ok:
        try:
            assert_deep_research_report_layout(md)
            assert_single_report_file(REPORTS_DIR, mission.mission_id)
        except Exception as exc:
            reflection_notes.append(
                f"AURA contract violation: {exc.__class__.__name__}: "
                f"{str(exc)[:200]}"
            )

    # Defect D: the reflection was saved BEFORE the contract assertions ran,
    # so any late contract-violation / diagnostic note appended to
    # ``reflection_notes`` above never reached the persisted artifact.  Now
    # that ALL checks have run, re-sync ``what_failed`` and re-persist (the
    # logger writes a single file per mission_id, so this overwrites in
    # place — no duplicate record).
    if list(reflection.what_failed) != reflection_notes:
        reflection.what_failed = list(reflection_notes)
        save_reflection(reflection)

    return {
        "mission": mission.model_dump(),
        "plan": plan.model_dump(),
        "evidence_pack": evidence_pack.model_dump(),
        "verification": verif.model_dump(),
        "report": report.model_dump(),
        "report_status": report_status,            # defect 11
        "report_generation_failed": report_generation_failed,
        "reflection": reflection.model_dump(),
        "report_path": (
            str(report_md_path.relative_to(config.BASE_DIR))
            if report_write_ok else ""
        ),
        "source_count": len(sources_fetched),
        # Defect 4: provenance flags so callers can never call mock-only
        # output strong/high-confidence.
        "mock_mode_used": used_mock_provider,
        "provider_label": provider.__class__.__name__,
        "provider_warnings": list(provider_warnings),
        # Rigorous structured payload (the 16-section report's data model).
        "rigorous_report": rigorous_payload,
        # Unified contract: rigorous_report_path == report_path.  There
        # is exactly ONE report file per mission.  Field retained for
        # backward compatibility with downstream consumers.
        "rigorous_report_path": (
            str(report_md_path.relative_to(config.BASE_DIR))
            if report_write_ok else ""
        ),
    }
