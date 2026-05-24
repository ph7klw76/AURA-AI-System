import json
from datetime import datetime, timezone
from pathlib import Path

import config
from core.memory import ensure_file

APPROVAL_REQUIRED_PATTERNS = [
    # External communication — SEND-context only (drafting is allowed)
    "send email",
    "send an email",
    "send the email",
    "send a message",
    "send them",
    "send out",
    "send it to",          # "...and send it to the collaborator"
    "send this to",
    "send invitation",
    "send invitations",
    "contact author",
    "contact authors",
    "contact researcher",
    "contact collaborator",
    "contact collaborators",
    "contact professor",
    "contact company",
    "contact the author",
    "contact the collaborator",
    "reach out to",        # "reach out to investors / collaborators"
    "schedule meeting",
    "schedule a meeting",
    # Publishing
    "publish",
    "post on",             # "post on Twitter", "post on LinkedIn"
    "post to",             # "post to my feed"
    "post a tweet",
    "tweet ",
    "twitter post",
    "press release",
    # External submission
    "submit grant",
    "submit proposal",
    "submit the grant",
    "submit the proposal",
    "submit a grant",
    "submit a proposal",
    "submit it to",
    "submit to the funder",
    "submit to journal",
    "submit to the journal",
    # Profile/identity changes
    "modify research_profile",
    "update profile",
    # Destructive data operations
    "delete file",
    "delete the file",
    "delete files",
    "delete the files",
    "delete the",          # "delete the bad raw files", "delete the corrupt data"
    "delete raw",
    "delete data",
    "delete bad",
    "remove file",
    "remove raw",
    "overwrite raw",
    "overwrite the",
    "wipe data",
    # External sharing
    "share data",
    "share private data",
    "share confidential",
    "upload confidential",
    "upload",
    # Financial / legal / commercial actions
    "make financial",
    "financial decision",
    "official commitment",
    "represent me",
    "represent the institution",
    # --- Wave 3: never-autonomous commercialization actions ---
    "sign agreement",
    "sign the agreement",
    "sign the licensing",       # "Sign the licensing agreement..."
    "sign the contract",
    "sign nda",
    "sign the nda",
    "sign an nda",              # "Sign an NDA with..."
    "sign a nda",
    "sign contract",
    "sign a contract",
    "execute license",
    "license agreement",
    "file patent",
    "file a patent",
    "file the patent",
    "file provisional",
    "register company",
    "register the company",
    "register a company",
    "incorporate company",
    "incorporate the",          # "Incorporate the OLED startup company..."
    "incorporate a company",
    "contact investor",
    "contact investors",
    "reach out to investors",
    "approach investors",
    "raise money",
    "raise funding",
    "accept funding",
    "take funding",
    "invest money",
    "invest in",
    "make an investment",
    "make investment",
]

NEVER_ALLOWED_ACTIONS = [
    "send_email",
    "submit_grant",
    "publish_content",
    "delete_important_files",
    "financial_transaction",
    "represent_officially",
]

ALWAYS_ALLOWED_ACTIONS = [
    "search_papers",
    "score_papers",
    "generate_brief_draft",
    "generate_gap_analysis_draft",
    "save_local_memory",
    "save_local_report",
    "suggest_profile_updates",
]


def requires_human_approval(user_input: str) -> tuple[bool, str]:
    lower = user_input.lower()
    for pattern in APPROVAL_REQUIRED_PATTERNS:
        if pattern in lower:
            return True, f"Input matches approval-required pattern: '{pattern}'"
    return False, ""


def is_action_allowed(action_name: str) -> bool:
    if action_name in NEVER_ALLOWED_ACTIONS:
        return False
    return True


