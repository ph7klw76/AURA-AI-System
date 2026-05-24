"""Task-agent runner — executes a validated AgentSpec against input payload.

Each runner is a deterministic, bounded function.  No LLM calls, no external
API calls, no filesystem writes, no shell execution.  Output is always marked
``verified_by_aura=False``.
"""

from __future__ import annotations

import re
from typing import Any

from .schemas import AgentSpec, TaskAgentResult


def run_task_agent(spec: AgentSpec, input_payload: dict[str, Any]) -> TaskAgentResult:
    """Dispatch to the appropriate runner based on *spec.name*.

    Returns a ``TaskAgentResult`` — never raises on bad input (errors are
    captured in ``.errors`` and ``.ok`` is set to ``False``).
    """
    runners: dict[str, Any] = {
        "claim_extractor": _run_claim_extractor,
        "evidence_table_formatter": _run_evidence_table_formatter,
        "query_variant_generator": _run_query_variant_generator,
        "mcp_result_normalizer": _run_mcp_result_normalizer,
        "repo_issue_classifier": _run_repo_issue_classifier,
        "competitor_name_extractor": _run_competitor_name_extractor,
        "reviewer_objection_mapper": _run_reviewer_objection_mapper,
        "risk_register_builder": _run_risk_register_builder,
        "test_case_suggester": _run_test_case_suggester,
        "local_document_excerpt_summarizer": _run_doc_summarizer,
    }

    runner = runners.get(spec.name)
    if runner is None:
        return TaskAgentResult(
            agent_id=spec.agent_id,
            ok=False,
            subtask=spec.subtask,
            errors=[f"No runner for role '{spec.name}'"],
            confidence="low",
        )

    return runner(spec, input_payload)


# ---------------------------------------------------------------------------
# Claim Extractor
# ---------------------------------------------------------------------------
_CLAIM_PATTERNS: list[tuple[str, str]] = [
    (r"(?:we |I |the |our |this )?(?:find|found|show|showed|demonstrate|conclude|confirm|prove|establish|reveal|indicate|suggest|observe|discover|report)\b", "claim"),
    (r"\b(?:hypothes[ei]s|propos(?:e|al)|argue|assert|theor(?:y|ize)|postulate)\b", "hypothesis"),
    (r"\b(?:result|finding|data|evidence|experimental|measurement|analysis)\s+(?:show|suggest|indicate|demonstrate|support|confirm|reveal)\b", "evidence_statement"),
    (r"\b(?:we believe|it is likely|may be|might be|could be|potentially|possibly)\b", "speculative_claim"),
    (r"\b(?:significantly|statistically|p\s*<\s*0\.\d+|p\s*=\s*0\.\d+)\b", "statistical_claim"),
]


