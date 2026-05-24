"""
Session-scoped folder-preference store.

Preferences are keyed by ``(session_id, agent_name)`` — explicitly NOT
global last-choice files.  The controller is expected to allocate a
fresh ``session_id`` per task; the store is reset for new sessions so a
preference set during one task cannot leak into another.

Persistence model (defect 29)
-----------------------------
The store is **in-memory only** for the lifetime of the Python process.
There is intentionally NO disk persistence in this module.

Cross-process resumption is the CONTROLLER'S responsibility: it must
hold on to the ``session_id`` returned by a paused
:func:`core.orchestrator.run_aura_core` call and pass it back on the
next call.  The same Python process that paused must resume.

If you need durable cross-process persistence, add it deliberately at a
higher layer (e.g. write the controller's transcript to disk) — DO NOT
expect this module to do it.  An earlier version of this docstring
implied an optional disk-persistence parameter on :func:`set_preference`;
that claim was incorrect and has been removed so signatures, behaviour,
and documentation now agree exactly.

Default prompt policy (defect 1)
--------------------------------
The optional-local-folder prompt is **ON by default** when an agent
participates in a session.  Operators can silence it explicitly via:

  * ``context["disable_local_folder_prompt"] = True``    (per-run override), or
  * env var ``AURA_LOCAL_FOLDERS_DISABLED=1``            (process-wide override).

The legacy opt-in flags (``ask_local_folders``,
``local_folder_options.ask``, ``AURA_LOCAL_FOLDERS_ENABLED``) are still
honoured so existing callers and tests keep working — but they are no
longer required to activate the prompt.

API
---
    new_session_id(seed=None) -> str
    get_preference(session_id, agent) -> FolderPreference
    set_preference(session_id, agent, *, use_local_folder, folder_path,
                   ask_later=False) -> FolderPreference
    needs_prompt(session_id, agent) -> bool
    build_prompt_request(session_id, agent) -> NeedsUserInputRequest
    absorb_user_response(session_id, agent, response) -> FolderPreference | None
    is_opt_in_enabled(context) -> bool
    clear_session(session_id) -> None
"""
from __future__ import annotations

import os
import threading
import uuid

from .models import FolderPreference, NeedsUserInputRequest


VALID_AGENTS: frozenset[str] = frozenset({"research_scout", "patent_intelligence"})

# (session_id, agent) → FolderPreference
_STORE: dict[tuple[str, str], FolderPreference] = {}
_LOCK = threading.RLock()


def new_session_id(seed: str | None = None) -> str:
    """Generate a fresh session_id.  Tests pass ``seed`` for determinism."""
    if seed:
        return f"sess-{seed}"
    return f"sess-{uuid.uuid4().hex[:12]}"


def get_preference(session_id: str, agent: str) -> FolderPreference:
    """Return the recorded preference or an ``unset`` default."""
    if not session_id or agent not in VALID_AGENTS:
        return FolderPreference(state="unset", session_id=session_id, agent=agent)
    with _LOCK:
        pref = _STORE.get((session_id, agent))
    if pref is not None:
        return pref
    return FolderPreference(state="unset", session_id=session_id, agent=agent)


def set_preference(
    session_id: str,
    agent: str,
    *,
    use_local_folder: bool,
    folder_path: str | None,
    ask_later: bool = False,
) -> FolderPreference:
    """Record a preference.

    Behaviour matrix:
      * ``ask_later=True`` (regardless of other args) → state="ask_later",
        empty path, no validation_error.  Next call re-prompts.
      * ``use_local_folder=True`` and a non-empty folder_path → state="enabled".
      * ``use_local_folder=True`` and BLANK folder_path → DEFECT 21:
        we do NOT silently demote to "disabled".  state stays at
        "ask_later" with ``validation_error`` set so the prompt re-fires.
      * ``use_local_folder=False`` → state="disabled".
    """
    if agent not in VALID_AGENTS:
        raise ValueError(f"Unknown agent for folder preference: {agent!r}")
    if not session_id:
        raise ValueError("session_id is required for folder preferences")

    validation_error = ""
    if ask_later:
        state = "ask_later"
        path = ""
    elif use_local_folder:
        path = (folder_path or "").strip()
        if not path:
            # Defect 21: do NOT silently disable.  Surface the validation
            # error and keep the preference in ask_later so the controller
            # re-prompts on the next invocation.
            state = "ask_later"
            validation_error = (
                "You said yes to a local folder but supplied an empty "
                "folder_path. Please provide a real folder path or "
                "answer no."
            )
        else:
            state = "enabled"
    else:
        state = "disabled"
        path = ""

    pref = FolderPreference(
        state=state,
        folder_path=path,
        session_id=session_id,
        agent=agent,
        validation_error=validation_error,
    )
    with _LOCK:
        _STORE[(session_id, agent)] = pref
    return pref


