from __future__ import annotations

import os
import sys
import argparse

from rich.console import Console
from rich.prompt import Prompt

from core.orchestrator import run_aura_core
from core.llm import ask_llm
from core.runtime import ensure_ollama_ready

# Phase 1 Defect 3: cap on prompt-loop iterations so a buggy controller / agent
# cannot drive the CLI into a forever loop.
_MAX_PROMPT_LOOP_ITERATIONS = 6
from core.formatter import (
    print_title,
    print_governor,
    print_research_scout,
    print_specialists,
    print_verification,
    print_self_evolution,
    print_separator,
    print_error,
    console,
)
from core.evolution_review import (
    EVOLUTION_TRIGGERS,
    is_evolution_trigger,
    load_pending_proposals,
    run_interactive,
)
from qwen_evolver.deep_research.orchestrator import run_research
from qwen_evolver.deep_research.schemas import ResearchMission, ResearchDepth
import config

_console = Console()


def _collect_folder_response(prompt_dict: dict) -> dict:
    """CLI prompt collector for a single ``needs_user_input`` payload.

    Returns a response dict that ``run_aura_core(user_responses=...)``
    understands.  The user may answer:

      * ``y`` (or empty + folder path) → ``{use_local_folder: True, folder_path}``
      * ``n``                          → ``{use_local_folder: False, folder_path: None}``
      * ``later``                      → ``{ask_later: True}``
    """
    target = prompt_dict.get("target_agent", "?")
    message = prompt_dict.get("message", "")
    _console.print(f"\n[bold yellow]AURA needs your input ({target}):[/bold yellow]")
    _console.print(message)
    choice = Prompt.ask(
        "Use a local folder? [y]es / [n]o / [later]",
        choices=["y", "n", "later"],
        default="n",
    ).strip().lower()
    if choice == "later":
        return {"ask_later": True}
    if choice == "n":
        return {"use_local_folder": False, "folder_path": None}
    # y → ask for the path until non-empty (defect 21).
    while True:
        path = Prompt.ask("Folder path").strip()
        if path:
            return {"use_local_folder": True, "folder_path": path}
        _console.print(
            "[red]Folder path cannot be empty. "
            "Type 'cancel' to switch to 'no'.[/red]"
        )
        retry = Prompt.ask("Folder path (or 'cancel')").strip()
        if retry.lower() == "cancel":
            return {"use_local_folder": False, "folder_path": None}
        if retry:
            return {"use_local_folder": True, "folder_path": retry}


def run_aura_with_prompt_loop(
    user_input: str,
    *,
    prompt_handler=None,
    max_iterations: int = _MAX_PROMPT_LOOP_ITERATIONS,
) -> dict:
    """Defect 3: drive ``run_aura_core`` through any ``needs_user_input``
    pauses until the pipeline either completes or hits the iteration cap.

    Parameters
    ----------
    user_input
        The user's request to the AURA pipeline.
    prompt_handler
        Callable taking a ``pending_prompt`` dict and returning a response
        dict suitable for ``user_responses[target_agent]``.  Defaults to
        :func:`_collect_folder_response` which reads from the CLI.
    max_iterations
        Hard cap on resume cycles so a stuck loop fails fast rather than
        hanging the user's terminal.

    Returns the final ``run_aura_core`` result.  When the cap is exceeded
    the returned dict still carries ``pipeline_status="awaiting_user_input"``
    plus an additional ``aborted_reason``.
    """
    handler = prompt_handler or _collect_folder_response
    session_id: str | None = None
    user_responses: dict = {}

    for _ in range(max_iterations):
        result = run_aura_core(
            user_input,
            session_id=session_id,
            user_responses=user_responses,
        )
        if result.get("pipeline_status") != "awaiting_user_input":
            return result
        # Resume next iteration with the same session and the answer.
        session_id = result.get("session_id") or session_id
        prompt = result.get("pending_prompt") or {}
        target = prompt.get("target_agent") or result.get("paused_by") or ""
        if not target:
            # Defensive: cannot decide who to answer.
            result["aborted_reason"] = "missing_paused_by"
            return result
        try:
            response = handler(prompt)
        except (EOFError, KeyboardInterrupt):
            result["aborted_reason"] = "user_aborted"
            return result
        user_responses = dict(user_responses)
        user_responses[target] = response

    result["aborted_reason"] = "max_prompt_iterations_exceeded"
    return result


