from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

_ASSESSMENT_COLORS = {
    "weak": "red",
    "acceptable": "yellow",
    "strong": "green",
    "incomplete": "bold red",
}

_ROUTE_COLORS = {
    "approve": "green",
    "revise": "yellow",
    "retrieve_more_evidence": "cyan",
    "human_review": "bold red",
    "reject": "red",
}

_SEVERITY_ICONS = {
    "critical": "[bold red]CRIT[/bold red]",
    "high":     "[red]HIGH[/red]",
    "medium":   "[yellow]MED [/yellow]",
    "low":      "[dim]LOW [/dim]",
}

_SUPPORT_ICONS = {
    "supported":           "[green]OK[/green]",
    "partially_supported": "[yellow]~[/yellow]",
    "unsupported":         "[red]NO[/red]",
    "contradicted":        "[bold red]!!![/bold red]",
    "unverifiable":        "[dim]?[/dim]",
}


def _render_action(action) -> str:
    """Defect 17: render a recommended_action item as readable text.

    Recommended actions arrive as either strings (legacy) or structured
    dicts (with ``description``, ``action_class``, ``policy``, etc.).
    Printing the raw ``dict`` is unreadable; this helper produces a
    one-line, console-safe rendering.
    """
    if isinstance(action, str):
        return action
    if not isinstance(action, dict):
        return str(action)
    desc = str(action.get("description") or action.get("text") or "").strip()
    if not desc:
        # Fall back to anything useful so we never print "{}".
        desc = str(action.get("title") or action.get("name") or "(no description)")
    tags: list[str] = []
    for key in ("action_class", "policy", "priority", "severity"):
        val = action.get(key)
        if val:
            tags.append(f"{key}={val}")
    return desc + (f"  [dim]({', '.join(tags)})[/dim]" if tags else "")


def print_title() -> None:
    """Print the AURA title, reflecting the currently selected model."""
    import config
    current_model = config.get_model_name()
    if ":" in current_model:
        subtitle = f"Powered by {current_model} via Ollama"
    else:
        subtitle = f"Using {current_model} (remote)"
    console.print(Panel.fit(
        f"[bold cyan]AURA Core MVP[/bold cyan]\n[dim]{subtitle}[/dim]",
        border_style="cyan",
    ))


_AUTONOMY_COLORS = {
    "L0": "dim", "L1": "dim", "L2": "cyan",
    "L3": "green", "L4": "yellow", "L5": "bold red",
}

_STD_COLORS = {
    "yes": "green", "maybe": "yellow", "no": "red",
    "low": "green", "medium": "yellow", "high": "red", "critical": "bold red",
    "urgent": "bold red",
}


def print_governor(decision: dict) -> None:
    task = decision.get("task_type", "unknown")
    priority = decision.get("priority", "medium")
    risk = decision.get("risk_level", "low")
    autonomy = decision.get("autonomy_level", "L2")
    ev_req = decision.get("evidence_requirement", "medium")
    should = decision.get("should_this_be_done", "yes")
    ma_score = decision.get("mission_alignment_score", 0.0)
    sv_score = decision.get("strategic_value_score", 0.0)

    autonomy_color = _AUTONOMY_COLORS.get(autonomy, "white")
    risk_color = _STD_COLORS.get(risk, "white")
    should_color = _STD_COLORS.get(should, "white")

    console.print(Panel(
        f"[bold]Task:[/bold] {task}   "
        f"[bold]Priority:[/bold] [{_STD_COLORS.get(priority,'white')}]{priority}[/{_STD_COLORS.get(priority,'white')}]   "
        f"[bold]Risk:[/bold] [{risk_color}]{risk}[/{risk_color}]\n"
        f"[bold]Autonomy:[/bold] [{autonomy_color}]{autonomy}[/{autonomy_color}]   "
        f"[bold]Evidence:[/bold] {ev_req}   "
        f"[bold]Do this:[/bold] [{should_color}]{should}[/{should_color}]\n"
        f"[bold]Mission:[/bold] {ma_score:.2f}   [bold]Value:[/bold] {sv_score:.2f}   "
        f"[bold]Agents:[/bold] {', '.join(decision.get('selected_agents', []))}\n"
        f"[bold]Rationale:[/bold] {decision.get('rationale', '')}",
        title="[bold yellow]Executive Governor Decision[/bold yellow]",
        border_style="yellow",
    ))

    if decision.get("requires_approval"):
        console.print(f"[bold red]APPROVAL REQUIRED:[/bold red] {decision.get('approval_reason', '')}")

    # Workflow sequence
    workflow = decision.get("workflow_sequence") or []
    if workflow:
        console.print("[bold yellow]Workflow:[/bold yellow]")
        for i, step in enumerate(workflow, 1):
            if isinstance(step, dict):
                agent, purpose, mode = step.get("agent",""), step.get("purpose",""), step.get("mode","")
            else:
                agent = getattr(step, "agent", "")
                purpose = getattr(step, "purpose", "")
                mode = getattr(step, "mode", "")
            mode_str = f" [{mode}]" if mode else ""
            console.print(f"  {i}. [cyan]{agent}[/cyan]{mode_str} — {purpose}")

    # Task decomposition
    decomp = decision.get("task_decomposition") or []
    if decomp:
        console.print("[bold yellow]Task Decomposition:[/bold yellow]")
        for i, step in enumerate(decomp, 1):
            console.print(f"  {i}. {step}")

    # Blocked actions
    blocked = decision.get("blocked_actions") or []
    if blocked:
        console.print("[bold red]Blocked Actions:[/bold red]")
        for b in blocked:
            console.print(f"  [red]✗[/red] {b}")

    # Self-evolution policy
    evo_policy = decision.get("self_evolution_policy") or {}
    if isinstance(evo_policy, dict):
        run_evo = evo_policy.get("run", True)
        evo_reason = evo_policy.get("reason", "")
    else:
        run_evo = getattr(evo_policy, "run", True)
        evo_reason = getattr(evo_policy, "reason", "")
    if not run_evo:
        console.print(f"[dim]Self-evolution skipped: {evo_reason}[/dim]")