def needs_prompt(session_id: str, agent: str) -> bool:
    """True iff the user has not yet recorded a (non-ask_later, non-invalid)
    answer."""
    pref = get_preference(session_id, agent)
    if pref.state in ("unset", "ask_later"):
        return True
    # Defect 21: an "enabled" pref with an empty folder_path is invalid; keep
    # re-prompting.  set_preference normally prevents this, but a stale
    # record might still exist.
    if pref.state == "enabled" and not pref.folder_path:
        return True
    return False


def clear_session(session_id: str) -> None:
    """Drop ALL preferences for a session.  Used by tests + CLI."""
    if not session_id:
        return
    with _LOCK:
        for key in list(_STORE.keys()):
            if key[0] == session_id:
                _STORE.pop(key, None)


def _agent_prompt_message(agent: str, *, validation_error: str = "") -> str:
    if agent == "research_scout":
        base = (
            "Would you like to provide a folder containing local literature "
            "PDFs or Word documents for analysis alongside literature search "
            "results?"
        )
    elif agent == "patent_intelligence":
        base = (
            "Would you like to provide a folder containing patent PDFs or "
            "Word documents for analysis alongside patent search results?"
        )
    else:
        base = "Would you like to provide a folder of local documents?"
    if validation_error:
        return f"{validation_error}\n\n{base}"
    return base


def build_prompt_request(session_id: str, agent: str) -> NeedsUserInputRequest:
    """Build the structured ``needs_user_input`` request the controller
    surfaces to the UI / CLI.  When the previous response failed validation
    (defect 21), the validation_error is prepended to the message so the
    user sees what to fix."""
    pref = get_preference(session_id, agent)
    return NeedsUserInputRequest(
        target_agent=agent,
        session_id=session_id,
        message=_agent_prompt_message(
            agent, validation_error=pref.validation_error,
        ),
    )


# Defect 1: prompts are ON by default.
def is_opt_in_enabled(context: dict | None) -> bool:
    """Return True when the controller wants the folder-prompt path active.

    Default-ON policy.  Explicit overrides:
      * ``context["disable_local_folder_prompt"] = True`` → off (per-run)
      * env ``AURA_LOCAL_FOLDERS_DISABLED=1``             → off (process-wide)

    Legacy opt-in flags are still honoured for callers that set them
    explicitly, but they are no longer required to enable prompts.
    """
    # Per-run explicit disable.
    if isinstance(context, dict):
        if context.get("disable_local_folder_prompt"):
            return False
        opt = context.get("local_folder_options")
        if isinstance(opt, dict) and opt.get("ask") is False:
            return False
    # Process-wide explicit disable.
    if os.getenv("AURA_LOCAL_FOLDERS_DISABLED", "0") == "1":
        return False
    return True


def absorb_user_response(
    session_id: str,
    agent: str,
    response: dict | None,
) -> FolderPreference | None:
    """Record a controller-collected response.

    ``response`` shape (any of these forms is accepted):

        {"use_local_folder": True,  "folder_path": "/path/to/papers"}
        {"use_local_folder": False, "folder_path": null}
        {"ask_later": True}

    Returns the resulting :class:`FolderPreference`, or ``None`` if the
    response was not a dict.  When the response is invalid (defect 21),
    the returned preference carries ``state="ask_later"`` with a populated
    ``validation_error``.
    """
    if not isinstance(response, dict):
        return None
    ask_later = bool(response.get("ask_later"))
    use_local = bool(response.get("use_local_folder"))
    folder_path = response.get("folder_path") or ""
    if not isinstance(folder_path, str):
        folder_path = ""
    return set_preference(
        session_id,
        agent,
        use_local_folder=use_local,
        folder_path=folder_path,
        ask_later=ask_later,
    )
