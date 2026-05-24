"""
Build patent-focused web-search queries from a user topic.

Output is a list of ``PatentSearchQuery`` — each query carries:
- ``query``           the actual search string (with site:-filters baked in)
- ``purpose``         human-readable rationale ("site-restricted exact phrase")
- ``target_domains``  the hosts this query is biased toward
- ``priority``        small integer; lower = run earlier under budget pressure

Strategy
--------
1. For each allowed domain, emit one quoted-topic and one un-quoted-broader
   query restricted to that domain (priorities 0 and 1).
2. Emit one cross-domain query that just appends "patent" to the topic
   (priority 2 — these are noisier but catch hits outside the site:-restricted
   set).
3. Optionally use an LLM (via ``core.llm.ask_json``) to expand the topic into
   technical synonyms. Best-effort: LLM failure falls back to a single-term
   plan. ``use_llm=False`` keeps the planner fully deterministic for tests.

Total query count is capped at ``PATENT_WEB_QUERY_COUNT`` (or the
``max_queries`` kwarg). The planner never over-expands into generic terms
that lose patent specificity.
"""

from __future__ import annotations

import config

from .schemas import PatentSearchQuery


# ---------------------------------------------------------------------------
# Term expansion (LLM-optional)
# ---------------------------------------------------------------------------

_TERM_EXPANSION_PROMPT = """\
You are a patent search strategist. Expand the user's topic into a SHORT list
of technical synonyms suitable for patent searching.

Rules:
- Output strict JSON: {"terms": ["term 1", "term 2", ...]}
- 2 to 4 terms maximum.
- Include the original topic as the first term, verbatim.
- Use canonical scientific terminology (e.g. "thermally activated delayed
  fluorescence" alongside "TADF").
- Do NOT include marketing terms, applications, or jurisdiction names.
"""


def _expand_terms_with_llm(topic: str) -> list[str]:
    """Try the LLM. Fall back silently to [topic] on any failure."""
    try:
        from core.llm import ask_json  # local import — keep planner cheap
        result = ask_json(_TERM_EXPANSION_PROMPT, f"Topic: {topic}", temperature=0.1)
    except Exception:
        return [topic]
    terms = result.get("terms") if isinstance(result, dict) else None
    if not isinstance(terms, list) or not terms:
        return [topic]
    cleaned: list[str] = []
    for t in terms:
        if isinstance(t, (str, int)) and str(t).strip():
            cleaned.append(str(t).strip())
    if topic not in cleaned:
        cleaned.insert(0, topic)
    return cleaned[:4]


def _quote_if_phrase(term: str) -> str:
    return f'"{term}"' if " " in term.strip() else term.strip()


def _dedupe_queries(queries: list[PatentSearchQuery]) -> list[PatentSearchQuery]:
    """Drop duplicates while preserving order (case-insensitive on .query)."""
    seen: set[str] = set()
    out: list[PatentSearchQuery] = []
    for q in queries:
        key = q.query.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan_patent_queries(
    topic: str,
    *,
    use_llm: bool = False,
    max_queries: int | None = None,
    allowed_domains: list[str] | None = None,
) -> list[PatentSearchQuery]:
    """Return a deterministic, capped list of PatentSearchQuery objects.

    Parameters
    ----------
    topic
        The user's topic / technology phrase.
    use_llm
        If True, ask the LLM for synonyms. Defaults to False for determinism.
    max_queries
        Hard cap. Defaults to ``config.PATENT_WEB_QUERY_COUNT``.
    allowed_domains
        Override the allow-list (defaults to ``config.PATENT_WEB_ALLOWED_DOMAINS``).
    """
    topic = (topic or "").strip()
    if not topic:
        return []

    cap = max_queries if max_queries is not None else config.PATENT_WEB_QUERY_COUNT
    domains = allowed_domains if allowed_domains is not None else config.PATENT_WEB_ALLOWED_DOMAINS
    if not domains:
        domains = ["patents.google.com", "patentscope.wipo.int", "uspto.gov"]

    terms = _expand_terms_with_llm(topic) if use_llm else [topic]

    queries: list[PatentSearchQuery] = []

    # 1. site:-restricted quoted-topic queries (priority 0 — highest signal).
    #    Intent: land on specific patent pages on each allow-listed host.
    primary = _quote_if_phrase(terms[0])
    for domain in domains:
        queries.append(PatentSearchQuery(
            query=f"site:{domain} {primary}",
            purpose=f"site-restricted exact-phrase search on {domain}",
            target_domains=[domain],
            priority=0,
            intent="patent_landing_page",
        ))

    # 2. site:-restricted broader queries — drop the quotes, append "patent"
    #    so noisier engines also surface relevant hits.  Intent here is
    #    broader prior-art discovery within each host.
    for domain in domains:
        # Use the second-term expansion if we have one, else the topic itself.
        broader_term = terms[1] if len(terms) > 1 else terms[0]
        queries.append(PatentSearchQuery(
            query=f"site:{domain} {broader_term} patent",
            purpose=f"site-restricted broader keyword on {domain}",
            target_domains=[domain],
            priority=1,
            intent="broad_prior_art_discovery",
        ))

    # 3. Cross-domain query (one only) to catch on-domain pages a backend
    #    might rank highly without a site:-filter.  Technology-cluster intent.
    queries.append(PatentSearchQuery(
        query=f"{primary} patent",
        purpose="cross-domain patent hint query",
        target_domains=list(domains),
        priority=2,
        intent="technology_cluster_search",
    ))

    # Dedupe + sort by priority (stable), then cap.
    queries = _dedupe_queries(queries)
    queries.sort(key=lambda q: q.priority)
    return queries[:cap]