def print_research_scout(output: dict) -> None:
    mode = output.get("mode", "ideation")
    console.print(Panel(
        f"[bold]Mode:[/bold] {mode}\n"
        f"[bold]Confidence:[/bold] {output.get('confidence', 'medium')}\n"
        f"[bold]Literature Scan Used:[/bold] {output.get('literature_scan_used', False)}\n\n"
        f"[bold]Summary:[/bold]\n{output.get('summary', '')}",
        title=f"[bold green]Research Scout — {mode.title()} Mode[/bold green]",
        border_style="green",
    ))

    findings = output.get("findings", [])
    if findings:
        console.print("[bold green]Findings:[/bold green]")
        for i, f in enumerate(findings, 1):
            console.print(f"  {i}. {f}")

    top_papers = output.get("top_papers", [])
    if top_papers:
        console.print("\n[bold green]Top Papers:[/bold green]")
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table.add_column("Title", max_width=48)
        table.add_column("Score", justify="right", min_width=5)
        table.add_column("Action", min_width=14)
        table.add_column("Source", min_width=8)
        for p in top_papers[:8]:
            table.add_row(
                p.get("title", "")[:48],
                f"{p.get('total_score', 0.0):.2f}",
                p.get("recommended_action", ""),
                p.get("source", ""),
            )
        console.print(table)

    gap = output.get("research_gap_candidate", "")
    if gap:
        console.print(Panel(
            gap,
            title="[bold magenta]Research Gap Candidate[/bold magenta]",
            border_style="magenta",
        ))

    actions = output.get("recommended_actions", [])
    if actions:
        console.print("[bold green]Recommended Actions:[/bold green]")
        for a in actions:
            console.print(f"  -> {_render_action(a)}")

    report_paths = output.get("report_paths", [])
    if report_paths:
        console.print("[bold]Report Paths:[/bold]")
        for p in report_paths:
            console.print(f"  {p}")