def _run_claim_extractor(
    spec: AgentSpec, payload: dict[str, Any]
) -> TaskAgentResult:
    """Extract candidate claims from a text block.

    Does NOT verify truth — returns raw candidate claims for downstream review.
    """
    text = payload.get("text") or payload.get("content") or ""
    if not text.strip():
        return TaskAgentResult(
            agent_id=spec.agent_id,
            ok=False,
            subtask=spec.subtask,
            errors=["Input 'text' or 'content' is empty."],
            confidence="low",
        )

    claims: list[str] = []
    sentences = _split_sentences(text)
    for sentence in sentences:
        s = sentence.strip()
        if len(s) < 15:
            continue
        for pattern, _label in _CLAIM_PATTERNS:
            if re.search(pattern, s, re.IGNORECASE):
                claims.append(s)
                break

    return TaskAgentResult(
        agent_id=spec.agent_id,
        ok=True,
        subtask=spec.subtask,
        summary=f"Extracted {len(claims)} candidate claims from {len(sentences)} sentences.",
        findings=claims,
        claims_for_verification=claims,
        limitations=[
            "Extraction is pattern-based — may miss novel or unusual claim phrasing.",
            "Claims are NOT verified — must pass Scientific Verifier before use.",
        ],
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Evidence Table Formatter
# ---------------------------------------------------------------------------
def _run_evidence_table_formatter(
    spec: AgentSpec, payload: dict[str, Any]
) -> TaskAgentResult:
    """Format raw evidence records into structured table-like output."""
    records = payload.get("evidence_records") or payload.get("records") or []
    if not isinstance(records, list) or not records:
        return TaskAgentResult(
            agent_id=spec.agent_id,
            ok=False,
            subtask=spec.subtask,
            errors=["Input must contain 'evidence_records' as a non-empty list."],
            confidence="low",
        )

    formatted: list[dict[str, Any]] = []
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        formatted.append({
            "index": i + 1,
            "source": rec.get("source", rec.get("citation", "unknown")),
            "claim": rec.get("claim", rec.get("text", "")),
            "support": rec.get("support", rec.get("support_status", "unknown")),
            "notes": rec.get("notes", rec.get("note", "")),
        })

    return TaskAgentResult(
        agent_id=spec.agent_id,
        ok=True,
        subtask=spec.subtask,
        summary=f"Formatted {len(formatted)} evidence records.",
        findings=[f"Formatted {len(formatted)} records into evidence table."],
        evidence_records=formatted,
        limitations=["Formatting only — does not judge evidence quality."],
        confidence="medium",
    )


# ---------------------------------------------------------------------------
# Query Variant Generator
# ---------------------------------------------------------------------------
def _run_query_variant_generator(
    spec: AgentSpec, payload: dict[str, Any]
) -> TaskAgentResult:
    """Generate alternative search-query variants from a topic."""
    topic = payload.get("topic") or payload.get("query") or ""
    if not topic.strip():
        return TaskAgentResult(
            agent_id=spec.agent_id,
            ok=False,
            subtask=spec.subtask,
            errors=["Input 'topic' or 'query' is empty."],
            confidence="low",
        )

    variants: list[str] = []
    t = topic.strip()
    # Generate variants via simple templates — no LLM call.
    for prefix in ("", "recent advances in ", "review of ", "state of the art in ",
                   "challenges in ", "future directions of ", "novel approaches to "):
        v = f"{prefix}{t}".strip()
        if v and v not in variants:
            variants.append(v)
    for suffix in (" methodology", " limitations", " survey", " critical analysis"):
        v = f"{t}{suffix}".strip()
        if v not in variants:
            variants.append(v)

    return TaskAgentResult(
        agent_id=spec.agent_id,
        ok=True,
        subtask=spec.subtask,
        summary=f"Generated {len(variants)} query variants for '{t[:60]}'.",
        findings=variants,
        limitations=[
            "Template-based generation — does not use semantic understanding.",
            "Does NOT perform web search — variants are suggestions only.",
        ],
        confidence="low",
    )


# ---------------------------------------------------------------------------
# MCP Result Normalizer
# ---------------------------------------------------------------------------
def _run_mcp_result_normalizer(
    spec: AgentSpec, payload: dict[str, Any]
) -> TaskAgentResult:
    """Normalize a raw external MCP result into AURA evidence records."""
    raw = payload.get("mcp_result") or payload.get("raw") or {}
    source = payload.get("mcp_server", "unknown_mcp")

    evidence: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        # Flatten top-level text/content keys into evidence records.
        for key in ("text", "content", "result", "evidence", "data", "results", "output"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                evidence.append({
                    "source": f"mcp:{source}",
                    "key": key,
                    "content": val[:3000],
                    "raw_length": len(val),
                })
            elif isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, dict):
                        evidence.append({
                            "source": f"mcp:{source}",
                            "key": f"{key}[{i}]",
                            **{k: str(v)[:1000] for k, v in item.items()},
                        })
                    elif isinstance(item, str) and item.strip():
                        evidence.append({
                            "source": f"mcp:{source}",
                            "key": f"{key}[{i}]",
                            "content": item[:3000],
                        })

    if not evidence:
        evidence.append({
            "source": f"mcp:{source}",
            "content": str(raw)[:3000],
        })

    return TaskAgentResult(
        agent_id=spec.agent_id,
        ok=True,
        subtask=spec.subtask,
        summary=f"Normalized MCP result from '{source}' into {len(evidence)} evidence record(s).",
        evidence_records=evidence,
        limitations=[
            "Normalized from raw MCP output — NOT verified.",
            "Source is external, unverified evidence.",
        ],
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Repo Issue Classifier
# ---------------------------------------------------------------------------
_AURA_MODULE_KEYWORDS: dict[str, list[str]] = {
    "research_scout": ["search", "literature", "paper", "ideation", "gap", "trend"],
    "grant_architect": ["grant", "proposal", "aims", "significance", "funding"],
    "scientific_verifier": ["verify", "fact", "claim", "evidence", "accuracy"],
    "teaching_mentor": ["teach", "lesson", "quiz", "rubric", "explain"],
    "lab_data_analyst": ["data", "analysis", "statistics", "plot", "experiment"],
    "founder_innovation": ["commercial", "startup", "market", "product", "business"],
    "patent_intelligence": ["patent", "IP", "prior art", "freedom to operate"],
    "collaboration_operator": ["collaborate", "outreach", "agenda", "partner"],
}


def _run_repo_issue_classifier(
    spec: AgentSpec, payload: dict[str, Any]
) -> TaskAgentResult:
    """Classify GitHub issue text by likely affected AURA module.

    Read-only — does not modify the issue.
    """
    text = (
        payload.get("title", "")
        + " "
        + (payload.get("body") or payload.get("text") or "")
    ).strip()

    if not text:
        return TaskAgentResult(
            agent_id=spec.agent_id,
            ok=False,
            subtask=spec.subtask,
            errors=["Input must include 'title' and/or 'body'/'text'."],
            confidence="low",
        )

    matches: list[dict[str, Any]] = []
    text_lower = text.lower()
    for module, keywords in _AURA_MODULE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            matches.append({"module": module, "keyword_matches": score})

    matches.sort(key=lambda m: m["keyword_matches"], reverse=True)

    findings = (
        [f"Likely affects: {m['module']} (score={m['keyword_matches']})" for m in matches[:3]]
        if matches
        else ["No strong module match detected."]
    )

    return TaskAgentResult(
        agent_id=spec.agent_id,
        ok=True,
        subtask=spec.subtask,
        summary=f"Classified issue against {len(_AURA_MODULE_KEYWORDS)} AURA modules.",
        findings=findings,
        evidence_records=matches,
        limitations=["Keyword-based classification — may misclassify.", "Read-only — does not modify the issue."],
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Competitor Name Extractor
# ---------------------------------------------------------------------------
def _run_competitor_name_extractor(
    spec: AgentSpec, payload: dict[str, Any]
) -> TaskAgentResult:
    """Extract possible competitor names from idea-reality output text.

    Returns market_signal only — no competitor database lookup.
    """
    text = payload.get("idea_reality_output") or payload.get("text") or ""
    if not text.strip():
        return TaskAgentResult(
            agent_id=spec.agent_id,
            ok=False,
            subtask=spec.subtask,
            errors=["Input must include 'idea_reality_output' or 'text'."],
            confidence="low",
        )

    # Heuristic: look for capitalized multi-word names (likely company/project names)
    # and names near competitor-indicating keywords.
    names: list[str] = []
    indicator_kw = ["competitor", "company", "startup", "firm", "project", "platform", "inc", "llc", "ltd", "corp"]

    # Simple heuristic — extract quoted names and capitalized sequences
    quoted = re.findall(r'"([^"]{3,80})"', text)
    names.extend(quoted)
    # Capitalized sequences near competitor keywords
    for kw in indicator_kw:
        idx = text.lower().find(kw)
        if idx >= 0:
            ctx = text[max(0, idx - 200): idx + 200]
            cap_seqs = re.findall(r'\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\b', ctx)
            names.extend(cap_seqs)

    deduped = list(dict.fromkeys(names))[:20]

    return TaskAgentResult(
        agent_id=spec.agent_id,
        ok=True,
        subtask=spec.subtask,
        summary=f"Extracted {len(deduped)} possible competitor/project names.",
        findings=deduped,
        limitations=[
            "Heuristic extraction — may include false positives or miss names.",
            "Market signal only — NOT a verified competitor analysis.",
        ],
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Reviewer Objection Mapper
# ---------------------------------------------------------------------------
_REVIEWER_OBJECTION_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:novel|novelty|original)\b", "novelty_concern"),
    (r"\b(?:feasib(?:le|ility)|practical|realistic)\b", "feasibility_concern"),
    (r"\b(?:method|approach|technique|protocol|procedure|experimental)\b", "methodology_concern"),
    (r"\b(?:significan(?:ce|t)|impact|important|contribution|advance)\b", "significance_concern"),
    (r"\b(?:assum(?:e|ption)|limit(?:ation)?|constraint|boundar)\b", "assumption_concern"),
    (r"\b(?:statistic|sample|power|n\s*=|p\s*[<>])\b", "statistical_concern"),
    (r"\b(?:budget|cost|resource|funding|expensive)\b", "resource_concern"),
    (r"\b(?:timeline|schedule|duration|milestone|deadline)\b", "timeline_concern"),
]


def _run_reviewer_objection_mapper(
    spec: AgentSpec, payload: dict[str, Any]
) -> TaskAgentResult:
    """Map a proposal/draft to possible reviewer objections.

    Does NOT make grant decisions — identifies potential concerns only.
    """
    text = payload.get("draft") or payload.get("proposal") or payload.get("text") or ""
    if not text.strip():
        return TaskAgentResult(
            agent_id=spec.agent_id,
            ok=False,
            subtask=spec.subtask,
            errors=["Input must include 'draft', 'proposal', or 'text'."],
            confidence="low",
        )

    objections: list[str] = []
    for pattern, concern_type in _REVIEWER_OBJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            objections.append(
                f"Potential {concern_type.replace('_', ' ')} — "
                f"pattern '{pattern}' matched in draft text."
            )

    return TaskAgentResult(
        agent_id=spec.agent_id,
        ok=True,
        subtask=spec.subtask,
        summary=f"Mapped {len(objections)} potential reviewer objection categories.",
        findings=objections,
        limitations=[
            "Pattern-based detection only — may miss nuanced concerns.",
            "Does NOT evaluate objection validity — flags for human review.",
        ],
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Risk Register Builder
# ---------------------------------------------------------------------------
def _run_risk_register_builder(
    spec: AgentSpec, payload: dict[str, Any]
) -> TaskAgentResult:
    """Build a simple risk register from project text."""
    text = payload.get("project_description") or payload.get("text") or ""
    if not text.strip():
        return TaskAgentResult(
            agent_id=spec.agent_id,
            ok=False,
            subtask=spec.subtask,
            errors=["Input 'project_description' or 'text' is empty."],
            confidence="low",
        )

    risks: list[str] = []
    risk_patterns = [
        (r"\brisk\b", "identified_risk_mention"),
        (r"\b(?:uncertain|unknown|unclear|speculative)\b", "uncertainty_flag"),
        (r"\b(?:depend(?:s|ent|ency)|relies on|requires)\b", "dependency_flag"),
        (r"\b(?:fail|failure|break|error|bug|crash)\b", "failure_mode"),
        (r"\b(?:security|privacy|confidential|sensitive|protect)\b", "security_concern"),
    ]
    for pattern, label in risk_patterns:
        count = len(re.findall(pattern, text, re.IGNORECASE))
        if count > 0:
            risks.append(f"{label}: {count} mention(s) of '{pattern}'")

    return TaskAgentResult(
        agent_id=spec.agent_id,
        ok=True,
        subtask=spec.subtask,
        summary=f"Built risk register with {len(risks)} entries.",
        findings=risks,
        limitations=["Pattern-based — not a comprehensive risk assessment."],
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Test Case Suggester
# ---------------------------------------------------------------------------
def _run_test_case_suggester(
    spec: AgentSpec, payload: dict[str, Any]
) -> TaskAgentResult:
    """Suggest test cases based on a feature/module description."""
    desc = payload.get("description") or payload.get("feature") or payload.get("text") or ""
    if not desc.strip():
        return TaskAgentResult(
            agent_id=spec.agent_id,
            ok=False,
            subtask=spec.subtask,
            errors=["Input 'description', 'feature', or 'text' is empty."],
            confidence="low",
        )

    cases: list[str] = []
    # Basic categories of test cases
    if re.search(r"\b(?:input|param(?:eter)?|arg(?:ument)?)\b", desc, re.IGNORECASE):
        cases.append("Test with empty/missing inputs.")
        cases.append("Test with boundary/maximum-length inputs.")
    if re.search(r"\b(?:output|result|return|response)\b", desc, re.IGNORECASE):
        cases.append("Verify output format matches expected schema.")
        cases.append("Test with unexpected/invalid output scenarios.")
    cases.append("Test happy-path / nominal case.")
    cases.append("Test error/exception handling path.")

    return TaskAgentResult(
        agent_id=spec.agent_id,
        ok=True,
        subtask=spec.subtask,
        summary=f"Suggested {len(cases)} test cases.",
        findings=cases,
        limitations=["Template-based suggestions — not exhaustive.", "Does not execute tests."],
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Local Document Excerpt Summarizer
# ---------------------------------------------------------------------------
def _run_doc_summarizer(
    spec: AgentSpec, payload: dict[str, Any]
) -> TaskAgentResult:
    """Summarize a local document excerpt (deterministic, no LLM)."""
    text = payload.get("text") or payload.get("content") or ""
    max_len = payload.get("max_length", 500)

    if not text.strip():
        return TaskAgentResult(
            agent_id=spec.agent_id,
            ok=False,
            subtask=spec.subtask,
            errors=["Input 'text' or 'content' is empty."],
            confidence="low",
        )

    sentences = _split_sentences(text)
    # Simple extractive summary: first 2 + longest sentence
    summary = ""
    if sentences:
        first_two = ". ".join(sentences[:2]).strip()
        longest = max(sentences, key=len) if len(sentences) > 2 else ""
        summary = first_two
        if longest and len(summary) + len(longest) < max_len:
            summary += ". " + longest
    summary = summary[:max_len]

    return TaskAgentResult(
        agent_id=spec.agent_id,
        ok=True,
        subtask=spec.subtask,
        summary=f"Summarized {len(sentences)} sentences into {len(summary)} chars.",
        findings=[summary],
        limitations=[
            "Extractive (deterministic) summary — does not use semantic understanding.",
            "May miss key content in later sections.",
        ],
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _split_sentences(text: str) -> list[str]:
    """Naive sentence splitter."""
    import re as _re
    # Split on .!? followed by space or newline
    parts = _re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]
