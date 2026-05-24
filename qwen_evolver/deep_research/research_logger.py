"""
Research Logger — stores run detail and reflection.
"""

from __future__ import annotations

from pathlib import Path

import config
from core.path_safety import safe_mission_path
from .schemas import ResearchReflection

LOGS_DIR = config.BASE_DIR / "data" / "deep_research" / "reflections"

def save_reflection(reflection: ResearchReflection) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    # Fail closed on traversal-style mission_id (path-safety).
    path = safe_mission_path(LOGS_DIR, reflection.mission_id, "_reflection.json")
    path.write_text(reflection.model_dump_json(indent=2), encoding="utf-8")
