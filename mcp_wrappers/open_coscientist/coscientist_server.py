"""STDIO MCP wrapper around ``open_coscientist`` (AI Co-Scientist).

The upstream repo (jataware / ph7klw76 fork) ships only an *HTTP* FastMCP
server for its PubMed/INDRA literature tools.  AURA's outbound MCP gateway
speaks **STDIO only** and the capability AURA actually wants is the core
multi-agent **hypothesis generation** (`open_coscientist.HypothesisGenerator`).

This thin wrapper exposes that over STDIO as a small, conservative toolset:

  * ``coscientist_health()``        — readiness, no LLM call.
  * ``generate_hypotheses(...)``    — run the co-scientist loop for a research
                                      goal and return ranked hypotheses.

SAFETY / HONESTY
----------------
Output is **AI-generated research hypotheses** — speculative ideation, NOT
validated science.  It is consumed by AURA as UNVERIFIED evidence
(``hypothesis_signal``) and still passes AURA's Scientific Verifier.  The tool
performs no external writes; it only calls an LLM (and, if explicitly enabled,
read-only literature tools).

Run:  python coscientist_server.py        # STDIO transport (FastMCP default)

Requires (in this wrapper's OWN environment, isolated from AURA's):
    pip install open-coscientist fastmcp
Plus an LLM key for the chosen litellm model, e.g. GEMINI_API_KEY /
OPENAI_API_KEY / ANTHROPIC_API_KEY.  COSCIENTIST_MODEL selects the model
(litellm format, default ``gemini/gemini-2.5-flash``).
"""
from __future__ import annotations

import os
import sys

# Some providers (e.g. DeepSeek) reject params open-coscientist sends, such as
# ``response_format`` json_schema.  Tell litellm to silently DROP params a
# provider doesn't support so the call still goes through (the model then
# returns free text, which open-coscientist's response parser handles).
try:  # pragma: no cover - depends on the wrapper venv
    import litellm
    litellm.drop_params = True

    # Some OpenAI-compatible endpoints reject
    # ``response_format={"type":"json_schema",...}`` but support JSON mode
    # (``{"type":"json_object"}``).  This OPT-IN shim downgrades json_schema →
    # json_object at the litellm boundary.  DEFAULT OFF: models that DO support
    # json_schema (gpt-4o, gemini) need it for reliable structured output, and
    # downgrading would break them.  Set COSCIENTIST_DOWNGRADE_JSON_SCHEMA=1
    # only for endpoints that reject json_schema (note: DeepSeek still tends to
    # fail open-coscientist's strict schema validation even in json_object mode).
    if os.getenv("COSCIENTIST_DOWNGRADE_JSON_SCHEMA", "0") == "1":
        def _downgrade(kwargs: dict) -> dict:
            rf = kwargs.get("response_format")
            if isinstance(rf, dict) and rf.get("type") == "json_schema":
                kwargs["response_format"] = {"type": "json_object"}
            return kwargs

        _orig_acompletion = litellm.acompletion
        _orig_completion = litellm.completion

        async def _patched_acompletion(*args, **kwargs):  # noqa: ANN001
            return await _orig_acompletion(*args, **_downgrade(kwargs))

        def _patched_completion(*args, **kwargs):  # noqa: ANN001
            return _orig_completion(*args, **_downgrade(kwargs))

        litellm.acompletion = _patched_acompletion
        litellm.completion = _patched_completion
except Exception:  # noqa: BLE001
    pass

