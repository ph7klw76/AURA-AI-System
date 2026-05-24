"""Configuration for the optional LangGraph Memory Service adapter.

All config is environment-variable driven.  The service is disabled by default
(AURA_MEMORY_SERVICE_ENABLED=0), so existing AURA behaviour is unchanged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


@dataclass
class MemoryServiceConfig:
    """Immutable configuration for the memory service adapter."""

    enabled: bool = False
    service_url: str = "http://localhost:2024"
    write_mode: str = "propose_only"  # disabled | propose_only | approved_only
    require_review_for_procedural: bool = True
    require_verifier_for_evidence: bool = True
    max_retrieved: int = 8
    namespace_prefix: str = "aura"
    audit_log_path: str = "data/memory_service.jsonl"
    pending_file_path: str = "data/memory_candidates.jsonl"
    timeout_seconds: int = 30
    fail_closed: bool = False

    @property
    def write_disabled(self) -> bool:
        return self.write_mode == "disabled" or not self.enabled

    @property
    def propose_only(self) -> bool:
        return self.enabled and self.write_mode == "propose_only"

    @property
    def approved_only(self) -> bool:
        return self.enabled and self.write_mode == "approved_only"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_memory_service_config() -> MemoryServiceConfig:
    """Load memory-service configuration from environment variables."""
    return MemoryServiceConfig(
        enabled=_env_bool("AURA_MEMORY_SERVICE_ENABLED", True),
        service_url=os.environ.get("AURA_MEMORY_SERVICE_URL", "http://localhost:2024"),
        write_mode=os.environ.get("AURA_MEMORY_WRITE_MODE", "propose_only"),
        require_review_for_procedural=_env_bool(
            "AURA_MEMORY_REQUIRE_REVIEW_FOR_PROCEDURAL", True,
        ),
        require_verifier_for_evidence=_env_bool(
            "AURA_MEMORY_REQUIRE_VERIFIER_FOR_EVIDENCE", True,
        ),
        max_retrieved=_env_int("AURA_MEMORY_MAX_RETRIEVED", 8),
        namespace_prefix=os.environ.get("AURA_MEMORY_NAMESPACE_PREFIX", "aura"),
        audit_log_path=os.environ.get(
            "AURA_MEMORY_AUDIT_LOG", "data/memory_service.jsonl",
        ),
        pending_file_path=os.environ.get(
            "AURA_MEMORY_PENDING_FILE", "data/memory_candidates.jsonl",
        ),
        timeout_seconds=_env_int("AURA_MEMORY_TIMEOUT_SECONDS", 30),
        fail_closed=_env_bool("AURA_MEMORY_FAIL_CLOSED", False),
    )


def is_memory_service_enabled() -> bool:
    return load_memory_service_config().enabled
