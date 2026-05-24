import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config


def ensure_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()


def append_jsonl(path: Path, record: dict) -> None:
    ensure_file(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def read_jsonl(path: Path, limit: int = 100) -> list[dict]:
    ensure_file(path)
    records: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records[-limit:]


def save_memory(kind: str, content: str, metadata: dict | None = None) -> None:
    record = {
        "kind": kind,
        "content": content,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    append_jsonl(config.MEMORY_PATH, record)


def save_reflection(record: dict) -> None:
    record["created_at"] = datetime.now(timezone.utc).isoformat()
    append_jsonl(config.REFLECTION_PATH, record)


def retrieve_relevant_memory(query: str, limit: int = 8) -> list[dict]:
    all_records = read_jsonl(config.MEMORY_PATH, limit=200)
    query_lower = query.lower()
    query_tokens = set(query_lower.split())

    def score(rec: dict) -> int:
        text = (rec.get("content", "") + " " + json.dumps(rec.get("metadata", {}))).lower()
        return sum(1 for token in query_tokens if token in text)

    scored = [(score(r), r) for r in all_records if score(r) > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]