# Enable lenient schema validation for models that don't support structured
# JSON output (e.g. DeepSeek v4-flash).  The open_coscientist library's
# ``validate_json_schema`` will accept partial / extra-keyed JSON instead of
# raising ValidationError, letting the multi-agent workflow complete.
_USE_LENIENT = os.getenv("COSCIENTIST_LENIENT_SCHEMA", "1")
if _USE_LENIENT not in ("0", "false", "no", ""):
    os.environ.setdefault("COSCIENTIST_LENIENT_SCHEMA", "1")

    # Auto-patch the installed open_coscientist library at startup so that
    # lenient validation + response_format fallback are active even when the
    # user has not manually applied patches to the pip-installed package.
    _THIS_DIR = os.path.dirname(os.path.abspath(__file__))
    for _src, _dst_rel in (
        ("llm_patched.py", "llm.py"),
        ("review_patched.py", "nodes/review.py"),
    ):
        _src_path = os.path.join(_THIS_DIR, _src)
        if os.path.isfile(_src_path):
            try:
                import open_coscientist as _oc
                _pkg_dir = os.path.dirname(os.path.abspath(_oc.__file__))
                _dst_path = os.path.join(_pkg_dir, _dst_rel)
                os.makedirs(os.path.dirname(_dst_path), exist_ok=True)
                with open(_src_path, "rb") as _f:
                    _content = _f.read()
                with open(_dst_path, "rb") as _f:
                    _existing = _f.read()
                if _content != _existing:
                    with open(_dst_path, "wb") as _f:
                        _f.write(_content)
                    print(f"[open-coscientist-mcp] patched {_dst_rel}", file=sys.stderr)
            except Exception as _pe:
                print(f"[open-coscientist-mcp] patch warning: {_pe}", file=sys.stderr)

from fastmcp import FastMCP

# Conservative caps so a single call cannot trigger a runaway LLM bill.
_MAX_HYPOTHESES = int(os.getenv("COSCIENTIST_MAX_HYPOTHESES_CAP", "8"))
_MAX_ITERATIONS = int(os.getenv("COSCIENTIST_MAX_ITERATIONS_CAP", "2"))
_MAX_EVOLUTION = int(os.getenv("COSCIENTIST_MAX_EVOLUTION_CAP", "4"))


def _resolve_aura_llm() -> str:
    """Mirror the SAME model + key + endpoint AURA uses, mapped to litellm.

    The wrapper subprocess inherits AURA's environment, so AURA's interactively
    chosen ``LLM_API_KEY`` / ``LLM_MODEL`` flow through automatically.

    Resolution (unless overridden by ``COSCIENTIST_MODEL``):
      * model  = LLM_MODEL | AURA_MODEL | AURA_DEFAULT_MODEL | "deepseek-v4-flash"
      * key    = LLM_API_KEY (AURA's remote key)
      * base   = REMOTE_API_URL | https://api.deepseek.com/v1/chat/completions

    Mapping to a litellm model string:
      * already litellm format ("provider/model")        → used as-is
      * Ollama-style ("name:tag")                         → "ollama/<name>"
      * otherwise (OpenAI-compatible remote, e.g. DeepSeek) → "openai/<name>"
        and OPENAI_API_KEY / OPENAI_API_BASE are set so litellm hits the SAME
        endpoint AURA uses.
    """
    explicit = os.getenv("COSCIENTIST_MODEL", "").strip()
    model = explicit if explicit else (
        os.getenv("LLM_MODEL")
        or os.getenv("AURA_MODEL")
        or os.getenv("AURA_DEFAULT_MODEL")
        or "deepseek-v4-flash"
    ).strip()

    return _litellm_model(model)


def _litellm_model(model: str) -> str:
    """Map a plain model name to a litellm ``provider/model`` string."""
    if "/" in model:  # already litellm-formatted
        return model
    if ":" in model:  # Ollama local model (e.g. qwen3:8b)
        return f"ollama/{model}"
    if "deepseek" in model.lower():  # native litellm deepseek provider
        key = os.getenv("LLM_API_KEY", "")
        if key and not os.getenv("DEEPSEEK_API_KEY"):
            os.environ["DEEPSEEK_API_KEY"] = key
        return f"deepseek/{model}"

    # OpenAI-compatible remote.
    base = (os.getenv("REMOTE_API_URL")
            or "https://api.deepseek.com/v1/chat/completions").strip()
    for suffix in ("/chat/completions", "/completions"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    key = os.getenv("LLM_API_KEY", "")
    if key and not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = key
    if base:
        os.environ.setdefault("OPENAI_API_BASE", base)
        os.environ.setdefault("OPENAI_BASE_URL", base)
    return f"openai/{model}"


_DEFAULT_MODEL = _resolve_aura_llm()

mcp = FastMCP("open-coscientist")


def _clamp(value: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(value), hi))
    except (TypeError, ValueError):
        return lo


