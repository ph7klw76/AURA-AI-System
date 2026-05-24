"""
AURA Lab/Data Analyst — Wave 2 specialist.

Plans local scientific data analysis: required columns, methods, calculations,
plots, reproducibility checks, and interpretation limits. NEVER touches raw
files. Reviewed by the Scientific Verifier when interpretation is involved.

Public surface:
    run(user_input, context) -> dict (validates against LabDataAnalystOutput)
    lab_data_analyst = run   # alias matching reference signature
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from core.llm import ask_json
from core.memory import retrieve_relevant_memory
from core.schemas import LabDataAnalystOutput


SYSTEM_PROMPT = """\
You are the AURA Lab/Data Analyst.

Your job is to PLAN scientific data analysis — required columns, methods,
calculations, plots, reproducibility checks, and interpretation limits.

You are useful for:
- OLED J-V-L analysis (current density, voltage, luminance)
- EQE / external quantum efficiency analysis
- Photoluminescence / electroluminescence spectra
- Time-resolved fluorescence (TCSPC) decays
- DFT / kMC / Monte Carlo simulation outputs
- CSV / Excel / spreadsheet workflows

Hard rules — never break:
- Use ONLY the evidence provided (user input + previous agent outputs).
- Do NOT pretend you have seen the data. Plan the analysis; do not invent results.
- Do NOT propose deleting, overwriting, or modifying raw files.
- Always recommend working on a copy.
- Be strict about UNITS, DEVICE AREA, CALIBRATION, REPEATED DEVICES, UNCERTAINTY.
- Separate evidence from assumptions.
- State interpretation limits explicitly (e.g. "EQE without calibration is unreliable").
- Include reproducibility checks (repeated devices, replication across batches).
- Return strict JSON only — no prose, no markdown fences.

Return JSON with EXACTLY this schema (no extra keys):
{
  "agent_name": "lab_data_analyst",
  "summary": "...",
  "findings": ["..."],
  "assumptions": ["..."],
  "risks": ["..."],
  "recommended_actions": ["..."],
  "claims_for_verification": ["..."],
  "evidence_level": "none|weak|moderate|strong",
  "confidence": "low|medium|high",
  "approval_level": "none|draft_only",
  "analysis_type": "...",
  "data_requirements": ["..."],
  "required_columns": ["..."],
  "methods_recommended": ["..."],
  "calculations_recommended": ["..."],
  "plots_recommended": ["..."],
  "data_quality_checks": ["..."],
  "reproducibility_checks": ["..."],
  "interpretation_limits": ["..."],
  "safe_file_handling": ["..."],
  "next_analysis_steps": ["..."]
}

approval_level must be "none" for read-only analysis planning, or "draft_only"
when you propose anything that would generate output files. NEVER use
"human_approval_required" — destructive recommendations belong in
recommended_actions with explicit ACTION_POLICY action_class instead.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_context(value: Any, max_chars: int = 3000) -> str:
    try:
        text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    except Exception:
        text = str(value)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]"
    return text


_ANALYSIS_TYPE_HINTS: list[tuple[str, list[str]]] = [
    ("OLED J-V-L analysis",                 ["j-v-l", "jvl", "current density", "luminance vs voltage"]),
    ("External quantum efficiency analysis", ["eqe", "external quantum efficiency"]),
    ("Spectral analysis",                    ["spectrum", "spectra", "photoluminescence",
                                              "electroluminescence", "absorption", "emission spectrum"]),
    ("Time-resolved fluorescence analysis",  ["tcspc", "fluorescence decay", "lifetime decay",
                                              "transient absorption", "time-resolved"]),
    ("Simulation output analysis",           ["simulation", "monte carlo", "kmc", "dft",
                                              "molecular dynamics"]),
    ("Tabular scientific data analysis",     ["csv", "excel", "spreadsheet", "dataset",
                                              "data file"]),
]


def _infer_analysis_type(user_input: str) -> str:
    text = (user_input or "").lower()
    for label, keywords in _ANALYSIS_TYPE_HINTS:
        if any(k in text for k in keywords):
            return label
    return "Scientific data-analysis planning"


def _scout_excerpt(scout_output: dict) -> str:
    """Defect 28: safe Scout-context normalization."""
    from core import normalization as _norm
    if not isinstance(scout_output, dict):
        return "{}"
    excerpt = {
        "summary": _norm.ensure_str(scout_output.get("summary"), max_len=400),
        "findings": _norm.ensure_str_list(
            scout_output.get("findings"), max_items=4,
        ),
        "evidence_quality": _norm.ensure_str(scout_output.get("evidence_quality")),
    }
    return _safe_context(excerpt, max_chars=800)


def _fallback_output(error: Exception | str, analysis_type: str) -> dict:
    """Conservative fallback when validation or the LLM call fails.

    Always populates the safety-critical fields (safe_file_handling,
    interpretation_limits, reproducibility_checks) so a malformed LLM response
    cannot leave those sections empty.
    """
    message = str(error)
    return LabDataAnalystOutput(
        summary="Lab/Data Analyst could not produce a fully validated analysis plan.",
        findings=["Manual review is needed before using this analysis plan."],
        assumptions=["The structure and quality of the data are not fully known."],
        risks=[
            "Interpretation may be unreliable without units, calibration, and repeated measurements.",
            f"Internal error or validation issue: {message[:300]}",
        ],
        recommended_actions=[
            "Confirm data columns, units, and measurement conditions.",
            "Preserve raw data before any processing.",
            "Run Scientific Verifier on interpretation claims.",
        ],
        claims_for_verification=[],
        evidence_level="weak",
        confidence="low",
        approval_level="none",
        partial_results=True,
        failed_stage="llm_data_analysis_plan",
        analysis_type=analysis_type,
        data_requirements=[
            "Raw data file (do not modify)",
            "Column names",
            "Units for every column",
            "Device area (for OLED metrics)",
            "Measurement conditions",
        ],
        required_columns=[],
        methods_recommended=[],
        calculations_recommended=[],
        plots_recommended=[],
        data_quality_checks=[
            "Check for missing values.",
            "Check for unit consistency.",
            "Check for calibration metadata.",
        ],
        reproducibility_checks=[
            "Compare repeated devices.",
            "Report variation across devices.",
            "Confirm independent measurement runs.",
        ],
        interpretation_limits=[
            "Do not claim device superiority without benchmark comparison.",
            "Do not interpret EQE without calibration and device-area confirmation.",
            "Do not generalize from a single device.",
        ],
        safe_file_handling=[
            "Do not delete raw data.",
            "Do not overwrite original files.",
            "Work on copies for any processed output.",
        ],
        next_analysis_steps=[
            "Prepare a clean copy of the dataset.",
            "Identify required plots and metrics.",
        ],
    ).model_dump()