def print_verification(report: dict) -> None:
    # Defensive coercion: the verifier schema declares these as str, but
    # malformed LLM output (or a downstream combiner) has been known to
    # leak a dict here.  Coerce to str so the rich Panel / .upper() /
    # _ASSESSMENT_COLORS.get() never crash on an unhashable type.
    def _as_str(v, default: str = "") -> str:
        if isinstance(v, str):
            return v
        if v is None:
            return default
        if isinstance(v, (int, float, bool)):
            return str(v)
        # dict / list / etc. — render compactly so the user sees the shape
        # but the formatter can keep going.
        try:
            import json
            return json.dumps(v, default=str)[:200] or default
        except Exception:
            return default

    assessment = _as_str(
        report.get("overall_assessment"), "incomplete",
    )
    route = _as_str(report.get("route"), "revise")
    final_rec = _as_str(report.get("final_recommendation"))
    color = _ASSESSMENT_COLORS.get(assessment, "white")
    route_color = _ROUTE_COLORS.get(route, "white")

    audit_line = ""
    if report.get("verified_at"):
        model = report.get("model_used", "?")
        trunc = " [truncated]" if report.get("truncated") else ""
        sources = ", ".join(report.get("evidence_sources_checked", [])) or "none"
        audit_line = f"\n[dim]Verified: {report['verified_at'][:19]}Z | Model: {model}{trunc} | Sources: {sources}[/dim]"

    console.print(Panel(
        f"[bold]Assessment:[/bold] [{color}]{assessment.upper()}[/{color}]   "
        f"[bold]Route:[/bold] [{route_color}]{route}[/{route_color}]\n\n"
        f"[bold]Recommendation:[/bold] {final_rec}"
        f"{audit_line}",
        title="[bold blue]Scientific Verification[/bold blue]",
        border_style="blue",
    ))

    # Claim-level checks table (only show if present)
    claim_checks = report.get("claim_checks", [])
    if claim_checks:
        console.print("[bold blue]Claim Checks:[/bold blue]")
        table = Table(box=box.MINIMAL_DOUBLE_HEAD, show_header=True, header_style="bold blue")
        table.add_column("Sev", min_width=4, no_wrap=True)
        table.add_column("Sup", min_width=3, no_wrap=True)
        table.add_column("Type", min_width=9)
        table.add_column("Claim", max_width=50)
        table.add_column("Conf", justify="right", min_width=4)
        for c in claim_checks[:10]:
            sev = c.get("severity", "low")
            sup = c.get("support_status", "unverifiable")
            table.add_row(
                _SEVERITY_ICONS.get(sev, sev),
                _SUPPORT_ICONS.get(sup, sup),
                c.get("claim_type", ""),
                c.get("claim", "")[:50],
                f"{c.get('confidence', 0.5):.2f}",
            )
        console.print(table)

        # Show corrections for high/critical claims
        high_checks = [c for c in claim_checks if c.get("severity") in ("high", "critical") and c.get("correction")]
        if high_checks:
            console.print("[bold red]Critical/High-Severity Corrections:[/bold red]")
            for c in high_checks[:5]:
                console.print(f"  [{c.get('severity','?').upper()}] {c.get('claim','')[:60]}")
                console.print(f"         -> {c.get('correction', '')[:120]}")

    # Risk panels (only show non-empty ones)
    _print_risk_list("Methodology Risks",     report.get("methodology_risks", []),    "yellow")
    _print_risk_list("Novelty Risks",          report.get("novelty_risks", []),         "yellow")
    _print_risk_list("Citation Risks",         report.get("citation_risks", []),        "red")
    _print_risk_list("Grant Risks",            report.get("grant_risks", []),           "yellow")
    _print_risk_list("Action Governance Risks",report.get("action_governance_risks",[]),"bold red")

    # Human approvals required
    approvals = report.get("required_human_approvals", [])
    if approvals:
        console.print("[bold red]REQUIRES HUMAN APPROVAL:[/bold red]")
        for a in approvals:
            console.print(f"  [red]![/red] {a}")

    # Revision instructions
    revisions = report.get("revision_instructions", [])
    if revisions:
        console.print("[bold yellow]Revision Instructions:[/bold yellow]")
        for i, r in enumerate(revisions, 1):
            console.print(f"  {i}. {r}")

    # Route banner for human_review and reject
    if route == "human_review":
        console.print(Panel(
            "[bold red]Human review required before any further use of these outputs.[/bold red]",
            border_style="red",
        ))
    elif route == "reject":
        console.print(Panel(
            "[bold red]Outputs REJECTED by verifier — do not use without major revision.[/bold red]",
            border_style="red",
        ))


def _print_risk_list(label: str, items: list, color: str = "yellow") -> None:
    if not items:
        return
    console.print(f"[bold {color}]{label}:[/bold {color}]")
    for item in items[:6]:
        console.print(f"  [{color}]*[/{color}] {item}")


_PRIORITY_COLORS = {
    "high":   "red",
    "medium": "yellow",
    "low":    "dim",
}

_SAVE_DECISION_ICONS = {
    "save_now":     "[green]SAVE[/green]",
    "needs_review": "[yellow]REV [/yellow]",
    "discard":      "[dim]DISC[/dim]",
}