def _configure_llm() -> tuple[str | None, str | None]:
    """Ask the user which LLM model to use, and optionally an API key."""
    _console.print("[bold]LLM Configuration[/bold]")
    _console.print(
        "You can type a model name (e.g. [cyan]deepseek-v4-flash[/cyan]) "
        "or press Enter to keep the default."
    )

    # Default model respects AURA_MODEL → DEFAULT_MODEL (deepseek‑v4‑flash)
    default_model = config.get_model_name()
    model_input = Prompt.ask("Model", default=default_model)
    model = model_input.strip() or default_model

    api_key = None
    api_key_input = Prompt.ask(
        "Optional API key (press Enter to skip)", default="", password=True
    )
    api_key = api_key_input.strip() or None

    _console.print()
    return model, api_key


def _verify_llm_connection(model_name: str, api_key: str | None) -> bool:
    try:
        test_prompt = "Return the word OK exactly."
        response = ask_llm(
            system_prompt="You are a connectivity tester.",
            user_prompt=test_prompt,
            temperature=0.0,
        )
        _console.print(
            f"✓ Connectivity test succeeded for model [bold]{model_name}[/bold]."
        )
        return True
    except Exception as exc:
        _console.print(
            f"[red]✗ LLM connectivity test failed:[/red] {exc}"
        )
        return False


def _bootstrap_ollama(model_name: str = "") -> None:
    """Auto‑start Ollama if it isn't running, and verify the specified model.

    If *model_name* is empty, the currently active model from config is used.
    Disable with AURA_SKIP_OLLAMA_BOOTSTRAP=1.
    Auto‑pull the model on demand with AURA_AUTO_PULL_MODEL=1.
    """
    if os.getenv("AURA_SKIP_OLLAMA_BOOTSTRAP") == "1":
        return

    timeout = float(os.getenv("AURA_OLLAMA_TIMEOUT", "60"))
    pull_if_missing = os.getenv("AURA_AUTO_PULL_MODEL") == "1"

    def _say(msg: str) -> None:
        _console.print(f"[dim cyan]·· {msg}[/dim cyan]")

    try:
        ensure_ollama_ready(
            timeout_s=timeout,
            pull_if_missing=pull_if_missing,
            on_status=_say,
            model_name=model_name or config.get_model_name(),
        )
    except RuntimeError as exc:
        _console.print(f"[bold red]Bootstrap failed:[/bold red] {exc}")
        _console.print(
            "[dim]Set AURA_SKIP_OLLAMA_BOOTSTRAP=1 to bypass this check, or "
            "fix the issue and re‑run.[/dim]"
        )
        sys.exit(1)


def _run_evolution_review() -> None:
    pending = load_pending_proposals()
    if not pending:
        _console.print(
            "[dim cyan]No pending evolution proposals. "
            "(All previous proposals are already approved, rejected, or deferred — "
            "or no sessions have run yet.)[/dim cyan]"
        )
        return
    _console.print(
        f"\n[bold cyan]Self-Evolution Review[/bold cyan] — "
        f"[yellow]{len(pending)}[/yellow] pending proposal(s)."
    )
    _console.print(
        "[dim]For each proposal: [a]pprove (applies to disk), "
        "[r]eject (logged, never re‑shown), [s]kip (stays pending), "
        "[q]uit review (back to AURA prompt).[/dim]\n"
    )
    summary = run_interactive(max_to_review=10)
    _console.print(
        f"\n[dim cyan]Returned to AURA prompt. "
        f"Approved: {summary['approved']}  Applied: {summary['applied']}  "
        f"Rejected: {summary['rejected']}  Skipped: {summary['skipped']}.  "
        f"Remaining: {summary['pending'] - summary['approved'] - summary['rejected']}.[/dim cyan]\n"
    )


