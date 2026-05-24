"""
Source Reader — fetches and normalises web content for evidence extraction.
"""

from __future__ import annotations

import re
from pathlib import Path
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

import config
from core.path_safety import validate_mission_id, safe_path
from .schemas import SourceRecord, SearchResult

DATA_DIR = config.BASE_DIR / "data" / "deep_research" / "sources"


def _sanitize_filename(text: str) -> str:
    return re.sub(r"[^\w\-_. ]", "_", text)

def fetch_source(result: SearchResult, mission_id: str) -> SourceRecord:
    now = datetime.now(timezone.utc).isoformat()
    # Fail closed on traversal-style mission_id before any fs write.
    mission_id = validate_mission_id(mission_id)
    source_id = result.result_id
    record = SourceRecord(
        source_id=source_id,
        title=result.title,
        url=result.url,
        provider=result.provider,
        retrieved_at=now,
        status="fetched",
    )
    try:
        resp = requests.get(result.url, timeout=10, headers={"User-Agent": "AURA-Research/1.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        text = re.sub(r"\n\s*\n", "\n", text)
        text = re.sub(r" +", " ", text)
        truncated = text[:8000]
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        # source_id + title are also untrusted — sanitize both, then
        # assert containment via safe_path (defends against traversal in
        # any component).
        fname = (
            f"{mission_id}_{_sanitize_filename(str(source_id)[:40])}_"
            f"{_sanitize_filename(result.title[:30])}.txt"
        )
        path = safe_path(DATA_DIR, fname)
        path.write_text(text, encoding="utf-8")
        record.inline_text = truncated
        record.raw_text_path = str(path.relative_to(config.BASE_DIR))
    except Exception:
        record.status = "failed"
    return record
