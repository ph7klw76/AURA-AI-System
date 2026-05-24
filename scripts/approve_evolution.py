"""
AURA Evolution Approval CLI — review and apply pending Self-Evolution proposals.

Usage:
    python scripts/approve_evolution.py              # interactive review
    python scripts/approve_evolution.py --list       # show pending without acting
    python scripts/approve_evolution.py --auto-skip  # defer all pending without applying

Decisions are logged to data/approval_log.jsonl and tracked by content hash,
so a proposal you've already decided on never re-appears.

The same review can be triggered from within `python main.py` by typing
'evolve', 'approve evolution', 'pending', etc.
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import config
from core.evolution_review import run_interactive


def _force_utf8_stdout() -> None:
    """Windows' cp1252 console can't print proposals containing ≥, μ, ·, ··· etc."""
    if hasattr(sys.stdout, "buffer"):
        try:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review and approve AURA Self-Evolution proposals."
    )
    parser.add_argument("--list", action="store_true",
                        help="Just list pending proposals and exit.")
    parser.add_argument("--auto-skip", action="store_true",
                        help="Mark every pending proposal as 'deferred' without applying.")
    args = parser.parse_args()

    print()
    print("AURA Evolution Approval")
    print("-----------------------")
    print(f"reflections.jsonl: {config.REFLECTION_PATH}")
    print(f"profile YAML:      {config.RESEARCH_PROFILE_PATH}")
    print(f"approval_log:      {config.APPROVAL_LOG_PATH}")
    print()

    run_interactive(list_only=args.list, auto_skip=args.auto_skip)


if __name__ == "__main__":
    _force_utf8_stdout()
    main()
