"""
AURA Draft Writer — persist specialist outputs to Markdown files in reports/.

Every AURA session that produces a high-stakes specialist output (Grant
Architect, Teaching Mentor, Lab/Data Analyst, Influence/Public Communication,
Collaboration Operator, Founder/Innovation, Patent Intelligence) automatically
writes a timestamped Markdown file to reports/, so drafts never disappear when
the terminal scrolls.

Public surface:
    save_specialist_drafts(result, user_input="") -> list[Path]
        Writes one .md per specialist found in result["specialists"].
        Returns the list of written paths.

    DRAFT_KINDS — set of specialist names that get saved.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import config


DRAFT_KINDS: frozenset[str] = frozenset({
    "grant_architect",
    "china_grant_architect",
    "teaching_mentor",
    "lab_data_analyst",
    "influence_public_communication",
    "collaboration_operator",
    "founder_innovation",
    "patent_intelligence",
    # research_scout writes its own weekly brief — handled separately
})


# ---------------------------------------------------------------------------
# Per-specialist Markdown formatters
# ---------------------------------------------------------------------------

# Internal annotations that AURA agents append to user-facing list items
# but that should NOT leak into a persisted draft.  Anything starting with
# one of these prefixes (case-insensitive, after stripping leading
# whitespace) is dropped during rendering.
_INTERNAL_LIST_PREFIXES: tuple[str, ...] = (
    "Blocked by ACTION_POLICY",
    "[INTERNAL]",
    "[DEBUG]",
    "shape:",                 # core.normalization shape_warning()
    "Verifier failure:",      # scientific_verifier _failure_safe_report
    "failed_stage:",
)


def _is_internal_marker(text: str) -> bool:
    stripped = text.lstrip()
    return any(stripped.startswith(p) for p in _INTERNAL_LIST_PREFIXES)


def _safe(s, default="") -> str:
    if s is None:
        return default
    return str(s)


def _bullets(items, label: str | None = None) -> str:
    # Defect: internal markers (``Blocked by ACTION_POLICY: ...``, shape
    # warnings, verifier-failure tags) were leaking into persisted drafts
    # and being read by users as if they were real content.  Filter them
    # here so every formatter benefits automatically.
    items = [
        _safe(i) for i in (items or [])
        if str(i).strip() and not _is_internal_marker(str(i))
    ]
    if not items:
        return ""
    lines = []
    if label:
        lines.append(f"\n### {label}\n")
    for it in items:
        lines.append(f"- {it}")
    return "\n".join(lines) + "\n"


def _format_structured_risks(items, label: str | None = None) -> str:
    """Render a list of structured KeyRisk dicts as readable Markdown.

    Each entry follows the schema
        {"category": str, "description": str, "severity": str,
         "likelihood": str, "mitigation": str}
    and is rendered as:
        - **[category · severity/likelihood]** description.
          *Mitigation:* mitigation text.

    Falls back to ``_bullets`` for plain-string entries so legacy outputs
    (founder_innovation Phase 2 had a flat list of strings) still work.
    """
    if not items:
        return ""
    rendered: list[str] = []
    for item in items:
        if isinstance(item, dict):
            cat = str(item.get("category", "")).strip() or "other"
            sev = str(item.get("severity", "")).strip()
            lik = str(item.get("likelihood", "")).strip()
            desc = str(item.get("description", "")).strip()
            mit = str(item.get("mitigation", "")).strip()
            if not desc:
                continue
            sev_lik = "/".join(p for p in (sev, lik) if p) or "unknown"
            line = f"- **[{cat} · {sev_lik}]** {desc}"
            if mit:
                line += f"  \n  *Mitigation:* {mit}"
            rendered.append(line)
        else:
            text = str(item).strip()
            if text and not _is_internal_marker(text):
                rendered.append(f"- {text}")
    if not rendered:
        return ""
    head = f"\n### {label}\n\n" if label else ""
    return head + "\n".join(rendered) + "\n"


def _section(label: str, body: str) -> str:
    body = _safe(body).strip()
    if not body:
        return ""
    return f"\n### {label}\n\n{body}\n"


def _kv_table(rows: list[tuple[str, object]]) -> str:
    """Render a small Key / Value table for header metadata."""
    pairs = [(k, _safe(v).strip() or "—") for k, v in rows if v not in (None, "")]
    if not pairs:
        return ""
    lines = ["| Field | Value |", "|---|---|"]
    for k, v in pairs:
        # collapse newlines in v
        v = re.sub(r"\s+", " ", v)[:240]
        lines.append(f"| {k} | {v} |")
    return "\n".join(lines) + "\n"


# Grant Architect ------------------------------------------------------------

_AP_PLACEHOLDER = (
    "_(not produced by the general Grant Architect — run the China "
    "sub-mode `agents.grant_architect.run_china` for the full A-P "
    "content, or extend the general agent's prompt to populate this "
    "item)_"
)


def format_grant_architect_md(output: dict, user_input: str = "") -> str:
    """Render the general Grant Architect output in the AURA A-P layout.

    The A-P layout (16 parts A..P carrying 36 numbered items) is the
    AURA-default proposal style codified in
    ``core/grant_templates/china_blueprint.py::CHINA_GRANT_MASTER_TEMPLATE``.
    The general Grant Architect produces a SUBSET of the China sub-mode's
    data, so items it cannot fill render with an explicit placeholder
    pointing the user at ``run_china`` for full fidelity.

    A References section is ALWAYS emitted — even when empty — so the
    reader can see what literature was (or was not) supplied by the
    Research Scout to back the draft.
    """
    out = output or {}
    L: list[str] = []

    title = (out.get("possible_title") or "").strip() or "Grant Architect Draft"
    L.append(f"# Grant Architect Draft")
    L.append(f"## {title}\n")
    if user_input:
        L.append(f"> **Prompt:** {user_input.strip()}\n")
    L.append(_kv_table([
        ("Possible Title", out.get("possible_title")),
        ("Grant Readiness", out.get("grant_readiness")),
        ("Confidence", out.get("confidence")),
        ("Evidence Level", out.get("evidence_level")),
        ("Approval Level", out.get("approval_level")),
    ]))

    # Surface what context was available so the reader knows why
    # some A-P items are placeholders.
    refs_in = out.get("references_used") or []
    refs_in = [str(r).strip() for r in refs_in
               if isinstance(r, str) and r.strip()]
    L.append("\n> _Drafting context coverage: "
             f"references_used = {len(refs_in)} item(s); "
             "run `research_scout` upstream to enrich the References "
             "section and back every [N] citation._\n")

    def part(letter: str, title: str) -> None:
        L.append(f"\n## {letter}. {title}\n")

    def item(num: int, label: str, body: str | list | None = None,
             placeholder: bool = False) -> None:
        L.append(f"### {num}. {label}\n")
        if isinstance(body, list):
            cleaned = _clean_list(body)
            if cleaned:
                for b in cleaned:
                    L.append(f"- {b}")
            else:
                L.append(_AP_PLACEHOLDER if placeholder else "_(none)_")
        elif isinstance(body, str) and body.strip():
            L.append(body.strip())
        else:
            L.append(_AP_PLACEHOLDER if placeholder else "_(none)_")
        L.append("")

    # ---- A. Project Framing -------------------------------------------
    part("A", "Project Framing")
    formal = (out.get("possible_title") or "").strip() or _AP_PLACEHOLDER
    item(1, "Three candidate project titles", [
        f"**Formal scientific title:** {formal}",
        "**Reviewer-friendly title:** " + _AP_PLACEHOLDER,
        "**Ambitious but credible title:** " + _AP_PLACEHOLDER,
    ])
    item(2, "English title (+ optional Chinese title placeholder)", [
        f"**English:** {formal}",
        "**中文 / Chinese:** _(placeholder — provide if the call requires Chinese)_",
    ])
    abstract_full = (
        ((out.get("summary") or "").strip() + "\n\n"
         + (out.get("problem_statement") or "").strip()).strip()
        or _AP_PLACEHOLDER
    )
    item(3, "Full technical abstract", abstract_full)
    item(4, "Concise abstract", (out.get("summary") or "").strip() or _AP_PLACEHOLDER)
    item(5, "Keyword set",
         _AP_PLACEHOLDER, placeholder=True)

    # ---- B. Scientific Rationale --------------------------------------
    part("B", "Scientific Rationale")
    item(6, "Background and significance",
         (out.get("problem_statement") or "").strip() or _AP_PLACEHOLDER)
    item(7, "Literature-state summary (per knowledge category)",
         _AP_PLACEHOLDER, placeholder=True)
    item(8, "Research gap map table",
         _AP_PLACEHOLDER, placeholder=True)

    # ---- C. Scientific Architecture -----------------------------------
    part("C", "Scientific Architecture")
    item(9, "Central question",
         _AP_PLACEHOLDER, placeholder=True)
    item(10, "Subquestions",
         _AP_PLACEHOLDER, placeholder=True)
    item(11, "Central hypothesis",
         (out.get("central_hypothesis") or "").strip() or _AP_PLACEHOLDER)
    item(12, "Specific objectives", out.get("objectives") or [])
    item(13, "Objective-to-gap traceability matrix",
         _AP_PLACEHOLDER, placeholder=True)
    item(14, "Conceptual framework chain",
         "molecular design → excited-state behavior → device architecture "
         "→ optical output → application relevance "
         "_(default chain — refine to your topic)_")

    # ---- D. Work Packages ---------------------------------------------
    part("D", "Work Packages")
    item(15, "Design 4-5 work packages", out.get("work_packages") or [])
    item(16, "Per-WP detail (objective, rationale, methods, outputs, "
              "risks, fallback, deliverables)",
         _AP_PLACEHOLDER, placeholder=True)

    # ---- E. Methodology -----------------------------------------------
    part("E", "Methodology")
    item(17, "Rigorous methodology",
         (out.get("methodology_overview") or "").strip() or _AP_PLACEHOLDER)
    item(18, "Evidence Needed Before Submission (missing methods / overclaims)",
         out.get("evidence_needed_before_submission") or [])

    # ---- F. Innovation ------------------------------------------------
    part("F", "Innovation")
    item(19, "Innovation categories "
              "(conceptual / material / device / translational)",
         _AP_PLACEHOLDER, placeholder=True)
    item(20, "Per-innovation strength (strong / moderate / weak)",
         _AP_PLACEHOLDER, placeholder=True)

    # ---- G. Preliminary Basis -----------------------------------------
    part("G", "Preliminary Basis")
    item(21, "Research foundation (placeholders where user data is unavailable)",
         _AP_PLACEHOLDER, placeholder=True)
    item(22, "Evidence matrix (claim → support → missing → evidence needed)",
         out.get("evidence_needed_before_submission") or [])

    # ---- H. Feasibility -----------------------------------------------
    part("H", "Feasibility")
    item(23, "Scientific / technical / resource / timeline / "
              "applicant-fit feasibility",
         _AP_PLACEHOLDER, placeholder=True)

    # ---- I. Timeline --------------------------------------------------
    part("I", "Timeline")
    item(24, "Timeline + milestones + critical dependencies + go/no-go points",
         out.get("timeline") or [])

    # ---- J. Expected Outcomes -----------------------------------------
    part("J", "Expected Outcomes")
    item(25, "Realistic expected outputs", out.get("expected_outcomes") or [])

    # ---- K. Risk Register ---------------------------------------------
    part("K", "Risk Register")
    # Merge: project risks + risk_mitigation + extra context.
    combined_risks = list(out.get("risks") or []) + list(out.get("risk_mitigation") or [])
    item(26, "Full risk table (risk + mitigation, derived from "
              "Additional Project Risks + Risk Mitigation)",
         combined_risks)

    # ---- L. Budget Logic ----------------------------------------------
    part("L", "Budget Logic")
    item(27, "Task-to-budget rationale (indicative; not final numbers)",
         out.get("budget") or [])
    item(28, "Final numbers withheld unless user-provided",
         "_(no final figures unless the user supplies them)_")
    item(29, "Reviewer vulnerabilities in the budget logic",
         _AP_PLACEHOLDER, placeholder=True)

    # ---- M. Compliance and Attachments --------------------------------
    part("M", "Compliance and Attachments")
    item(30, "Compliance + attachments checklist",
         out.get("collaborator_needs") or [])

    # ---- N. Reviewer Simulation ---------------------------------------
    part("N", "Reviewer Simulation")
    item(31, "Reviewer Attack Points (general agent — single panel "
              "of attack points; run_china produces five canonical reviewers)",
         out.get("reviewer_attack_points") or [])
    item(32, "Per-reviewer detail (strengths, weaknesses, score, "
              "mandatory revision)",
         _AP_PLACEHOLDER, placeholder=True)

    # ---- O. Competitiveness Score -------------------------------------
    part("O", "Competitiveness Score")
    item(33, "Proposal scored out of 100 across 10 axes",
         _AP_PLACEHOLDER, placeholder=True)
    item(34, "Decision band",
         f"_(grant_readiness = `{out.get('grant_readiness', 'unknown')}` — "
         "competitiveness scoring is China-sub-mode only)_")

    # ---- P. Weakness Repair Plan + Team + Assumptions + References ---
    part("P", "Weakness Repair Plan")
    item(35, "Top weaknesses (from reviewer_attack_points)",
         out.get("reviewer_attack_points") or [])
    item(36, "Per-weakness detail (why it matters, what to revise, "
              "evidence needed, how to rewrite)",
         _AP_PLACEHOLDER, placeholder=True)

    # ---- Appendix: team + assumptions + project-internal risks -------
    L.append("\n## Appendix\n")
    L.append("### Team Roles & FTE\n")
    team = _clean_list(out.get("team_roles") or [])
    if team:
        for t in team:
            L.append(f"- {t}")
    else:
        L.append("_(no team roles supplied)_")
    L.append("")
    L.append("### Assumptions\n")
    asm = _clean_list(out.get("assumptions") or [])
    if asm:
        for a in asm:
            L.append(f"- {a}")
    else:
        L.append("_(none)_")
    L.append("")
    L.append("### Additional Project Risks\n")
    pr = _clean_list(out.get("risks") or [])
    if pr:
        for r in pr:
            L.append(f"- {r}")
    else:
        L.append("_(none)_")
    L.append("")

    # ---- References (always emitted) ---------------------------------
    L.append("## References\n")
    if refs_in:
        for ref in refs_in:
            L.append(ref)
    else:
        L.append(
            "_No references were supplied by Research Scout for this run. "
            "All [N] citations in the body are therefore unresolved._\n\n"
            "To populate this section:\n"
            "1. Run `research_scout` upstream so its `top_papers` field is "
            "passed in `context`.\n"
            "2. Or supply a References block directly in the user prompt — "
            "the architect will preserve it.\n"
        )
    L.append("")
    return "\n".join(p for p in L if p is not None)


def _clean_list(items: list) -> list[str]:
    out: list[str] = []
    for it in items or []:
        s = _safe(it).strip()
        if not s or _is_internal_marker(s):
            continue
        out.append(s)
    return out


# Teaching Mentor ------------------------------------------------------------

def format_teaching_mentor_md(output: dict, user_input: str = "") -> str:
    out = output or {}
    lines = [f"# Teaching Mentor Draft"]
    if user_input:
        lines.append(f"\n> **Prompt:** {user_input.strip()}\n")
    lines.append("\n## Metadata\n")
    lines.append(_kv_table([
        ("Target Audience", out.get("target_audience")),
        ("Learner Level", out.get("learner_level")),
        ("Confidence", out.get("confidence")),
        ("Evidence Level", out.get("evidence_level")),
    ]))
    lines.append(_section("Summary", out.get("summary")))
    lines.append(_bullets(out.get("learning_outcomes"), label="Learning Outcomes"))
    lines.append(_section("Conceptual Explanation", out.get("conceptual_explanation")))
    lines.append(_bullets(out.get("socratic_questions"), label="Socratic Questions"))
    lines.append(_bullets(out.get("common_misconceptions"), label="Common Misconceptions"))
    lines.append(_bullets(out.get("quiz_questions"), label="Quiz Questions"))
    lines.append(_bullets(out.get("assessment_rubric"), label="Assessment Rubric"))
    lines.append(_section("Teaching Activity", out.get("teaching_activity")))
    lines.append(_bullets(out.get("technical_cautions"), label="Technical Cautions"))
    return "\n".join(p for p in lines if p)


# Lab/Data Analyst -----------------------------------------------------------

def format_lab_data_analyst_md(output: dict, user_input: str = "") -> str:
    out = output or {}
    lines = [f"# Lab/Data Analyst Plan"]
    if user_input:
        lines.append(f"\n> **Prompt:** {user_input.strip()}\n")
    lines.append("\n## Metadata\n")
    lines.append(_kv_table([
        ("Analysis Type", out.get("analysis_type")),
        ("Confidence", out.get("confidence")),
        ("Evidence Level", out.get("evidence_level")),
        ("Approval Level", out.get("approval_level")),
    ]))
    lines.append(_section("Summary", out.get("summary")))
    lines.append(_bullets(out.get("data_requirements"), label="Data Requirements"))
    lines.append(_bullets(out.get("required_columns"), label="Required Columns"))
    lines.append(_bullets(out.get("methods_recommended"), label="Recommended Methods"))
    lines.append(_bullets(out.get("calculations_recommended"), label="Recommended Calculations"))
    lines.append(_bullets(out.get("plots_recommended"), label="Recommended Plots"))
    lines.append(_bullets(out.get("data_quality_checks"), label="Data Quality Checks"))
    lines.append(_bullets(out.get("reproducibility_checks"), label="Reproducibility Checks"))
    lines.append(_bullets(out.get("interpretation_limits"), label="Interpretation Limits"))
    lines.append(_bullets(out.get("safe_file_handling"), label="Safe File Handling"))
    lines.append(_bullets(out.get("next_analysis_steps"), label="Next Analysis Steps"))
    lines.append(_bullets(out.get("assumptions"), label="Assumptions"))
    lines.append(_bullets(out.get("risks"), label="Risks"))
    return "\n".join(p for p in lines if p)


# Influence / Public Communication -------------------------------------------

def format_influence_md(output: dict, user_input: str = "") -> str:
    out = output or {}
    lines = [f"# Public Communication Draft"]
    if user_input:
        lines.append(f"\n> **Prompt:** {user_input.strip()}\n")
    lines.append(
        "\n> ⚠️ **Approval required before publishing — this is a DRAFT only.**\n"
    )
    lines.append("\n## Metadata\n")
    lines.append(_kv_table([
        ("Audience", out.get("audience")),
        ("Communication Goal", out.get("communication_goal")),
        ("Confidence", out.get("confidence")),
        ("Evidence Level", out.get("evidence_level")),
        ("Approval Level", out.get("approval_level")),
        ("Approval Required Before Publishing",
         out.get("approval_required_before_publishing")),
    ]))
    lines.append(_section("Core Message", out.get("core_message")))
    lines.append(_bullets(out.get("hook_options"), label="Hook Options"))
    lines.append(_section("LinkedIn Draft", out.get("linkedin_draft")))
    lines.append(_section("Public Explanation", out.get("public_explanation")))
    lines.append(_section("Narrative Angle", out.get("narrative_angle")))
    lines.append(_bullets(out.get("evidence_cautions"), label="Evidence Cautions"))
    lines.append(_bullets(out.get("overclaim_risks"), label="Overclaim Risks"))
    lines.append(_bullets(out.get("safer_wording"), label="Safer Wording"))
    return "\n".join(p for p in lines if p)


# Collaboration Operator -----------------------------------------------------

def format_collaboration_operator_md(output: dict, user_input: str = "") -> str:
    out = output or {}
    lines = [f"# Collaboration Outreach Draft"]
    if user_input:
        lines.append(f"\n> **Prompt:** {user_input.strip()}\n")
    lines.append(
        "\n> ⚠️ **Approval required before contacting — this is a DRAFT only.**\n"
    )
    lines.append("\n## Metadata\n")
    lines.append(_kv_table([
        ("Collaboration Goal", out.get("collaboration_goal")),
        ("Suggested Type", out.get("suggested_collaboration_type")),
        ("Confidence", out.get("confidence")),
        ("Evidence Level", out.get("evidence_level")),
        ("Approval Level", out.get("approval_level")),
        ("Approval Required Before Contacting",
         out.get("approval_required_before_contacting")),
    ]))
    lines.append(_section("Summary", out.get("summary")))
    lines.append(_bullets(out.get("possible_collaborators"), label="Possible Collaborators"))
    lines.append(_bullets(out.get("collaborator_rationale"), label="Collaborator Rationale"))
    lines.append(_bullets(out.get("evidence_for_fit"), label="Evidence for Fit"))
    lines.append(_bullets(out.get("missing_information"), label="Missing Information"))
    lines.append(_section("Draft Email — Subject", out.get("draft_email_subject")))
    lines.append(_section("Draft Email — Body", out.get("draft_email_body")))
    lines.append(_bullets(out.get("meeting_agenda"), label="Meeting Agenda"))
    lines.append(_bullets(out.get("questions_to_ask"), label="Questions to Ask"))
    lines.append(_bullets(out.get("institutional_risk_notes"), label="Institutional Risk Notes"))
    return "\n".join(p for p in lines if p)


# Founder / Innovation -------------------------------------------------------

def format_founder_innovation_md(output: dict, user_input: str = "") -> str:
    out = output or {}
    lines = [f"# Founder / Innovation Analysis"]
    if user_input:
        lines.append(f"\n> **Prompt:** {user_input.strip()}\n")
    disclaimer = (out.get("legal_financial_disclaimer") or "").strip()
    if disclaimer:
        lines.append(f"\n> ⚠️ **{disclaimer}**\n")
    lines.append("\n## Metadata\n")
    lines.append(_kv_table([
        ("Confidence", out.get("confidence")),
        ("Evidence Level", out.get("evidence_level")),
        ("Approval Level", out.get("approval_level")),
        ("Approval Required Before External Commitment",
         out.get("approval_required_before_external_commitment")),
    ]))
    lines.append(_section("Summary", out.get("summary")))
    lines.append(_section("Innovation Thesis", out.get("innovation_thesis")))
    lines.append(_section("Product Hypothesis", out.get("product_hypothesis")))
    lines.append(_bullets(out.get("target_users_or_customers"), label="Target Users / Customers"))
    lines.append(_section("Problem–Customer Fit", out.get("problem_customer_fit")))
    lines.append(_section("Possible Value Proposition", out.get("possible_value_proposition")))
    lines.append(_section("Technical Moat", out.get("technical_moat")))
    lines.append(_bullets(out.get("ip_considerations"), label="IP Considerations"))
    lines.append(_bullets(out.get("market_assumptions"), label="Market Assumptions"))
    lines.append(_bullets(out.get("commercialization_pathways"), label="Commercialization Pathways"))
    lines.append(_bullets(out.get("validation_experiments"), label="Validation Experiments"))
    lines.append(_bullets(out.get("business_model_options"), label="Business Model Options"))
    # Fix A: key_risks is a list of structured dicts; rendering them with
    # _bullets gives ``- {'category': '...', 'description': '...'}`` which is
    # unreadable.  Render each as a single readable line instead.
    lines.append(_format_structured_risks(out.get("key_risks"), label="Key Risks"))
    lines.append(_bullets(out.get("regulatory_or_ethical_considerations"),
                          label="Regulatory / Ethical Considerations"))
    lines.append(_bullets(out.get("next_90_day_plan"), label="Next 90-Day Plan"))
    return "\n".join(p for p in lines if p)


# Patent Intelligence --------------------------------------------------------

def format_patent_intelligence_md(output: dict, user_input: str = "") -> str:
    out = output or {}
    lines = [f"# Patent Intelligence Report (prototype)"]
    if user_input:
        lines.append(f"\n> **Prompt:** {user_input.strip()}\n")
    lines.append("\n## Metadata\n")
    # Records-retrieved metadata is misleading in mock mode: synthetic
    # records were DISCARDED before LLM analysis.  We also surface the
    # MIXED-source case (some real + some synthetic) so the user can
    # tell when mock partially polluted a real run.
    mock_mode_flag = bool(out.get("mock_mode_used"))
    n_records_total = int(out.get("deduplicated_patent_record_count") or 0)
    top_records_field = out.get("top_patent_records") or []
    n_synth = sum(
        1 for r in top_records_field
        if isinstance(r, dict) and "/mock-result/" in str(r.get("url", ""))
    )
    if n_synth > 0 and n_synth < n_records_total:
        # Mixed source.
        n_real = n_records_total - n_synth
        records_label = (
            f"{n_records_total} ({n_real} real + {n_synth} SYNTHETIC; "
            f"synthetic discarded before analysis)"
        )
    elif n_synth > 0 or (mock_mode_flag and n_records_total > 0):
        # All synthetic (or unknown breakdown but mock-mode flagged).
        records_label = (
            f"{n_records_total} (all SYNTHETIC, discarded before analysis)"
        )
    else:
        records_label = n_records_total
    lines.append(_kv_table([
        ("Confidence", out.get("confidence")),
        ("Evidence Level", out.get("evidence_level")),
        ("Approval Level", out.get("approval_level")),
        ("Records Retrieved", records_label),
        ("Mock Mode", mock_mode_flag),
    ]))
    lines.append(_section("Summary", out.get("summary")))

    # Retrieval provenance — populated by the provider-neutral search
    # subsystem.  Always rendered when present so the user can tell which
    # backend produced these results and whether fallback fired.
    lines.append(_format_patent_retrieval_provenance(
        out.get("retrieval_provenance") or {},
        provider_used=out.get("provider_used") or "",
        mock_mode=out.get("mock_mode_used"),
    ))

    # Always emit a clear "no records" notice — better than silently
    # missing all the analysis sections.
    n_records = int(out.get("deduplicated_patent_record_count") or 0)
    n_pages = int(out.get("retrieved_patent_page_count") or 0)
    if n_records == 0:
        why = (
            " (mock mode active — enable SearXNG for real data)"
            if out.get("mock_mode_used") else ""
        )
        lines.append(
            "\n> ℹ️ **No patent records were retrieved**"
            f"{why}.  Landscape sections below are therefore empty by design, "
            "not omitted.\n"
        )

    # The Patent Intelligence agent populates the LLM-derived landscape
    # fields at the TOP LEVEL of its output (apparent_landscape_summary,
    # apparent_theme_clusters, frequent_assignees_or_applicants,
    # possible_white_space, overlap_risks,
    # recommended_follow_up_searches).  Earlier versions of this
    # formatter only checked the nested ``patent_analysis`` dict for
    # legacy field names (``technology_scope`` / ``crowded_areas`` /
    # ``white_space_opportunities``) that DON'T exist in the real
    # schema — silently dropping the entire landscape from the saved
    # Markdown.  Render the canonical top-level fields here.
    pa = out.get("patent_analysis") or {}
    pa_caveats = pa.get("risks_and_caveats") or [] if isinstance(pa, dict) else []

    landscape_summary = (out.get("apparent_landscape_summary") or "").strip()
    if landscape_summary:
        lines.append(_section("Apparent Landscape Summary", landscape_summary))

    # Apparent theme clusters — list[dict{cluster_name, representative_record_ids, supporting_evidence}]
    clusters = out.get("apparent_theme_clusters") or []
    if clusters:
        lines.append("\n### Apparent Theme Clusters\n")
        for cl in clusters:
            if not isinstance(cl, dict):
                continue
            name = str(cl.get("cluster_name", "") or "(unnamed cluster)").strip()
            ids = cl.get("representative_record_ids") or []
            evid = str(cl.get("supporting_evidence", "") or "").strip()
            ids_str = ", ".join(str(i) for i in ids if i) if ids else ""
            line = f"- **{name}**"
            if ids_str:
                line += f"  _(refs: {ids_str})_"
            lines.append(line)
            if evid:
                lines.append(f"    {evid}")
        lines.append("")

    # Frequent assignees / applicants — list[str]
    assignees = out.get("frequent_assignees_or_applicants") or []
    if assignees:
        lines.append("\n### Frequent Assignees / Applicants (observed)\n")
        for a in assignees:
            if str(a).strip():
                lines.append(f"- {a}")
        lines.append("")

    # Possible white-space opportunities — list[dict{direction, rationale, confidence, caveat}]
    whitespace = out.get("possible_white_space") or []
    if whitespace:
        lines.append("\n### Possible White-Space (tentative)\n")
        for ws in whitespace:
            if isinstance(ws, dict):
                direction = str(ws.get("direction", "") or "").strip()
                conf = str(ws.get("confidence", "") or "").strip()
                caveat = str(ws.get("caveat", "") or "").strip()
                rationale = str(ws.get("rationale", "") or "").strip()
                head = f"- **{direction}**"
                if conf:
                    head += f"  _(confidence: {conf})_"
                lines.append(head)
                if rationale:
                    lines.append(f"    Rationale: {rationale}")
                if caveat:
                    lines.append(f"    Caveat: {caveat}")
            else:
                lines.append(f"- {ws}")
        lines.append("")

    # Overlap / crowded areas — list[str]
    overlap = out.get("overlap_risks") or []
    if overlap:
        lines.append(_bullets(overlap, label="Overlap Risks (crowded areas)"))

    # Recommended follow-up searches — list[str]
    follow_up = out.get("recommended_follow_up_searches") or []
    if follow_up:
        lines.append(_bullets(follow_up, label="Recommended Follow-Up Searches"))

    # Top retrieved patent records — list[dict{title, publication_number, assignees, ...}]
    top_records = out.get("top_patent_records") or []
    if top_records:
        lines.append("\n### Top Retrieved Patent Records (web reconnaissance)\n")
        for i, r in enumerate(top_records[:10], start=1):
            if not isinstance(r, dict):
                continue
            title = str(r.get("title", "") or "(untitled)").strip()
            pub = str(r.get("publication_number", "") or "").strip()
            assignee_list = r.get("assignee_or_applicant") or []
            assignee_str = ", ".join(
                str(a) for a in assignee_list if str(a).strip()
            )[:120]
            url = str(r.get("url", "") or "").strip()
            head = f"- **[R{i}]** {title}"
            if pub:
                head += f"  _({pub})_"
            lines.append(head)
            if assignee_str:
                lines.append(f"    Assignee: {assignee_str}")
            if url:
                lines.append(f"    {url}")
        lines.append("")

    # Fall back to the legacy nested patent_analysis dict for any extra
    # supplemental fields the LLM might have produced (research_implications,
    # grant_writing_implications, commercial_strategy_implications,
    # founder_startup_implications, recommended_next_actions, search_strategy,
    # technology_scope) — these are extras some prompt variants emit.
    if pa:
        if pa.get("technology_scope"):
            lines.append(_section("Technology Scope", pa.get("technology_scope")))
        if pa.get("search_strategy"):
            lines.append(_section("Search Strategy", pa.get("search_strategy")))
        lines.append(_bullets(pa.get("research_implications", []),
                              label="Research Implications"))
        lines.append(_bullets(pa.get("grant_writing_implications", []),
                              label="Grant Writing Implications"))
        lines.append(_bullets(pa.get("commercial_strategy_implications", []),
                              label="Commercial Strategy"))
        lines.append(_bullets(pa.get("founder_startup_implications", []),
                              label="Founder / Startup Implications"))
        lines.append(_bullets(pa.get("recommended_next_actions", []),
                              label="Recommended Next Actions"))

    # If the LLM produced no landscape output AND no records exist,
    # surface that explicitly so the user knows the analysis was empty
    # by design (the no-records callout earlier already covers the
    # mock-mode case).
    has_any_analysis = bool(
        landscape_summary or clusters or assignees
        or whitespace or overlap or follow_up or top_records
    )
    if not has_any_analysis and n_records > 0 and not out.get("mock_mode_used"):
        lines.append(_section(
            "Detail",
            f"Retrieved {n_records} record(s) but patent analysis produced no "
            "structured output (LLM stage failed or returned empty).",
        ))

    # Risks & Caveats from the LLM (these are analytical caveats, distinct
    # from the System & Run Diagnostics below).
    lines.append(_bullets(pa_caveats, label="Risks & Caveats"))

    # Collapse near-duplicate risks and dedup against pa_caveats so we
    # never render the same warning twice.
    risks = _collapse_patent_risks(out.get("risks") or [], pa_caveats)
    lines.append(_bullets(risks, label="System & Run Diagnostics"))

    # Local patent folder diagnostic — shows per-file extraction outcomes
    # so a user with a folder full of "evidence quality 'none'" can
    # actually see WHICH files failed and WHY.
    lines.append(_format_local_patent_diagnostic(
        out.get("local_ingestion_diagnostic") or {},
    ))

    # Local patent evidence — the actual chunks retrieved from the user's
    # folder that were fed to the LLM.  Surfacing these lets the user
    # audit what evidence the analysis was based on (and notice when the
    # LLM ignored them).
    lines.append(_format_local_patent_evidence(
        out.get("local_patent_evidence") or [],
    ))

    # Rigorous claim-centric analysis — Tables A (features), B (relevance),
    # C (gaps).  Implements Sections 9 + 7 of
    # revised_patent_analysis_rigorous.docx.
    lines.append(_format_rigorous_tables(out.get("rigorous_analysis") or {}))

    return "\n".join(p for p in lines if p)


def _format_rigorous_tables(rigor: dict) -> str:
    """Render Tables A/B/C from the rigorous-analysis dict.

    Skips entirely when the dict is empty or abstained.  Always renders
    the topic-decomposition summary first so the reader sees what was
    actually scored against.
    """
    if not isinstance(rigor, dict) or not rigor:
        return ""
    topic = rigor.get("topic_profile") or {}
    profiles = rigor.get("patent_profiles") or []
    relevance = rigor.get("relevance_table") or []
    gaps = rigor.get("gap_table") or []
    abstentions = rigor.get("abstentions") or []

    parts: list[str] = []
    parts.append(
        "\n---\n\n"
        "## Rigorous Claim-Centric Analysis\n\n"
        "_Implements the methodology in "
        "`revised_patent_analysis_rigorous.docx` "
        "(Sections 4–9): structured per-patent feature extraction with "
        "claim-graph evidence anchors, separated Relevance / Confidence / "
        "Action scores, and ranked technology gaps over a deduplicated "
        "patent corpus._\n"
    )

    if abstentions:
        parts.append("\n### Abstentions\n")
        for a in abstentions:
            parts.append(f"- {a}")
        parts.append("")
        if not (profiles or relevance or gaps):
            return "\n".join(parts)

    # Topic decomposition
    if topic:
        parts.append("\n### Decomposed Topic\n")
        parts.append(f"- **Topic:** {topic.get('topic_name', '(unknown)')}")
        for label, key in [
            ("Subtopics", "subtopics"),
            ("Desired capabilities", "desired_capabilities"),
            ("Target metrics", "target_metrics"),
            ("Operating conditions", "operating_conditions"),
            ("Application constraints", "application_constraints"),
            ("Exclusions", "exclusions"),
        ]:
            vals = topic.get(key) or []
            if vals:
                parts.append(f"- **{label}:** {', '.join(str(v) for v in vals)}")
        parts.append("")

    # Table A — key features per patent
    if profiles:
        parts.append("\n### Table A — Key Features (per patent)\n")
        parts.append(
            "| Patent ID | Status | Problem | Core invention | "
            "Top features (claim_support · importance) |"
        )
        parts.append("|---|---|---|---|---|")
        for p in profiles[:20]:
            if not isinstance(p, dict):
                continue
            features = p.get("features") or []
            top = sorted(
                (f for f in features if isinstance(f, dict)),
                key=lambda f: -float(f.get("importance_score") or 0.0),
            )[:3]
            feat_str = "<br>".join(
                f"**{(f.get('normalized_name') or f.get('name') or '')}** "
                f"_({f.get('claim_support', 'unknown')} · "
                f"{float(f.get('importance_score') or 0):.2f})_"
                for f in top
            ) or "_(none extracted)_"
            parts.append(
                f"| {_md_cell(p.get('patent_id'))} "
                f"| {_md_cell(p.get('status'))} "
                f"| {_md_cell(p.get('problem'))[:120]} "
                f"| {_md_cell(p.get('core_invention'))[:140]} "
                f"| {feat_str} |"
            )
        if len(profiles) > 20:
            parts.append(f"\n_… and {len(profiles) - 20} more profiles._")
        parts.append("")

    # Table B — patent-topic relevance
    if relevance:
        parts.append("\n### Table B — Patent–Topic Relevance\n")
        parts.append(
            "| Patent ID | Topic | Rel. | Conf. | Action | Band | "
            "Covered subtopics | Missing subtopics |"
        )
        parts.append("|---|---|---:|---:|---:|---|---|---|")
        relevance_sorted = sorted(
            (r for r in relevance if isinstance(r, dict)),
            key=lambda r: -float(r.get("action_score") or 0.0),
        )
        for r in relevance_sorted[:25]:
            covered = ", ".join(r.get("covered_subtopics") or [])
            missing = ", ".join(r.get("missing_subtopics") or [])
            parts.append(
                f"| {_md_cell(r.get('patent_id'))} "
                f"| {_md_cell(r.get('topic_name'))} "
                f"| {float(r.get('relevance_score') or 0):.0f} "
                f"| {float(r.get('confidence_score') or 0):.2f} "
                f"| {float(r.get('action_score') or 0):.1f} "
                f"| **{r.get('band', 'D')}** "
                f"| {_md_cell(covered)[:120]} "
                f"| {_md_cell(missing)[:120]} |"
            )
        if len(relevance) > 25:
            parts.append(f"\n_… and {len(relevance) - 25} more scorings._")
        parts.append("")

    # Table C — ranked technology gaps
    if gaps:
        parts.append("\n### Table C — Ranked Technology Gaps\n")
        parts.append(
            "| Subtopic | Coverage | Gap type | Score | Level | "
            "Reason | Suggested direction |"
        )
        parts.append("|---|---:|---|---:|---|---|---|")
        for g in gaps[:20]:
            if not isinstance(g, dict):
                continue
            parts.append(
                f"| {_md_cell(g.get('subtopic'))} "
                f"| {float(g.get('coverage_strength') or 0):.2f} "
                f"| `{g.get('gap_type', '?')}` "
                f"| **{float(g.get('gap_score') or 0):.2f}** "
                f"| {g.get('level', '?')} "
                f"| {_md_cell(g.get('reason'))[:160]} "
                f"| {_md_cell(g.get('suggested_direction'))[:140]} |"
            )
        if len(gaps) > 20:
            parts.append(f"\n_… and {len(gaps) - 20} more gaps._")
        parts.append("")

    parts.append(
        "\n_Honesty contract:_ every score above is backed by per-patent "
        "evidence snippets; independent-claim support is weighted highest "
        "(Section 4); claim-supported coverage outranks descriptive "
        "embodiment-only support; mock / synthetic records are NEVER passed "
        "through this pipeline.\n"
    )
    return "\n".join(parts)


def _md_cell(value) -> str:
    """Sanitize a string for inclusion in a Markdown table cell."""
    if value is None:
        return ""
    s = str(value)
    # Collapse newlines + escape pipes so the cell stays in one row.
    return s.replace("\n", " ").replace("|", "\\|").strip()


def _format_local_patent_evidence(refs: list) -> str:
    """Render the retrieved local patent chunks as a Markdown section.

    These are the ``PatentSearchProvider``-independent chunks that the
    Patent Intelligence Agent fed into the LLM analysis prompt.  Showing
    them in the saved draft lets the user verify which excerpts the LLM
    actually saw — important when the LLM produced thin or empty
    landscape analysis from a folder full of real patents.
    """
    if not refs or not isinstance(refs, list):
        return ""
    rendered: list[str] = ["\n### Local Patent Evidence (retrieved chunks)\n"]
    # Show distinct-document count too — a high chunk count concentrated
    # on a few documents is a red flag (the old top_k=6 bug) we want
    # users to notice instantly.
    distinct_docs = len({
        r.get("document_id") or r.get("safe_reference")
        for r in refs if isinstance(r, dict)
    })
    rendered.append(
        f"_{len(refs)} chunk(s) across {distinct_docs} document(s) from "
        "the local patent folder were passed to the LLM as analysis "
        "context._\n"
    )
    # Render up to 30 chunks; the rest are summarised by count.  This
    # keeps the saved Markdown readable while still showing meaningful
    # depth for folders with many documents.
    render_cap = 30
    for i, r in enumerate(refs[:render_cap], start=1):
        if not isinstance(r, dict):
            continue
        safe_ref = r.get("safe_reference") or r.get("document_id") or "(unknown)"
        loc = r.get("location_hint") or ""
        quality = r.get("extraction_quality") or "unknown"
        score = r.get("score") or r.get("retrieval_score")
        score_str = ""
        if isinstance(score, (int, float)):
            try:
                score_str = f", score={float(score):.2f}"
            except (TypeError, ValueError):
                score_str = ""
        excerpt = (r.get("excerpt") or "").strip().replace("\n", " ")
        if len(excerpt) > 600:
            excerpt = excerpt[:600] + "…"
        header = f"**[L{i}] {safe_ref}**"
        if loc:
            header += f" @ {loc}"
        header += f" _(quality={quality}{score_str})_"
        rendered.append(f"- {header}")
        if excerpt:
            rendered.append(f"    > {excerpt}")
    if len(refs) > render_cap:
        rendered.append(
            f"\n_… and {len(refs) - render_cap} more chunk(s) "
            "(truncated for length)._"
        )
    rendered.append("")
    return "\n".join(rendered)


def _format_local_patent_diagnostic(diag: dict) -> str:
    """Render a ``### Local Patent Documents`` section listing the per-file
    extraction outcome of every file in the user's local patent folder.

    Only emitted when there is at least one extraction record.  Empty /
    not-provided -> empty string.
    """
    if not diag or not isinstance(diag, dict):
        return ""
    extractions = diag.get("extractions") or []
    if not extractions and not diag.get("folder_path"):
        return ""

    counters = diag.get("counters") or {}
    n_ok = int(counters.get("extracted_ok", 0) or 0)
    n_empty = int(counters.get("empty_or_no_text", 0) or 0)
    n_failed = int(counters.get("failed", 0) or 0)
    ocr_needed = bool(diag.get("ocr_likely_needed"))
    folder = diag.get("folder_path") or "(unknown)"

    lines = [
        "\n### Local Patent Documents (user-supplied folder)\n",
        f"- **Folder:** `{folder}`",
        f"- **Discovered:** {diag.get('files_discovered', 0)} file(s); "
        f"{diag.get('files_supported', 0)} supported, "
        f"{diag.get('files_skipped', 0)} skipped",
        f"- **Extraction outcome:** "
        f"{n_ok} extracted, {n_empty} returned no text, {n_failed} failed",
        f"- **Chunks indexed:** {diag.get('chunks_indexed', 0)}",
        f"- **Evidence quality hint:** `{diag.get('evidence_quality_hint', 'none')}`",
    ]

    unsupp = diag.get("unsupported_formats") or []
    if unsupp:
        lines.append(f"- **Unsupported formats present:** {', '.join(unsupp)}")

    if ocr_needed:
        lines.append(
            "\n> ⚠️ **Most PDFs returned no text** — they appear to be "
            "scanned/image PDFs.  Enable OCR to recover the content:\n"
            "> ```\n"
            "> set AURA_LOCAL_PDF_OCR=1     # cmd.exe\n"
            "> $env:AURA_LOCAL_PDF_OCR=\"1\"  # PowerShell\n"
            "> ```\n"
            "> OCR requires `pytesseract` + the Tesseract binary on PATH."
        )

    if extractions:
        lines.append("\n**Per-file extraction:**\n")
        for ex in extractions[:20]:
            status = ex.get("status", "?")
            quality = ex.get("quality", "?")
            method = ex.get("method", "?") or "(none)"
            name = ex.get("file_name", "?")
            reason = ex.get("reason", "") or ""
            icon = {
                "extracted": "✅", "no_text": "⚠️", "failed": "❌",
            }.get(status, "•")
            row = (
                f"- {icon} `{name}` — status=**{status}**, "
                f"method={method}, quality={quality}"
            )
            if reason:
                row += f"\n    *Reason:* {reason}"
            lines.append(row)
        if len(extractions) > 20:
            lines.append(
                f"- … and {len(extractions) - 20} more file(s) "
                "(truncated for length)."
            )

    notes = diag.get("notes") or []
    if notes:
        lines.append("\n**Ingestion notes:**\n")
        for n in notes:
            lines.append(f"- {n}")

    lines.append("")
    return "\n".join(lines)


def _format_patent_retrieval_provenance(
    provenance: dict, *, provider_used: str, mock_mode,
) -> str:
    """Render a ``### Retrieval Provenance`` section for patent_intelligence.

    Always emitted — even if the dict is empty we surface the run-level
    provider name + mock flag so users see the source of the data.
    """
    primary = provenance.get("primary_provider") or provider_used or "(unknown)"
    used = provenance.get("provider_used") or provider_used or "(unknown)"
    api_ok = provenance.get("not_api_verified", True)
    exhaustive = provenance.get("non_exhaustive", True)
    fallback_used = bool(provenance.get("fallback_used", False))
    fallback_from = provenance.get("fallback_from")
    warnings_raw = provenance.get("warnings") or []

    pretty_name = {
        "google_web_no_key": "Google-oriented no-key web discovery",
        "duckduckgo_html": "DuckDuckGo HTML no-key web discovery",
        "searxng": "SearXNG meta-search",
        "mock": "MOCK provider (synthetic results)",
    }
    primary_label = pretty_name.get(primary, primary)
    used_label = pretty_name.get(used, used)

    lines = ["\n### Retrieval Provenance\n"]
    lines.append(f"- **Primary provider configured:** {primary_label}")
    if used != primary or fallback_used:
        lines.append(f"- **Provider that produced results:** {used_label}")
    else:
        lines.append(f"- **Provider used:** {used_label}")
    lines.append(
        f"- **API verification:** {'No' if api_ok else 'Yes'} — "
        "results are NOT API-verified patent records."
    )
    lines.append(
        f"- **Coverage:** {'Non-exhaustive' if exhaustive else 'Bounded'} "
        "(Stage 1 reconnaissance, not freedom-to-operate)."
    )
    lines.append(
        f"- **Fallback used:** {'Yes' if fallback_used else 'No'}"
        + (f" (fell back from {pretty_name.get(fallback_from or '', fallback_from)})"
           if fallback_used and fallback_from else "")
    )
    if mock_mode:
        lines.append(
            "- **Mock mode:** Yes — every result on this page is SYNTHETIC."
        )

    # Render structured warnings (provider-side) so users can see the
    # actual upstream failure modes without spelunking JSON.
    structured_warnings = []
    for w in warnings_raw:
        if isinstance(w, dict):
            code = str(w.get("code", "")).strip()
            msg = str(w.get("message", "")).strip()
            if msg:
                structured_warnings.append(f"  - `{code}`: {msg}" if code else f"  - {msg}")
    if structured_warnings:
        lines.append("\n**Provider warnings:**")
        lines.extend(structured_warnings)

    lines.append("")
    return "\n".join(lines)


# Mock-mode / SearXNG status messages are emitted in multiple wordings by
# the runtime; collapse them to a single canonical line.
#
# The needles are deliberately SPECIFIC ("mock fallback" / "synthetic" /
# "mock mode" / "mock search provider") rather than bare "mock" so that
# legitimate error messages mentioning the constant name ``PROVIDER_MOCK``
# or a path like ``mock_provider.py`` are NOT collapsed into a misleading
# "Mock fallback used" line.
_PATENT_RISK_COLLAPSE_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("mock fallback", "mock search provider", "synthetic mock",
         "mock mode active"),
        "Mock fallback used — results are SYNTHETIC and do not represent "
        "real patent reconnaissance.",
    ),
    (
        ("searxng not enabled", "searxng_enabled=0", "searxng unavailable",
         "falling back to mock"),
        "SearXNG not enabled — no real search provider available; "
        "set SEARXNG_ENABLED=1 for real data.",
    ),
)


def _collapse_patent_risks(
    risks: list, exclude_against: list,
) -> list[str]:
    """Filter + dedup patent risks for the saved Markdown.

    Three operations:
      1. Drop any risk whose lowercased text already appears (substring
         match) in ``exclude_against`` — usually ``risks_and_caveats`` —
         so the same caveat doesn't render twice.
      2. Collapse near-duplicate runtime status messages (mock fallback,
         SearXNG-disabled, etc.) to a single canonical line each.
      3. Drop internal markers via the existing :func:`_is_internal_marker`
         filter.
    """
    if not risks:
        return []
    exclude_lower = [
        str(x).strip().lower() for x in (exclude_against or [])
        if isinstance(x, (str, int, float)) and str(x).strip()
    ]
    collapsed_seen: set[int] = set()
    seen_lines: set[str] = set()
    out: list[str] = []
    for item in risks:
        if not isinstance(item, (str, int, float)):
            continue
        text = str(item).strip()
        if not text or _is_internal_marker(text):
            continue
        lower = text.lower()
        # Drop if a near-substring already appears in caveats.
        if any(
            lower in ex or ex in lower
            for ex in exclude_lower
            if len(ex) >= 20 and len(lower) >= 20
        ):
            continue
        # Collapse runtime-status duplicates — but only when a SPECIFIC
        # needle matches.  Generic substrings like bare "mock" used to
        # rewrite legitimate error messages (e.g. ``cannot import name
        # 'PROVIDER_MOCK'``) into a misleading mock-fallback canonical.
        matched = False
        for idx, (needles, canonical) in enumerate(_PATENT_RISK_COLLAPSE_RULES):
            if any(n in lower for n in needles):
                if idx in collapsed_seen:
                    matched = True
                    break
                collapsed_seen.add(idx)
                if canonical.lower() not in seen_lines:
                    out.append(canonical)
                    seen_lines.add(canonical.lower())
                matched = True
                break
        if matched:
            continue
        if lower in seen_lines:
            continue
        seen_lines.add(lower)
        out.append(text)
    return out


def format_china_grant_architect_md(output: dict, user_input: str = "") -> str:
    """Render the China Grant Architect output via the A-P renderer that
    ``run_china`` itself uses.  Delegates to
    ``agents.grant_architect._china_render_markdown`` so a single
    auditable code path produces both the standalone
    ``reports/china_grants/*.md`` file AND the draft_writer copy.

    Also appends a References section so the reader can see which
    Research Scout papers backed the draft.
    """
    from core.schemas import ChinaGrantArchitectOutput
    from agents.grant_architect import _china_render_markdown
    try:
        rr = ChinaGrantArchitectOutput.model_validate(output or {})
    except Exception:
        # Fall back to a minimal dump so the user still sees something.
        return (
            "# China Grant Architect Draft\n\n"
            "_(Markdown rendering failed: payload did not validate "
            "against ChinaGrantArchitectOutput. Raw fields below.)_\n\n"
            "```json\n" + json.dumps(output or {}, indent=2, default=str) + "\n```\n"
        )
    md = _china_render_markdown(rr)

    # Prepend the user prompt so the file is self-contained.
    header_lines: list[str] = []
    if user_input:
        header_lines.append(f"> **Prompt:** {user_input.strip()}\n")
    header_lines.append("")

    # Append References section using Scout's references_used if present
    # on the output.  The China renderer doesn't currently emit one
    # (it lives on the legacy GrantArchitectOutput), so we attach
    # whatever the output carries plus a placeholder explaining how to
    # populate it.
    refs = []
    raw_refs = (output or {}).get("references_used") or []
    if isinstance(raw_refs, list):
        refs = [str(r).strip() for r in raw_refs
                if isinstance(r, str) and r.strip()]

    # Surface local-document provenance in its own block so the user
    # sees which user-provided files were considered.  Drawn from the
    # Scout output nested under ``output['scout_provenance']`` when
    # the architect chooses to forward it; otherwise empty.
    local_block: list[str] = []
    local_lit = (output or {}).get("local_literature_evidence_used") or []
    if isinstance(local_lit, list) and local_lit:
        local_block.append("\n## Local-document evidence used\n")
        for i, r in enumerate(local_lit[:12], start=1):
            if not isinstance(r, dict):
                continue
            doc = r.get("document_title") or r.get("document_id") or "(local doc)"
            excerpt = (r.get("excerpt") or "")[:200].replace("\n", " ")
            local_block.append(
                f"- **[LOCAL:{r.get('document_id','?')}]** {doc} — "
                f"_{excerpt}…_"
            )

    refs_block = list(local_block) + ["\n## References\n"]
    if refs:
        refs_block.extend(refs)
    else:
        # Differentiate the two distinct failure modes so the user
        # knows where to look:
        #   (a) Scout never ran (orchestrator routing missed it)
        #   (b) Scout ran but returned no top_papers (search engine
        #       outage, off-topic query, mock provider, etc.)
        # We can tell which one by checking whether ``confirmed_facts``
        # or other Scout-derived fields are populated — if they are,
        # Scout ran; if not, it didn't.
        scout_signals = [
            (output or {}).get("confirmed_facts"),
            (output or {}).get("missing_information"),
            (output or {}).get("sections"),
        ]
        scout_ran = any(bool(s) for s in scout_signals)
        if scout_ran:
            refs_block.append(
                "_Research Scout ran but returned **zero `top_papers`** "
                "for this query. All [N] / [S:...] citations in the body "
                "are therefore unresolved._\n\n"
                "Likely causes:\n"
                "1. **Search provider failure** — SearXNG / DuckDuckGo "
                "returned no results or was unreachable. Check "
                "`reports/research_briefs/` or run `python "
                "scripts/verify_searxng.py` to diagnose.\n"
                "2. **Query too narrow** — re-run with a broader topic "
                "phrasing, or paste a References block directly in the "
                "user prompt.\n"
                "3. **Mock provider in use** — confirm "
                "`SEARXNG_ENABLED=1` and that no mock fallback "
                "silently activated.\n"
            )
        else:
            refs_block.append(
                "_No references were supplied by Research Scout for "
                "this run. All [N] / [S:...] citations in the body are "
                "therefore unresolved._\n\n"
                "To populate this section:\n"
                "1. The orchestrator should auto-prepend "
                "`research_scout` before any grant agent — confirm the "
                "Strategic Governor selected it (check session footer "
                "or `data/governor_decisions/`).\n"
                "2. Or supply a References block directly in the user "
                "prompt — the architect will preserve it.\n"
            )
    return "\n".join(header_lines) + md + "\n" + "\n".join(refs_block)


_FORMATTERS = {
    "grant_architect":                 format_grant_architect_md,
    "china_grant_architect":           format_china_grant_architect_md,
    "teaching_mentor":                 format_teaching_mentor_md,
    "lab_data_analyst":                format_lab_data_analyst_md,
    "influence_public_communication":  format_influence_md,
    "collaboration_operator":          format_collaboration_operator_md,
    "founder_innovation":              format_founder_innovation_md,
    "patent_intelligence":             format_patent_intelligence_md,
}


# ---------------------------------------------------------------------------
# Save mechanism
# ---------------------------------------------------------------------------

def _timestamped(name: str) -> str:
    # Phase 2 (goal F): second-resolution names overwrote each other when
    # two drafts of the same kind were written in the same second.  Append
    # microseconds + a short UUID so rapid-succession writes never collide.
    from core.path_safety import unique_filename_stamp
    return f"{name}_{unique_filename_stamp()}"


def _append_footer(body: str, result: dict) -> str:
    """Append a small footer with verifier verdict + governor rationale."""
    parts = ["\n---\n", "## Session Footer\n"]
    gov = (result.get("strategic_governor") or {}).get("rationale", "")
    if gov:
        parts.append(f"**Governor rationale:** {gov}\n")
    ver = result.get("scientific_verifier") or {}
    if ver:
        parts.append(
            f"\n**Scientific Verifier:** assessment=`{ver.get('overall_assessment')}` "
            f"route=`{ver.get('route')}` recommendation=`{ver.get('final_recommendation')}`\n"
        )
    # Phase 3 (MCP): when external MCP evidence informed this run, record a
    # compact provenance note so the persisted draft is honest about it.
    ext = result.get("external_mcp_evidence") or {}
    if isinstance(ext, dict) and ext.get("used"):
        parts.append(
            "\n**External MCP evidence (UNVERIFIED, supplementary):** "
            f"providers={ext.get('providers')} records={ext.get('records')} "
            f"mock_records={ext.get('mock_records')}. "
            "Treated as secondary context only; reviewed by the Scientific "
            "Verifier; not primary literature.\n"
        )
    parts.append(
        f"\n*Generated by AURA on {datetime.now().isoformat(timespec='seconds')}.*\n"
    )
    return body.rstrip() + "\n" + "".join(parts)


_UNVERIFIED_BANNER = (
    "> # ⚠️ UNVERIFIED DRAFT — HUMAN REVIEW REQUIRED\n"
    ">\n"
    "> This document was produced by AURA but the Scientific Verifier did NOT\n"
    "> route the session to `approve` or `revise`.  Treat every claim, number,\n"
    "> citation, and recommendation as **unverified**.  Do NOT submit, publish,\n"
    "> send, or act on this document without independent human review.\n"
    ">\n"
    "> Verifier route: `{route}`   Assessment: `{assessment}`   "
    "Recommendation: `{recommendation}`\n"
)


def save_unverified_drafts(
    result: dict,
    user_input: str = "",
    report_dir: Path | None = None,
) -> list[Path]:
    """Persist specialist drafts to ``pending_review/`` with a loud banner.

    This is the ``human_review`` / ``retrieve_more_evidence`` path: the
    Scientific Verifier did not produce an affirmative route, so the
    standard ``reports/`` persistence is correctly blocked.  But the user
    still wants the draft.  We write it under a clearly-segregated
    subfolder with a prominent UNVERIFIED banner so it cannot be
    mistaken for an approved artefact.

    The ``SAFE_PERSIST_ROUTES`` contract is not relaxed.
    """
    if not isinstance(result, dict):
        return []
    specialists = result.get("specialists") or {}
    if not isinstance(specialists, dict) or not specialists:
        return []

    base = Path(report_dir) if report_dir is not None else config.REPORT_DIR
    pending_dir = base / "pending_review"
    pending_dir.mkdir(parents=True, exist_ok=True)

    ver = result.get("scientific_verifier") or {}
    banner = _UNVERIFIED_BANNER.format(
        route=ver.get("route") or "(missing)",
        assessment=ver.get("overall_assessment") or "(missing)",
        recommendation=ver.get("final_recommendation") or "(missing)",
    )

    written: list[Path] = []
    draft_paths: dict[str, str] = {}

    for name, output in specialists.items():
        if name not in DRAFT_KINDS:
            continue
        if not isinstance(output, dict) or not output:
            continue
        if output.get("failed_stage") == "not_implemented":
            continue
        formatter = _FORMATTERS.get(name)
        if formatter is None:
            continue
        try:
            md = formatter(output, user_input=user_input)
        except Exception as exc:
            md = (
                f"# {name} Draft\n\n(Markdown rendering failed: {exc})\n\n"
                f"```json\n{json.dumps(output, indent=2, default=str)}\n```\n"
            )
        md = banner + "\n" + md
        md = _append_footer(md, result)
        filename = _timestamped(name) + "_UNVERIFIED.md"
        path = pending_dir / filename
        try:
            path.write_text(md, encoding="utf-8")
            written.append(path)
            draft_paths[name] = str(path)
        except Exception:
            continue

    if draft_paths:
        result["unverified_draft_paths"] = draft_paths

    return written


def save_specialist_drafts(
    result: dict,
    user_input: str = "",
    report_dir: Path | None = None,
) -> list[Path]:
    """Persist every high-stakes specialist output to a timestamped Markdown file.

    Returns the list of paths written. Also populates result["draft_paths"]
    (mapping agent_name -> path string) so the formatter / main.py can show
    the user where the file landed.
    """
    if not isinstance(result, dict):
        return []
    specialists = result.get("specialists") or {}
    if not isinstance(specialists, dict) or not specialists:
        return []

    report_dir = Path(report_dir) if report_dir is not None else config.REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    draft_paths: dict[str, str] = {}

    for name, output in specialists.items():
        if name not in DRAFT_KINDS:
            continue
        if not isinstance(output, dict) or not output:
            continue
        # Skip the "not_implemented" placeholder records
        if output.get("failed_stage") == "not_implemented":
            continue
        formatter = _FORMATTERS.get(name)
        if formatter is None:
            continue

        try:
            md = formatter(output, user_input=user_input)
        except Exception as exc:
            md = f"# {name} Draft\n\n(Markdown rendering failed: {exc})\n\n```json\n{json.dumps(output, indent=2, default=str)}\n```\n"

        md = _append_footer(md, result)
        filename = _timestamped(name) + ".md"
        path = report_dir / filename
        try:
            path.write_text(md, encoding="utf-8")
            written.append(path)
            draft_paths[name] = str(path)
        except Exception:
            continue

    if draft_paths:
        result["draft_paths"] = draft_paths

    return written