def log_approval_event(event: dict) -> None:
    event["logged_at"] = datetime.now(timezone.utc).isoformat()
    ensure_file(config.APPROVAL_LOG_PATH)
    with open(config.APPROVAL_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


# ---------------------------------------------------------------------------
# Phase 2 ACTION_POLICY — single source of truth for what specialists may do
# without approval, with approval, or never.
#
# Policy values:
#   auto              — orchestrator may surface/use this action without prompt
#   approval_required — user must explicitly approve in chat before any execution
#   never             — system refuses regardless of approval (financial, legal, etc.)
# ---------------------------------------------------------------------------

ACTION_POLICY: dict[str, str] = {
    # auto — fully autonomous, drafts and local computation
    "think":                   "auto",
    "search_papers":           "auto",
    "score_papers":            "auto",
    "draft_text":              "auto",
    "draft_email":             "auto",
    "draft_post":              "auto",
    "draft_proposal":          "auto",
    "draft_quiz":              "auto",
    "draft_outline":           "auto",
    "analyze_local_data":      "auto",
    "generate_report":         "auto",
    "save_local_memory":       "auto",
    "save_local_report":       "auto",
    "suggest_collaborators":   "auto",
    "suggest_profile_update":  "auto",
    "suggest_experiment":      "auto",
    "explain_concept":         "auto",

    # approval_required — explicit user approval needed in chat before execution
    "modify_profile":          "approval_required",
    "send_email":              "approval_required",
    "publish_content":         "approval_required",
    "submit_proposal":         "approval_required",
    "submit_grant":            "approval_required",
    "delete_file":             "approval_required",
    "modify_data_file":        "approval_required",
    "share_data_externally":   "approval_required",
    "contact_author":          "approval_required",

    # never — system refuses regardless of user approval
    "make_financial_decision": "never",
    "execute_trade":           "never",
    "official_commitment":     "never",
    "represent_user_legally":  "never",
    "file_patent":             "never",     # Wave 3 — must always go through human IP counsel
    "incorporate_company":     "never",     # Wave 3 — legal incorporation never autonomous
    "register_company":        "never",     # Wave 3 — same
    "sign_agreement":          "never",     # Wave 3 — never sign on user's behalf
    "sign_nda":                "never",     # Wave 3
    "accept_funding":          "approval_required",   # requires explicit user step
    "contact_investors":       "approval_required",   # requires explicit user step
    "schedule_meeting":        "approval_required",
    "send_invitation":         "approval_required",
}


def classify_action(action_class: str) -> str:
    """Return policy ('auto', 'approval_required', 'never') for an action class.

    Unknown action classes default to 'approval_required' — fail-safe for any
    Phase 2 specialist that proposes an action class not yet registered.
    """
    return ACTION_POLICY.get(action_class, "approval_required")


def normalize_action_classes(actions: list) -> list[dict]:
    """Return ``actions`` as a list of dicts, each with an inferred
    ``action_class`` populated — WITHOUT applying ACTION_POLICY gating.

    This is the normalization half of :func:`gate_recommended_actions`,
    extracted so the orchestrator can run it BEFORE the registry-level
    external-action gate.  Previously, free-text (string) actions and
    weakly-structured dicts (no ``action_class``) reached
    ``_enforce_external_action_gate`` with an empty class and therefore
    slipped past the ``can_create_external_action=False`` restriction.
    Inferring the class first closes that bypass.

    Accepts strings and dicts; anything else is dropped.
    """
    out: list[dict] = []
    for raw in actions or []:
        if isinstance(raw, dict):
            action = dict(raw)
            cls = str(action.get("action_class") or "").strip()
            if not cls:
                desc = str(action.get("description") or "")
                cls = _infer_action_class_from_text(desc.lower())
            action["action_class"] = cls
            out.append(action)
        elif isinstance(raw, str):
            cls = _infer_action_class_from_text(raw.lower())
            out.append({"description": raw, "action_class": cls, "rationale": ""})
        # Non-string / non-dict entries are dropped (cannot be gated safely).
    return out


def gate_recommended_actions(
    actions: list,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Apply ACTION_POLICY to a list of recommended actions.

    Accepts:
      * string actions (legacy) — action_class is inferred from description
      * dict actions WITHOUT an action_class — inferred from description
      * dict actions WITH an action_class — used as-is

    Returns ``(kept, requires_approval, blocked)``.

    Defect 7 + 8: when ``action_class`` is missing/empty/unknown, the
    description text is run through :func:`_infer_action_class_from_text`,
    which now recognises every policy-sensitive keyword family defined in
    ``ACTION_POLICY`` (including Wave-3 commercialization actions like
    ``file_patent``, ``incorporate_company``, ``sign_nda``, ``accept_funding``,
    ``contact_investors``, ``schedule_meeting``, ``send_invitation``).  If
    the classifier still cannot find a match, the unknown-action fallback
    in ``classify_action`` routes the action to ``approval_required`` so it
    never silently inherits ``auto`` (``draft_text``) status.
    """
    kept: list[dict] = []
    needs_approval: list[dict] = []
    blocked: list[dict] = []

    for raw in actions or []:
        if isinstance(raw, dict):
            action = dict(raw)
            description = str(action.get("description") or "")
            cls = str(action.get("action_class") or "").strip()
            # Defect 7: empty/missing action_class must be inferred from
            # the description text — do NOT default to draft_text here.
            if not cls:
                cls = _infer_action_class_from_text(description.lower())
                action["action_class"] = cls
        else:
            text = str(raw)
            cls = _infer_action_class_from_text(text.lower())
            action = {"description": text, "action_class": cls, "rationale": ""}

        policy = classify_action(cls or "approval_required")
        action["policy"] = policy

        if policy == "never":
            blocked.append(action)
            continue
        kept.append(action)
        if policy == "approval_required":
            needs_approval.append(action)

    return kept, needs_approval, blocked


# Defect 8: the legacy classifier covered only ~6 keyword families.  The
# expanded table mirrors every entry in ACTION_POLICY that has a recognisable
# verb form in natural language, ordered LONGEST-PHRASE-FIRST so specific
# multi-word matches win over short generic ones (e.g. "send invitation"
# beats "send" → "send_email").  This list is the single source of truth for
# text→class mapping; ACTION_POLICY remains the single source of truth for
# class→policy mapping.
_LEGACY_KEYWORD_TO_CLASS: list[tuple[str, str]] = [
    # --- Wave 3 commercialization (high-risk; longest phrases first) -------
    ("file a patent",            "file_patent"),
    ("file the patent",          "file_patent"),
    ("file provisional",         "file_patent"),
    ("file patent",              "file_patent"),
    ("patent filing",            "file_patent"),
    ("incorporate the company",  "incorporate_company"),
    ("incorporate a company",    "incorporate_company"),
    ("incorporate company",      "incorporate_company"),
    ("incorporate the ",         "incorporate_company"),     # "incorporate the OLED startup company"
    ("incorporate a ",           "incorporate_company"),
    ("incorporating the company","incorporate_company"),
    ("register a company",       "register_company"),
    ("register the company",     "register_company"),
    ("register company",         "register_company"),
    ("form a company",           "register_company"),
    ("sign the agreement",       "sign_agreement"),
    ("sign an agreement",        "sign_agreement"),
    ("sign agreement",           "sign_agreement"),
    ("sign the licensing",       "sign_agreement"),
    ("sign licensing",           "sign_agreement"),
    ("sign the contract",        "sign_agreement"),
    ("sign a contract",          "sign_agreement"),
    ("sign contract",            "sign_agreement"),
    ("execute license",          "sign_agreement"),
    ("license agreement",        "sign_agreement"),
    ("sign the nda",             "sign_nda"),
    ("sign an nda",              "sign_nda"),
    ("sign a nda",               "sign_nda"),
    ("sign nda",                 "sign_nda"),
    ("accept funding",           "accept_funding"),
    ("accept the funding",       "accept_funding"),
    ("take funding",             "accept_funding"),
    ("raise funding",            "accept_funding"),
    ("raise money",              "accept_funding"),
    ("contact the investor",     "contact_investors"),
    ("contact investor",         "contact_investors"),
    ("contact investors",        "contact_investors"),
    ("reach out to investors",   "contact_investors"),
    ("approach investors",       "contact_investors"),
    ("pitch to investors",       "contact_investors"),
    ("send a pitch deck",        "contact_investors"),

    # --- External communication --------------------------------------------
    ("send invitation to",       "send_invitation"),
    ("send invitations",         "send_invitation"),
    ("send invitation",          "send_invitation"),
    ("send the invitation",      "send_invitation"),
    ("schedule the meeting",     "schedule_meeting"),
    ("schedule a meeting",       "schedule_meeting"),
    ("schedule meeting",         "schedule_meeting"),
    ("book a meeting",           "schedule_meeting"),
    ("set up a meeting",         "schedule_meeting"),
    ("contact author",           "contact_author"),
    ("contact authors",          "contact_author"),
    ("contact the author",       "contact_author"),
    ("contact the collaborator", "contact_author"),
    ("contact collaborator",     "contact_author"),
    ("contact collaborators",    "contact_author"),
    ("contact professor",        "contact_author"),
    ("reach out to the author",  "contact_author"),
    ("reach out to author",      "contact_author"),
    ("send an email",            "send_email"),
    ("send the email",           "send_email"),
    ("send email",               "send_email"),
    ("email the author",         "send_email"),
    ("email the collaborator",   "send_email"),
    ("send a message",           "send_email"),
    ("email ",                   "send_email"),     # trailing space — generic catch

    # --- Publishing --------------------------------------------------------
    ("publish a post",           "publish_content"),
    ("publish on linkedin",      "publish_content"),
    ("post on linkedin",         "publish_content"),
    ("post on twitter",          "publish_content"),
    ("post a tweet",             "publish_content"),
    ("tweet ",                   "publish_content"),
    ("press release",            "publish_content"),
    ("publish",                  "publish_content"),
    ("post ",                    "publish_content"),     # generic catch

    # --- Submission --------------------------------------------------------
    ("submit a grant",           "submit_grant"),
    ("submit the grant",         "submit_grant"),
    ("submit grant",             "submit_grant"),
    ("submit a proposal",        "submit_proposal"),
    ("submit the proposal",      "submit_proposal"),
    ("submit proposal",          "submit_proposal"),
    ("submit to journal",        "submit_proposal"),
    ("submit to the journal",    "submit_proposal"),

    # --- Profile / data ----------------------------------------------------
    ("modify research_profile",  "modify_profile"),
    ("modify profile",           "modify_profile"),
    ("update profile",           "modify_profile"),
    ("update research_profile",  "modify_profile"),
    ("share data externally",    "share_data_externally"),
    ("share private data",       "share_data_externally"),
    ("share confidential",       "share_data_externally"),
    ("share data",               "share_data_externally"),
    ("upload private",           "share_data_externally"),
    ("delete the file",          "delete_file"),
    ("delete file",              "delete_file"),
    ("delete files",             "delete_file"),
    ("delete raw",               "delete_file"),
    ("delete data",              "delete_file"),
    ("delete ",                  "delete_file"),     # generic catch
    ("remove file",              "delete_file"),
    ("overwrite raw",            "modify_data_file"),
    ("overwrite the",            "modify_data_file"),
    ("modify the dataset",       "modify_data_file"),

    # --- Financial / legal --------------------------------------------------
    ("make financial",           "make_financial_decision"),
    ("financial decision",       "make_financial_decision"),
    ("execute trade",            "execute_trade"),
    ("represent the institution","represent_user_legally"),
    ("represent me legally",     "represent_user_legally"),
    ("official commitment",      "official_commitment"),

    # --- Safe defaults (drafts) — last so they don't shadow risky verbs ----
    ("draft an email",           "draft_email"),
    ("draft email",              "draft_email"),
    ("draft a post",             "draft_post"),
    ("draft post",               "draft_post"),
    ("draft a proposal",         "draft_proposal"),
    ("draft proposal",           "draft_proposal"),
    ("draft a quiz",             "draft_quiz"),
    ("draft quiz",               "draft_quiz"),
    ("draft outline",            "draft_outline"),
    ("draft an outline",         "draft_outline"),
    ("explain ",                 "explain_concept"),
    ("summarise",                "draft_text"),
    ("summarize",                "draft_text"),
    ("review the",               "draft_text"),
    ("note: ",                   "draft_text"),
]


def _infer_action_class_from_text(text: str) -> str:
    """Best-effort mapping for free-text action descriptions.

    Returns a known ACTION_POLICY key when a keyword is recognised, else
    ``""`` so ``classify_action`` falls back to ``approval_required`` —
    the fail-closed default required by defect 7.
    """
    text = (text or "").lower()
    for kw, cls in _LEGACY_KEYWORD_TO_CLASS:
        if kw in text:
            return cls
    return ""  # unknown — caller falls back to approval_required
