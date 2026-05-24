"""
Persistent cache of extracted ``PatentProfile`` objects.

The rigorous patent pipeline (``core.patent_rigor``) issues one LLM call
per patent for feature extraction.  On a 14-patent corpus that's
~140 seconds of latency on deepseek-v4-flash and routinely trips
patent_intelligence's soft timeout.  In practice the input content
rarely changes between runs — the same local PDFs and the same
top_patent_records reappear — so the right fix is a content-addressed
cache:

    key   = (document_id, sha256(body)[:16], schema_version)
    value = serialized PatentProfile dict + retrieved_at timestamp

The cache is intentionally simple: one JSON file per key under
``data/patent_rigor_cache/``.  Atomic rename + tmp file ensures partial
writes never corrupt entries.  No TTL — entries are invalidated only
when the body's SHA changes.

Honesty:
  * Cached profiles are returned VERBATIM with their original
    ``uncertainties`` and ``evidence`` snippets.
  * The cache never invents or modifies content.
  * A corrupt cache entry is silently ignored (treated as a miss),
    not raised.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Iterable

from .patent_rigor import PatentProfile


# Bump when the PatentProfile schema or extraction prompt changes in a
# way that invalidates older cache entries.
PROFILE_SCHEMA_VERSION: int = 1


def _default_cache_dir() -> Path:
    try:
        import config
        base = Path(getattr(config, "BASE_DIR", Path.cwd()))
    except Exception:
        base = Path.cwd()
    return base / "data" / "patent_rigor_cache"


def compute_body_hash(body: str) -> str:
    """16-hex-char prefix of sha256 — sufficient for cache identity."""
    if not body:
        return "0" * 16
    return hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()[:16]


def _safe_key_component(s: str) -> str:
    """Make a string safe for use in a filename (Windows + POSIX)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(s or ""))[:48]
    return cleaned or "x"


class PatentProfileCache:
    """File-system cache of ``PatentProfile`` objects.

    Thread-safe via atomic-rename writes (safe across multiple AURA
    processes running concurrently).  Reads are not locked — a partially
    written file is treated as a miss.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = (
            Path(cache_dir) if cache_dir is not None else _default_cache_dir()
        )
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Read-only filesystem — degrade to no-op cache.
            pass
        self._stats = {"hits": 0, "misses": 0, "writes": 0, "errors": 0}

    @classmethod
    def default(cls) -> "PatentProfileCache":
        return cls()

    # ------------------------------------------------------------------ keys
    def _key_path(self, document_id: str, body_hash: str) -> Path:
        return self.cache_dir / (
            f"{_safe_key_component(document_id)}__{body_hash}"
            f"__v{PROFILE_SCHEMA_VERSION}.json"
        )

    # ---------------------------------------------------------------- get/put
    def get(
        self, document_id: str, body_hash: str,
    ) -> PatentProfile | None:
        """Return the cached profile or None on miss / corruption."""
        path = self._key_path(document_id, body_hash)
        if not path.exists():
            self._stats["misses"] += 1
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self._stats["errors"] += 1
            self._stats["misses"] += 1
            return None
        profile_dict = payload.get("profile")
        if not isinstance(profile_dict, dict):
            self._stats["misses"] += 1
            return None
        try:
            profile = PatentProfile.model_validate(profile_dict)
        except Exception:
            self._stats["errors"] += 1
            self._stats["misses"] += 1
            return None
        self._stats["hits"] += 1
        return profile

    def put(
        self,
        document_id: str,
        body_hash: str,
        profile: PatentProfile,
    ) -> None:
        """Write the profile atomically.  Silently no-op on I/O error."""
        path = self._key_path(document_id, body_hash)
        payload = {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "document_id": document_id,
            "body_hash": body_hash,
            "cached_at": time.time(),
            "profile": profile.model_dump(),
        }
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(
                prefix=".tmp_", suffix=".json", dir=str(self.cache_dir),
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
                raise
            self._stats["writes"] += 1
        except Exception:
            self._stats["errors"] += 1

    # ---------------------------------------------------------------- bulk
    def partition_corpus(
        self, corpus: Iterable[dict],
    ) -> tuple[list[tuple[dict, str]], list[tuple[dict, str, PatentProfile]]]:
        """Split a corpus into (to-extract, cached) lists.

        Returns:
            misses: list of (corpus_entry, body_hash)
            hits:   list of (corpus_entry, body_hash, cached_profile)
        """
        misses: list[tuple[dict, str]] = []
        hits: list[tuple[dict, str, PatentProfile]] = []
        for entry in corpus:
            if not isinstance(entry, dict):
                continue
            doc_id = str(
                entry.get("patent_id")
                or entry.get("document_id")
                or "(unknown)"
            )[:60]
            body = str(entry.get("body", ""))
            body_hash = compute_body_hash(body)
            cached = self.get(doc_id, body_hash)
            if cached is not None:
                hits.append((entry, body_hash, cached))
            else:
                misses.append((entry, body_hash))
        return misses, hits

    # ---------------------------------------------------------------- stats
    @property
    def stats(self) -> dict:
        return dict(self._stats)

    def clear(self) -> int:
        """Remove every cache file.  Returns count removed."""
        n = 0
        for p in self.cache_dir.glob("*.json"):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
        return n
