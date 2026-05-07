import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

_ALLOWED_MODELS: frozenset[str] = frozenset({"qwen3:8b"})


def _validate_model(name: str) -> str:
    if name not in _ALLOWED_MODELS:
        raise ValueError(
            f"AURA only permits qwen3:8b. Got '{name}'. "
            f"Set AURA_MODEL=qwen3:8b or unset it to use the default."
        )
    return name


MODEL_NAME: str = _validate_model(os.getenv("AURA_MODEL", "qwen3:8b"))
TEMPERATURE: float = float(os.getenv("AURA_TEMPERATURE", "0.2"))
NUM_CTX: int = int(os.getenv("AURA_NUM_CTX", "8192"))
KEEP_ALIVE: str = os.getenv("AURA_KEEP_ALIVE", "30m")
OPENALEX_API_KEY: str = os.getenv("OPENALEX_API_KEY", "")

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
