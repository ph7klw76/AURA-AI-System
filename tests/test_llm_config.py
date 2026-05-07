"""
Static architecture tests: qwen3:8b-only enforcement, no direct Ollama calls
outside core/llm.py, no banned model references, no model override parameter.
"""
import importlib
import inspect
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Model name validation
# ---------------------------------------------------------------------------

def test_default_model_is_qwen3():
    import config
    assert config.MODEL_NAME == "qwen3:8b"


def test_validate_model_accepts_qwen3():
    import config
    assert config._validate_model("qwen3:8b") == "qwen3:8b"


def test_validate_model_rejects_gpt():
    import config
    with pytest.raises(ValueError, match="qwen3:8b"):
        config._validate_model("gpt-4")


def test_validate_model_rejects_claude():
    import config
    with pytest.raises(ValueError):
        config._validate_model("claude-3-sonnet")


def test_validate_model_rejects_llama():
    import config
    with pytest.raises(ValueError):
        config._validate_model("llama3.1:8b")


def test_validate_model_rejects_qwen_other_version():
    import config
    with pytest.raises(ValueError):
        config._validate_model("qwen2.5:7b")


def test_validate_model_rejects_gemini():
    import config
    with pytest.raises(ValueError):
        config._validate_model("gemini-pro")


# ---------------------------------------------------------------------------
# Static file checks
# ---------------------------------------------------------------------------

def _aura_root() -> Path:
    import config
    return Path(config.__file__).parent


def _non_test_py_files():
    return [
        f for f in _aura_root().rglob("*.py")
        if "__pycache__" not in str(f) and not f.name.startswith("test_")
    ]


def test_no_direct_ollama_calls_outside_llm():
    """No module outside core/llm.py may import or call ollama directly."""
    violations = []
    for py_file in _non_test_py_files():
        if py_file.name == "llm.py" and py_file.parent.name == "core":
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        if "import ollama" in content or "ollama.chat" in content:
            violations.append(str(py_file.relative_to(_aura_root())))
    assert violations == [], f"Direct Ollama usage outside core/llm.py: {violations}"


def test_no_banned_model_references_in_source():
    """No source file (non-test) references banned cloud or alternative models."""
    banned_terms = ["llama3.1", "qwen2.5", "gpt-3", "gpt-4", "claude-", "gemini-", "openai.com"]
    violations = []
    for py_file in _non_test_py_files():
        content = py_file.read_text(encoding="utf-8", errors="ignore").lower()
        for term in banned_terms:
            if term in content:
                violations.append(f"{py_file.name}: '{term}'")
    assert violations == [], f"Banned model references in source: {violations}"


def test_all_llm_consumers_import_from_core_llm():
    """Files that call ask_llm or ask_json must import from core.llm, not elsewhere."""
    violations = []
    for py_file in _non_test_py_files():
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        uses_ask = "ask_json(" in content or "ask_llm(" in content
        imports_correctly = "from core.llm import" in content or "from core import llm" in content
        if uses_ask and not imports_correctly:
            # llm.py itself defines ask_json/ask_llm
            if not (py_file.name == "llm.py" and py_file.parent.name == "core"):
                violations.append(str(py_file.relative_to(_aura_root())))
    assert violations == [], f"Files using ask_json/ask_llm without core.llm import: {violations}"


# ---------------------------------------------------------------------------
# LLM function signature checks (no model override parameter)
# ---------------------------------------------------------------------------

def test_ask_json_has_no_model_parameter():
    from core.llm import ask_json
    sig = inspect.signature(ask_json)
    assert "model" not in sig.parameters, (
        f"ask_json must not expose a 'model' override. Params: {list(sig.parameters)}"
    )


def test_ask_llm_has_no_model_parameter():
    from core.llm import ask_llm
    sig = inspect.signature(ask_llm)
    assert "model" not in sig.parameters, (
        f"ask_llm must not expose a 'model' override. Params: {list(sig.parameters)}"
    )


def test_core_llm_uses_config_model_name():
    """core/llm.py must reference config.MODEL_NAME, not a hardcoded model string."""
    aura_root = _aura_root()
    llm_path = aura_root / "core" / "llm.py"
    content = llm_path.read_text(encoding="utf-8")
    assert "config.MODEL_NAME" in content, "core/llm.py must use config.MODEL_NAME"
    # Must not hardcode the model string directly in the chat call
    assert '"qwen3:8b"' not in content or "config.MODEL_NAME" in content, (
        "core/llm.py should not hardcode the model name"
    )
