"""
Live test for the Google-oriented no-key patent search provider.

Hits the REAL https://www.google.com/search endpoint with patent-targeted
queries and reports exactly what happened (success / blocked / parsed
N URLs / fallback path).  Useful for verifying the no-key path actually
works from your network without committing brittle assertions to CI.

Usage
-----
    # From the AURA project root, with the AURA conda env active:
    python scripts/live_test_google_patent_search.py

    # With a specific query:
    python scripts/live_test_google_patent_search.py "TADF red OLED emitter"

    # With multiple queries, comma-separated:
    python scripts/live_test_google_patent_search.py \\
        "site:patents.google.com TADF",\\
        "site:patentscope.wipo.int red NIR OLED",\\
        "site:uspto.gov organic electroluminescent near infrared"

Honesty
-------
Google's HTML SERP layout is dynamic and rate-limited.  This script
runs ONE request per query, with a 2-second pause between queries.
Expect a CAPTCHA / consent page on the first try from many networks.
The script prints provider warnings verbatim so you can see what
Google actually returned without having to read raw HTML.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Allow running this script standalone from anywhere.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from integrations.patent_web.search_providers import (   # noqa: E402
    DuckDuckGoHtmlPatentSearchProvider,
    GoogleWebNoKeyPatentSearchProvider,
    SearXNGPatentSearchProvider,
)


DEFAULT_QUERIES = [
    'site:patents.google.com "TADF" OLED emitter',
    'site:patentscope.wipo.int "red NIR OLED"',
    'site:uspto.gov organic electroluminescent near infrared emitter',
]


def _dump_serp(query: str, body: str) -> Path | None:
    """Save the raw SERP body to /tmp for inspection when extraction fails."""
    import re as _re
    safe = _re.sub(r"[^A-Za-z0-9]+", "_", query)[:60]
    dump_dir = _PROJECT_ROOT / "data" / "google_serp_debug"
    dump_dir.mkdir(parents=True, exist_ok=True)
    path = dump_dir / f"serp_{safe}.html"
    try:
        path.write_text(body, encoding="utf-8", errors="replace")
        return path
    except Exception:
        return None


def _parse_queries(argv: list[str]) -> list[str]:
    if len(argv) <= 1:
        return DEFAULT_QUERIES
    raw = " ".join(argv[1:])
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or DEFAULT_QUERIES


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    queries = _parse_queries(argv)
    print(f"Live test: {len(queries)} query(ies)")
    print(f"AURA_GOOGLE_WEB_PATENT_ENABLED="
          f"{os.getenv('AURA_GOOGLE_WEB_PATENT_ENABLED', '1')}")
    print("Raw SERP HTML will be auto-saved to "
          "data/google_serp_debug/ on zero-result runs.")
    print("-" * 72)

    # Always capture the raw response body so we can dump it on
    # zero-result runs without requiring the user to set an env var.
    last_body: dict[str, str] = {}
    import requests as _req

    class _Capturing:
        def get(self, *args, **kw):
            r = _req.get(*args, **kw)
            last_body["text"] = getattr(r, "text", "")
            last_body["status"] = str(getattr(r, "status_code", 0))
            return r

    # We exercise EVERY available no-key / self-hosted provider per
    # query so you can see which one actually returns patent URLs from
    # your network.  SearXNG is only tried when SEARXNG_ENABLED=1 — for
    # users who haven't deployed the local stack yet.
    providers = [
        ("google_web_no_key", GoogleWebNoKeyPatentSearchProvider(
            http_session=_Capturing(),
        )),
        ("duckduckgo_html", DuckDuckGoHtmlPatentSearchProvider(
            http_session=_Capturing(),
        )),
    ]
    if os.getenv("SEARXNG_ENABLED", "0").strip() == "1":
        sx_url = os.getenv("SEARXNG_URL", "http://localhost:8080")
        print(f"SEARXNG_ENABLED=1 — also testing SearXNG at {sx_url}")
        providers.append((
            "searxng",
            SearXNGPatentSearchProvider(base_url=sx_url, timeout=15),
        ))
    else:
        print(
            "SearXNG check skipped (SEARXNG_ENABLED!=1).  "
            "Run scripts/verify_searxng.py first to set it up."
        )

    total_results = 0
    total_blocked = 0

    for i, q in enumerate(queries, start=1):
        print(f"\n[{i}/{len(queries)}] {q!r}")
        for label, provider in providers:
            print(f"  --- via {label} ---")
            resp = provider.search(q, limit=8)

            print(f"    success     = {resp.success}")
            print(f"    provider    = {resp.provider}")
            print(f"    not_api_verified  = {resp.not_api_verified}")
            print(f"    non_exhaustive    = {resp.non_exhaustive}")
            if resp.failure_reason:
                print(f"    failure     = {resp.failure_reason}")

            if resp.warnings:
                print("    warnings:")
                for w in resp.warnings:
                    print(f"      - [{w.code}] {w.message}")

            if resp.results:
                print(f"    results     = {len(resp.results)}:")
                for r in resp.results:
                    print(f"      - [{r.rank}] {r.title[:80]}")
                    print(f"            {r.url}")
            else:
                print("    results     = 0")

            total_results += len(resp.results)
            if resp.failure_reason in ("blocked_or_captcha", "js_required"):
                total_blocked += 1

            # Dump the raw SERP body when we got HTTP 200 but zero results
            # OR the provider declared js_required — useful for diagnosing
            # which page Google / DDG actually returned.
            if (
                (resp.success and not resp.results)
                or resp.failure_reason == "js_required"
            ) and last_body.get("text"):
                path = _dump_serp(f"{label}_{q}", last_body["text"])
                if path:
                    size_kb = len(last_body["text"]) // 1024
                    print(f"    [debug] raw SERP body saved to {path} ({size_kb} KB)")
                    lower = last_body["text"].lower()
                    for host in (
                        "patents.google.com", "patentscope.wipo.int", "uspto.gov",
                    ):
                        if host in lower:
                            count = lower.count(host)
                            print(f"    [debug] body contains {host!r} × {count}")

            # Polite pacing between providers AND queries.
            time.sleep(1.5)

    print("\n" + "=" * 72)
    print(f"Summary: {total_results} total patent URLs across "
          f"{len(queries)} queries; {total_blocked} blocked/CAPTCHA.")
    if total_blocked:
        print(
            "\nNOTE: 'blocked_or_captcha' means Google served a consent or\n"
            "CAPTCHA page in response to the automated User-Agent.  AURA\n"
            "does NOT bypass anti-bot protections.  For reliable patent\n"
            "retrieval, run SearXNG locally and set\n"
            "    AURA_PATENT_SEARCH_PROVIDER=searxng\n"
            "in your .env."
        )
    if total_results == 0 and total_blocked == 0:
        print(
            "\nNOTE: zero results AND zero blocks usually means Google's\n"
            "HTML structure has drifted from what the regex extractor\n"
            "expects.  Re-run with the AURA test suite to confirm the\n"
            "provider still passes its hermetic tests."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