def _enforce_safety_invariants(output: dict, analysis_type: str) -> dict:
    """Force conservative safety fields even if the LLM produced a thin output.

    Wave 2 hard requirement: safe_file_handling must always include 'do not
    delete' / 'do not overwrite' guidance, regardless of LLM behaviour.
    """
    # Defect 28: safe_file_handling must never be exploded into characters.
    from core import normalization as _norm
    safe = _norm.ensure_str_list(output.get("safe_file_handling"))
    text = " ".join(safe).lower()
    if "delete" not in text:
        safe.append("Do not delete raw data.")
    if "overwrite" not in text:
        safe.append("Do not overwrite original files.")
    if "copy" not in text and "copies" not in text:
        safe.append("Work on copies for processed output.")
    output["safe_file_handling"] = safe

    # If LLM forgot to set analysis_type, fill it from the inferred value
    if not (output.get("analysis_type") or "").strip():
        output["analysis_type"] = analysis_type

    # Force conservative approval_level — no scenario where this agent should
    # claim the output is ready for any external action.
    if output.get("approval_level") == "human_approval_required":
        output["approval_level"] = "draft_only"

    return output


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(user_input: str, context: dict | None = None) -> dict:
    """Generate a safe, reproducible scientific data-analysis plan."""
    ctx = context or {}
    analysis_type = _infer_analysis_type(user_input)

    try:
        memory_records = retrieve_relevant_memory(user_input, limit=8) or []
    except Exception:
        memory_records = []

    scout_output = ctx.get("research_scout") or {}
    if not scout_output and isinstance(ctx.get("specialists"), dict):
        scout_output = ctx["specialists"].get("research_scout", {}) or {}

    governor = ctx.get("strategic_governor") or {}

    user_prompt = (
        "User request:\n"
        f"{user_input}\n\n"
        f"Inferred analysis type (from keywords): {analysis_type}\n\n"
        "Strategic governor signals:\n"
        f"{_safe_context({k: governor.get(k) for k in ('task_type','evidence_requirement','autonomy_level','rationale')}, max_chars=400)}\n\n"
        "Research Scout excerpt (optional context):\n"
        f"{_scout_excerpt(scout_output)}\n\n"
        "Relevant AURA memory:\n"
        f"{_safe_context(memory_records[:8], max_chars=1200)}\n\n"
    )

    # --- Inject verifier revision instructions if present (retry context) ---
    verifier_instructions = ctx.get("verifier_revision_instructions")
    if verifier_instructions and isinstance(verifier_instructions, list):
        user_prompt += (
            "Verifier Revision Instructions (address each before finalising):\n"
            + "\n".join(f"  - {v}" for v in verifier_instructions[:8])
            + "\n\n"
        )
    verifier_corrections = ctx.get("verifier_corrections")
    if verifier_corrections and isinstance(verifier_corrections, list):
        user_prompt += (
            "Verifier Corrections (mandatory fixes):\n"
            + "\n".join(f"  * {c}" for c in verifier_corrections[:5])
            + "\n\n"
        )
    verifier_risks = ctx.get("verifier_risks")
    if verifier_risks and isinstance(verifier_risks, list):
        user_prompt += (
            "Verifier Risks to Mitigate:\n"
            + "\n".join(f"  ! {r}" for r in verifier_risks[:5])
            + "\n\n"
        )

    user_prompt += (
        "Task: produce a SAFE, REPRODUCIBLE data-analysis plan matching the JSON schema. "
        "Do not claim results from unseen data. Always include safe_file_handling. "
        "Always include interpretation_limits. Return strict JSON only."
    )

    try:
        raw = ask_json(SYSTEM_PROMPT, user_prompt, temperature=0.15)
    except Exception as exc:
        return _fallback_output(exc, analysis_type)

    if not isinstance(raw, dict):
        return _fallback_output("LLM returned non-dict output.", analysis_type)

    # Sanity check — reject empty / boilerplate dicts and fall back.
    _SUBSTANTIVE = (
        "summary", "analysis_type", "data_requirements", "methods_recommended",
        "plots_recommended", "next_analysis_steps",
    )
    if not any(raw.get(f) for f in _SUBSTANTIVE):
        return _fallback_output(
            "LLM response contained no substantive analysis fields.", analysis_type
        )

    raw["agent_name"] = "lab_data_analyst"
    raw = _enforce_safety_invariants(raw, analysis_type)

    try:
        validated = LabDataAnalystOutput.model_validate(raw)
    except ValidationError as exc:
        return _fallback_output(exc, analysis_type)

    return validated.model_dump()


# ---------------------------------------------------------------------------
# Compatibility alias — matches the reference signature lab_data_analyst(...)
# ---------------------------------------------------------------------------

lab_data_analyst = run