def print_self_evolution(output: dict) -> None:
    assessment = output.get("session_assessment", "")
    failure_modes = output.get("failure_modes", [])

    header_lines = []
    if assessment:
        header_lines.append(f"[bold]Session Assessment:[/bold] {assessment}")
    if failure_modes:
        labels = "  ".join(f"[red]{m}[/red]" for m in failure_modes)
        header_lines.append(f"[bold]Failure Modes:[/bold] {labels}")

    console.print(Panel(
        "\n".join(header_lines) if header_lines else "[dim]No session assessment.[/dim]",
        title="[bold dim]Self-Evolution — Session Assessment[/bold dim]",
        border_style="dim",
    ))

    # Structured lesson details table
    lesson_details = output.get("lesson_details", [])
    if lesson_details:
        console.print("[bold dim]Lesson Details:[/bold dim]")
        table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
        table.add_column("Decision", min_width=4, no_wrap=True)
        table.add_column("Conf", justify="right", min_width=4)
        table.add_column("Scope", min_width=7)
        table.add_column("Lesson", max_width=60)
        for ld in lesson_details[:8]:
            if not isinstance(ld, dict):
                continue
            dec = ld.get("save_decision", "needs_review")
            table.add_row(
                _SAVE_DECISION_ICONS.get(dec, dec),
                f"{float(ld.get('confidence', 0.5)):.2f}",
                ld.get("scope", "session"),
                ld.get("lesson", "")[:60],
            )
        console.print(table)

    # Backward-compat flat lessons (shown only if no lesson_details)
    if not lesson_details:
        lessons = output.get("reusable_lessons", [])
        if lessons:
            console.print("[bold dim]Reusable Lessons:[/bold dim]")
            for l in lessons:
                console.print(f"  - {l}")

    # Workflow improvements
    improvements = output.get("workflow_update_proposals", []) or output.get("workflow_improvements", [])
    if improvements:
        console.print("[bold dim]Workflow Improvements:[/bold dim]")
        for i in improvements[:4]:
            console.print(f"  -> {i}")

    # Next experiments
    next_exps = output.get("next_experiments", [])
    if next_exps:
        console.print("[bold dim]Next Experiments:[/bold dim]")
        for exp in next_exps[:3]:
            if not isinstance(exp, dict):
                continue
            pri = exp.get("priority", "medium")
            color = _PRIORITY_COLORS.get(pri, "white")
            console.print(
                f"  [{color}][{pri.upper()}][/{color}] [{exp.get('agent_mode', '?')}] "
                f"{exp.get('description', '')[:80]}"
            )

    # Profile update proposals (draft — conspicuously marked)
    profile_props = output.get("profile_update_proposals", [])
    if profile_props:
        console.print("[bold yellow]Profile Update Proposals (DRAFT — not applied):[/bold yellow]")
        for p in profile_props[:3]:
            if not isinstance(p, dict):
                continue
            console.print(
                f"  ~ [{p.get('field_path', '?')}]  {p.get('proposed_value', '')[:80]}"
                f"  | {p.get('rationale', '')[:60]}"
            )

    if output.get("human_approval_required"):
        console.print(Panel(
            "[bold red]Evolution engine requires human approval before applying any updates.[/bold red]",
            border_style="red",
        ))


_GRANT_READINESS_COLORS = {
    "idea_only":            "dim",
    "concept_note_ready":   "cyan",
    "needs_evidence":       "yellow",
    "proposal_draft_ready": "green",
}

_LEARNER_LEVEL_COLORS = {
    "general_public": "cyan",
    "undergraduate":  "green",
    "graduate":       "yellow",
    "researcher":     "bold magenta",
    "mixed":          "white",
}


def print_grant_architect(output: dict) -> None:
    """Render a Grant Architect output panel + sections."""
    if not output:
        return
    readiness = output.get("grant_readiness", "idea_only")
    readiness_color = _GRANT_READINESS_COLORS.get(readiness, "white")
    confidence = output.get("confidence", "medium")
    evidence = output.get("evidence_level", "weak")

    header = (
        f"[bold]Possible title:[/bold] {output.get('possible_title', '(not set)')}\n"
        f"[bold]Grant readiness:[/bold] [{readiness_color}]{readiness}[/{readiness_color}]\n"
        f"[bold]Confidence:[/bold] {confidence}    [bold]Evidence level:[/bold] {evidence}\n\n"
        f"[bold]Summary:[/bold]\n{output.get('summary', '')}"
    )
    console.print(Panel(
        header,
        title="[bold yellow]Grant Architect[/bold yellow]",
        border_style="yellow",
    ))

    problem = output.get("problem_statement", "")
    if problem:
        console.print(Panel(
            problem,
            title="[bold]Problem Statement[/bold]",
            border_style="dim yellow",
        ))

    hypothesis = output.get("central_hypothesis", "")
    if hypothesis:
        console.print(Panel(
            hypothesis,
            title="[bold]Central Hypothesis[/bold]",
            border_style="dim yellow",
        ))

    objectives = output.get("objectives", [])
    if objectives:
        console.print("[bold yellow]Objectives:[/bold yellow]")
        for i, obj in enumerate(objectives, 1):
            console.print(f"  {i}. {obj}")

    work_packages = output.get("work_packages", [])
    if work_packages:
        console.print("\n[bold yellow]Work Packages:[/bold yellow]")
        for wp in work_packages:
            console.print(f"  - {wp}")

    methodology = output.get("methodology_overview", "")
    if methodology:
        console.print(f"\n[bold yellow]Methodology Overview:[/bold yellow] {methodology}")

    outcomes = output.get("expected_outcomes", [])
    if outcomes:
        console.print("\n[bold yellow]Expected Outcomes:[/bold yellow]")
        for o in outcomes:
            console.print(f"  - {o}")

    attacks = output.get("reviewer_attack_points", [])
    if attacks:
        console.print("\n[bold red]Reviewer Attack Points:[/bold red]")
        for a in attacks:
            console.print(f"  ! {a}")

    needed = output.get("evidence_needed_before_submission", [])
    if needed:
        console.print("\n[bold magenta]Evidence Needed Before Submission:[/bold magenta]")
        for e in needed:
            console.print(f"  ? {e}")

    mitigation = output.get("risk_mitigation", [])
    if mitigation:
        console.print("\n[bold]Risk Mitigation:[/bold]")
        for m in mitigation:
            console.print(f"  - {m}")

    collaborators = output.get("collaborator_needs", [])
    if collaborators:
        console.print("\n[bold cyan]Collaborator Needs:[/bold cyan]")
        for c in collaborators:
            console.print(f"  + {c}")

    risks = output.get("risks", [])
    if risks:
        console.print("\n[bold red]Risks:[/bold red]")
        for r in risks:
            console.print(f"  - {r}")


