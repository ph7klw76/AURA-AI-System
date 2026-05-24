"""
AURA Evolution Review — shared logic for approving Self-Evolution proposals.

Used by:
  - scripts/approve_evolution.py  (standalone CLI)
  - main.py                       (in-loop command: 'evolve', 'approve evolution', ...)

The Self-Evolution Engine emits proposals after each session and saves them to
data/reflections.jsonl. Proposals are NEVER auto-applied — they sit until the
user reviews them through this module.

Public surface:
    load_pending_proposals() -> list[dict]
    apply_profile_update(payload) -> tuple[bool, str]
    apply_memory_update(payload) -> tuple[bool, str]
    log_decision(prop, decision, applied, message) -> None
    run_interactive(*, list_only=False, auto_skip=False,
                    input_fn=input, print_fn=print) -> dict
        Runs the full review flow. Returns a summary dict.

Trigger words recognised by main.py (case-insensitive, exact match after strip):
    EVOLUTION_TRIGGERS — module-level frozenset of strings.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml

import config
from core.memory import save_memory


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Phase 3 (goal 5): the bare "approve" trigger was ambiguous — a user
# typing "approve" almost always means "approve <something I just saw>",
# not "launch the Self-Evolution review flow".  It is removed.  Explicit
# evolution commands ("approve evolution", "approve proposals",
# "approve pending", "evolve", "review proposals", ...) are preserved.
EVOLUTION_TRIGGERS: frozenset[str] = frozenset({
    "evolve",
    "evolution",
    "self-evolution",
    "self evolution",
    "review evolution",
    "review proposals",
    "review pending",
    "approve evolution",
    "approve proposals",
    "approve pending",
    "pending",
    "pending proposals",
    "pending evolution",
    "/evolve",
    "/approve",
    "/evolution",
})


def is_evolution_trigger(user_input: str) -> bool:
    """Return True if the user typed one of the recognised evolution commands."""
    return (user_input or "").strip().lower() in EVOLUTION_TRIGGERS


# ---------------------------------------------------------------------------
# Proposal collection
# ---------------------------------------------------------------------------

def _proposal_hash(kind: str, payload: dict) -> str:
    """Stable content hash so we never re-prompt for the same proposal twice."""
    blob = kind + "|" + json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def load_actioned_hashes() -> set[str]:
    """Read approval_log.jsonl for hashes the user has already decided on."""
    if not config.APPROVAL_LOG_PATH.exists():
        return set()
    actioned: set[str] = set()
    with open(config.APPROVAL_LOG_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("trigger", "").startswith("evolution_proposal_"):
                h = rec.get("proposal_hash")
                if h:
                    actioned.add(h)
    return actioned


def load_pending_proposals() -> list[dict]:
    """Walk reflections.jsonl; emit one entry per outstanding proposal."""
    if not config.REFLECTION_PATH.exists():
        return []

    actioned = load_actioned_hashes()
    pending: list[dict] = []

    with open(config.REFLECTION_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            created_at = rec.get("created_at", "")
            session_assessment = (rec.get("session_assessment") or "")[:120]

            # Profile updates — list of dicts
            for p in rec.get("profile_update_proposals", []) or []:
                if not isinstance(p, dict):
                    continue
                payload = {
                    "field_path": p.get("field_path", ""),
                    "current_value": p.get("current_value", ""),
                    "proposed_value": p.get("proposed_value", ""),
                    "rationale": p.get("rationale", ""),
                }
                h = _proposal_hash("profile", payload)
                if h not in actioned:
                    pending.append({
                        "kind": "profile",
                        "hash": h,
                        "session": session_assessment,
                        "created_at": created_at,
                        "payload": payload,
                    })

            # Memory updates — list of strings
            for content in rec.get("memory_update_proposals", []) or []:
                if not content or not isinstance(content, str):
                    continue
                payload = {"content": content}
                h = _proposal_hash("memory", payload)
                if h not in actioned:
                    pending.append({
                        "kind": "memory",
                        "hash": h,
                        "session": session_assessment,
                        "created_at": created_at,
                        "payload": payload,
                    })

    return pending


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def apply_profile_update(payload: dict) -> tuple[bool, str]:
    """Apply a profile patch to profiles/research_profile.yaml.

    Backs up the existing file before writing. Returns (success, message).
    """
    field_path = (payload.get("field_path") or "").strip()
    if not field_path:
        return False, "Empty field_path — cannot apply."

    profile_path = config.RESEARCH_PROFILE_PATH
    if not profile_path.exists():
        return False, f"Profile file does not exist: {profile_path}"

    with open(profile_path, encoding="utf-8") as f:
        profile = yaml.safe_load(f) or {}

    parts = field_path.split(".")
    target = profile
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]

    leaf = parts[-1]
    proposed = payload.get("proposed_value", "")

    existing = target.get(leaf)
    if isinstance(existing, list) and isinstance(proposed, str):
        new_items = [s.strip() for s in proposed.split(",") if s.strip()]
        merged = list(existing)
        for item in new_items:
            if item not in merged:
                merged.append(item)
        target[leaf] = merged
        action = f"UNION list at {field_path}: +{len(merged) - len(existing)} item(s)"
    elif isinstance(existing, dict) and isinstance(proposed, dict):
        existing.update(proposed)
        action = f"MERGE dict at {field_path}"
    else:
        try:
            if "." in str(proposed) or "weights" in field_path.lower():
                target[leaf] = float(proposed)
            else:
                target[leaf] = proposed
        except (TypeError, ValueError):
            target[leaf] = proposed
        action = f"SET {field_path} = {target[leaf]!r}"

    # Phase 2 (goal F): microsecond + UUID suffix so two profile updates in
    # the same second do not overwrite each other's backup.
    from core.path_safety import unique_filename_stamp
    backup = profile_path.with_suffix(
        profile_path.suffix + "." + unique_filename_stamp() + ".bak"
    )
    backup.write_text(profile_path.read_text(encoding="utf-8"), encoding="utf-8")

    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(profile, f, sort_keys=False, allow_unicode=True)

    return True, f"{action}. Backup: {backup.name}"


def apply_memory_update(payload: dict) -> tuple[bool, str]:
    """Append a verified memory entry."""
    content = (payload.get("content") or "").strip()
    if not content:
        return False, "Empty content."
    metadata = {
        "source": "user_approved_evolution_proposal",
        "verified": True,
        "scope": "domain",
        "confidence": 1.0,
    }
    try:
        save_memory("preference", content, metadata)
        return True, "Appended to memories.jsonl (kind=preference, verified=True)"
    except Exception as exc:
        return False, f"save_memory failed: {exc}"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_decision(prop: dict, decision: str, applied: bool, message: str) -> None:
    """Write an approval-log row tagged with the proposal hash.

    Phase 2 (goal H) — truthful defer semantics
    -------------------------------------------
    Only ``approve`` / ``reject`` are *actioned* states — they record the
    proposal under the ``evolution_proposal_*`` trigger that
    :func:`load_actioned_hashes` reads, so the proposal is never re-shown.

    ``defer`` (and ``skip``) must remain PENDING for future review.  They
    are logged under a SEPARATE ``evolution_defer_*`` trigger that
    :func:`load_actioned_hashes` deliberately ignores, so the proposal
    re-appears next time — while still leaving an auditable trail.
    """
    actioned = (decision or "").strip().lower() in ("approve", "reject")
    trigger_prefix = "evolution_proposal_" if actioned else "evolution_defer_"
    row = {
        "trigger": f"{trigger_prefix}{prop['kind']}",
        "proposal_hash": prop["hash"],
        "kind": prop["kind"],
        "decision": decision,
        "applied": applied,
        "message": message,
        "payload": prop["payload"],
        "from_session": (prop.get("session") or "")[:120],
        "session_created_at": prop.get("created_at", ""),
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    config.APPROVAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.APPROVAL_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# ---------------------------------------------------------------------------
# Interactive review (plain print/input; main.py can wrap with Rich)
# ---------------------------------------------------------------------------

def _format_proposal(idx: int, total: int, prop: dict) -> list[str]:
    lines = []
    lines.append("")
    lines.append("=" * 78)
    lines.append(
        f"  Proposal {idx}/{total}   [{prop['kind'].upper()}]   hash={prop['hash']}"
    )
    lines.append("=" * 78)
    if prop.get("session"):
        lines.append(f"  from session: {prop['session']}")
    if prop.get("created_at"):
        lines.append(f"  created_at:   {prop['created_at']}")
    lines.append("")
    p = prop["payload"]
    if prop["kind"] == "profile":
        lines.append(f"  field_path:      {p['field_path']!r}")
        lines.append(f"  current_value:   {p['current_value']!r}")
        lines.append(f"  proposed_value:  {p['proposed_value']!r}")
        lines.append(f"  rationale:       {p['rationale']!r}")
    elif prop["kind"] == "memory":
        lines.append("  proposed memory entry:")
        lines.append(f"    {p['content']!r}")
    lines.append("")
    return lines


def run_interactive(
    *,
    list_only: bool = False,
    auto_skip: bool = False,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
    max_to_review: int | None = None,
) -> dict:
    """Run the review loop. Returns a summary dict.

    Args:
        list_only: just print pending proposals and return without prompting.
        auto_skip: mark every pending proposal as 'deferred' without prompting.
        input_fn:  function used to read user decisions (default `input`).
        print_fn:  function used to render lines (default `print`).
        max_to_review: cap on how many proposals to show in one session.
            None = unlimited. Useful when invoked from main.py where you may
            want to stop at, say, 10 per call.

    Returns:
        {"pending": int, "approved": int, "rejected": int,
         "skipped": int, "applied": int, "stopped_early": bool}
    """
    pending = load_pending_proposals()
    summary = {
        "pending": len(pending),
        "approved": 0, "rejected": 0, "skipped": 0, "deferred": 0,
        "applied": 0, "stopped_early": False,
    }

    if not pending:
        print_fn("  No pending evolution proposals.")
        return summary

    print_fn(f"  {len(pending)} pending proposal(s).")

    if list_only:
        for i, p in enumerate(pending, 1):
            if p["kind"] == "profile":
                desc = f"{p['payload']['field_path']} -> {p['payload']['proposed_value']!r}"
            else:
                desc = p["payload"]["content"][:120]
            print_fn(f"    {i}. [{p['kind']}] hash={p['hash']}  {desc}")
        return summary

    if auto_skip:
        print_fn(f"  Auto-deferring {len(pending)} proposal(s) "
                 "(they remain PENDING for future review)...")
        for p in pending:
            # Phase 2 (goal H): defer is NOT an actioned state — these
            # proposals stay pending and will re-appear next review.
            log_decision(p, decision="defer", applied=False,
                         message="auto-deferred via auto_skip=True")
        summary["deferred"] = len(pending)
        return summary

    to_review = pending if max_to_review is None else pending[:max_to_review]
    if max_to_review is not None and len(pending) > max_to_review:
        print_fn(f"  (reviewing first {max_to_review}; run again to see the rest)")

    for i, prop in enumerate(to_review, 1):
        for line in _format_proposal(i, len(to_review), prop):
            print_fn(line)

        # Prompt loop
        decision = None
        while decision is None:
            try:
                ans = input_fn("  [a]pprove / [r]eject / [s]kip / [q]uit > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                decision = "q"
                break
            if ans in ("a", "approve"):
                decision = "a"
            elif ans in ("r", "reject"):
                decision = "r"
            elif ans in ("s", "skip", ""):
                decision = "s"
            elif ans in ("q", "quit", "exit"):
                decision = "q"
            else:
                print_fn("    (please type a, r, s, or q)")

        if decision == "q":
            print_fn("\n  Quitting review. Remaining proposals stay pending for next time.")
            summary["stopped_early"] = True
            break

        if decision == "a":
            if prop["kind"] == "profile":
                ok, msg = apply_profile_update(prop["payload"])
            elif prop["kind"] == "memory":
                ok, msg = apply_memory_update(prop["payload"])
            else:
                ok, msg = False, f"Unknown kind: {prop['kind']}"
            status = "APPROVED + APPLIED" if ok else "APPROVED but APPLY FAILED"
            print_fn(f"  {status}: {msg}")
            log_decision(prop, decision="approve", applied=ok, message=msg)
            summary["approved"] += 1
            if ok:
                summary["applied"] += 1
        elif decision == "r":
            print_fn("  REJECTED. Logged; will not be re-shown.")
            log_decision(prop, decision="reject", applied=False,
                         message="user rejected")
            summary["rejected"] += 1
        else:
            print_fn("  SKIPPED. Will appear again next time you run review.")
            summary["skipped"] += 1

    print_fn("")
    print_fn("=" * 78)
    print_fn(
        f"  Summary: approved={summary['approved']}  applied={summary['applied']}"
        f"  rejected={summary['rejected']}  skipped={summary['skipped']}"
        f"  deferred={summary['deferred']}"
        + ("  (stopped early)" if summary["stopped_early"] else "")
    )
    print_fn("=" * 78)
    return summary
