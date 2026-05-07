from __future__ import annotations

from rich.console import Console
from rich.prompt import Prompt

from core.orchestrator import run_aura_core
from core.formatter import (
    print_title,
    print_governor,
    print_research_scout,
    print_verification,
    print_self_evolution,
    print_separator,
    print_error,
    console,
)

_console = Console()


def main() -> None:
    print_title()
    _console.print("[dim]Type 'exit' or 'quit' to stop. Type 'json' after a result to see raw JSON.[/dim]\n")

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
        if user_input.lower() == "json" and last_result:
            import json
            _console.print_json(json.dumps(last_result, indent=2, default=str))
            continue

        print_separator()
        result = run_aura_core(user_input)
        last_result = result

        gov = result.get("strategic_governor", {})
        if gov:
            print_governor(gov)

        scout = result.get("research_scout")
        if scout:
            print_research_scout(scout)

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

        print_separator()
        _console.print("[dim]Type 'json' to see raw output, or enter a new task.[/dim]")


if __name__ == "__main__":
    main()
