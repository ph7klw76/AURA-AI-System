import os
import warnings
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Phase 3 (goal D) — robust environment-variable parsing
# ---------------------------------------------------------------------------
# A malformed numeric/boolean env value (e.g. ``AURA_NUM_CTX=abc``) must NOT
# crash at import time.  These helpers fall back to a safe default and emit a
# single warning instead of raising, so a typo in ``.env`` degrades gracefully
# rather than taking down every ``import config``.

def env_int(name: str, default: int) -> int:
    """Parse an int env var; on missing/blank/malformed value return *default*."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        warnings.warn(
            f"Invalid integer for {name}={raw!r}; using default {default}.",
            RuntimeWarning,
            stacklevel=2,
        )
        return default


def env_float(name: str, default: float) -> float:
    """Parse a float env var; on missing/blank/malformed value return *default*."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        warnings.warn(
            f"Invalid float for {name}={raw!r}; using default {default}.",
            RuntimeWarning,
            stacklevel=2,
        )
        return default


def env_bool(name: str, default: bool) -> bool:
    """Parse a boolean env var.

    Truthy: ``1 true yes on`` (case-insensitive).  Falsy: ``0 false no off``.
    Missing/blank → *default*.  Any other value → *default* with a warning.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    val = raw.strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    warnings.warn(
        f"Invalid boolean for {name}={raw!r}; using default {default}.",
        RuntimeWarning,
        stacklevel=2,
    )
    return default

# ---------------------------------------------------------------------------
# LLM configuration -----------------------------------------------------------
# Use get_model_name() to read the latest MODEL from environment.
# DEFAULT_MODEL is fallback when no AURA_MODEL or LLM_MODEL is set.
# ---------------------------------------------------------------------------

DEFAULT_MODEL: str = os.getenv("AURA_DEFAULT_MODEL", "deepseek-v4-flash")

def get_model_name() -> str:
    """Return the LLM model name currently active.

    Priority order:
        1. LLM_MODEL     — set by main.py after interactive choice or CLI flag
        2. AURA_MODEL    — static preference in .env
        3. DEFAULT_MODEL — built‑in fallback (deepseek‑v4‑flash)
    """
    return os.getenv("LLM_MODEL") or os.getenv("AURA_MODEL") or DEFAULT_MODEL

# Frozen runtime values that do not change per request (paths, etc.)
TEMPERATURE: float = env_float("AURA_TEMPERATURE", 0.2)
NUM_CTX: int = env_int("AURA_NUM_CTX", 8192)
KEEP_ALIVE: str = os.getenv("AURA_KEEP_ALIVE", "30m")
OPENALEX_API_KEY: str = os.getenv("OPENALEX_API_KEY", "")

# Optional third-party scholarly source configuration
CROSSREF_MAILTO: str = os.getenv("CROSSREF_MAILTO", "")
SEMANTIC_SCHOLAR_API_KEY: str = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")

# ---------------------------------------------------------------------------
# SearXNG configuration -------------------------------------------------------
# ---------------------------------------------------------------------------

SEARXNG_ENABLED: bool = env_bool("SEARXNG_ENABLED", False)
SEARXNG_URL: str = os.getenv("SEARXNG_URL", "http://localhost:8080")
SEARXNG_TIMEOUT_SECONDS: int = env_int("SEARXNG_TIMEOUT_SECONDS", 20)
SEARXNG_CONTAINER_NAME: str = os.getenv("SEARXNG_CONTAINER_NAME", "searxng")
SEARXNG_AUTO_START: bool = env_bool("SEARXNG_AUTO_START", True)
SEARXNG_AUTO_START_DOCKER_DESKTOP: bool = env_bool("SEARXNG_AUTO_START_DOCKER_DESKTOP", True)
SEARXNG_DOCKER_COMPOSE_FILE: str = os.getenv("SEARXNG_DOCKER_COMPOSE_FILE", "")
SEARXNG_DOCKER_PROJECT_DIR: str = os.getenv("SEARXNG_DOCKER_PROJECT_DIR", "")
SEARXNG_JSON_HEALTH_QUERY: str = os.getenv("SEARXNG_JSON_HEALTH_QUERY", "searxng")

# ---------------------------------------------------------------------------
# Patent Web Search (Stage 1) — web-based patent reconnaissance via SearXNG
# ---------------------------------------------------------------------------

PATENT_WEB_SEARCH_ENABLED: bool = env_bool("PATENT_WEB_SEARCH_ENABLED", True)
# "auto" picks whichever real provider is configured.
PATENT_WEB_SEARCH_PROVIDER: str = os.getenv("PATENT_WEB_SEARCH_PROVIDER", "auto")
PATENT_WEB_QUERY_COUNT: int = env_int("PATENT_WEB_QUERY_COUNT", 4)
PATENT_WEB_MAX_RESULTS_PER_QUERY: int = env_int("PATENT_WEB_MAX_RESULTS_PER_QUERY", 10)
PATENT_WEB_MAX_PAGES_TO_FETCH: int = env_int("PATENT_WEB_MAX_PAGES_TO_FETCH", 20)
PATENT_WEB_FETCH_TIMEOUT_SECONDS: int = env_int("PATENT_WEB_FETCH_TIMEOUT_SECONDS", 20)
PATENT_WEB_MAX_RESPONSE_BYTES: int = env_int("PATENT_WEB_MAX_RESPONSE_BYTES", 2000000)
PATENT_WEB_ALLOWED_DOMAINS: list[str] = [
    d.strip()
    for d in os.getenv(
        "PATENT_WEB_ALLOWED_DOMAINS",
        "patents.google.com,patentscope.wipo.int,uspto.gov",
    ).split(",")
    if d.strip()
]
PATENT_WEB_ALLOW_MOCK_FALLBACK: bool = env_bool("PATENT_WEB_ALLOW_MOCK_FALLBACK", False)

# --- Provider-neutral patent search subsystem (Phase 3 goal F) ------------
# SINGLE SOURCE OF TRUTH for the provider-neutral patent search subsystem.
# ``integrations.patent_web.search_providers.factory`` consumes
# ``get_patent_search_settings()`` rather than re-parsing these env vars with
# its own (previously divergent) defaults.  Supported provider values:
#   "google_web_no_key" — best-effort Google SERP scrape, no API key
#   "duckduckgo_html"   — best-effort DuckDuckGo HTML, no API key
#   "searxng"           — self-hosted SearXNG meta-search
#   "mock"              — synthetic, for tests / explicit offline use
#   "auto"              — pick SearXNG if enabled, else a no-key web provider
PATENT_SEARCH_DEFAULT_PROVIDER: str = "auto"
PATENT_SEARCH_DEFAULT_FALLBACK_CHAIN: str = "duckduckgo_html,searxng"
PATENT_SEARCH_DEFAULT_MAX_RESULTS: int = 10


def get_patent_search_settings() -> dict:
    """Return the normalized provider-neutral patent-search configuration.

    Parsed at call time (not import time) so runtime env changes are honoured
    and a malformed value cannot crash ``import config``.  This is the ONE
    place that interprets these env vars; the provider factory consumes the
    result rather than re-reading the environment.
    """
    provider = (
        os.getenv("AURA_PATENT_SEARCH_PROVIDER")
        or os.getenv("PATENT_WEB_SEARCH_PROVIDER")
        or PATENT_SEARCH_DEFAULT_PROVIDER
    ).strip().lower()

    # Mock fallback: the canonical AURA_PATENT_SEARCH_ALLOW_MOCK_FALLBACK is
    # authoritative when explicitly set (even to 0); only when it is unset do
    # we consult the legacy PATENT_WEB_ALLOW_MOCK_FALLBACK.  Default OFF.
    canonical = os.getenv("AURA_PATENT_SEARCH_ALLOW_MOCK_FALLBACK")
    if canonical is not None and canonical.strip() != "":
        allow_mock = env_bool("AURA_PATENT_SEARCH_ALLOW_MOCK_FALLBACK", False)
    else:
        allow_mock = env_bool("PATENT_WEB_ALLOW_MOCK_FALLBACK", False)

    return {
        "provider": provider,
        "allow_fallback": env_bool("AURA_PATENT_SEARCH_ALLOW_FALLBACK", True),
        "allow_mock_fallback": allow_mock,
        "max_results": max(1, env_int(
            "AURA_PATENT_SEARCH_MAX_RESULTS", PATENT_SEARCH_DEFAULT_MAX_RESULTS)),
        "fallback_chain": os.getenv(
            "AURA_PATENT_SEARCH_FALLBACK_CHAIN",
            PATENT_SEARCH_DEFAULT_FALLBACK_CHAIN,
        ),
        "google_web_enabled": env_bool("AURA_GOOGLE_WEB_PATENT_ENABLED", True),
    }

MEMORY_PATH: Path = BASE_DIR / "data" / "memories.jsonl"
REFLECTION_PATH: Path = BASE_DIR / "data" / "reflections.jsonl"
APPROVAL_LOG_PATH: Path = BASE_DIR / "data" / "approval_log.jsonl"
RESEARCH_DB_PATH: Path = BASE_DIR / "data" / "research_memory.db"
PERFORMANCE_LOG_PATH: Path = BASE_DIR / "data" / "performance_log.jsonl"
RESEARCH_PROFILE_PATH: Path = BASE_DIR / "profiles" / "research_profile.yaml"
REPORT_DIR: Path = BASE_DIR / "reports"

DATA_DIR: Path = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "profiles").mkdir(parents=True, exist_ok=True)
(BASE_DIR / "outputs").mkdir(parents=True, exist_ok=True)