def print_teaching_mentor(output: dict) -> None:
    """Render a Teaching Mentor output panel + sections."""
    if not output:
        return
    learner_level = output.get("learner_level", "undergraduate")
    level_color = _LEARNER_LEVEL_COLORS.get(learner_level, "white")
    confidence = output.get("confidence", "medium")
    evidence = output.get("evidence_level", "weak")

    header = (
        f"[bold]Target audience:[/bold] {output.get('target_audience', '(not set)')}\n"
        f"[bold]Learner level:[/bold] [{level_color}]{learner_level}[/{level_color}]\n"
        f"[bold]Confidence:[/bold] {confidence}    [bold]Evidence level:[/bold] {evidence}\n\n"
        f"[bold]Summary:[/bold]\n{output.get('summary', '')}"
    )
    console.print(Panel(
        header,
        title="[bold blue]Teaching Mentor[/bold blue]",
        border_style="blue",
    ))

    outcomes = output.get("learning_outcomes", [])
    if outcomes:
        console.print("[bold blue]Learning Outcomes:[/bold blue]")
        for i, o in enumerate(outcomes, 1):
            console.print(f"  {i}. {o}")

    explanation = output.get("conceptual_explanation", "")
    if explanation:
        console.print(Panel(
            explanation,
            title="[bold blue]Conceptual Explanation[/bold blue]",
            border_style="dim blue",
        ))

    socratic = output.get("socratic_questions", [])
    if socratic:
        console.print("[bold blue]Socratic Questions:[/bold blue]")
        for q in socratic:
            console.print(f"  ? {q}")

    misconceptions = output.get("common_misconceptions", [])
    if misconceptions:
        console.print("\n[bold magenta]Common Misconceptions:[/bold magenta]")
        for m in misconceptions:
            console.print(f"  ! {m}")

    quiz = output.get("quiz_questions", [])
    if quiz:
        console.print("\n[bold blue]Quiz Questions:[/bold blue]")
        for i, q in enumerate(quiz, 1):
            console.print(f"  {i}. {q}")

    rubric = output.get("assessment_rubric", [])
    if rubric:
        console.print("\n[bold blue]Assessment Rubric:[/bold blue]")
        for r in rubric:
            console.print(f"  - {r}")

    activity = output.get("teaching_activity", "")
    if activity:
        console.print(f"\n[bold blue]Teaching Activity:[/bold blue] {activity}")

    cautions = output.get("technical_cautions", [])
    if cautions:
        console.print("\n[bold red]Technical Cautions:[/bold red]")
        for c in cautions:
            console.print(f"  ! {c}")


def print_lab_data_analyst(output: dict) -> None:
    """Render a Lab/Data Analyst output. Wave 2 contract — fields rendered defensively."""
    if not output:
        return
    confidence = output.get("confidence", "medium")
    evidence = output.get("evidence_level", "weak")
    approval = output.get("approval_level", "none")

    header = (
        f"[bold]Analysis type:[/bold] {output.get('analysis_type', '(not set)')}\n"
        f"[bold]Confidence:[/bold] {confidence}    [bold]Evidence level:[/bold] {evidence}    "
        f"[bold]Approval level:[/bold] {approval}\n\n"
        f"[bold]Summary:[/bold]\n{output.get('summary', '')}"
    )
    console.print(Panel(
        header,
        title="[bold cyan]Lab / Data Analyst[/bold cyan]",
        border_style="cyan",
    ))

    for label, key in (
        ("Data Requirements",       "data_requirements"),
        ("Plots Recommended",       "plots_recommended"),
        ("Reproducibility Checks",  "reproducibility_checks"),
        ("Assumptions",             "assumptions"),
        ("Risks",                   "risks"),
    ):
        items = output.get(key, [])
        if items:
            console.print(f"\n[bold cyan]{label}:[/bold cyan]")
            for item in items:
                console.print(f"  - {item}")