def _print_help() -> None:
    _console.print("[bold]AURA commands[/bold]")
    _console.print("  [cyan]<any prompt>[/cyan]         — run a research task through AURA")
    _console.print("  [cyan]evolve[/cyan] / [cyan]approve evolution[/cyan] / [cyan]pending[/cyan]  — review pending Self‑Evolution proposals")
    _console.print("  [cyan]json[/cyan]                  — show the raw JSON of the last AURA result")
    _console.print("  [cyan]help[/cyan] / [cyan]?[/cyan]              — this list")
    _console.print("  [cyan]exit[/cyan] / [cyan]quit[/cyan]          — stop AURA")
    _console.print("\n[bold]Deep Research CLI (direct)[/bold]")
    _console.print("  [cyan]python main.py research --query \"...\" --depth standard [--model MODEL] [--api-key KEY][/cyan]")
    _console.print("  [cyan]python main.py research-grants --query \"...\" --depth extensive [--model MODEL] [--api-key KEY][/cyan]")
    _console.print("  [cyan]python main.py show-report --mission-id ID[/cyan]")
    _console.print("  [cyan]python main.py show-evidence --mission-id ID[/cyan]")
    _console.print("  [cyan]python main.py show-reflection --mission-id ID[/cyan]")


def _run_deep_research_cli(
    query: str,
    depth: str,
    model: str | None = None,
    api_key: str | None = None,
    grant_focused: bool = False,
) -> None:
    if model:
        os.environ["LLM_MODEL"] = model
        _console.print(f"[bold]Using model: [cyan]{model}[/cyan][/bold]")
    if api_key:
        os.environ["LLM_API_KEY"] = api_key
    used_model = os.environ.get("LLM_MODEL", config.get_model_name())
    _console.print(f"Deep research will be executed with model: [cyan]{used_model}[/cyan]")

    # Bootstrap local model if needed
    if model and ":" in model:
        _bootstrap_ollama(model_name=model)

    try:
        mission = ResearchMission(
            original_user_request=query,
            interpreted_objective=query,
            requested_depth=ResearchDepth(depth),
            domain="grant" if grant_focused else "",
        )
        result = run_research(mission)
        _console.print_json(data=result)
        report_path = result.get("report_path", "")
        if report_path:
            _console.print(f"\n[green]Report saved to {report_path}[/green]")
        # Phase 3 (goal 3/B): a run that completed but failed to generate the
        # report (or write it) is NOT a success — exit nonzero so automation
        # and CI can detect the degraded outcome.
        if result.get("report_generation_failed") or not report_path:
            _console.print(
                "[red]Deep research did not produce a valid report "
                f"(status={result.get('report_status', 'unknown')!r}).[/red]"
            )
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:
        # Phase 3 (goal 3/B): a raised error must surface a nonzero exit code.
        _console.print(f"[red]Deep research failed: {exc}[/red]")
        sys.exit(1)


_TOP_LEVEL_HELP = """\
AURA - Autonomous Unified Research Agent

Usage:
  python main.py                      Launch interactive mode
  python main.py --help | -h          Show this help and exit
  python main.py research --query "..." [--depth rapid|standard|extensive]
                                       [--model MODEL] [--api-key KEY]
  python main.py research-grants --query "..." [--depth ...] [--model ...]
  python main.py show-report     --mission-id ID
  python main.py show-evidence   --mission-id ID
  python main.py show-reflection --mission-id ID

Interactive commands (inside the AURA prompt):
  <any prompt>              Run a research task through AURA
  evolve / approve evolution / pending
                            Review pending Self-Evolution proposals
  json                      Show the raw JSON of the last AURA result
  help / ?                  Show the interactive command list
  exit / quit               Stop AURA
"""


