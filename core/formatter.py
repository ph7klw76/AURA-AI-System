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


def print_title() -> None:
    console.print(Panel.fit(
        "[bold cyan]AURA Core MVP[/bold cyan]\n[dim]Powered by Qwen3:8B via Ollama[/dim]",
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
            console.print(f"  -> {a}")

    report_paths = output.get("report_paths", [])
    if report_paths:
        console.print("[bold]Report Paths:[/bold]")
        for p in report_paths:
            console.print(f"  {p}")


def print_verification(report: dict) -> None:
    assessment = report.get("overall_assessment", "incomplete")
    route = report.get("route", "revise")
    final_rec = report.get("final_recommendation", "")
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


def print_error(message: str) -> None:
    console.print(f"[bold red]ERROR:[/bold red] {message}")


def print_separator() -> None:
    console.rule(style="dim")
