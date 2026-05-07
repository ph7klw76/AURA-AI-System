import json
from datetime import datetime, timezone
from pathlib import Path

import config
from core.memory import ensure_file

APPROVAL_REQUIRED_PATTERNS = [
    "send email",
    "email to",
    "contact author",
    "contact researcher",
    "publish",
    "submit grant",
    "submit proposal",
    "modify research_profile",
    "update profile",
    "delete file",
    "share data",
    "upload",
    "make financial",
    "financial decision",
    "official commitment",
    "represent me",
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