def main() -> None:
    # ----- Top-level help (Phase 3 goal 4): `--help` / `-h` must print help
    # and exit 0 WITHOUT entering the interactive prompt flow.  The argparse
    # parser below uses add_help=False (so it doesn't fight the subcommands),
    # therefore we handle the top-level help ourselves here. -----
    argv = sys.argv[1:]
    known_commands = {
        "research", "research-grants",
        "show-report", "show-evidence", "show-reflection",
    }
    if argv and argv[0] in ("-h", "--help") and not (set(argv) & known_commands):
        # Plain text so it works even if rich markup is disabled.
        print(_TOP_LEVEL_HELP)
        sys.exit(0)

    # ----- CLI mode -----
    parser = argparse.ArgumentParser(add_help=False)
    sub = parser.add_subparsers(dest="command")

    # Common options for research commands
    def _add_model_args(p):
        p.add_argument("--model", default=None, help="LLM model name (e.g., deepseek-v4-flash)")
        p.add_argument("--api-key", default=None, help="API key for the model (if required)")

    rp = sub.add_parser("research")
    rp.add_argument("--query", required=True)
    rp.add_argument("--depth", default="standard", choices=["rapid", "standard", "extensive"])
    _add_model_args(rp)

    rg = sub.add_parser("research-grants")
    rg.add_argument("--query", required=True)
    rg.add_argument("--depth", default="extensive", choices=["rapid", "standard", "extensive"])
    _add_model_args(rg)

    sr = sub.add_parser("show-report")
    sr.add_argument("--mission-id", required=True)

    se = sub.add_parser("show-evidence")
    se.add_argument("--mission-id", required=True)

    sref = sub.add_parser("show-reflection")
    sref.add_argument("--mission-id", required=True)

    args, _ = parser.parse_known_args()
    if args.command == "research":
        _run_deep_research_cli(args.query, args.depth, model=args.model, api_key=args.api_key, grant_focused=False)
        return
    if args.command == "research-grants":
        _run_deep_research_cli(args.query, args.depth, model=args.model, api_key=args.api_key, grant_focused=True)
        return
    if args.command in ("show-report", "show-evidence", "show-reflection"):
        from core.path_safety import (
            validate_mission_id, safe_mission_path, MissionIdError,
        )
        report_base = config.BASE_DIR / "reports" / "deep_research"
        data_base = config.BASE_DIR / "data" / "deep_research"
        # Fail closed on traversal-style mission_id before reading.
        try:
            validate_mission_id(args.mission_id)
            file_map = {
                "show-report": safe_mission_path(
                    report_base, args.mission_id, "_report.md"),
                "show-evidence": safe_mission_path(
                    data_base / "evidence", args.mission_id, "_evidence.jsonl"),
                "show-reflection": safe_mission_path(
                    data_base / "reflections", args.mission_id, "_reflection.json"),
            }
        except MissionIdError as exc:
            _console.print(f"[red]Invalid mission_id: {exc}[/red]")
            return
        path = file_map.get(args.command)
        if path and path.exists():
            _console.print(path.read_text(encoding="utf-8"))
        else:
            _console.print("[red]File not found.[/red]")
        return

    # ----- Interactive mode -----
    print_title()
    model_name, api_key = _configure_llm()
    if model_name:
        os.environ["LLM_MODEL"] = model_name
    if api_key:
        os.environ["LLM_API_KEY"] = api_key

    # For remote models (no colon) we skip Ollama bootstrap
    if ":" in model_name:
        _bootstrap_ollama(model_name=model_name)
    else:
        _console.print(
            "[dim]Skipping local Ollama bootstrap (model is remote).[/dim]"
        )
        connected = _verify_llm_connection(model_name, api_key)
        if not connected:
            proceed = Prompt.ask("Continue anyway? (y/n)", choices=["y", "n"], default="n")
            if proceed.lower() != "y":
                _console.print("[dim]Exiting AURA.[/dim]")
                return

    _console.print(
        "[dim]Type 'exit' to quit, 'json' to dump last result, "
        "'evolve' to review Self‑Evolution proposals, 'help' for the full list.[/dim]\n"
    )

    last_result: dict | None = None

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]AURA[/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            _console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            _console.print("[dim]Goodbye.[/dim]")
            break
        if user_input.lower() in ("help", "?", "/help"):
            _print_help()
            continue
        if user_input.lower() == "json" and last_result:
            import json
            _console.print_json(json.dumps(last_result, indent=2, default=str))
            continue
        if is_evolution_trigger(user_input):
            _run_evolution_review()
            continue

        print_separator()
        current_model = os.environ.get("LLM_MODEL", config.get_model_name())
        _console.print(
            f"[bold blue]AURA is processing your request (model: [cyan]{current_model}[/cyan])…[/bold blue]"
        )
        # Phase 1 Defect 3: route through the prompt loop so
        # needs_user_input pauses are resolved interactively.
        result = run_aura_with_prompt_loop(user_input)
        last_result = result
        if result.get("pipeline_status") == "awaiting_user_input":
            _console.print(
                "[yellow]Pipeline still awaiting user input "
                f"({result.get('aborted_reason', 'paused')}); skipping rendering.[/yellow]"
            )
            continue

        gov = result.get("strategic_governor", {})
        if gov:
            print_governor(gov)

        scout = result.get("research_scout")
        if scout:
            print_research_scout(scout)

        specialists = result.get("specialists", {}) or {}
        if specialists:
            print_specialists(specialists)

        n_retries = result.get("retry_count", 0)
        if n_retries > 0:
            pre = result.get("pre_retry_verifier") or {}
            cur = result.get("scientific_verifier") or {}
            history = result.get("retry_history") or []
            n_revise = result.get("revise_iterations_used", 0)
            _console.print(
                f"\n[bold yellow]Auto-retry ran {n_retries} pass(es)[/bold yellow] — "
                f"first-pass verifier route was [red]{pre.get('route', '?')}[/red]."
            )
            for h in history:
                strat = h.get("strategy", "?")
                ri = h.get("iteration", "?")
                rb = h.get("route_before", "?")
                ra = h.get("route_after", "?")
                blurb = {
                    "literature_scan":
                        "switched research_scout → literature_scan",
                    "revise_with_instructions":
                        f"addressed {h.get('num_revision_instructions', 0)} revision instruction(s)",
                }.get(strat, strat)
                color = "green" if ra not in ("retrieve_more_evidence", "revise") else "yellow"
                _console.print(
                    f"  pass {ri}: [cyan]{strat}[/cyan] — {blurb}   "
                    f"route: [red]{rb}[/red] → [{color}]{ra}[/{color}]"
                )
            if n_revise:
                _console.print(
                    f"  [dim](revise iterations used: {n_revise} of "
                    f"max — see AURA_MAX_REVISE_ITERATIONS to adjust)[/dim]"
                )
            _console.print(
                f"  final route: [green]{cur.get('route', '?')}[/green]   "
                f"assessment: [green]{cur.get('overall_assessment', '?')}[/green]   "
                f"recommendation: [green]{cur.get('final_recommendation', '?')}[/green]"
            )

        verifier = result.get("scientific_verifier")
        if verifier:
            print_verification(verifier)

        evolution = result.get("self_evolution_engine", {})
        if evolution:
            print_self_evolution(evolution)

        errors = result.get("errors", [])
        if errors:
            for err in errors:
                print_error(f"[{err.get('agent', '?')}] {err.get('error', '?')}")

        draft_paths = result.get("draft_paths") or {}
        if draft_paths:
            _console.print(
                f"\n[bold green]Drafts saved to disk[/bold green] "
                f"([yellow]{len(draft_paths)}[/yellow] file(s)):"
            )
            for agent_name, path in draft_paths.items():
                _console.print(f"  [cyan]{agent_name}[/cyan]  →  [dim]{path}[/dim]")

        print_separator()
        _console.print("[dim]Type 'json' to see raw output, or enter a new task.[/dim]")


if __name__ == "__main__":
    main()