def print_influence_public_communication(output: dict) -> None:
    """Render an Influence / Public Communication output. Wave 2 contract.

    Defect 10: field names now match the authoritative
    ``InfluencePublicCommunicationOutput`` schema:
    ``narrative_angle`` (singular str), ``evidence_cautions``,
    ``overclaim_risks``, ``safer_wording``,
    ``approval_required_before_publishing``.
    """
    if not output:
        return
    confidence = output.get("confidence", "medium")
    evidence = output.get("evidence_level", "weak")
    approval = output.get("approval_level", "draft_only")
    approval_before_publish = bool(output.get("approval_required_before_publishing", True))

    header = (
        f"[bold]Core message:[/bold] {output.get('core_message', '(not set)')}\n"
        f"[bold]Confidence:[/bold] {confidence}    [bold]Evidence level:[/bold] {evidence}    "
        f"[bold]Approval level:[/bold] {approval}\n"
        f"[bold]Approval required before publishing:[/bold] {approval_before_publish}\n\n"
        f"[bold]Summary:[/bold]\n{output.get('summary', '')}"
    )
    console.print(Panel(
        header,
        title="[bold magenta]Influence / Public Communication[/bold magenta]",
        border_style="magenta",
    ))

    draft = output.get("linkedin_draft", "")
    if draft:
        console.print(Panel(
            draft,
            title="[bold]LinkedIn Draft[/bold]",
            border_style="dim magenta",
        ))

    public_explanation = output.get("public_explanation", "")
    if public_explanation:
        console.print(Panel(
            public_explanation,
            title="[bold]Public Explanation[/bold]",
            border_style="dim magenta",
        ))

    narrative_angle = output.get("narrative_angle", "")
    if narrative_angle:
        console.print(Panel(
            narrative_angle,
            title="[bold]Narrative Angle[/bold]",
            border_style="magenta",
        ))

    for label, key in (
        ("Hook Options",        "hook_options"),
        ("Risks",               "risks"),
        ("Evidence Cautions",   "evidence_cautions"),
        ("Overclaim Risks",     "overclaim_risks"),
        ("Safer Wording",       "safer_wording"),
    ):
        items = output.get(key, []) or []
        if items:
            console.print(f"\n[bold magenta]{label}:[/bold magenta]")
            for item in items:
                console.print(f"  - {item}")


def print_collaboration_operator(output: dict) -> None:
    """Render a Collaboration Operator output. Wave 3 contract."""
    if not output:
        return
    confidence = output.get("confidence", "medium")
    evidence = output.get("evidence_level", "weak")
    approval = output.get("approval_level", "draft_only")
    contact_required = output.get("approval_required_before_contacting", True)
    collab_type = output.get("suggested_collaboration_type", "unknown")

    header = (
        f"[bold]Collaboration goal:[/bold] {output.get('collaboration_goal', '(not set)')}\n"
        f"[bold]Type:[/bold] {collab_type}\n"
        f"[bold]Confidence:[/bold] {confidence}    [bold]Evidence level:[/bold] {evidence}    "
        f"[bold]Approval level:[/bold] {approval}\n"
        f"[bold red]Approval required before contacting:[/bold red] {contact_required}\n\n"
        f"[bold]Summary:[/bold]\n{output.get('summary', '')}"
    )
    console.print(Panel(
        header,
        title="[bold cyan]Collaboration Operator[/bold cyan]",
        border_style="cyan",
    ))

    for label, key in (
        ("Possible Collaborators",      "possible_collaborators"),
        ("Rationale",                   "collaborator_rationale"),
        ("Evidence for Fit",            "evidence_for_fit"),
        ("Missing Information",         "missing_information"),
        ("Meeting Agenda",              "meeting_agenda"),
        ("Questions to Ask",            "questions_to_ask"),
    ):
        items = output.get(key, [])
        if items:
            console.print(f"\n[bold cyan]{label}:[/bold cyan]")
            for item in items:
                console.print(f"  - {item}")

    subject = output.get("draft_email_subject", "")
    body = output.get("draft_email_body", "")
    if subject or body:
        text = ""
        if subject:
            text += f"[bold]Subject:[/bold] {subject}\n\n"
        if body:
            text += body
        console.print(Panel(
            text,
            title="[bold]Draft Email (REVIEW BEFORE SENDING)[/bold]",
            border_style="dim cyan",
        ))

    risk_notes = output.get("institutional_risk_notes", [])
    if risk_notes:
        console.print("\n[bold red]Institutional Risk Notes:[/bold red]")
        for note in risk_notes:
            console.print(f"  ! {note}")


