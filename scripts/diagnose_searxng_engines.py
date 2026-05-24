"""
Deep diagnostic for "SearXNG up but returning ~0 results".

Two distinct failure modes that look identical from a single query:

  A) **Engines disabled** in settings.yml — only a handful are configured
     to even attempt search.  Visible via /config.
  B) **Engines enabled but BLOCKED** by Google/Bing/Brave in 2026 — they
     return 429/403, SearXNG silently filters them out.  /config still
     reports them as enabled.  Net: only Wikipedia/Mojeek/Wiby/Yacy
     style engines actually return results.

This script tells you which one is hitting you.

Usage:
    python scripts/diagnose_searxng_engines.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# Test queries — broad to neutral to patent-specific.  If results
# collapse only on the third, the problem is patent-specific
# (site:-restricted scraping).  If results collapse on the second,
# engines are blocking ALL queries.
_PROBES = [
    ("Wikipedia-style broad", "OLED"),
    ("Neutral web search",    "thermally activated delayed fluorescence"),
    ("Patent-specific",       'site:patents.google.com "TADF" OLED emitter'),
]

_HEADERS = {"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"}


def _print(label: str, value: str) -> None:
    print(f"  {label:<28} {value}")


def main() -> int:
    url = os.getenv("SEARXNG_URL", "http://localhost:8080").rstrip("/")
    print("=" * 72)
    print(f"SearXNG engines diagnostic  ({url})")
    print("=" * 72)

    try:
        import requests
    except ImportError:
        print("❌ Need `requests`.  pip install requests")
        return 3

    # ---- 1. Engine inventory ----------------------------------------------
    print("\n[1/3] Engines configured (from /config)\n")
    try:
        c = requests.get(f"{url}/config", headers=_HEADERS, timeout=10)
        c.raise_for_status()
        engines = c.json().get("engines", [])
    except Exception as exc:
        print(f"❌ Could not read /config: {exc}")
        return 2

    by_category: dict[str, list[dict]] = {}
    for e in engines:
        for cat in e.get("categories", ["other"]) or ["other"]:
            by_category.setdefault(cat, []).append(e)
    for cat in sorted(by_category):
        enabled = [e for e in by_category[cat] if not e.get("disabled")]
        disabled = [e for e in by_category[cat] if e.get("disabled")]
        if cat in ("general", "science", "files", "social media"):
            names_on = sorted(e["name"] for e in enabled)
            print(f"  {cat:<18} enabled={len(enabled):>3}  disabled={len(disabled):>3}")
            if names_on:
                print(f"  {'':<18}   ENABLED: {', '.join(names_on[:14])}")
                if len(names_on) > 14:
                    print(f"  {'':<18}            … and {len(names_on) - 14} more")

    general_enabled = [
        e for e in engines
        if "general" in (e.get("categories") or [])
        and not e.get("disabled")
    ]
    if len(general_enabled) < 3:
        print(
            f"\n  ⚠  Only {len(general_enabled)} general-search engine(s) "
            "enabled.  This is Failure mode (A) — fix settings.yml.\n"
            "     See scripts/verify_searxng.py for the engines block to add."
        )
        return 1

    # ---- 2. Probe per category --------------------------------------------
    print("\n[2/3] Probe queries with engine-attribution\n")
    probe_outcomes: list[tuple[str, dict]] = []
    for label, q in _PROBES:
        print(f"  Query [{label}]: {q!r}")
        try:
            r = requests.get(
                f"{url}/search",
                params={"q": q, "format": "json"},
                headers=_HEADERS, timeout=20,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print(f"    ❌ {exc.__class__.__name__}: {exc}\n")
            probe_outcomes.append((label, {"results": [], "engines": {}}))
            continue

        results = data.get("results", []) or []
        # Tally per-engine contribution.
        per_engine: dict[str, int] = {}
        for res in results:
            for eng in (res.get("engines") or []):
                per_engine[eng] = per_engine.get(eng, 0) + 1
            # Some result formats use single 'engine' field too.
            if not res.get("engines") and res.get("engine"):
                e = res["engine"]
                per_engine[e] = per_engine.get(e, 0) + 1

        unresponsive_engines = (data.get("unresponsive_engines") or [])
        _print("results", str(len(results)))
        if per_engine:
            top = sorted(per_engine.items(), key=lambda x: -x[1])[:6]
            _print("  responding engines", ", ".join(
                f"{n}({c})" for n, c in top
            ))
        if unresponsive_engines:
            # Format: [["engine_name", "reason"], ...]
            short = []
            for entry in unresponsive_engines[:8]:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    short.append(f"{entry[0]}({entry[1][:40]})")
                else:
                    short.append(str(entry))
            _print("  UNRESPONSIVE engines", ", ".join(short))
        probe_outcomes.append((label, {
            "results": results, "engines": per_engine,
            "unresponsive": unresponsive_engines,
        }))
        time.sleep(2)
        print()

    # ---- 3. Verdict --------------------------------------------------------
    print("\n[3/3] Verdict\n")
    res_counts = [len(po["results"]) for _, po in probe_outcomes]
    unresp_total = sum(
        len(po.get("unresponsive", []) or []) for _, po in probe_outcomes
    )

    if all(n == 0 for n in res_counts):
        print("  ❌ Every probe returned 0 results.")
        if unresp_total:
            print(
                "     UNRESPONSIVE engine errors are present — Failure mode (B):\n"
                "     engines are configured but Google/Bing/Brave/etc. are\n"
                "     blocking SearXNG.  Common reasons:\n"
                "       - Your IP / data-center range is on Google's bot list\n"
                "       - SearXNG's User-Agent is heuristically flagged\n"
                "       - The instance is brand new — try again in 24h after\n"
                "         a healthy traffic pattern accumulates\n"
                "\n"
                "     Practical fixes:\n"
                "       1. Add engines that DON'T block aggressively:\n"
                "            mojeek, wiby, yacy, wikipedia, marginalia\n"
                "       2. Drop high-block engines (google, brave) from the\n"
                "          patent-search subset:\n"
                "            settings.yml -> engines: -> name: google ->\n"
                "              disabled: true\n"
                "       3. For patent search specifically, use\n"
                "          PATENTSCOPE direct (no SearXNG needed) — see\n"
                "          README section 7c-7 for the provider abstraction.\n"
            )
        else:
            print(
                "     But no engines reported errors either — likely your\n"
                "     queries are being filtered before they reach engines.\n"
                "     Inspect:  docker logs searxng --tail 100"
            )
        return 1

    if res_counts[0] > 5 and res_counts[2] == 0:
        print(
            "  ⚠  Broad query works, patent-specific does NOT.\n"
            "     This is the most common failure: Google/Bing reject\n"
            "     site:-restricted queries from SearXNG instances.\n"
            "\n"
            "     Workarounds:\n"
            "       1. Drop the site: filter — search broader, then filter\n"
            "          URLs client-side (AURA does this already).\n"
            "       2. Add a patent-aware engine to settings.yml — see\n"
            "          docs.searxng.org engines list.\n"
            "       3. For reliable patent retrieval, use the EPO Open\n"
            "          Patent Services API (free, requires registration)\n"
            "          OR Google Patents Public Datasets on BigQuery."
        )
        return 1

    print("  ✅ SearXNG is working.  Results across all probes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
