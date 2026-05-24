"""
Evidence store: JSONL persistence per mission.
"""

from __future__ import annotations

from pathlib import Path

import config
from core.path_safety import safe_mission_path
from .schemas import EvidencePack

EVIDENCE_DIR = config.BASE_DIR / "data" / "deep_research" / "evidence"

def save_evidence_pack(pack: EvidencePack) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    # Fail closed on traversal-style mission_id (path-safety).
    path = safe_mission_path(EVIDENCE_DIR, pack.mission_id, "_evidence.jsonl")
    with path.open("a", encoding="utf-8") as f:
        f.write(pack.model_dump_json() + "\n")

def load_evidence_pack(mission_id: str) -> EvidencePack | None:
    path = safe_mission_path(EVIDENCE_DIR, mission_id, "_evidence.jsonl")
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return None
    return EvidencePack.model_validate_json(lines[-1])