def print_founder_innovation(output: dict) -> None:
    """Render a Founder/Innovation output. Wave 3 contract."""
    if not output:
        return
    confidence = output.get("confidence", "medium")
    evidence = output.get("evidence_level", "weak")
    approval = output.get("approval_level", "draft_only")
    ext_required = output.get("approval_required_before_external_commitment", True)

    header = (
        f"[bold]Innovation thesis:[/bold] {output.get('innovation_thesis', '(not set)')}\n"
        f"[bold]Confidence:[/bold] {confidence}    [bold]Evidence level:[/bold] {evidence}    "
        f"[bold]Approval level:[/bold] {approval}\n"
        f"[bold red]Approval required before external commitment:[/bold red] {ext_required}\n\n"
        f"[bold]Summary:[/bold]\n{output.get('summary', '')}"
    )
    console.print(Panel(
        header,
        title="[bold green]Founder / Innovation[/bold green]",
        border_style="green",
    ))

    if output.get("product_hypothesis"):
        console.print(Panel(
            output["product_hypothesis"],
            title="[bold]Product Hypothesis[/bold]",
            border_style="dim green",
        ))

    if output.get("possible_value_proposition"):
        console.print(f"\n[bold green]Value Proposition:[/bold green] {output['possible_value_proposition']}")
    if output.get("technical_moat"):
        console.print(f"[bold green]Technical Moat:[/bold green] {output['technical_moat']}")
    if output.get("problem_customer_fit"):
        console.print(f"[bold green]Problem-Customer Fit:[/bold green] {output['problem_customer_fit']}")

    for label, key in (
        ("Target Users / Customers",   "target_users_or_customers"),
        ("IP Considerations",          "ip_considerations"),
        ("Market Assumptions",         "market_assumptions"),
        ("Commercialization Pathways", "commercialization_pathways"),
        ("Validation Experiments",     "validation_experiments"),
        ("Business Model Options",     "business_model_options"),
        ("Key Risks",                  "key_risks"),
        ("Regulatory / Ethical Considerations", "regulatory_or_ethical_considerations"),
        ("Next 90-Day Plan",           "next_90_day_plan"),
    ):
        items = output.get(key, [])
        if items:
            console.print(f"\n[bold green]{label}:[/bold green]")
            for item in items:
                console.print(f"  - {item}")

    disclaimer = output.get("legal_financial_disclaimer", "")
    if disclaimer:
        console.print(Panel(
            disclaimer,
            title="[bold red]Disclaimer[/bold red]",
            border_style="red",
        ))


def print_patent_intelligence(output: dict) -> None:
    """Render a Patent Intelligence output (Stage 1 reconnaissance).

    Defect 11: field names now match the authoritative
    ``PatentIntelligenceOutput`` schema — ``apparent_theme_clusters``,
    ``possible_white_space``, ``overlap_risks``,
    ``apparent_landscape_summary``, ``frequent_assignees_or_applicants``,
    ``mock_mode_used``, ``limitations``.  The obsolete keys
    (``top_patent_clusters``, ``white_space_opportunities``,
    ``crowded_areas``) are no longer read.
    """
    if not output:
        return
    confidence = output.get("confidence", "medium")
    evidence = output.get("evidence_level", "weak")
    mock_mode = bool(output.get("mock_mode_used"))
    provider_used = output.get("provider_used") or "(unknown)"
    n_pages = output.get("retrieved_patent_page_count", 0)
    n_records = output.get("deduplicated_patent_record_count", 0)

    title_suffix = " — MOCK MODE (SYNTHETIC)" if mock_mode else ""

    header_lines = [
        f"[bold]Confidence:[/bold] {confidence}    "
        f"[bold]Evidence level:[/bold] {evidence}",
        f"[bold]Provider:[/bold] {provider_used}    "
        f"[bold]Retrieved pages:[/bold] {n_pages}    "
        f"[bold]Deduped records:[/bold] {n_records}",
        f"\n[bold]Summary:[/bold]\n{output.get('summary', 'No summary')}",
    ]
    if mock_mode:
        header_lines.insert(0, "[bold red]⚠ Mock mode used — results are SYNTHETIC[/bold red]")

    console.print(Panel(
        "\n".join(header_lines),
        title=f"[bold magenta]Patent Intelligence (Stage 1){title_suffix}[/bold magenta]",
        border_style="red" if mock_mode else "magenta",
    ))

    landscape_summary = output.get("apparent_landscape_summary", "")
    if landscape_summary:
        console.print(Panel(
            landscape_summary,
            title="[bold]Apparent Landscape Summary[/bold]",
            border_style="dim magenta",
        ))

    theme_clusters = output.get("apparent_theme_clusters", []) or []
    if theme_clusters:
        console.print("\n[bold magenta]Apparent Theme Clusters:[/bold magenta]")
        for cl in theme_clusters[:6]:
            if isinstance(cl, dict):
                name = cl.get("cluster_name", "(unnamed)")
                ev = cl.get("supporting_evidence", "")
                console.print(f"  - {name}" + (f" — {ev}" if ev else ""))
            else:
                console.print(f"  - {cl}")

    white_space = output.get("possible_white_space", []) or []
    if white_space:
        console.print("\n[bold magenta]Possible White-Space (tentative):[/bold magenta]")
        for ws in white_space[:6]:
            if isinstance(ws, dict):
                direction = ws.get("direction", "")
                conf = ws.get("confidence", "")
                caveat = ws.get("caveat", "")
                line = f"  - {direction}"
                if conf:
                    line += f" (conf={conf})"
                if caveat:
                    line += f" — caveat: {caveat}"
                console.print(line)
            else:
                console.print(f"  - {ws}")

    overlap_risks = output.get("overlap_risks", []) or []
    if overlap_risks:
        console.print("\n[bold yellow]Overlap Risks (crowded areas):[/bold yellow]")
        for r in overlap_risks[:6]:
            console.print(f"  - {r}")

    assignees = output.get("frequent_assignees_or_applicants", []) or []
    if assignees:
        console.print("\n[bold magenta]Frequent Assignees / Applicants:[/bold magenta]")
        console.print("  " + ", ".join(assignees[:8]))

    followups = output.get("recommended_follow_up_searches", []) or []
    if followups:
        console.print("\n[bold magenta]Recommended Follow-Up Searches:[/bold magenta]")
        for q in followups[:5]:
            console.print(f"  - {q}")

    risks = output.get("risks", []) or []
    if risks:
        console.print("\n[bold red]Risks & Caveats:[/bold red]")
        for r in risks[:5]:
            console.print(f"  - {r}")

    limitations = output.get("limitations", []) or []
    if limitations:
        console.print("\n[bold yellow]Limitations:[/bold yellow]")
        for lim in limitations[:6]:
            console.print(f"  - {lim}")