@mcp.tool(name="coscientist_health")
def coscientist_health() -> dict:
    """Report whether the co-scientist backend is importable + which model is
    configured.  Does NOT call an LLM."""
    info: dict = {
        "ok": True,
        "model": _DEFAULT_MODEL,
        "caps": {
            "max_hypotheses": _MAX_HYPOTHESES,
            "max_iterations": _MAX_ITERATIONS,
            "max_evolution": _MAX_EVOLUTION,
        },
        # AURA's LLM_API_KEY is mirrored into OPENAI_API_KEY by _resolve_aura_llm.
        "llm_key_present": any(
            os.environ.get(k)
            for k in ("LLM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                      "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LITELLM_API_KEY")
        ),
        "api_base": os.environ.get("OPENAI_API_BASE", ""),
    }
    try:
        import open_coscientist  # noqa: F401
        info["open_coscientist_importable"] = True
        info["version"] = getattr(open_coscientist, "__version__", "unknown")
    except Exception as exc:  # noqa: BLE001
        info["ok"] = False
        info["open_coscientist_importable"] = False
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


@mcp.tool(name="generate_hypotheses")
async def generate_hypotheses(
    research_goal: str,
    initial_hypotheses_count: int = 3,
    max_iterations: int = 1,
    evolution_max_count: int = 2,
    model_name: str = "",
    preferences: str = "",
    constraints: str = "",
) -> dict:
    """Generate ranked research hypotheses for *research_goal* (AI co-scientist).

    SPECULATIVE / UNVERIFIED ideation — NOT validated science.  Returns a dict
    with ``hypotheses`` (text + score) and a short ``meta_review``.  Literature-
    review is disabled by default so this runs self-contained (no separate
    lit-review MCP server needed).
    """
    goal = (research_goal or "").strip()
    if not goal:
        return {"ok": False, "error": "research_goal is required and must be non-empty."}

    try:
        from open_coscientist import HypothesisGenerator
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"open_coscientist not available: {type(exc).__name__}: {exc}"}

    # When lenient schema mode is active (model lacks structured output),
    # increase hypothesis count and skip review/evolution to avoid cascading
    # failures in downstream nodes that require strict JSON.
    _lenient_mode = os.environ.get("COSCIENTIST_LENIENT_SCHEMA", "1").strip() not in ("", "0", "false", "no")
    if _lenient_mode:
        initial_hypotheses_count = max(initial_hypotheses_count, 4)
        max_iterations = 0
        evolution_max_count = 0

    generator = HypothesisGenerator(
        model_name=(model_name.strip() or _DEFAULT_MODEL),
        max_iterations=_clamp(max_iterations, 0, _MAX_ITERATIONS),
        initial_hypotheses_count=_clamp(initial_hypotheses_count, 1, _MAX_HYPOTHESES),
        evolution_max_count=_clamp(evolution_max_count, 0, _MAX_EVOLUTION),
    )

    opts: dict = {
        # Self-contained: do NOT require the separate literature-review MCP
        # server.  (Set COSCIENTIST_ENABLE_LIT_REVIEW=1 to allow it.)
        "enable_literature_review_node": os.getenv("COSCIENTIST_ENABLE_LIT_REVIEW", "0") == "1",
    }
    if preferences.strip():
        opts["preferences"] = preferences.strip()
    if constraints.strip():
        opts["constraints"] = constraints.strip()

    try:
        result = await generator.generate_hypotheses(
            research_goal=goal, opts=opts, stream=False,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the MCP transport
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:400]}"}

    hyps = []
    for h in (result.get("hypotheses") or [])[:_MAX_HYPOTHESES]:
        if isinstance(h, dict):
            hyps.append({
                "text": h.get("text") or h.get("hypothesis") or "",
                "score": h.get("score"),
                "rationale": (h.get("rationale") or "")[:1500],
            })
    return {
        "ok": True,
        "result_type": "hypothesis_signal",
        "research_goal": goal,
        "model": generator.model_name,
        "hypotheses": hyps,
        "meta_review": result.get("meta_review", {}),
        "limitations": [
            "AI-generated research hypotheses — speculative ideation, NOT "
            "validated science. Must be reviewed by AURA's Scientific Verifier.",
        ],
    }


if __name__ == "__main__":
    # FastMCP defaults to STDIO transport.
    sys.stderr.write("[open-coscientist-mcp] STDIO server starting "
                     f"(model {_DEFAULT_MODEL}).\n")
    mcp.run()