def print_specialists(specialists: dict) -> None:
    """Render every Phase 2 specialist output found in the orchestrator result.

    Dispatches each agent to its dedicated printer; falls back to a generic panel
    for unknown specialists so the formatter never silently drops output.
    """
    if not isinstance(specialists, dict) or not specialists:
        return
    for name, output in specialists.items():
        if name == "research_scout":
            continue   # research_scout has its own dedicated printer
        if not isinstance(output, dict):
            continue
        if name == "grant_architect":
            print_grant_architect(output)
        elif name == "teaching_mentor":
            print_teaching_mentor(output)
        elif name == "lab_data_analyst":
            print_lab_data_analyst(output)
        elif name == "influence_public_communication":
            print_influence_public_communication(output)
        elif name == "collaboration_operator":
            print_collaboration_operator(output)
        elif name == "founder_innovation":
            print_founder_innovation(output)
        elif name == "patent_intelligence":
            print_patent_intelligence(output)
        else:
            # Generic panel for any not-yet-implemented or future specialist
            console.print(Panel(
                output.get("summary", "(no summary)"),
                title=f"[bold]{name}[/bold]",
                border_style="dim",
            ))


def print_error(message: str) -> None:
    console.print(f"[bold red]ERROR:[/bold red] {message}")


def print_separator() -> None:
    console.rule(style="dim")


# ---------------------------------------------------------------------------
# format_outputs — render the full orchestrator result to a single string
# ---------------------------------------------------------------------------

def format_outputs(outputs: dict) -> str:
    """Render the full orchestrator result dict to a plain-text string.

    Used by tests and by callers that want the formatted view without printing
    to the live terminal. Renders every section that's present and skips the
    rest. Tolerates missing or partial outputs — never raises on malformed
    specialist outputs.
    """
    if not isinstance(outputs, dict):
        return "(no outputs)"

    from rich.console import Console
    capture_console = Console(record=True, width=120, force_terminal=False)

    # Replace the module-level `console` for the duration of the render so the
    # existing print_* functions write into our capture console.
    global console
    real_console = console
    try:
        console = capture_console
        gov = outputs.get("strategic_governor") or {}
        if gov:
            print_governor(gov)

        scout = outputs.get("research_scout")
        if scout:
            print_research_scout(scout)

        # Phase 2 specialists (registry-driven)
        specialists = outputs.get("specialists") or {}
        # Backward-compat: also surface top-level keys for known specialists
        # (some test fixtures populate the legacy flat keys, not specialists dict)
        for legacy_name in ("grant_architect", "teaching_mentor",
                            "lab_data_analyst", "influence_public_communication",
                            "collaboration_operator", "founder_innovation"):
            if legacy_name in outputs and legacy_name not in specialists:
                if isinstance(outputs[legacy_name], dict):
                    specialists[legacy_name] = outputs[legacy_name]
        if specialists:
            print_specialists(specialists)

        verifier = outputs.get("scientific_verifier")
        if verifier:
            print_verification(verifier)

        evolution = outputs.get("self_evolution_engine") or {}
        if evolution:
            print_self_evolution(evolution)

        errors = outputs.get("errors") or []
        for err in errors:
            agent = err.get("agent", "?") if isinstance(err, dict) else "?"
            msg = err.get("error", str(err)) if isinstance(err, dict) else str(err)
            print_error(f"[{agent}] {msg}")
    finally:
        console = real_console

    return capture_console.export_text()
